"""Lazy high-level session lifecycle and one-shot run helper."""

# ruff: noqa: TC001

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError

from droid_sdk._high_level._immutable import JsonObject
from droid_sdk._high_level.attachments import (
    Document,
    Image,
    PdfDocumentSource,
    TextDocumentSource,
)
from droid_sdk._high_level.config import (
    JsonSchema,
    SandboxSettings,
    SessionConfig,
    SessionSettings,
    SessionSource,
    SessionTag,
    UpdateSettingsResult,
)
from droid_sdk._high_level.enums import (
    Autonomy,
    ContextAccuracy,
    McpServerStatus,
    McpServerType,
    Mode,
    ReasoningEffort,
    ToolCategory,
)
from droid_sdk._high_level.extensions import (
    CompactOutcome,
    HttpMcpServerConfig,
    McpConfigError,
    McpMutationResult,
    McpServerConfig,
    McpServersResult,
    McpServerStatusInfo,
    McpStatusSummary,
    McpToolInfo,
    McpToolInputSchema,
    RewindEvictedFile,
    RewindFileCreation,
    RewindFileSnapshot,
    RewindInfo,
    RewindOutcome,
    SdkMcpServer,
    SkillInfo,
    SkillMutationResult,
    SkillResource,
    SkillsResult,
    SseMcpServerConfig,
    StdioMcpServerConfig,
    ToolInfo,
)
from droid_sdk._high_level.interaction_adapter import InteractionDispatcher
from droid_sdk._high_level.interactions import InteractionHandlers
from droid_sdk._high_level.messages import (
    ContextUsage,
    RunResult,
    StreamEvent,
    StreamMessage,
)
from droid_sdk._high_level.output import prepare_output_adapter
from droid_sdk._high_level.runtime import Runtime
from droid_sdk._high_level.streaming import RunStream
from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    DroidConnectionError,
    DroidError,
    InvalidWorkingDirectoryError,
    SessionBusyError,
    SessionClosedError,
    SessionNotOpenError,
    SessionReplacedError,
    SessionReplacementError,
)
from droid_sdk.observability import ObservabilityAdapter
from droid_sdk.schemas.client import (
    AddUserMessageRequestParams,
    HttpMcpConfig,
    SseMcpConfig,
    StdioMcpConfig,
)
from droid_sdk.schemas.client import (
    HttpHeader as WireHttpHeader,
)
from droid_sdk.schemas.client import (
    McpOAuthOptions as WireMcpOAuthOptions,
)
from droid_sdk.schemas.enums import (
    AutonomyLevel as WireAutonomy,
)
from droid_sdk.schemas.enums import (
    DroidInteractionMode,
    SettingsLevel,
)
from droid_sdk.schemas.enums import (
    McpServerType as WireMcpServerType,
)
from droid_sdk.schemas.enums import (
    ReasoningEffort as WireReasoningEffort,
)
from droid_sdk.transport import ProcessTransport

ModelT = TypeVar("ModelT", bound=BaseModel)


class _Unset:
    pass


_UNSET = _Unset()


class _State(Enum):
    LAZY = "lazy"
    OPENING = "opening"
    OPEN = "open"
    BUSY = "busy"
    REPLACING = "replacing"
    RETIRED = "retired"
    CLOSING = "closing"
    CLOSED = "closed"


def _wire_reasoning(value: ReasoningEffort | None) -> WireReasoningEffort | None:
    return None if value is None else WireReasoningEffort(value.value)


def _wire_source(value: SessionSource | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        key: item.value if isinstance(item, Enum) else item
        for key, item in (
            (field, getattr(value, field)) for field in value.__dataclass_fields__
        )
        if item is not None
    }


def _wire_tags(values: Sequence[SessionTag]) -> list[dict[str, Any]]:
    return [
        {
            "name": value.name,
            **({} if value.metadata is None else {"metadata": dict(value.metadata)}),
        }
        for value in values
    ]


def _settings(value: Any) -> SessionSettings:
    mode = (
        None
        if value.interaction_mode is None
        or value.interaction_mode.value not in {"auto", "spec"}
        else Mode(value.interaction_mode.value)
    )
    autonomy = (
        None if value.autonomy_level is None else Autonomy(value.autonomy_level.value)
    )
    sandbox = (
        None
        if value.sandbox is None
        else SandboxSettings(
            enabled=value.sandbox.enabled,
            mode=None if value.sandbox.mode is None else value.sandbox.mode.value,
        )
    )
    return SessionSettings(
        model=value.model_id,
        reasoning_effort=ReasoningEffort(value.reasoning_effort.value),
        mode=mode,
        autonomy=autonomy,
        spec_model=value.spec_mode_model_id,
        spec_reasoning_effort=(
            None
            if value.spec_mode_reasoning_effort is None
            else ReasoningEffort(value.spec_mode_reasoning_effort.value)
        ),
        tags=tuple(
            SessionTag(name=tag.name, metadata=tag.metadata)
            for tag in (value.tags or ())
        ),
        sandbox=sandbox,
        additional_tools=value.additional_tool_ids,
        enabled_tools=value.enabled_tool_ids,
        disabled_tools=value.disabled_tool_ids,
        restrict_tools=value.restrict_tool_ids,
    )


def _mcp_config(value: McpServerConfig) -> dict[str, Any]:
    if isinstance(value, SdkMcpServer):
        raise TypeError("SDK MCP servers must be started before serialization")
    try:
        if isinstance(value, StdioMcpServerConfig):
            model: BaseModel = StdioMcpConfig(
                name=value.name,
                command=value.command,
                args=list(value.args),
                env=dict(value.env),
            )
        else:
            oauth: WireMcpOAuthOptions | Literal[False] | None
            if value.oauth is None or value.oauth is False:
                oauth = value.oauth
            else:
                oauth = WireMcpOAuthOptions.model_validate(
                    {
                        field: (item.value if isinstance(item, Enum) else item)
                        for field, item in (
                            (field, getattr(value.oauth, field))
                            for field in value.oauth.__dataclass_fields__
                        )
                        if item is not None
                    }
                )
            headers = [
                WireHttpHeader(name=header.name, value=header.value)
                for header in value.headers
            ]
            if isinstance(value, HttpMcpServerConfig):
                model = HttpMcpConfig(
                    type="http",
                    name=value.name,
                    url=value.url,
                    headers=headers,
                    oauth=oauth,
                )
            else:
                model = SseMcpConfig(
                    type="sse",
                    name=value.name,
                    url=value.url,
                    headers=headers,
                    oauth=oauth,
                )
    except (ValidationError, ValueError):
        raise ValueError("Invalid MCP server configuration") from None
    return model.model_dump(by_alias=True, exclude_none=True)


