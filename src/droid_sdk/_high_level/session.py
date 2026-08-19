"""Lazy high-level session lifecycle and one-shot run helper."""

# ruff: noqa: TC001

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import uuid
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError
from typing_extensions import Self

from droid_sdk._high_level._client import (
    open_droid_client,
    resolve_working_directory,
)
from droid_sdk._high_level._convert import (
    document_to_wire,
    full_settings_from_wire,
    list_or_none,
    load_cwd,
    mcp_config_to_wire,
    merged_settings,
    raw_inner_notification,
    wire_reasoning,
    wire_source,
    wire_system_prompt,
    wire_tags,
)
from droid_sdk._high_level._immutable import JsonObject
from droid_sdk._high_level._session_operations import SessionOperationsMixin
from droid_sdk._high_level.attachments import Document, Image
from droid_sdk._high_level.config import (
    JsonSchema,
    SessionConfig,
    SessionSettings,
    SessionSource,
    SessionTag,
    freeze_tool_ids,
)
from droid_sdk._high_level.enums import (
    ReasoningEffort,
)
from droid_sdk._high_level.extensions import (
    McpServerConfig,
    SdkMcpServer,
)
from droid_sdk._high_level.interaction_adapter import InteractionDispatcher
from droid_sdk._high_level.interactions import InteractionHandlers
from droid_sdk._high_level.messages import (
    RunResult,
    StreamEvent,
    StreamMessage,
)
from droid_sdk._high_level.output import prepare_output_adapter
from droid_sdk._high_level.runtime import Runtime
from droid_sdk._high_level.streaming import RunStream
from droid_sdk._util import (
    cancel_and_drain,
    cancellation_checkpoint,
    consume_task_result,
    wait_shielded,
)
from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    SessionBusyError,
    SessionClosedError,
    SessionError,
    SessionNotOpenError,
    SessionReplacedError,
    SessionReplacementError,
)
from droid_sdk.observability import ObservabilityAdapter
from droid_sdk.schemas.cli import SettingsUpdatedNotification
from droid_sdk.schemas.client import AddUserMessageRequestParams
from droid_sdk.schemas.enums import (
    AutonomyLevel as WireAutonomy,
)
from droid_sdk.schemas.enums import (
    DroidInteractionMode,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence

ModelT = TypeVar("ModelT", bound=BaseModel)


class _State(Enum):
    LAZY = "lazy"
    OPENING = "opening"
    OPEN = "open"
    BUSY = "busy"
    REPLACING = "replacing"
    RETIRED = "retired"
    CLOSING = "closing"
    CLOSED = "closed"


class Session(SessionOperationsMixin):
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
        # Cancellation delivery point between successor attach and source
        # retirement; tests inject a gated coroutine to widen the window.
        self._replacement_checkpoint: Callable[[], Awaitable[None]] = (
            cancellation_checkpoint
        )
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
        disabled_tools: Iterable[str] | None = None,
        auto_reject_permission_requests: bool | None = None,
        disable_builtin_skills: bool | None = None,
        session_source: SessionSource | None = None,
    ) -> Session:
        disabled_tools = freeze_tool_ids("disabled_tools", disabled_tools)
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

    async def __aenter__(self) -> Self:
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
            await wait_shielded(task, self._cancel_open_waiter)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if not cancelled:
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
        await cancel_and_drain(task)
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
        requested_cwd = resolve_working_directory(self._requested_cwd)
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
                    configs.append(mcp_config_to_wire(config))
                else:
                    configs.append(mcp_config_to_wire(server))
            self._load_mcp_configs = configs

            runtime = self._runtime_config
            adapter = self._observability
            client = await open_droid_client(
                runtime,
                api_key=self._api_key,
                cwd=requested_cwd,
                observability=adapter,
            )
            client.set_permission_handler(self._dispatcher.handle_permission)
            client.set_ask_user_handler(self._dispatcher.handle_question)

            if self._resume_id is not None:
                session_start_attempted = True
                load_result = await client.load_session(
                    session_id=self._resume_id,
                    mcp_servers=configs or None,
                    disabled_tool_ids=list_or_none(
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
                    session_source=wire_source(
                        cast(
                            "SessionSource | None",
                            self._resume_options["session_source"],
                        )
                    ),
                )
                session_id = self._resume_id
                cwd_value = load_cwd(load_result, requested_cwd)
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
                    reasoning_effort=wire_reasoning(self._reasoning_effort),
                    system_prompt=wire_system_prompt(self._config.system_prompt),
                    spec_mode_model_id=self._config.spec_model,
                    spec_mode_reasoning_effort=wire_reasoning(
                        self._config.spec_reasoning_effort
                    ),
                    additional_tool_ids=list_or_none(self._config.additional_tools),
                    enabled_tool_ids=list_or_none(self._config.enabled_tools),
                    disabled_tool_ids=list_or_none(self._config.disabled_tools),
                    restrict_tool_ids=list_or_none(self._config.restrict_tools),
                    session_source=wire_source(self._config.session_source),
                    tags=cast("Any", wire_tags(tags)),
                    auto_reject_permission_requests=(
                        self._config.auto_reject_permission_requests
                    ),
                    disable_builtin_skills=self._config.disable_builtin_skills,
                )
                session_id = initialize_result.session_id
                cwd_value = requested_cwd
                wire_settings = initialize_result.settings
                if (
                    self._config.system_prompt is not None
                    and wire_settings.system_prompt is None
                ):
                    raise SessionError(
                        "The installed Droid version does not support custom "
                        "system prompts. Update Droid and try again."
                    )

            self._client = client
            self._id = session_id
            self._cwd = cwd_value
            self._settings = full_settings_from_wire(wire_settings)
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
                    "files": [document_to_wire(file) for file in files] or None,
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
                task.add_done_callback(consume_task_result)
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

    def on_notification(
        self,
        callback: Callable[[Mapping[str, object]], None],
        *,
        type: str | None = None,
    ) -> Callable[[], None]:
        self._ensure_active()

        def dispatch(raw: dict[str, Any]) -> None:
            inner = raw_inner_notification(raw)
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
        return await wait_shielded(task, self._abandon_cancelled_replacement)

    async def _abandon_cancelled_replacement(
        self,
        task: asyncio.Task[tuple[Any, Session]],
    ) -> None:
        await cancel_and_drain(task)
        if not task.cancelled():
            with contextlib.suppress(BaseException):
                _, successor = task.result()
                await self._restore_after_cancelled_replacement(successor)

    async def _replacement_impl(
        self,
        operation: Callable[[], Any],
    ) -> tuple[Any, Session]:
        successor: Session | None = None
        try:
            result = await operation()
            successor = await self._attach_replacement(result.new_session_id)
            self._replacement_successor = successor
            await self._replacement_checkpoint()
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
            self._settings = full_settings_from_wire(restored.settings)
            self._cwd = load_cwd(restored, self._cwd or Path.cwd())
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
                self._settings = full_settings_from_wire(restored.settings)
                self._cwd = load_cwd(restored, self._cwd or Path.cwd())
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
        return self._create_successor(replacement_id, loaded)

    def _create_successor(self, replacement_id: str, loaded: Any) -> Session:
        """Build the open session that takes over this session's connection."""
        successor = Session(
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            config=self._config,
            interactions=self._interactions,
            runtime=self._runtime_config,
            api_key=self._api_key,
        )
        successor._requested_cwd = self._requested_cwd
        successor._resume_id = self._resume_id
        successor._resume_options = self._resume_options
        successor._load_options = self._load_options
        successor._load_mcp_configs = self._load_mcp_configs
        # The successor adopts the live wiring: the same client, the
        # dispatcher whose handlers that client dispatches to, and the
        # in-process MCP servers.
        successor._dispatcher = self._dispatcher
        successor._client = self._client
        successor._sdk_servers = self._sdk_servers
        successor._id = replacement_id
        successor._settings = full_settings_from_wire(loaded.settings)
        successor._cwd = load_cwd(loaded, self._cwd or Path.cwd())
        successor._state = _State.OPEN
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
            additional_tool_ids=list_or_none(self._load_options["additional_tools"]),
            enabled_tool_ids=list_or_none(self._load_options["enabled_tools"]),
            disabled_tool_ids=list_or_none(self._load_options["disabled_tools"]),
            auto_reject_permission_requests=cast(
                "bool | None",
                self._load_options["auto_reject_permission_requests"],
            ),
            disable_builtin_skills=cast(
                "bool | None",
                self._load_options["disable_builtin_skills"],
            ),
            session_source=wire_source(
                cast("SessionSource | None", self._load_options["session_source"])
            ),
        )
        restrict_tools = list_or_none(self._load_options["restrict_tools"])
        if restrict_tools is not None:
            await client.update_session_settings(
                restrict_tool_ids=restrict_tools,
            )
        return loaded

    def _bind_metadata(self) -> None:
        client = self._require_client()

        def update(raw: dict[str, Any]) -> None:
            inner = raw_inner_notification(raw)
            if inner is None:
                return
            if inner.get("type") == "settings_updated":
                if self._settings is None:
                    return
                try:
                    notification = SettingsUpdatedNotification.model_validate(inner)
                except ValidationError:
                    return
                self._settings = merged_settings(
                    self._settings,
                    notification.settings,
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


__all__ = ["Session", "run"]
