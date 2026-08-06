"""DroidClient — high-level async API for the Factory Droid SDK.

Provides typed async methods for all ``droid.*`` JSON-RPC methods,
session lifecycle management, and event/handler systems. Built on top
of the ``ProtocolEngine`` and a ``DroidClientTransport`` implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections.abc import AsyncIterator, Callable
from types import TracebackType  # noqa: TC003
from typing import TYPE_CHECKING, Any, Literal

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.errors import (
    SessionError,
)
from droid_sdk.protocol import (
    COMPACTION_TIMEOUT,
    MCP_AUTH_TIMEOUT,
    SESSION_INIT_TIMEOUT,
    ProtocolEngine,
)
from droid_sdk.schemas.cli import (
    SessionNotification,
)
from droid_sdk.schemas.client import (
    AddMcpServerResult,
    AddUserMessageRequestParams,
    AuthenticateMcpServerResult,
    Base64ImageSource,
    CancelMcpAuthResult,
    ClearMcpAuthResult,
    CloseSessionRequestParams,
    CloseSessionResult,
    CompactSessionRequestParams,
    CompactSessionResult,
    DocumentSource,
    ExecuteRewindRequestParams,
    ExecuteRewindResult,
    ForkSessionRequestParams,
    ForkSessionResult,
    GetContextBreakdownResult,
    GetContextStatsResult,
    GetRewindInfoRequestParams,
    GetRewindInfoResult,
    InitializeSessionRequestParams,
    InitializeSessionResult,
    ListCommandsResult,
    ListMcpRegistryResult,
    ListMcpServersResult,
    ListMcpToolsResult,
    ListSkillsResult,
    ListToolsRequestParams,
    ListToolsResult,
    LoadSessionRequestParams,
    LoadSessionResult,
    OutputFormat,
    RemoveMcpServerResult,
    RenameSessionRequestParams,
    RenameSessionResult,
    RewindFileCreation,
    RewindFileSnapshot,
    SessionSource,
    SessionTag,
    SubmitBugReportResult,
    SubmitMcpAuthCodeResult,
    ToggleMcpServerResult,
    ToggleMcpToolResult,
    UpdateSessionSettingsRequestParams,
)
from droid_sdk.schemas.enums import (
    AutonomyLevel,
    AutonomyMode,
    DecompSessionType,
    DroidInteractionMode,
    DroidServerMethod,
    DroidWorkingState,
    McpServerType,
    ReasoningEffort,
    SessionNotificationType,
    SettingsLevel,
)
from droid_sdk.stream import (
    StreamMessage,
    TokenUsageUpdate,
    ToolProgress,
    ToolResult,
    TurnComplete,
    WorkingStateChanged,
    _notification_to_stream_message,
)
from droid_sdk.types import DroidClientTransport  # noqa: TC001

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Type alias for notification listener callbacks
NotificationCallback = Callable[[dict[str, Any]], None]

# Type alias for unsubscribe functions
Unsubscribe = Callable[[], None]


class DroidClient:
    """High-level async client for the Factory Droid SDK.

    Wraps a ``DroidClientTransport`` and ``ProtocolEngine`` to provide
    typed async methods for all ``droid.*`` RPC methods.

    Supports two construction modes:

    1. **Explicit transport** — provide a pre-configured transport::

        transport = ProcessTransport(exec_path="/path/to/droid", cwd="/tmp")
        async with DroidClient(transport=transport) as client:
            ...

    2. **Config-based fallback** — provide ``exec_path`` and optional
       ``cwd``/``env``; a ``ProcessTransport`` is created internally
       during ``connect()``::

        async with DroidClient(exec_path="/path/to/droid", cwd="/tmp") as client:
            ...

    At least one of ``transport`` or ``exec_path`` must be provided.

    Args:
        transport: A ``DroidClientTransport`` implementation (e.g.
            ``ProcessTransport`` or a mock).
        exec_path: Path to the droid executable. Used to auto-create a
            ``ProcessTransport`` if no explicit ``transport`` is given.
        cwd: Working directory for the auto-created ``ProcessTransport``.
        env: Additional environment variables for the auto-created
            ``ProcessTransport``.
    """

    def __init__(
        self,
        *,
        transport: DroidClientTransport | None = None,
        exec_path: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if transport is None and exec_path is None:
            raise ValueError(
                "DroidClient requires either 'transport' or 'exec_path'. "
                "Provide a DroidClientTransport instance, or pass exec_path "
                "to auto-create a ProcessTransport."
            )

        self._transport = transport
        # Config for deferred ProcessTransport creation
        self._exec_path = exec_path
        self._cwd = cwd
        self._env = env

        self._protocol: ProtocolEngine | None = None
        self._session_id: str | None = None
        self._closed: bool = False

        # Client-level notification listeners: list of (callback, optional_type_filter)
        self._notification_listeners: list[
            tuple[NotificationCallback, SessionNotificationType | None]
        ] = []

        # Client-level server→client request handlers
        self._permission_handler: Callable[..., Any] | None = None
        self._ask_user_handler: Callable[..., Any] | None = None

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        if self._transport is None:
            return False
        return self._transport.is_connected

    @property
    def session_id(self) -> str | None:
        """Current session ID, or ``None`` if no session is active."""
        return self._session_id

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the droid process.

        If no explicit transport was provided at construction, creates a
        ``ProcessTransport`` from the stored ``exec_path``/``cwd``/``env``
        config.

        If the transport has a ``connect()`` method (e.g. ``ProcessTransport``),
        it is called to spawn the subprocess. Then a ``ProtocolEngine`` is
        created and wired to the transport's message/error handlers.
        Client-level notification listeners and handlers are wired to
        the protocol engine's dispatch system.
        """
        self._closed = False

        # Lazy-create ProcessTransport from config if no explicit transport
        if self._transport is None:
            from droid_sdk.transport import ProcessTransport

            assert self._exec_path is not None  # guaranteed by __init__
            self._transport = ProcessTransport(
                exec_path=self._exec_path,
                cwd=self._cwd,
                env=self._env,
            )

        # Connect the transport (e.g. spawn subprocess)
        await self._transport.connect()

        self._protocol = ProtocolEngine(transport=self._transport)

        # Wire up protocol engine's notification dispatch to client listeners
        self._protocol.on_notification(self._dispatch_notification)

        # Wire up protocol engine's server→client request handlers
        self._protocol.set_permission_handler(self._dispatch_permission_request)
        self._protocol.set_ask_user_handler(self._dispatch_ask_user_request)

        # Start consuming messages from the transport
        await self._protocol.start()

    async def close(self) -> None:
        """Close the client and release all resources.

        Rejects pending requests, clears handlers and listeners, and
        closes the transport. Idempotent — safe to call multiple times.
        ``close()`` before ``connect()`` is a no-op.
        """
        if self._closed:
            return

        self._closed = True

        # Clear client-level handlers and listeners
        self._notification_listeners.clear()
        self._permission_handler = None
        self._ask_user_handler = None

        if self._protocol is not None:
            await self._protocol.close()

        if self._transport is not None:
            await self._transport.close()

    # ----------------------------------------------------------
    # Async context manager
    # ----------------------------------------------------------

    async def __aenter__(self) -> DroidClient:
        """Connect on context entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close on context exit."""
        await self.close()

    # ----------------------------------------------------------
    # Session methods
    # ----------------------------------------------------------

    async def initialize_session(
        self,
        *,
        machine_id: str,
        cwd: str,
        session_id: str | None = None,
        workspace_id: str | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        autonomy_mode: AutonomyMode | None = None,
        interaction_mode: DroidInteractionMode | None = None,
        autonomy_level: AutonomyLevel | None = None,
        model_id: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        spec_mode_model_id: str | None = None,
        spec_mode_reasoning_effort: ReasoningEffort | None = None,
        decomp_session_type: DecompSessionType | None = None,
        decomp_mission_id: str | None = None,
        skip_permissions_unsafe: bool | None = None,
        enabled_tool_ids: list[str] | None = None,
        disabled_tool_ids: list[str] | None = None,
        session_location: str | None = None,
        session_source: SessionSource | dict[str, Any] | None = None,
        tags: list[SessionTag | dict[str, Any]] | None = None,
        mcp_oauth_callback_uri: str | None = None,
    ) -> InitializeSessionResult:
        """Initialize a new session.

        Sends ``droid.initialize_session`` with an extended timeout
        (``SESSION_INIT_TIMEOUT``). On success, stores the session ID
        and returns the typed result.

        Args:
            machine_id: Machine identifier.
            cwd: Current working directory.
            session_id: Optional specific session ID to create.
            workspace_id: Optional workspace ID.
            mcp_servers: Optional MCP server configurations.
            autonomy_mode: Deprecated autonomy mode.
            interaction_mode: Interaction mode setting.
            autonomy_level: Autonomy level setting.
            model_id: Optional model ID.
            reasoning_effort: Optional reasoning effort level.
            spec_mode_model_id: Optional spec mode model ID.
            spec_mode_reasoning_effort: Optional spec mode reasoning effort.
            decomp_session_type: Session type for mission decomposition.
            decomp_mission_id: Mission ID for worker sessions.
            skip_permissions_unsafe: Skip permission checks.
            enabled_tool_ids: Additional tool IDs to enable beyond defaults.
            disabled_tool_ids: Tool IDs to disable (subtractive). Combine with
                ``enabled_tool_ids=[]`` and an explicit disable list to lock
                the tool set down.
            session_location: Session metadata location.
            session_source: Session source information.
            tags: Optional session tags.
            mcp_oauth_callback_uri: OAuth callback URI for MCP.

        Returns:
            Typed ``InitializeSessionResult`` with session_id, session,
            and settings.

        Raises:
            ConnectionError: If the client has been closed.
            ProtocolError: If the server returns an error.
        """
        self._ensure_not_closed()
        protocol = self._ensure_protocol()

        validated_session_source = (
            SessionSource.model_validate(session_source)
            if session_source is not None
            else None
        )
        validated_tags = (
            [SessionTag.model_validate(tag) for tag in tags]
            if tags is not None
            else None
        )
        params = _serialize_params(
            InitializeSessionRequestParams(
                machine_id=machine_id,
                cwd=cwd,
                session_id=session_id,
                workspace_id=workspace_id,
                autonomy_mode=autonomy_mode,
                interaction_mode=interaction_mode,
                autonomy_level=autonomy_level,
                model_id=model_id,
                reasoning_effort=reasoning_effort,
                spec_mode_model_id=spec_mode_model_id,
                spec_mode_reasoning_effort=spec_mode_reasoning_effort,
                decomp_session_type=decomp_session_type,
                decomp_mission_id=decomp_mission_id,
                skip_permissions_unsafe=skip_permissions_unsafe,
                enabled_tool_ids=enabled_tool_ids,
                disabled_tool_ids=disabled_tool_ids,
                session_location=session_location,
                session_source=validated_session_source,
                tags=validated_tags,
                mcp_oauth_callback_uri=mcp_oauth_callback_uri,
            )
        )
        # Preserve compatibility with legacy unvalidated MCP dictionaries.
        if mcp_servers is not None:
            params["mcpServers"] = mcp_servers

        response = await protocol.send_request(
            method=DroidServerMethod.INITIALIZE_SESSION.value,
            params=params,
            timeout=SESSION_INIT_TIMEOUT,
        )

        result = InitializeSessionResult.model_validate(response.get("result", {}))
        self._session_id = result.session_id
        return result

    async def load_session(
        self,
        *,
        session_id: str,
        mcp_servers: list[dict[str, Any]] | None = None,
        mcp_oauth_callback_uri: str | None = None,
    ) -> LoadSessionResult:
        """Load an existing session.

        Sends ``droid.load_session``. On success, stores the session ID.
        If the session is not found (``ENTITY_NOT_FOUND``), raises
        ``SessionNotFoundError``.

        Args:
            session_id: Session ID to load.
            mcp_servers: Optional MCP server configurations.
            mcp_oauth_callback_uri: OAuth callback URI for MCP.

        Returns:
            Typed ``LoadSessionResult`` with session and settings.

        Raises:
            SessionNotFoundError: If the session does not exist.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        protocol = self._ensure_protocol()

        params = _serialize_params(
            LoadSessionRequestParams(
                session_id=session_id,
                mcp_oauth_callback_uri=mcp_oauth_callback_uri,
            )
        )
        # Preserve compatibility with legacy unvalidated MCP dictionaries.
        if mcp_servers is not None:
            params["mcpServers"] = mcp_servers

        response = await protocol.send_request(
            method=DroidServerMethod.LOAD_SESSION.value,
            params=params,
            timeout=SESSION_INIT_TIMEOUT,
        )

        result = LoadSessionResult.model_validate(response.get("result", {}))
        self._session_id = session_id
        return result

    async def add_user_message(
        self,
        *,
        text: str,
        images: list[Base64ImageSource | dict[str, Any]] | None = None,
        files: list[DocumentSource | dict[str, Any]] | None = None,
        output_format: OutputFormat | dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Add a user message to the session.

        Sends ``droid.add_user_message``. Requires an active session.

        Args:
            text: Message text content.
            images: Optional attached images.
            files: Optional attached documents.
            output_format: Optional structured-output contract. Either an
                :class:`~droid_sdk.schemas.client.OutputFormat` or a raw dict
                of the form ``{"type": "json_schema", "schema": {...}}`` to
                constrain the reply to a JSON value matching the schema.
            request_id: Optional custom request ID for the JSON-RPC envelope.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        validated_output_format = (
            OutputFormat.model_validate(output_format)
            if output_format is not None
            else None
        )
        params = _serialize_params(
            AddUserMessageRequestParams(
                text=text,
                output_format=validated_output_format,
            )
        )
        if images is not None:
            params["images"] = images
        if files is not None:
            params["files"] = files

        # Use custom request_id by monkey-patching the protocol temporarily,
        # or pass via overridden send_request. The protocol engine generates
        # its own IDs. For custom request_id support, we'll use the protocol's
        # send_request with a specially constructed envelope.
        if request_id is not None:
            await protocol.send_request(
                method=DroidServerMethod.ADD_USER_MESSAGE.value,
                params=params,
                request_id=request_id,
            )
        else:
            await protocol.send_request(
                method=DroidServerMethod.ADD_USER_MESSAGE.value,
                params=params,
            )

    async def interrupt_session(self) -> None:
        """Interrupt the current session.

        Sends ``droid.interrupt_session`` with empty params.
        Requires an active session.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        await protocol.send_request(
            method=DroidServerMethod.INTERRUPT_SESSION.value,
            params={},
        )

    async def kill_worker_session(self, *, worker_session_id: str) -> None:
        """Kill a worker session.

        Sends ``droid.kill_worker_session`` with the worker session ID.
        Requires an active session.

        Args:
            worker_session_id: Worker session ID to kill.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        await protocol.send_request(
            method=DroidServerMethod.KILL_WORKER_SESSION.value,
            params={"workerSessionId": worker_session_id},
        )

    async def update_session_settings(
        self,
        *,
        model_id: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        autonomy_mode: AutonomyMode | None = None,
        interaction_mode: DroidInteractionMode | None = None,
        autonomy_level: AutonomyLevel | None = None,
        spec_mode_model_id: str | None = None,
        spec_mode_reasoning_effort: ReasoningEffort | None = None,
        enabled_tool_ids: list[str] | None = None,
        disabled_tool_ids: list[str] | None = None,
    ) -> None:
        """Update session settings.

        Sends only the provided fields as partial settings update.
        Requires an active session.

        Args:
            model_id: Optional model ID to set.
            reasoning_effort: Optional reasoning effort level.
            autonomy_mode: Deprecated autonomy mode.
            interaction_mode: Optional interaction mode.
            autonomy_level: Optional autonomy level.
            spec_mode_model_id: Optional spec mode model ID.
            spec_mode_reasoning_effort: Optional spec mode reasoning effort.
            enabled_tool_ids: Additional tool IDs to enable beyond defaults.
            disabled_tool_ids: Tool IDs to disable (subtractive).

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params = _serialize_params(
            UpdateSessionSettingsRequestParams(
                model_id=model_id,
                reasoning_effort=reasoning_effort,
                autonomy_mode=autonomy_mode,
                interaction_mode=interaction_mode,
                autonomy_level=autonomy_level,
                spec_mode_model_id=spec_mode_model_id,
                spec_mode_reasoning_effort=spec_mode_reasoning_effort,
                enabled_tool_ids=enabled_tool_ids,
                disabled_tool_ids=disabled_tool_ids,
            )
        )

        await protocol.send_request(
            method=DroidServerMethod.UPDATE_SESSION_SETTINGS.value,
            params=params,
        )

    # ----------------------------------------------------------
    # MCP methods
    # ----------------------------------------------------------

    async def toggle_mcp_server(
        self,
        *,
        server_name: str,
        enabled: bool,
        settings_level: SettingsLevel,
    ) -> ToggleMcpServerResult:
        """Toggle an MCP server on or off.

        Sends ``droid.toggle_mcp_server``. Requires an active session.

        Args:
            server_name: MCP server name.
            enabled: Whether to enable or disable the server.
            settings_level: Settings level for the operation.

        Returns:
            Typed ``ToggleMcpServerResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
            "enabled": enabled,
            "settingsLevel": _enum_value(settings_level),
        }

        response = await protocol.send_request(
            method=DroidServerMethod.TOGGLE_MCP_SERVER.value,
            params=params,
        )

        return ToggleMcpServerResult.model_validate(response.get("result", {}))

    async def authenticate_mcp_server(
        self,
        *,
        server_name: str,
    ) -> AuthenticateMcpServerResult:
        """Authenticate an MCP server (OAuth flow).

        Sends ``droid.authenticate_mcp_server`` with an extended timeout
        (``MCP_AUTH_TIMEOUT``, 300s) since OAuth requires user interaction.
        Requires an active session.

        Args:
            server_name: MCP server name to authenticate.

        Returns:
            Typed ``AuthenticateMcpServerResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            TimeoutError: If authentication times out.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
        }

        response = await protocol.send_request(
            method=DroidServerMethod.AUTHENTICATE_MCP_SERVER.value,
            params=params,
            timeout=MCP_AUTH_TIMEOUT,
        )

        return AuthenticateMcpServerResult.model_validate(response.get("result", {}))

    async def cancel_mcp_auth(
        self,
        *,
        server_name: str,
    ) -> CancelMcpAuthResult:
        """Cancel an in-progress MCP authentication.

        Sends ``droid.cancel_mcp_auth``. Requires an active session.

        Args:
            server_name: MCP server name.

        Returns:
            Typed ``CancelMcpAuthResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
        }

        response = await protocol.send_request(
            method=DroidServerMethod.CANCEL_MCP_AUTH.value,
            params=params,
        )

        return CancelMcpAuthResult.model_validate(response.get("result", {}))

    async def clear_mcp_auth(
        self,
        *,
        server_name: str,
    ) -> ClearMcpAuthResult:
        """Clear stored MCP authentication tokens.

        Sends ``droid.clear_mcp_auth``. Requires an active session.

        Args:
            server_name: MCP server name.

        Returns:
            Typed ``ClearMcpAuthResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
        }

        response = await protocol.send_request(
            method=DroidServerMethod.CLEAR_MCP_AUTH.value,
            params=params,
        )

        return ClearMcpAuthResult.model_validate(response.get("result", {}))

    async def submit_mcp_auth_code(
        self,
        *,
        server_name: str,
        code: str,
        state: str,
    ) -> SubmitMcpAuthCodeResult:
        """Submit an MCP authentication code.

        Sends ``droid.submit_mcp_auth_code``. Requires an active session.

        Args:
            server_name: MCP server name.
            code: Authentication code.
            state: Authentication state token.

        Returns:
            Typed ``SubmitMcpAuthCodeResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
            "code": code,
            "state": state,
        }

        response = await protocol.send_request(
            method=DroidServerMethod.SUBMIT_MCP_AUTH_CODE.value,
            params=params,
        )

        return SubmitMcpAuthCodeResult.model_validate(response.get("result", {}))

    async def add_mcp_server(
        self,
        *,
        name: str,
        type: McpServerType | str,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> AddMcpServerResult:
        """Add an MCP server.

        Sends ``droid.add_mcp_server``. Supports both stdio and http
        server configurations. Requires an active session.

        Args:
            name: Server name identifier.
            type: Transport type (``"stdio"`` or ``"http"``).
            url: URL endpoint (for http servers).
            headers: HTTP headers (for http servers).
            command: Command to spawn (for stdio servers).
            args: Command arguments (for stdio servers).
            env: Environment variables (for stdio servers).

        Returns:
            Typed ``AddMcpServerResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "name": name,
            "type": _enum_value(type),
        }
        _set_if_not_none(params, "url", url)
        _set_if_not_none(params, "headers", headers)
        _set_if_not_none(params, "command", command)
        _set_if_not_none(params, "args", args)
        _set_if_not_none(params, "env", env)

        response = await protocol.send_request(
            method=DroidServerMethod.ADD_MCP_SERVER.value,
            params=params,
        )

        return AddMcpServerResult.model_validate(response.get("result", {}))

    async def remove_mcp_server(
        self,
        *,
        server_name: str,
        settings_level: SettingsLevel,
    ) -> RemoveMcpServerResult:
        """Remove an MCP server.

        Sends ``droid.remove_mcp_server``. Requires an active session.

        Args:
            server_name: MCP server name to remove.
            settings_level: Settings level for the operation.

        Returns:
            Typed ``RemoveMcpServerResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
            "settingsLevel": _enum_value(settings_level),
        }

        response = await protocol.send_request(
            method=DroidServerMethod.REMOVE_MCP_SERVER.value,
            params=params,
        )

        return RemoveMcpServerResult.model_validate(response.get("result", {}))

    async def list_mcp_registry(self) -> ListMcpRegistryResult:
        """List available MCP registry servers.

        Sends ``droid.list_mcp_registry``. Requires an active session.

        Returns:
            Typed ``ListMcpRegistryResult`` with ``servers`` list.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_MCP_REGISTRY.value,
            params={},
        )

        return ListMcpRegistryResult.model_validate(response.get("result", {}))

    async def list_mcp_tools(self) -> ListMcpToolsResult:
        """List available MCP tools.

        Sends ``droid.list_mcp_tools``. Requires an active session.

        Returns:
            Typed ``ListMcpToolsResult`` with ``tools`` list.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_MCP_TOOLS.value,
            params={},
        )

        return ListMcpToolsResult.model_validate(response.get("result", {}))

    async def list_mcp_servers(self) -> ListMcpServersResult:
        """List MCP servers with status and summary.

        Sends ``droid.list_mcp_servers``. Requires an active session.

        Returns:
            Typed ``ListMcpServersResult`` with ``servers`` and ``summary``.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_MCP_SERVERS.value,
            params={},
        )

        return ListMcpServersResult.model_validate(response.get("result", {}))

    async def toggle_mcp_tool(
        self,
        *,
        server_name: str,
        tool_name: str,
        enabled: bool,
    ) -> ToggleMcpToolResult:
        """Toggle an MCP tool on or off.

        Sends ``droid.toggle_mcp_tool``. Requires an active session.

        Args:
            server_name: MCP server name.
            tool_name: Tool name to toggle.
            enabled: Whether to enable or disable the tool.

        Returns:
            Typed ``ToggleMcpToolResult`` with ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "serverName": server_name,
            "toolName": tool_name,
            "enabled": enabled,
        }

        response = await protocol.send_request(
            method=DroidServerMethod.TOGGLE_MCP_TOOL.value,
            params=params,
        )

        return ToggleMcpToolResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Skills and bug report methods
    # ----------------------------------------------------------

    async def list_skills(self) -> ListSkillsResult:
        """List available skills.

        Sends ``droid.list_skills``. Requires an active session.

        Returns:
            Typed ``ListSkillsResult`` with ``skills`` list.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_SKILLS.value,
            params={},
        )

        return ListSkillsResult.model_validate(response.get("result", {}))

    async def submit_bug_report(
        self,
        *,
        user_comment: str,
        client_logs: str | None = None,
    ) -> SubmitBugReportResult:
        """Submit a bug report.

        Sends ``droid.submit_bug_report``. Requires an active session.

        Args:
            user_comment: User's bug report comment.
            client_logs: Optional client log data.

        Returns:
            Typed ``SubmitBugReportResult`` with ``bug_report_id``.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params: dict[str, Any] = {
            "userComment": user_comment,
        }
        _set_if_not_none(params, "clientLogs", client_logs)

        response = await protocol.send_request(
            method=DroidServerMethod.SUBMIT_BUG_REPORT.value,
            params=params,
        )

        return SubmitBugReportResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Tool / command discovery
    # ----------------------------------------------------------

    async def list_tools(
        self,
        *,
        enabled_tool_ids: list[str] | None = None,
        disabled_tool_ids: list[str] | None = None,
    ) -> ListToolsResult:
        """List native CLI tools with their allow-state.

        Sends ``droid.list_tools``. This can be called before session
        initialization, allowing callers to discover tool IDs for initial
        allow/deny settings. The result reports each tool's ``id`` plus
        ``default_allowed`` and ``currently_allowed``.

        Args:
            enabled_tool_ids: Optional hypothetical enable list to evaluate
                ``currently_allowed`` against (does not mutate the session).
            disabled_tool_ids: Optional hypothetical disable list.

        Returns:
            Typed ``ListToolsResult`` with a ``tools`` list.

        Raises:
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        protocol = self._ensure_protocol()

        params = _serialize_params(
            ListToolsRequestParams(
                enabled_tool_ids=enabled_tool_ids,
                disabled_tool_ids=disabled_tool_ids,
            )
        )

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_TOOLS.value,
            params=params,
        )

        return ListToolsResult.model_validate(response.get("result", {}))

    async def list_commands(self) -> ListCommandsResult:
        """List custom slash commands.

        Sends ``droid.list_commands``. Requires an active session.

        Returns:
            Typed ``ListCommandsResult`` with a ``commands`` list.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.LIST_COMMANDS.value,
            params={},
        )

        return ListCommandsResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Session lifecycle: close / compact / fork / rename
    # ----------------------------------------------------------

    async def close_session(
        self,
        *,
        reason: Literal["clear", "logout", "prompt_input_exit", "other"] | None = None,
    ) -> CloseSessionResult:
        """Close the active session.

        Sends ``droid.close_session``. Requires an active session.

        Args:
            reason: Optional close reason (``"clear"``, ``"logout"``,
                ``"prompt_input_exit"`` or ``"other"``).

        Returns:
            Typed ``CloseSessionResult`` (empty payload).

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params = _serialize_params(CloseSessionRequestParams(reason=reason))

        response = await protocol.send_request(
            method=DroidServerMethod.CLOSE_SESSION.value,
            params=params,
        )

        result = CloseSessionResult.model_validate(response.get("result", {}))
        self._session_id = None
        return result

    async def compact_session(
        self,
        *,
        custom_instructions: str | None = None,
    ) -> CompactSessionResult:
        """Compact the conversation to reclaim context.

        Sends ``droid.compact_session`` with an extended timeout, since
        compaction runs an LLM summarization pass. Requires an active
        session.

        Args:
            custom_instructions: Optional instructions to steer the
                compaction summary.

        Returns:
            Typed ``CompactSessionResult`` with ``new_session_id`` and
            ``removed_count``.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params = _serialize_params(
            CompactSessionRequestParams(custom_instructions=custom_instructions)
        )

        response = await protocol.send_request(
            method=DroidServerMethod.COMPACT_SESSION.value,
            params=params,
            timeout=COMPACTION_TIMEOUT,
        )

        return CompactSessionResult.model_validate(response.get("result", {}))

    async def fork_session(
        self,
        *,
        title: str | None = None,
        tags: list[SessionTag | dict[str, Any]] | None = None,
    ) -> ForkSessionResult:
        """Fork the active session into a new one.

        Sends ``droid.fork_session``. Requires an active session.

        Args:
            title: Optional title for the fork.
            tags: Optional session tags for the fork.

        Returns:
            Typed ``ForkSessionResult`` with ``new_session_id``.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        validated_tags = (
            [SessionTag.model_validate(tag) for tag in tags]
            if tags is not None
            else None
        )
        params = _serialize_params(
            ForkSessionRequestParams(title=title, tags=validated_tags)
        )

        response = await protocol.send_request(
            method=DroidServerMethod.FORK_SESSION.value,
            params=params,
        )

        return ForkSessionResult.model_validate(response.get("result", {}))

    async def rename_session(self, *, title: str) -> RenameSessionResult:
        """Rename the active session.

        Sends ``droid.rename_session``. Requires an active session.

        Args:
            title: New session title.

        Returns:
            Typed ``RenameSessionResult`` with a ``success`` flag.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        params = _serialize_params(RenameSessionRequestParams(title=title))

        response = await protocol.send_request(
            method=DroidServerMethod.RENAME_SESSION.value,
            params=params,
        )

        return RenameSessionResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Context introspection
    # ----------------------------------------------------------

    async def get_context_stats(self) -> GetContextStatsResult:
        """Get context-window usage statistics.

        Sends ``droid.get_context_stats``. Requires an active session.

        Returns:
            Typed ``GetContextStatsResult`` with used/remaining/limit tokens.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.GET_CONTEXT_STATS.value,
            params={},
        )

        return GetContextStatsResult.model_validate(response.get("result", {}))

    async def get_context_breakdown(self) -> GetContextBreakdownResult:
        """Get a detailed breakdown of context-window usage.

        Sends ``droid.get_context_breakdown``. Requires an active session.

        Returns:
            Typed ``GetContextBreakdownResult`` with per-category, per-skill,
            per-MCP-server and per-droid token usage.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        self._ensure_session()
        protocol = self._ensure_protocol()

        response = await protocol.send_request(
            method=DroidServerMethod.GET_CONTEXT_BREAKDOWN.value,
            params={},
        )

        return GetContextBreakdownResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Rewind
    # ----------------------------------------------------------

    async def get_rewind_info(self, *, message_id: str) -> GetRewindInfoResult:
        """Get file-restore information for rewinding to a message.

        Sends ``droid.get_rewind_info``. Requires an active session.

        Args:
            message_id: The message to rewind to.

        Returns:
            Typed ``GetRewindInfoResult`` with restorable, created and
            evicted file lists.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        session_id = self._ensure_session()
        protocol = self._ensure_protocol()

        params = _serialize_params(
            GetRewindInfoRequestParams(
                session_id=session_id,
                message_id=message_id,
            )
        )

        response = await protocol.send_request(
            method=DroidServerMethod.GET_REWIND_INFO.value,
            params=params,
        )

        return GetRewindInfoResult.model_validate(response.get("result", {}))

    async def execute_rewind(
        self,
        *,
        message_id: str,
        files_to_restore: list[RewindFileSnapshot | dict[str, Any]],
        files_to_delete: list[RewindFileCreation | dict[str, Any]],
        fork_title: str,
    ) -> ExecuteRewindResult:
        """Execute a rewind, forking the session at ``message_id``.

        Sends ``droid.execute_rewind`` with an extended timeout. Requires
        an active session.

        Args:
            message_id: The message to rewind to.
            files_to_restore: File snapshots to restore, each
                ``{"filePath", "contentHash", "size"}``.
            files_to_delete: Files to delete, each ``{"filePath"}``.
            fork_title: Title for the new forked session.

        Returns:
            Typed ``ExecuteRewindResult`` with ``new_session_id`` and
            restore/delete counts.

        Raises:
            SessionError: If no active session.
            ProtocolError: If the server returns an error.
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()
        session_id = self._ensure_session()
        protocol = self._ensure_protocol()

        validated_files_to_restore = [
            RewindFileSnapshot.model_validate(file) for file in files_to_restore
        ]
        validated_files_to_delete = [
            RewindFileCreation.model_validate(file) for file in files_to_delete
        ]
        params = _serialize_params(
            ExecuteRewindRequestParams(
                session_id=session_id,
                message_id=message_id,
                files_to_restore=validated_files_to_restore,
                files_to_delete=validated_files_to_delete,
                fork_title=fork_title,
            )
        )

        response = await protocol.send_request(
            method=DroidServerMethod.EXECUTE_REWIND.value,
            params=params,
            timeout=SESSION_INIT_TIMEOUT,
        )

        return ExecuteRewindResult.model_validate(response.get("result", {}))

    # ----------------------------------------------------------
    # Streaming: receive_response() async iterator
    # ----------------------------------------------------------

    async def receive_response(self) -> AsyncIterator[StreamMessage]:
        """Async iterator yielding typed :class:`StreamMessage` objects.

        Subscribes to session notifications, converts each to a
        :class:`StreamMessage` via :func:`_notification_to_stream_message`,
        and yields them. The iterator terminates with a
        :class:`TurnComplete` sentinel when the droid working state
        transitions to ``Idle`` after being in a non-idle state.

        Uses an unbounded :class:`asyncio.Queue` internally to handle
        concurrent notifications without dropping messages.

        Usage::

            await client.add_user_message(text="Hello")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantTextDelta):
                    print(msg.text, end="", flush=True)
                elif isinstance(msg, TurnComplete):
                    print("\\nDone!", msg.token_usage)

        Yields:
            Typed :class:`StreamMessage` objects (text deltas, tool
            events, state changes, token usage, errors). The final
            yielded message is always :class:`TurnComplete`.

        Raises:
            ConnectionError: If the client has been closed.
        """
        self._ensure_not_closed()

        queue: asyncio.Queue[StreamMessage | None] = asyncio.Queue()
        was_not_idle = False
        last_token_usage: TokenUsageUpdate | None = None
        # Correlate tool_use_id -> tool_name so tool_result / tool_progress
        # notifications (which omit the name) can be backfilled.
        tool_names: dict[str, str] = {}

        def _on_notification(notification_dict: dict[str, Any]) -> None:
            nonlocal was_not_idle, last_token_usage

            # Parse the raw notification dict into typed Pydantic model
            try:
                parsed = SessionNotification.model_validate(notification_dict)
            except Exception:
                logger.debug(
                    "receive_response: could not parse notification, skipping",
                    exc_info=True,
                )
                return

            inner = parsed.params.notification
            result = _notification_to_stream_message(inner)

            if result is None:
                return

            # Handle list of ToolUse (from CREATE_MESSAGE)
            if isinstance(result, list):
                for item in result:
                    tool_names[item.tool_use_id] = item.tool_name
                    queue.put_nowait(item)
                return

            # Backfill the tool name on results/progress from the matching
            # tool_use, correlating via tool_use_id.
            if isinstance(result, (ToolResult, ToolProgress)):
                should_backfill_tool_name = (
                    isinstance(result, ToolResult) and result.tool_name is None
                ) or (isinstance(result, ToolProgress) and not result.tool_name)
                if should_backfill_tool_name and result.tool_use_id is not None:
                    name = tool_names.get(result.tool_use_id)
                    if name is not None:
                        result = dataclasses.replace(result, tool_name=name)

            # Track token usage for TurnComplete
            if isinstance(result, TokenUsageUpdate):
                last_token_usage = result

            # Track non-idle state so we know when to terminate
            if isinstance(result, WorkingStateChanged):
                if result.state != DroidWorkingState.Idle:
                    was_not_idle = True
                elif was_not_idle:
                    # Transition to Idle after being non-idle → turn complete
                    queue.put_nowait(result)
                    queue.put_nowait(TurnComplete(token_usage=last_token_usage))
                    queue.put_nowait(None)  # sentinel to stop iteration
                    return
                else:
                    # Initial Idle (agent was never non-idle) — skip
                    return

            queue.put_nowait(result)

        unsubscribe = self.on_notification(_on_notification)
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
        finally:
            unsubscribe()

    # ----------------------------------------------------------
    # Notification event system
    # ----------------------------------------------------------

    def on_notification(
        self,
        callback: NotificationCallback,
        *,
        notification_type: SessionNotificationType | None = None,
    ) -> Unsubscribe:
        """Register a listener for session notification events.

        The listener is invoked whenever a ``droid.session_notification``
        arrives from the server. Optionally filter by notification type.

        Multiple listeners can be registered; all receive the same
        notification. Listener exceptions are isolated — if one raises,
        others still receive the event and the read loop continues.

        Args:
            callback: Function invoked with the full notification dict.
            notification_type: Optional type filter. If provided, only
                notifications matching this type are delivered.

        Returns:
            An unsubscribe function. Call it to remove this listener.
        """
        entry = (callback, notification_type)
        self._notification_listeners.append(entry)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._notification_listeners.remove(entry)

        return unsubscribe

    # ----------------------------------------------------------
    # Server→client request handlers
    # ----------------------------------------------------------

    def set_permission_handler(self, handler: Callable[..., Any]) -> None:
        """Register a handler for server→client permission requests.

        The handler receives the request params dict and should return
        a ``ToolConfirmationOutcome`` string value (or any string).
        Async handlers are awaited. Replaces any previously registered
        handler.

        Args:
            handler: Sync or async callable ``(params) -> str``.
        """
        self._permission_handler = handler
        # Update protocol engine if already connected
        if self._protocol is not None:
            self._protocol.set_permission_handler(self._dispatch_permission_request)

    def clear_permission_handler(self) -> None:
        """Remove the permission request handler.

        Restores default behavior: return Cancel.
        """
        self._permission_handler = None
        if self._protocol is not None:
            self._protocol.clear_permission_handler()

    def set_ask_user_handler(self, handler: Callable[..., Any]) -> None:
        """Register a handler for server→client ask_user requests.

        The handler receives the request params dict and should return
        a dict with ``cancelled`` and ``answers`` keys.
        Async handlers are awaited. Replaces any previously registered
        handler.

        Args:
            handler: Sync or async callable ``(params) -> dict``.
        """
        self._ask_user_handler = handler
        if self._protocol is not None:
            self._protocol.set_ask_user_handler(self._dispatch_ask_user_request)

    def clear_ask_user_handler(self) -> None:
        """Remove the ask_user request handler.

        Restores default behavior: return ``cancelled=True, answers=[]``.
        """
        self._ask_user_handler = None
        if self._protocol is not None:
            self._protocol.clear_ask_user_handler()

    # ----------------------------------------------------------
    # Internal: Client-level dispatch methods
    # ----------------------------------------------------------

    def _dispatch_notification(self, notification: dict[str, Any]) -> None:
        """Dispatch a notification to all registered client-level listeners.

        Filters by notification type if a type filter is set.
        Exception in one listener does not affect others.
        """
        # Extract the notification type from the payload
        notif_type: str | None = None
        params = notification.get("params")
        if isinstance(params, dict):
            inner = params.get("notification")
            if isinstance(inner, dict):
                notif_type = inner.get("type")

        for callback, type_filter in list(self._notification_listeners):
            if type_filter is not None and notif_type != type_filter.value:
                continue
            try:
                callback(notification)
            except Exception:
                logger.warning(
                    "Client notification listener raised an exception",
                    exc_info=True,
                )

    def _dispatch_permission_request(self, params: dict[str, Any]) -> Any:
        """Dispatch to the client-level permission handler.

        If no handler is set, returns the default Cancel outcome.
        """
        handler = self._permission_handler
        if handler is None:
            return "cancel"
        return handler(params)

    def _dispatch_ask_user_request(self, params: dict[str, Any]) -> Any:
        """Dispatch to the client-level ask_user handler.

        If no handler is set, returns the default cancelled response.
        """
        handler = self._ask_user_handler
        if handler is None:
            return {"cancelled": True, "answers": []}
        return handler(params)

    # ----------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------

    def _ensure_not_closed(self) -> None:
        """Raise ConnectionError if the client has been closed."""
        if self._closed:
            raise DroidConnectionError(
                "Client has been closed. Create a new DroidClient instance "
                "or call connect() to reconnect."
            )

    def _ensure_session(self) -> str:
        """Return the active session ID, or raise SessionError if absent."""
        if self._session_id is None:
            raise SessionError(
                "No active session. Call initialize_session or load_session first."
            )
        return self._session_id

    def _ensure_protocol(self) -> ProtocolEngine:
        """Return the protocol engine, raising if not connected."""
        if self._protocol is None:
            raise DroidConnectionError("Client not connected. Call connect() first.")
        return self._protocol


def _set_if_not_none(d: dict[str, Any], key: str, value: Any) -> None:
    """Set a key in the dict only if value is not None."""
    if value is not None:
        d[key] = value


def _serialize_params(model: BaseModel) -> dict[str, Any]:
    """Serialize validated request parameters to their wire aliases."""
    return model.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def _enum_value(val: Any) -> Any:
    """Extract .value from an enum, or return None."""
    if val is None:
        return None
    if hasattr(val, "value"):
        return val.value
    return val


__all__ = [
    "DroidClient",
]