class Session:
    """A lazy, single-turn-at-a-time Droid session."""

    def __init__(
        self,
        *,
        cwd: str | Path | None = None,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        config: SessionConfig | None = None,
        interactions: InteractionHandlers | None = None,
        runtime: Runtime | None = None,
        api_key: str | None = None,
    ) -> None:
        self._requested_cwd: Path | None = Path.cwd() if cwd is None else Path(cwd)
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._config = config or SessionConfig()
        self._interactions = interactions or InteractionHandlers()
        self._dispatcher = InteractionDispatcher(self._interactions)
        self._runtime_config = runtime or Runtime()
        self._observability = ObservabilityAdapter(self._runtime_config.observability)
        self._api_key = api_key
        self._resume_id: str | None = None
        self._resume_options: dict[str, object] = {}
        self._state = _State.LAZY
        self._client: DroidClient | None = None
        self._id: str | None = None
        self._cwd: Path | None = self._requested_cwd
        self._settings: SessionSettings | None = None
        self._active_stream: RunStream[Any, Any] | None = None
        self._subscriptions: set[Callable[[], None]] = set()
        self._sdk_servers: list[SdkMcpServer] = []
        self._replacement_id: str | None = None
        self._replacement_successor: Session | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._open_task: asyncio.Task[None] | None = None
        self._open_cleanup_task: asyncio.Task[None] | None = None
        self._open_waiters = 0
        self._close_task: asyncio.Task[None] | None = None
        self._close_requested = False
        self._replacement_task: asyncio.Task[tuple[Any, Session]] | None = None
        self._replacement_close_requested = False
        self._load_mcp_configs: list[dict[str, Any]] = []
        self._load_options: dict[str, object] = {
            "additional_tools": self._config.additional_tools,
            "enabled_tools": self._config.enabled_tools,
            "disabled_tools": self._config.disabled_tools,
            "restrict_tools": self._config.restrict_tools,
            "auto_reject_permission_requests": (
                self._config.auto_reject_permission_requests
            ),
            "disable_builtin_skills": self._config.disable_builtin_skills,
            "session_source": self._config.session_source,
        }

    @classmethod
    def resume(
        cls,
        session_id: str,
        *,
        interactions: InteractionHandlers | None = None,
        mcp_servers: Sequence[McpServerConfig] = (),
        runtime: Runtime | None = None,
        api_key: str | None = None,
        disabled_tools: set[str] | frozenset[str] | None = None,
        auto_reject_permission_requests: bool | None = None,
        disable_builtin_skills: bool | None = None,
        session_source: SessionSource | None = None,
    ) -> Session:
        value = cls(
            interactions=interactions,
            runtime=runtime,
            api_key=api_key,
        )
        value._resume_id = session_id
        value._requested_cwd = None
        value._cwd = None
        value._resume_options = {
            "mcp_servers": tuple(mcp_servers),
            "disabled_tools": disabled_tools,
            "auto_reject_permission_requests": auto_reject_permission_requests,
            "disable_builtin_skills": disable_builtin_skills,
            "session_source": session_source,
        }
        value._load_options = {
            "additional_tools": None,
            "enabled_tools": None,
            "disabled_tools": disabled_tools,
            "restrict_tools": None,
            "auto_reject_permission_requests": auto_reject_permission_requests,
            "disable_builtin_skills": disable_builtin_skills,
            "session_source": session_source,
        }
        return value

    @property
    def id(self) -> str:
        if self._id is None:
            raise SessionNotOpenError("The session has not been opened")
        return self._id

    @property
    def cwd(self) -> Path | None:
        return self._cwd

    @property
    def settings(self) -> SessionSettings:
        if self._settings is None:
            raise SessionNotOpenError("The session has not been opened")
        return self._settings

    async def __aenter__(self) -> Session:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self.close()

    async def open(self) -> None:
        task: asyncio.Task[None] | None = None
        while task is None:
            cleanup_task: asyncio.Task[None] | None = None
            async with self._lifecycle_lock:
                cleanup_task = self._open_cleanup_task
                if cleanup_task is None:
                    if self._close_requested:
                        raise SessionClosedError("A closed session cannot be reopened")
                    if self._state in {_State.OPEN, _State.BUSY}:
                        return
                    if self._state is _State.OPENING:
                        task = self._open_task
                        assert task is not None
                    elif self._state is _State.REPLACING:
                        raise SessionBusyError("The session is being replaced")
                    elif self._state in {_State.CLOSING, _State.CLOSED}:
                        raise SessionClosedError("A closed session cannot be reopened")
                    elif self._state is _State.RETIRED:
                        self._raise_replaced()
                    else:
                        self._state = _State.OPENING
                        task = asyncio.create_task(self._open_impl())
                        self._open_task = task
                    self._open_waiters += 1
            if cleanup_task is not None:
                await asyncio.shield(cleanup_task)
        assert task is not None
        cancelled = False
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if cancelled:
                await self._cancel_open_waiter(task)
            else:
                self._open_waiters -= 1

    async def _cancel_open_waiter(self, task: asyncio.Task[None]) -> None:
        self._open_waiters -= 1
        if self._open_waiters != 0 or self._open_task is not task:
            return
        cleanup_task = asyncio.create_task(self._finish_cancelled_open(task))
        self._open_cleanup_task = cleanup_task
        await asyncio.shield(cleanup_task)

    async def _finish_cancelled_open(self, task: asyncio.Task[None]) -> None:
        cleanup_task: asyncio.Task[None] | None = None
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with self._lifecycle_lock:
            if self._state is _State.OPEN:
                self._state = _State.CLOSING
                cleanup_task = asyncio.create_task(self._close_impl())
                self._close_task = cleanup_task
            elif self._state is _State.CLOSING:
                cleanup_task = self._close_task
        if cleanup_task is not None:
            await asyncio.gather(cleanup_task, return_exceptions=True)
        async with self._lifecycle_lock:
            if (
                self._state is _State.CLOSED
                and self._close_task is cleanup_task
                and not self._close_requested
            ):
                self._reset_to_lazy()
            elif self._open_cleanup_task is asyncio.current_task():
                self._open_cleanup_task = None

    async def _open_impl(self) -> None:
        if self._requested_cwd is not None:
            try:
                if not self._requested_cwd.is_dir():
                    raise InvalidWorkingDirectoryError(str(self._requested_cwd))
                requested_cwd = self._requested_cwd.resolve()
            except OSError as exc:
                raise InvalidWorkingDirectoryError(str(self._requested_cwd)) from exc
        else:
            requested_cwd = Path.cwd()

        client: DroidClient | None = None
        started: list[SdkMcpServer] = []
        session_start_attempted = False
        self._observability.log(
            level="info",
            name="droid.sdk.session.open",
            message="Opening Droid session",
            attributes={"status": "starting"},
        )
        try:
            mcp_values = (
                cast("Sequence[McpServerConfig]", self._resume_options["mcp_servers"])
                if self._resume_id is not None
                else self._config.mcp_servers
            )
            configs: list[dict[str, Any]] = []
            for server in mcp_values:
                if isinstance(server, SdkMcpServer):
                    started.append(server)
                    config = await server.start()
                    configs.append(_mcp_config(config))
                else:
                    configs.append(_mcp_config(server))
            self._load_mcp_configs = configs

            runtime = self._runtime_config
            adapter = self._observability
            if runtime.transport is not None:
                if not runtime.transport.is_connected:
                    raise DroidError("A supplied transport must already be connected")
                transport = runtime.transport
            else:
                key = self._api_key or os.environ.get("FACTORY_API_KEY")
                env = dict(runtime.env)
                if key:
                    env["FACTORY_API_KEY"] = key
                executable = (
                    "droid" if runtime.executable is None else str(runtime.executable)
                )
                transport = ProcessTransport(
                    exec_path=executable,
                    exec_args=[
                        "exec",
                        "--input-format",
                        "stream-jsonrpc",
                        "--output-format",
                        "stream-jsonrpc",
                        *runtime.args,
                    ],
                    cwd=str(requested_cwd),
                    env=env,
                )
            client = DroidClient(
                transport=transport,
                trace_meta_injector=adapter.trace_meta_injector,
                timing_callback=adapter.timing_callback,
            )
            try:
                await client.connect()
            except FileNotFoundError as exc:
                raise DroidConnectionError(
                    "Droid executable was not found",
                    exec_path=(
                        None if runtime.executable is None else str(runtime.executable)
                    ),
                    cwd=str(requested_cwd),
                ) from exc
            client.set_permission_handler(self._dispatcher.handle_permission)
            client.set_ask_user_handler(self._dispatcher.handle_question)

            if self._resume_id is not None:
                session_start_attempted = True
                load_result = await client.load_session(
                    session_id=self._resume_id,
                    mcp_servers=configs or None,
                    disabled_tool_ids=_list_or_none(
                        self._resume_options["disabled_tools"]
                    ),
                    auto_reject_permission_requests=cast(
                        "bool | None",
                        self._resume_options["auto_reject_permission_requests"],
                    ),
                    disable_builtin_skills=cast(
                        "bool | None",
                        self._resume_options["disable_builtin_skills"],
                    ),
                    session_source=_wire_source(
                        cast(
                            "SessionSource | None",
                            self._resume_options["session_source"],
                        )
                    ),
                )
                session_id = self._resume_id
                cwd_value = _load_cwd(load_result, requested_cwd)
                wire_settings = load_result.settings
            else:
                sdk_tag = SessionTag(
                    name="sdk",
                    metadata={
                        "language": "python",
                        "version": importlib.metadata.version("droid-sdk"),
                    },
                )
                tags = tuple(tag for tag in self._config.tags if tag.name != "sdk")
                tags += (sdk_tag,)
                session_start_attempted = True
                initialize_result = await client.initialize_session(
                    machine_id=self._config.machine_id or "default",
                    cwd=str(requested_cwd),
                    mcp_servers=configs or None,
                    interaction_mode=(
                        None
                        if self._config.mode is None
                        else DroidInteractionMode(self._config.mode.value)
                    ),
                    autonomy_level=(
                        None
                        if self._config.autonomy is None
                        else WireAutonomy(self._config.autonomy.value)
                    ),
                    model_id=self._model,
                    reasoning_effort=_wire_reasoning(self._reasoning_effort),
                    spec_mode_model_id=self._config.spec_model,
                    spec_mode_reasoning_effort=_wire_reasoning(
                        self._config.spec_reasoning_effort
                    ),
                    additional_tool_ids=_list_or_none(self._config.additional_tools),
                    enabled_tool_ids=_list_or_none(self._config.enabled_tools),
                    disabled_tool_ids=_list_or_none(self._config.disabled_tools),
                    restrict_tool_ids=_list_or_none(self._config.restrict_tools),
                    session_source=_wire_source(self._config.session_source),
                    tags=cast("Any", _wire_tags(tags)),
                    auto_reject_permission_requests=(
                        self._config.auto_reject_permission_requests
                    ),
                    disable_builtin_skills=self._config.disable_builtin_skills,
                )
                session_id = initialize_result.session_id
                cwd_value = requested_cwd
                wire_settings = initialize_result.settings

            self._client = client
            self._id = session_id
            self._cwd = cwd_value
            self._settings = _settings(wire_settings)
            self._sdk_servers = started
            self._bind_metadata()
            if self._state is _State.OPENING:
                self._state = _State.OPEN
            self._observability.log(
                level="info",
                name="droid.sdk.session.open",
                message="Droid session opened",
                attributes={
                    "session_id": session_id,
                    "status": "success",
                },
            )
        except BaseException as exc:
            self._observability.log(
                level="error",
                name="droid.sdk.session.open",
                message="Droid session failed to open",
                attributes={"status": "error"},
                error=exc,
            )
            if client is not None:
                if session_start_attempted:
                    with contextlib.suppress(BaseException):
                        await client.close_session(reason="other")
                with contextlib.suppress(BaseException):
                    await client.close()
            await asyncio.gather(
                *(server.close() for server in started), return_exceptions=True
            )
            for unsubscribe in tuple(self._subscriptions):
                with contextlib.suppress(BaseException):
                    unsubscribe()
            self._subscriptions.clear()
            if self._client is client:
                self._client = None
            self._id = None
            self._settings = None
            self._sdk_servers.clear()
            if self._state is _State.OPENING:
                self._state = _State.LAZY
            raise

    async def close(self) -> None:
        task: asyncio.Task[None] | None = None
        state_at_entry = self._state
        replacement = self._replacement_task
        replacement_at_entry = replacement is not None and not replacement.done()
        if state_at_entry is _State.RETIRED and not replacement_at_entry:
            return
        self._close_requested = True
        if replacement_at_entry:
            self._replacement_close_requested = True
        async with self._lifecycle_lock:
            if replacement_at_entry:
                assert replacement is not None
                if self._close_task is None:
                    self._state = _State.CLOSING
                    task = asyncio.create_task(
                        self._close_after_replacement(replacement)
                    )
                    self._close_task = task
                else:
                    task = self._close_task
            elif self._state is _State.CLOSED:
                task = self._close_task
                if task is None:
                    return
            elif self._state is _State.RETIRED:
                return
            elif self._state is _State.CLOSING:
                task = self._close_task
                if task is None:
                    return
            elif self._state is _State.REPLACING:
                replacement = self._replacement_task
                assert replacement is not None
                self._state = _State.CLOSING
                task = asyncio.create_task(self._close_after_replacement(replacement))
                self._close_task = task
            elif self._state is _State.OPENING:
                opening = self._open_task
                assert opening is not None
                self._state = _State.CLOSING
                task = asyncio.create_task(self._close_after_open(opening))
                self._close_task = task
            elif self._state is _State.LAZY:
                self._state = _State.CLOSED
                return
            else:
                self._state = _State.CLOSING
                task = asyncio.create_task(self._close_impl())
                self._close_task = task
        await asyncio.shield(task)

    async def _close_after_open(self, opening: asyncio.Task[None]) -> None:
        try:
            await opening
        except BaseException:
            self._state = _State.CLOSED
            return
        await self._close_impl()

    async def _close_after_replacement(
        self,
        replacement: asyncio.Task[tuple[Any, Session]],
    ) -> None:
        try:
            _, successor = await replacement
        except BaseException:
            if self._client is None:
                self._state = _State.CLOSED
                return
            await self._close_impl()
            return
        await successor.close()
        self._state = _State.RETIRED

    async def _close_impl(self) -> None:
        session_id = self._id
        self._observability.log(
            level="info",
            name="droid.sdk.session.close",
            message="Closing Droid session",
            attributes={
                "session_id": session_id,
                "status": "starting",
            },
        )
        errors: list[BaseException] = []
        stream = self._active_stream
        if stream is not None:
            try:
                await stream.aclose()
            except BaseException as exc:
                errors.append(exc)
        for unsubscribe in tuple(self._subscriptions):
            try:
                unsubscribe()
            except BaseException as exc:
                errors.append(exc)
        self._subscriptions.clear()
        client = self._client
        if client is not None:
            try:
                await client.close_session(reason="other")
            except BaseException as exc:
                errors.append(exc)
            try:
                await client.close()
            except BaseException as exc:
                errors.append(exc)
        server_results = await asyncio.gather(
            *(server.close() for server in self._sdk_servers), return_exceptions=True
        )
        errors.extend(
            result for result in server_results if isinstance(result, BaseException)
        )
        self._client = None
        self._sdk_servers.clear()
        self._active_stream = None
        self._state = _State.CLOSED
        self._observability.log(
            level="error" if errors else "info",
            name="droid.sdk.session.close",
            message="Droid session closed",
            attributes={
                "session_id": session_id,
                "status": "error" if errors else "success",
            },
        )
        if errors:
            raise errors[0]

    def _reset_to_lazy(self) -> None:
        self._state = _State.LAZY
        self._close_task = None
        self._open_task = None
        self._open_cleanup_task = None
        self._close_requested = False
        self._client = None
        self._id = None
        self._settings = None
        self._active_stream = None
        self._subscriptions.clear()
        self._sdk_servers.clear()
        self._cwd = self._requested_cwd

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: None = None,
        timeout: float | None = None,
        include_partial_messages: Literal[False] = False,
    ) -> RunStream[None, StreamMessage[None]]: ...

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: type[ModelT],
        timeout: float | None = None,
        include_partial_messages: Literal[False] = False,
    ) -> RunStream[ModelT, StreamMessage[ModelT]]: ...

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: JsonSchema,
        timeout: float | None = None,
        include_partial_messages: Literal[False] = False,
    ) -> RunStream[JsonObject, StreamMessage[JsonObject]]: ...

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: None = None,
        timeout: float | None = None,
        include_partial_messages: Literal[True],
    ) -> RunStream[None, StreamEvent[None]]: ...

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: type[ModelT],
        timeout: float | None = None,
        include_partial_messages: Literal[True],
    ) -> RunStream[ModelT, StreamEvent[ModelT]]: ...

    @overload
    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: JsonSchema,
        timeout: float | None = None,
        include_partial_messages: Literal[True],
    ) -> RunStream[JsonObject, StreamEvent[JsonObject]]: ...

    def stream(
        self,
        prompt: str,
        *,
        images: Sequence[Image] = (),
        files: Sequence[Document] = (),
        output: type[BaseModel] | JsonSchema | None = None,
        timeout: float | None = None,
        include_partial_messages: bool = False,
    ) -> RunStream[Any, Any]:
        self._ensure_active()
        if self._active_stream is not None:
            raise SessionBusyError(f"Session {self.id} already has an active turn")
        adapter = prepare_output_adapter(output)
        turn_id = str(uuid.uuid4())
        stream_unsubscribes: tuple[Callable[[], None], ...] = ()

        async def start(stream: RunStream[Any, Any]) -> None:
            nonlocal stream_unsubscribes
            client = self._require_client()
            self._dispatcher.error_sink = stream.queue_error_event
            unsubscribe = client.on_notification(stream.feed_notification)
            unsubscribe_error = client.on_error(stream.feed_error)
            self._subscriptions.update((unsubscribe, unsubscribe_error))
            stream_unsubscribes = (
                unsubscribe,
                unsubscribe_error,
            )
            message = AddUserMessageRequestParams.model_validate(
                {
                    "text": prompt,
                    "messageId": turn_id,
                    "images": [
                        {
                            "type": "base64",
                            "data": image.source.data,
                            "mediaType": image.source.media_type,
                        }
                        for image in images
                    ]
                    or None,
                    "files": [_document_source(file) for file in files] or None,
                    "outputFormat": adapter.output_format,
                }
            )
            await client.add_user_message(
                text=message.text,
                message_id=message.message_id,
                images=cast("Any", message.images),
                files=cast("Any", message.files),
                output_format=message.output_format,
            )

        async def finish(interrupt: bool) -> None:
            client = self._client
            for unsubscribe in stream_unsubscribes:
                unsubscribe()
                self._subscriptions.discard(unsubscribe)
            if self._active_stream is stream_value:
                self._active_stream = None
                if self._state is _State.BUSY:
                    self._state = _State.OPEN
            self._dispatcher.error_sink = None
            if interrupt and client is not None:
                task = asyncio.create_task(client.interrupt_session())
                task.add_done_callback(_consume_task_result)
            if interrupt:
                status = "interrupted"
            elif stream_value.completed:
                result = stream_value.result
                if result.success:
                    status = "success"
                elif result.interrupted:
                    status = "interrupted"
                else:
                    status = "error"
            else:
                status = "error"
            self._observability.log(
                level="info" if status == "success" else "warn",
                name="droid.sdk.run.terminal",
                message="Droid run finished",
                attributes={
                    "session_id": self.id,
                    "status": status,
                },
            )
            self._observability.record_run_terminal(status=status)

        stream_value = RunStream(
            expected_turn_id=turn_id,
            session_id=self.id,
            include_partial_messages=include_partial_messages,
            output_adapter=adapter,
            start=start,
            finish=finish,
            timeout=timeout,
        )
        self._active_stream = stream_value
        self._state = _State.BUSY
        return stream_value

    async def interrupt(self) -> None:
        self._ensure_active()
        await self._require_client().interrupt_session()

    async def update_settings(
        self,
        *,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        mode: Mode | None = None,
        autonomy: Autonomy | None = None,
        spec_model: str | None | _Unset = _UNSET,
        spec_reasoning_effort: ReasoningEffort | None | _Unset = _UNSET,
        tags: Sequence[SessionTag] | None = None,
        compaction_token_limit: int | None = None,
        compaction_threshold_check_enabled: bool | None = None,
        additional_tools: set[str] | frozenset[str] | None = None,
        enabled_tools: set[str] | frozenset[str] | None = None,
        disabled_tools: set[str] | frozenset[str] | None = None,
        restrict_tools: set[str] | frozenset[str] | None = None,
    ) -> UpdateSettingsResult:
        self._ensure_active()
        spec_model_value = None if isinstance(spec_model, _Unset) else spec_model
        spec_reasoning_value = (
            None if isinstance(spec_reasoning_effort, _Unset) else spec_reasoning_effort
        )
        explicit_null_fields: list[
            Literal["specModeModelId", "specModeReasoningEffort"]
        ] = []
        if spec_model is None:
            explicit_null_fields.append("specModeModelId")
        if spec_reasoning_effort is None:
            explicit_null_fields.append("specModeReasoningEffort")
        await self._require_client().update_session_settings(
            model_id=model,
            reasoning_effort=_wire_reasoning(reasoning_effort),
            interaction_mode=(
                None if mode is None else DroidInteractionMode(mode.value)
            ),
            autonomy_level=(None if autonomy is None else WireAutonomy(autonomy.value)),
            spec_mode_model_id=spec_model_value,
            spec_mode_reasoning_effort=_wire_reasoning(spec_reasoning_value),
            tags=cast("Any", None if tags is None else _wire_tags(tags)),
            compaction_token_limit=compaction_token_limit,
            compaction_threshold_check_enabled=(compaction_threshold_check_enabled),
            additional_tool_ids=_list_or_none(additional_tools),
            enabled_tool_ids=_list_or_none(enabled_tools),
            disabled_tool_ids=_list_or_none(disabled_tools),
            restrict_tool_ids=_list_or_none(restrict_tools),
            explicit_null_fields=explicit_null_fields,
        )
        for key, value in (
            ("additional_tools", additional_tools),
            ("enabled_tools", enabled_tools),
            ("disabled_tools", disabled_tools),
            ("restrict_tools", restrict_tools),
        ):
            if value is not None:
                self._load_options[key] = frozenset(value)
        current = self.settings
        self._settings = SessionSettings(
            model=current.model if model is None else model,
            reasoning_effort=(
                current.reasoning_effort
                if reasoning_effort is None
                else reasoning_effort
            ),
            mode=current.mode if mode is None else mode,
            autonomy=current.autonomy if autonomy is None else autonomy,
            spec_model=(
                current.spec_model if isinstance(spec_model, _Unset) else spec_model
            ),
            spec_reasoning_effort=(
                current.spec_reasoning_effort
                if isinstance(spec_reasoning_effort, _Unset)
                else spec_reasoning_effort
            ),
            tags=current.tags if tags is None else tags,
            sandbox=current.sandbox,
            additional_tools=(
                current.additional_tools
                if additional_tools is None
                else additional_tools
            ),
            enabled_tools=(
                current.enabled_tools if enabled_tools is None else enabled_tools
            ),
            disabled_tools=(
                current.disabled_tools if disabled_tools is None else disabled_tools
            ),
            restrict_tools=(
                current.restrict_tools if restrict_tools is None else restrict_tools
            ),
        )
        return UpdateSettingsResult()

    async def rename(self, title: str) -> None:
        self._ensure_active()
        await self._require_client().rename_session(title=title)

    def on_notification(
        self,
        callback: Callable[[Mapping[str, object]], None],
        *,
        type: str | None = None,
    ) -> Callable[[], None]:
        self._ensure_active()

        def dispatch(raw: dict[str, Any]) -> None:
            inner = _inner_notification(raw)
            if inner is None:
                return
            if type is None or inner.get("type") == type:
                callback(cast("Mapping[str, object]", inner))

        unsubscribe_inner = self._require_client().on_notification(dispatch)

        def unsubscribe() -> None:
            unsubscribe_inner()
            self._subscriptions.discard(unsubscribe)

        self._subscriptions.add(unsubscribe)
        return unsubscribe

    async def list_tools(
        self,
        *,
        model: str | None = None,
        mode: Mode | None = None,
        autonomy: Autonomy | None = None,
        spec_model: str | None = None,
        additional_tools: set[str] | frozenset[str] | None = None,
        enabled_tools: set[str] | frozenset[str] | None = None,
        disabled_tools: set[str] | frozenset[str] | None = None,
        restrict_tools: set[str] | frozenset[str] | None = None,
        skip_permissions_unsafe: bool | None = None,
    ) -> list[ToolInfo]:
        self._ensure_active()
        result = await self._require_client().list_tools(
            model_id=model,
            interaction_mode=(
                None if mode is None else DroidInteractionMode(mode.value)
            ),
            autonomy_level=(None if autonomy is None else WireAutonomy(autonomy.value)),
            spec_mode_model_id=spec_model,
            additional_tool_ids=_list_or_none(additional_tools),
            enabled_tool_ids=_list_or_none(enabled_tools),
            disabled_tool_ids=_list_or_none(disabled_tools),
            restrict_tool_ids=_list_or_none(restrict_tools),
            skip_permissions_unsafe=skip_permissions_unsafe,
        )
        return [
            ToolInfo(
                id=item.llm_id or item.id,
                display_name=item.display_name or item.llm_id or item.id,
                description=item.description or "",
                category=_tool_category(item.category),
                default_allowed=item.default_allowed,
                allowed=item.currently_allowed,
            )
            for item in result.tools
        ]

    async def list_skills(self) -> SkillsResult:
        self._ensure_active()
        result = await self._require_client().list_skills()
        return SkillsResult(
            skills=[
                SkillInfo(
                    name=item.name,
                    description=item.description,
                    location=cast("Any", item.location.value),
                    file_path=item.file_path,
                    enabled=item.enabled,
                    user_invocable=item.user_invocable,
                    version=item.version,
                    content=item.content,
                    resources=tuple(
                        SkillResource(
                            name=resource.name,
                            path=resource.path,
                            type=resource.type,
                        )
                        for resource in (item.resources or ())
                    ),
                    disabled_by=item.disabled_by,
                )
                for item in result.skills
            ],
            project_available=result.project_available,
        )

    async def enable_skill(
        self,
        name: str,
        *,
        scope: Literal["user", "project"] = "user",
    ) -> SkillMutationResult:
        return await self._set_skill(name, False, scope)

    async def disable_skill(
        self,
        name: str,
        *,
        scope: Literal["user", "project"] = "user",
    ) -> SkillMutationResult:
        return await self._set_skill(name, True, scope)

    async def _set_skill(
        self,
        name: str,
        disabled: bool,
        scope: Literal["user", "project"],
    ) -> SkillMutationResult:
        self._ensure_active()
        result = await self._require_client().set_skill_disabled(
            skill_name=name,
            disabled=disabled,
            settings_level=SettingsLevel(scope),
        )
        return SkillMutationResult(result.success)

    async def list_mcp_servers(self) -> McpServersResult:
        self._ensure_active()
        result = await self._require_client().list_mcp_servers()
        return McpServersResult(
            servers=tuple(_mcp_server(item) for item in result.servers),
            summary=_mcp_summary(result.summary),
        )

    async def list_mcp_tools(self) -> list[McpToolInfo]:
        self._ensure_active()
        result = await self._require_client().list_mcp_tools()
        return [
            McpToolInfo(
                server_name=item.server_name,
                name=item.name,
                description=item.description,
                is_enabled=item.is_enabled,
                is_read_only=item.is_read_only,
                input_schema=(
                    None
                    if item.input_schema is None
                    else McpToolInputSchema(
                        type=item.input_schema.type,
                        properties=item.input_schema.properties,
                        required=item.input_schema.required,
                    )
                ),
            )
            for item in result.tools
        ]

    async def add_mcp_server(
        self,
        config: StdioMcpServerConfig | HttpMcpServerConfig | SseMcpServerConfig,
    ) -> McpMutationResult:
        self._ensure_active()
        raw = _mcp_config(config)
        headers = cast("object", raw.get("headers"))
        result = await self._require_client().add_mcp_server(
            name=config.name,
            type=WireMcpServerType(raw.get("type", "stdio")),
            url=cast("str | None", raw.get("url")),
            headers=(
                None
                if not isinstance(headers, list)
                else _header_mapping(cast("list[object]", headers))
            ),
            command=cast("str | None", raw.get("command")),
            args=cast("list[str] | None", raw.get("args")),
            env=cast("dict[str, str] | None", raw.get("env")),
            oauth=cast("Any", raw.get("oauth")),
        )
        return McpMutationResult(result.success)

    async def remove_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().remove_mcp_server(
            server_name=name,
            settings_level=SettingsLevel.User,
        )
        return McpMutationResult(result.success)

    async def enable_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        return await self._toggle_mcp_server(name, True)

    async def disable_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        return await self._toggle_mcp_server(name, False)

    async def _toggle_mcp_server(
        self,
        name: str,
        enabled: bool,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().toggle_mcp_server(
            server_name=name,
            enabled=enabled,
            settings_level=SettingsLevel.User,
        )
        return McpMutationResult(result.success)

    async def enable_mcp_tool(
        self, server_name: str, tool_name: str
    ) -> McpMutationResult:
        return await self._toggle_mcp_tool(server_name, tool_name, True)

    async def disable_mcp_tool(
        self, server_name: str, tool_name: str
    ) -> McpMutationResult:
        return await self._toggle_mcp_tool(server_name, tool_name, False)

    async def _toggle_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        enabled: bool,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().toggle_mcp_tool(
            server_name=server_name,
            tool_name=tool_name,
            enabled=enabled,
        )
        return McpMutationResult(result.success)

    async def authenticate_mcp_server(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().authenticate_mcp_server(server_name=name)
        return McpMutationResult(result.success)

    async def cancel_mcp_auth(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().cancel_mcp_auth(server_name=name)
        return McpMutationResult(result.success)

    async def clear_mcp_auth(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().clear_mcp_auth(server_name=name)
        return McpMutationResult(result.success)

    async def submit_mcp_auth_code(
        self, name: str, *, code: str, state: str
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().submit_mcp_auth_code(
            server_name=name, code=code, state=state
        )
        return McpMutationResult(result.success)

    async def submit_mcp_auth_error(
        self,
        name: str,
        *,
        error: str,
        state: str,
        error_description: str | None = None,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().submit_mcp_auth_error(
            server_name=name,
            error=error,
            state=state,
            error_description=error_description,
        )
        return McpMutationResult(result.success)

    async def context(self) -> ContextUsage:
        self._ensure_active()
        result = await self._require_client().get_context_stats()
        timestamp = datetime.fromisoformat(result.updated_at.replace("Z", "+00:00"))
        return ContextUsage(
            used=result.used,
            remaining=result.remaining,
            limit=result.limit,
            accuracy=ContextAccuracy(result.accuracy.value),
            updated_at=timestamp,
        )

    async def enter_spec(
        self,
        *,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> UpdateSettingsResult:
        if model is None and reasoning_effort is None:
            return await self.update_settings(mode=Mode.SPEC)
        if model is None:
            return await self.update_settings(
                mode=Mode.SPEC,
                spec_reasoning_effort=reasoning_effort,
            )
        if reasoning_effort is None:
            return await self.update_settings(
                mode=Mode.SPEC,
                spec_model=model,
            )
        return await self.update_settings(
            mode=Mode.SPEC,
            spec_model=model,
            spec_reasoning_effort=reasoning_effort,
        )

    async def leave_spec(self) -> UpdateSettingsResult:
        return await self.update_settings(mode=Mode.AUTO)

    async def fork(
        self,
        *,
        title: str | None = None,
        tags: Sequence[SessionTag] | None = None,
    ) -> Session:
        _, successor = await self._replacement_operation(
            lambda: self._require_client().fork_session(
                title=title,
                tags=cast("Any", None if tags is None else _wire_tags(tags)),
            )
        )
        return successor

    async def compact(
        self,
        *,
        instructions: str | None = None,
    ) -> CompactOutcome:
        result, successor = await self._replacement_operation(
            lambda: self._require_client().compact_session(
                custom_instructions=instructions
            )
        )
        return CompactOutcome(successor, result.removed_count)

    async def rewind_info(self, message_id: str) -> RewindInfo:
        self._ensure_active()
        result = await self._require_client().get_rewind_info(message_id=message_id)
        return RewindInfo(
            available_files=tuple(
                RewindFileSnapshot(item.file_path, item.content_hash, item.size)
                for item in result.available_files
            ),
            created_files=tuple(
                RewindFileCreation(item.file_path) for item in result.created_files
            ),
            evicted_files=tuple(
                RewindEvictedFile(item.file_path, item.reason)
                for item in result.evicted_files
            ),
        )

    async def rewind(
        self,
        message_id: str,
        *,
        restore: Sequence[RewindFileSnapshot] = (),
        delete: Sequence[RewindFileCreation] = (),
        title: str,
    ) -> RewindOutcome:
        result, successor = await self._replacement_operation(
            lambda: self._require_client().execute_rewind(
                message_id=message_id,
                files_to_restore=[
                    {
                        "filePath": item.file_path,
                        "contentHash": item.content_hash,
                        "size": item.size,
                    }
                    for item in restore
                ],
                files_to_delete=[{"filePath": item.file_path} for item in delete],
                fork_title=title,
            )
        )
        return RewindOutcome(
            successor,
            result.restored_count,
            result.deleted_count,
            result.failed_restore_count,
            result.failed_delete_count,
        )

    async def _replacement_operation(
        self,
        operation: Callable[[], Any],
    ) -> tuple[Any, Session]:
        async with self._lifecycle_lock:
            if self._close_requested:
                raise SessionClosedError("The session is closed")
            self._ensure_active()
            if self._active_stream is not None:
                raise SessionBusyError("Cannot replace a session with an active turn")
            self._state = _State.REPLACING
            self._replacement_successor = None
            self._replacement_close_requested = False
            task = asyncio.create_task(self._replacement_impl(operation))
            self._replacement_task = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if task.done() and not task.cancelled():
                with contextlib.suppress(BaseException):
                    _, successor = task.result()
                    await self._restore_after_cancelled_replacement(successor)
            raise

    async def _replacement_impl(
        self,
        operation: Callable[[], Any],
    ) -> tuple[Any, Session]:
        successor: Session | None = None
        try:
            result = await operation()
            successor = await self._attach_replacement(result.new_session_id)
            self._replacement_successor = successor
            await _replacement_handoff_checkpoint()
            self._retire_after_replacement(successor)
            return result, successor
        except asyncio.CancelledError:
            if successor is not None:
                await self._restore_after_cancelled_replacement(successor)
            elif self._state is _State.REPLACING:
                self._state = _State.OPEN
            raise
        except BaseException:
            if self._state is _State.REPLACING:
                self._state = _State.OPEN
            raise

    async def _restore_after_cancelled_replacement(self, successor: Session) -> None:
        if self._replacement_close_requested:
            self._detach_cancelled_successor(successor)
            return
        client = successor._require_client()
        try:
            restored = await self._load_with_policies(client, self.id)
            self._settings = _settings(restored.settings)
            self._cwd = _load_cwd(restored, self._cwd or Path.cwd())
        except BaseException:
            self._state = _State.CLOSING
            with contextlib.suppress(BaseException):
                await self._close_impl()
            self._detach_cancelled_successor(successor)
            self._replacement_successor = None
            return
        self._detach_cancelled_successor(successor)
        self._replacement_id = None
        self._replacement_successor = None
        self._replacement_task = None
        self._state = _State.OPEN

    def _detach_cancelled_successor(self, successor: Session) -> None:
        for unsubscribe in tuple(successor._subscriptions):
            with contextlib.suppress(BaseException):
                unsubscribe()
        successor._subscriptions.clear()
        successor._client = None
        successor._sdk_servers = []
        successor._state = _State.RETIRED
        successor._replacement_id = self.id

    def _retire_after_replacement(self, successor: Session) -> None:
        self._replacement_id = successor.id
        self._state = _State.RETIRED
        for unsubscribe in tuple(self._subscriptions):
            unsubscribe()
        self._subscriptions.clear()
        self._client = None
        self._sdk_servers = []

    async def _attach_replacement(self, replacement_id: str) -> Session:
        client = self._require_client()
        try:
            loaded = await self._load_with_policies(client, replacement_id)
        except BaseException as cause:
            try:
                restored = await self._load_with_policies(client, self.id)
                self._settings = _settings(restored.settings)
                self._cwd = _load_cwd(restored, self._cwd or Path.cwd())
            except BaseException as rollback:
                self._state = _State.CLOSING
                with contextlib.suppress(BaseException):
                    await self._close_impl()
                raise SessionReplacementError(
                    self.id,
                    replacement_id,
                    rollback_error=rollback,
                ) from cause
            raise SessionReplacementError(self.id, replacement_id) from cause

        successor = object.__new__(Session)
        successor.__dict__ = self.__dict__.copy()
        successor._id = replacement_id
        successor._settings = _settings(loaded.settings)
        successor._cwd = _load_cwd(loaded, self._cwd or Path.cwd())
        successor._state = _State.OPEN
        successor._active_stream = None
        successor._subscriptions = set()
        successor._replacement_successor = None
        successor._lifecycle_lock = asyncio.Lock()
        successor._open_task = None
        successor._open_cleanup_task = None
        successor._open_waiters = 0
        successor._close_task = None
        successor._close_requested = False
        successor._replacement_task = None
        successor._replacement_close_requested = False
        successor._bind_metadata()
        return successor

    async def _load_with_policies(
        self,
        client: DroidClient,
        session_id: str,
    ) -> Any:
        loaded = await client.load_session(
            session_id=session_id,
            mcp_servers=self._load_mcp_configs or None,
            additional_tool_ids=_list_or_none(self._load_options["additional_tools"]),
            enabled_tool_ids=_list_or_none(self._load_options["enabled_tools"]),
            disabled_tool_ids=_list_or_none(self._load_options["disabled_tools"]),
            auto_reject_permission_requests=cast(
                "bool | None",
                self._load_options["auto_reject_permission_requests"],
            ),
            disable_builtin_skills=cast(
                "bool | None",
                self._load_options["disable_builtin_skills"],
            ),
            session_source=_wire_source(
                cast("SessionSource | None", self._load_options["session_source"])
            ),
        )
        restrict_tools = _list_or_none(self._load_options["restrict_tools"])
        if restrict_tools is not None:
            await client.update_session_settings(
                restrict_tool_ids=restrict_tools,
            )
        return loaded

    def _bind_metadata(self) -> None:
        client = self._require_client()

        def update(raw: dict[str, Any]) -> None:
            inner = _inner_notification(raw)
            if inner is None:
                return
            if inner.get("type") == "settings_updated":
                settings = inner.get("settings")
                if isinstance(settings, Mapping) and self._settings is not None:
                    self._settings = _merge_settings(
                        self._settings,
                        cast("Mapping[str, object]", settings),
                    )
                return
            if inner.get("type") == "session_working_directory_changed":
                cwd = inner.get("cwd")
                if isinstance(cwd, str):
                    self._cwd = Path(cwd)

        unsubscribe = client.on_notification(update)
        self._subscriptions.add(unsubscribe)

    def _ensure_active(self) -> None:
        if self._state in {_State.LAZY, _State.OPENING}:
            raise SessionNotOpenError("Call open() before using the session")
        if self._state in {_State.CLOSING, _State.CLOSED}:
            raise SessionClosedError("The session is closed")
        if self._state is _State.RETIRED:
            self._raise_replaced()
        if self._state is _State.REPLACING:
            raise SessionBusyError("The session is being replaced")

    def _raise_replaced(self) -> None:
        assert self._id is not None and self._replacement_id is not None
        raise SessionReplacedError(self._id, self._replacement_id)

    def _require_client(self) -> DroidClient:
        if self._client is None:
            if self._state is _State.RETIRED:
                self._raise_replaced()
            raise SessionNotOpenError("The session has not been opened")
        return self._client


@overload
async def run(
    prompt: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    images: Sequence[Image] = (),
    files: Sequence[Document] = (),
    output: None = None,
    timeout: float | None = None,
    config: SessionConfig | None = None,
    interactions: InteractionHandlers | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> RunResult[None]: ...


@overload
async def run(
    prompt: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    images: Sequence[Image] = (),
    files: Sequence[Document] = (),
    output: type[ModelT],
    timeout: float | None = None,
    config: SessionConfig | None = None,
    interactions: InteractionHandlers | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> RunResult[ModelT]: ...


@overload
async def run(
    prompt: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    images: Sequence[Image] = (),
    files: Sequence[Document] = (),
    output: JsonSchema,
    timeout: float | None = None,
    config: SessionConfig | None = None,
    interactions: InteractionHandlers | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> RunResult[JsonObject]: ...


async def run(
    prompt: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    images: Sequence[Image] = (),
    files: Sequence[Document] = (),
    output: type[BaseModel] | JsonSchema | None = None,
    timeout: float | None = None,
    config: SessionConfig | None = None,
    interactions: InteractionHandlers | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> RunResult[Any]:
    session = Session(
        cwd=cwd,
        model=model,
        reasoning_effort=reasoning_effort,
        config=config,
        interactions=interactions,
        runtime=runtime,
        api_key=api_key,
    )
    try:
        await session.open()
        stream = session.stream(
            prompt,
            images=images,
            files=files,
            output=output,
            timeout=timeout,
        )
        async with stream:
            async for _ in stream:
                pass
        return stream.result
    finally:
        close_task = asyncio.create_task(session.close())
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            await close_task
            raise


def _list_or_none(value: object) -> list[str] | None:
    if value is None:
        return None
    return sorted(cast("Sequence[str]", value))


async def _replacement_handoff_checkpoint() -> None:
    """Give cancellation a deterministic handoff point after replacement."""
    await asyncio.sleep(0)


def _consume_task_result(task: asyncio.Future[Any]) -> None:
    with contextlib.suppress(BaseException):
        task.result()


def _load_cwd(result: Any, fallback: Path) -> Path:
    extra = cast("dict[str, object]", result.model_extra or {})
    cwd = extra.get("cwd")
    if isinstance(cwd, str):
        return Path(cwd)
    worktree = extra.get("worktree")
    if isinstance(worktree, Mapping):
        typed_worktree = cast("Mapping[str, object]", worktree)
        path = typed_worktree.get("path")
        if isinstance(path, str):
            return Path(path)
    return fallback


def _document_source(document: Document) -> dict[str, Any]:
    source = document.source
    if isinstance(source, TextDocumentSource):
        return {
            "type": "text",
            "mediaType": "text/plain",
            "data": source.data,
            "name": source.name,
        }
    assert isinstance(source, PdfDocumentSource)
    return {
        "type": "base64",
        "mediaType": "application/pdf",
        "data": source.data,
        "parsedData": source.parsed_data,
        "name": source.name,
        "path": source.path,
    }


def _inner_notification(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    params = cast("object", raw.get("params"))
    if not isinstance(params, Mapping):
        return None
    inner = cast("Mapping[str, object]", params).get("notification")
    return cast("dict[str, Any]", inner) if isinstance(inner, dict) else None


def _header_mapping(values: list[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        header = cast("Mapping[str, object]", value)
        name = header.get("name")
        content = header.get("value")
        if isinstance(name, str) and isinstance(content, str):
            result[name] = content
    return result


def _tool_category(value: str | None) -> ToolCategory:
    try:
        return ToolCategory(value)
    except ValueError:
        return ToolCategory.OTHER


def _merge_settings(
    current: SessionSettings,
    update: Mapping[str, object],
) -> SessionSettings:
    def enum_value(
        key: str,
        enum: type[Enum],
        fallback: object,
        *,
        allow_none: bool = False,
    ) -> object:
        value = update.get(key, fallback)
        if value is fallback:
            return fallback
        if value is None and allow_none:
            return None
        try:
            return enum(value)
        except (TypeError, ValueError):
            return fallback

    tags: Sequence[SessionTag] = current.tags
    raw_tags = update.get("tags")
    if isinstance(raw_tags, list):
        parsed_tags: list[SessionTag] = []
        for raw_tag in cast("list[object]", raw_tags):
            if not isinstance(raw_tag, Mapping):
                continue
            tag = cast("Mapping[str, object]", raw_tag)
            name = tag.get("name")
            metadata = tag.get("metadata")
            if isinstance(name, str):
                parsed_tags.append(
                    SessionTag(
                        name=name,
                        metadata=(
                            cast("Mapping[str, str]", metadata)
                            if isinstance(metadata, Mapping)
                            else None
                        ),
                    )
                )
        tags = parsed_tags

    def tool_set(key: str, fallback: object) -> object:
        value = update.get(key, fallback)
        if isinstance(value, list) and all(
            isinstance(item, str) for item in cast("list[object]", value)
        ):
            return frozenset(cast("list[str]", value))
        return fallback

    model = update.get("modelId", current.model)
    spec_model = update.get("specModeModelId", current.spec_model)
    return SessionSettings(
        model=model if isinstance(model, str) else current.model,
        reasoning_effort=cast(
            "ReasoningEffort",
            enum_value(
                "reasoningEffort",
                ReasoningEffort,
                current.reasoning_effort,
            ),
        ),
        mode=cast(
            "Mode | None",
            enum_value(
                "interactionMode",
                Mode,
                current.mode,
                allow_none=True,
            ),
        ),
        autonomy=cast(
            "Autonomy | None",
            enum_value(
                "autonomyLevel",
                Autonomy,
                current.autonomy,
                allow_none=True,
            ),
        ),
        spec_model=(
            spec_model
            if isinstance(spec_model, str) or spec_model is None
            else current.spec_model
        ),
        spec_reasoning_effort=cast(
            "ReasoningEffort | None",
            enum_value(
                "specModeReasoningEffort",
                ReasoningEffort,
                current.spec_reasoning_effort,
                allow_none=True,
            ),
        ),
        tags=tags,
        sandbox=current.sandbox,
        additional_tools=cast(
            "set[str] | frozenset[str] | None",
            tool_set("additionalToolIds", current.additional_tools),
        ),
        enabled_tools=cast(
            "set[str] | frozenset[str] | None",
            tool_set("enabledToolIds", current.enabled_tools),
        ),
        disabled_tools=cast(
            "set[str] | frozenset[str] | None",
            tool_set("disabledToolIds", current.disabled_tools),
        ),
        restrict_tools=cast(
            "set[str] | frozenset[str] | None",
            tool_set("restrictToolIds", current.restrict_tools),
        ),
    )


def _mcp_summary(value: Any) -> McpStatusSummary:
    return McpStatusSummary(
        total=value.total,
        connected=value.connected,
        connecting=value.connecting,
        failed=value.failed,
        disabled=value.disabled,
        config_error=(
            None
            if value.config_error is None
            else McpConfigError(value.config_error.path, value.config_error.message)
        ),
    )


def _mcp_server(value: Any) -> McpServerStatusInfo:
    return McpServerStatusInfo(
        name=value.name,
        status=McpServerStatus(value.status.value),
        source=value.source.value,
        is_managed=value.is_managed,
        server_type=McpServerType(value.server_type.value),
        error=value.error,
        tool_count=value.tool_count,
        has_auth_tokens=value.has_auth_tokens,
        requires_auth=value.requires_auth,
        pending_auth_url=value.pending_auth_url,
        pending_auth_message=value.pending_auth_message,
        pending_auth_state=value.pending_auth_state,
    )


__all__ = ["Session", "run"]
