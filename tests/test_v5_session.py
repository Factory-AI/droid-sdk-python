from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

import droid_sdk._high_level.session as session_module
from droid_sdk import (
    Document,
    DroidConnectionError,
    ErrorEvent,
    ErrorType,
    HttpHeader,
    HttpMcpServerConfig,
    InteractionHandlers,
    McpOAuthOptions,
    Mode,
    ReasoningEffort,
    Runtime,
    RunTimeoutError,
    Session,
    SessionBusyError,
    SessionClosedError,
    SessionConfig,
    SessionNotOpenError,
    SessionReplacedError,
    SessionReplacementError,
    TextDocumentSource,
)
from droid_sdk._util import cancellation_checkpoint
from droid_sdk.errors import SessionError
from droid_sdk.mcp import create_sdk_mcp_server
from droid_sdk.observability import LogEvent, MetricEvent, Observability
from droid_sdk.schemas.client import SessionSettings as WireSessionSettings
from droid_sdk.schemas.enums import (
    ReasoningEffort as WireReasoningEffort,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from droid_sdk.types import DroidClientTransport


def wire_settings(system_prompt: object = None) -> WireSessionSettings:
    return WireSessionSettings(
        model_id="model",
        reasoning_effort=WireReasoningEffort.Medium,
        spec_mode_model_id="spec-model",
        spec_mode_reasoning_effort=WireReasoningEffort.High,
        system_prompt=system_prompt,
        tags=[],
    )


class FakeTransport:
    is_connected = True


class FakeClient:
    instances: ClassVar[list[FakeClient]] = []
    fail_connect: ClassVar[bool] = False
    fail_replacement_load: ClassVar[bool] = False
    fail_fork: ClassVar[bool] = False
    connect_entered: ClassVar[asyncio.Event | None] = None
    connect_gate: ClassVar[asyncio.Event | None] = None
    initialize_entered: ClassVar[asyncio.Event | None] = None
    initialize_gate: ClassVar[asyncio.Event | None] = None
    remote_session_created: ClassVar[asyncio.Event | None] = None
    remote_session_gate: ClassVar[asyncio.Event | None] = None
    replacement_gate: ClassVar[asyncio.Event | None] = None
    replacement_entered: ClassVar[asyncio.Event | None] = None
    send_gate: ClassVar[asyncio.Event | None] = None
    close_entered: ClassVar[asyncio.Event | None] = None
    close_gate: ClassVar[asyncio.Event | None] = None
    close_session_error: ClassVar[Exception | None] = None
    fail_send: ClassVar[bool] = False
    hang_interrupt: ClassVar[bool] = False
    supports_system_prompt: ClassVar[bool] = True
    load_system_prompt: ClassVar[object] = None

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.initialize_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.load_calls: list[dict[str, Any]] = []
        self.message_calls: list[dict[str, Any]] = []
        self.mcp_calls: list[dict[str, Any]] = []
        self.callbacks: list[Callable[[dict[str, Any]], None]] = []
        self.error_callbacks: list[Callable[[Exception], None]] = []
        self.permission_handler: Callable[..., Any] | None = None
        self.ask_user_handler: Callable[..., Any] | None = None
        self.interrupt_calls = 0
        self.close_calls = 0
        self.close_session_calls = 0
        type(self).instances.append(self)

    async def connect(self) -> None:
        if self.connect_entered is not None:
            self.connect_entered.set()
        if self.connect_gate is not None:
            await self.connect_gate.wait()
        if self.fail_connect:
            raise FileNotFoundError("missing")

    async def initialize_session(self, **kwargs: Any) -> SimpleNamespace:
        self.initialize_calls.append(kwargs)
        if self.initialize_entered is not None:
            self.initialize_entered.set()
        if self.initialize_gate is not None:
            await self.initialize_gate.wait()
        if self.remote_session_created is not None:
            self.remote_session_created.set()
        if self.remote_session_gate is not None:
            await self.remote_session_gate.wait()
        return SimpleNamespace(
            session_id="session-1",
            settings=wire_settings(
                kwargs.get("system_prompt") if self.supports_system_prompt else None
            ),
        )

    async def update_session_settings(self, **kwargs: Any) -> None:
        self.update_calls.append(kwargs)

    def set_permission_handler(self, handler: Callable[..., Any]) -> None:
        self.permission_handler = handler

    def set_ask_user_handler(self, handler: Callable[..., Any]) -> None:
        self.ask_user_handler = handler

    def on_error(
        self,
        callback: Callable[[Exception], None],
    ) -> Callable[[], None]:
        self.error_callbacks.append(callback)

        def unsubscribe() -> None:
            self.error_callbacks.remove(callback)

        return unsubscribe

    async def add_user_message(self, **kwargs: Any) -> None:
        self.message_calls.append(kwargs)
        if self.fail_send:
            raise RuntimeError("send failed")
        if self.send_gate is not None:
            await self.send_gate.wait()

    async def interrupt_session(self) -> None:
        self.interrupt_calls += 1
        if self.hang_interrupt:
            await asyncio.Event().wait()

    async def rename_session(self, *, title: str) -> None:
        assert title

    async def add_mcp_server(self, **kwargs: Any) -> SimpleNamespace:
        self.mcp_calls.append(kwargs)
        return SimpleNamespace(success=True)

    async def fork_session(self, **kwargs: Any) -> SimpleNamespace:
        return await self._replacement_result()

    async def compact_session(self, **kwargs: Any) -> SimpleNamespace:
        result = await self._replacement_result()
        result.removed_count = 3
        return result

    async def execute_rewind(self, **kwargs: Any) -> SimpleNamespace:
        result = await self._replacement_result()
        result.restored_count = 1
        result.deleted_count = 2
        result.failed_restore_count = 0
        result.failed_delete_count = 0
        return result

    async def _replacement_result(self) -> SimpleNamespace:
        if self.replacement_entered is not None:
            self.replacement_entered.set()
        if self.replacement_gate is not None:
            await self.replacement_gate.wait()
        if self.fail_fork:
            raise RuntimeError("fork failed")
        return SimpleNamespace(new_session_id="session-2")

    async def load_session(self, **kwargs: Any) -> SimpleNamespace:
        self.load_calls.append(kwargs)
        if self.fail_replacement_load and kwargs["session_id"] == "session-2":
            raise RuntimeError("replacement unavailable")
        return SimpleNamespace(
            settings=wire_settings(self.load_system_prompt),
            model_extra={},
        )

    def on_notification(
        self,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        self.callbacks.append(callback)

        def unsubscribe() -> None:
            self.callbacks.remove(callback)

        return unsubscribe

    async def close_session(self, *, reason: str) -> None:
        assert reason == "other"
        self.close_session_calls += 1
        if self.close_session_error is not None:
            raise self.close_session_error

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_entered is not None:
            self.close_entered.set()
        if self.close_gate is not None:
            await self.close_gate.wait()


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances.clear()
    FakeClient.fail_connect = False
    FakeClient.fail_replacement_load = False
    FakeClient.fail_fork = False
    FakeClient.connect_entered = None
    FakeClient.connect_gate = None
    FakeClient.initialize_entered = None
    FakeClient.initialize_gate = None
    FakeClient.remote_session_created = None
    FakeClient.remote_session_gate = None
    FakeClient.replacement_gate = None
    FakeClient.replacement_entered = None
    FakeClient.send_gate = None
    FakeClient.close_entered = None
    FakeClient.close_gate = None
    FakeClient.close_session_error = None
    FakeClient.fail_send = False
    FakeClient.hang_interrupt = False
    FakeClient.supports_system_prompt = True
    FakeClient.load_system_prompt = None
    monkeypatch.setattr(session_module, "DroidClient", FakeClient)


def runtime() -> Runtime:
    return Runtime(transport=cast("DroidClientTransport", FakeTransport()))


class ObservabilitySink:
    def __init__(self) -> None:
        self.logs: list[LogEvent] = []
        self.metrics: list[MetricEvent] = []

    def log(self, event: LogEvent) -> None:
        self.logs.append(event)

    def record(self, event: MetricEvent) -> None:
        self.metrics.append(event)


@pytest.mark.asyncio
async def test_session_is_lazy_and_context_manager_owns_cleanup() -> None:
    session = Session(runtime=runtime())
    with pytest.raises(SessionNotOpenError):
        _ = session.id

    async with session:
        assert session.id == "session-1"
        assert session.settings.model == "model"
        await session.open()

    client = FakeClient.instances[0]
    assert len(client.initialize_calls) == 1
    assert client.close_session_calls == 1
    assert client.close_calls == 1
    with pytest.raises(SessionClosedError):
        await session.rename("closed")


@pytest.mark.asyncio
async def test_session_creates_with_custom_system_prompt() -> None:
    preset = {
        "type": "preset",
        "preset": "droid",
        "append": "Prioritize security findings.",
    }
    session = Session(
        config=SessionConfig(system_prompt=preset),
        runtime=runtime(),
    )

    await session.open()

    client = FakeClient.instances[0]
    wire_prompt = client.initialize_calls[0]["system_prompt"]
    assert wire_prompt.model_dump() == preset
    assert session.settings.system_prompt == preset
    await session.close()


@pytest.mark.asyncio
async def test_session_rejects_droid_without_custom_system_prompt_support() -> None:
    FakeClient.supports_system_prompt = False
    session = Session(
        config=SessionConfig(system_prompt="Required behavioral constraint."),
        runtime=runtime(),
    )

    with pytest.raises(SessionError, match="does not support custom system prompts"):
        await session.open()

    client = FakeClient.instances[0]
    assert client.close_session_calls == 1
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_resume_restores_but_does_not_resend_system_prompt() -> None:
    FakeClient.load_system_prompt = "Persisted replacement prompt."
    session = Session.resume("session-1", runtime=runtime())

    await session.open()

    client = FakeClient.instances[0]
    assert "system_prompt" not in client.load_calls[0]
    assert session.settings.system_prompt == "Persisted replacement prompt."
    await session.close()


@pytest.mark.asyncio
async def test_session_updates_and_merges_settings_notifications() -> None:
    session = Session(runtime=runtime())
    await session.open()
    client = FakeClient.instances[0]

    await session.update_settings(
        mode=Mode.SPEC,
        spec_model=None,
        spec_reasoning_effort=None,
    )

    update = client.update_calls[-1]
    assert update["explicit_null_fields"] == [
        "specModeModelId",
        "specModeReasoningEffort",
    ]
    assert session.settings.spec_model is None
    assert session.settings.spec_reasoning_effort is None

    client.callbacks[0](
        {
            "params": {
                "notification": {
                    "type": "settings_updated",
                    "settings": {
                        "modelId": "new-model",
                        "reasoningEffort": "high",
                    },
                }
            }
        }
    )
    assert session.settings.model == "new-model"
    assert session.settings.reasoning_effort is ReasoningEffort.HIGH
    await session.close()


@pytest.mark.asyncio
async def test_update_settings_accepts_iterables_and_rejects_strings() -> None:
    session = Session(runtime=runtime())
    await session.open()
    client = FakeClient.instances[0]

    await session.update_settings(disabled_tools=["Execute", "Edit"])
    assert client.update_calls[-1]["disabled_tool_ids"] == ["Edit", "Execute"]
    assert session.settings.disabled_tools == frozenset({"Execute", "Edit"})

    calls_before = len(client.update_calls)
    with pytest.raises(TypeError, match="disabled_tools"):
        await session.update_settings(disabled_tools="Execute")
    assert len(client.update_calls) == calls_before
    await session.close()


@pytest.mark.asyncio
async def test_session_maps_missing_executable_and_cleans_up() -> None:
    FakeClient.fail_connect = True
    session = Session(runtime=runtime())

    with pytest.raises(DroidConnectionError, match="executable was not found"):
        await session.open()

    assert FakeClient.instances[0].close_calls == 1


@pytest.mark.asyncio
async def test_concurrent_open_and_close_share_lifecycle_tasks() -> None:
    FakeClient.connect_entered = asyncio.Event()
    FakeClient.connect_gate = asyncio.Event()
    session = Session(runtime=runtime())

    first_open = asyncio.create_task(session.open())
    await FakeClient.connect_entered.wait()
    second_open = asyncio.create_task(session.open())
    close = asyncio.create_task(session.close())
    first_open.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_open

    assert len(FakeClient.instances) == 1
    assert not second_open.done()
    assert not close.done()
    FakeClient.connect_gate.set()
    await second_open
    await close

    client = FakeClient.instances[0]
    assert len(client.initialize_calls) == 1
    assert client.close_session_calls == 1
    assert client.close_calls == 1
    with pytest.raises(SessionClosedError):
        await session.open()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "expects_close_session"),
    [
        ("connect", False),
        ("initialize", True),
        ("remote-created", True),
    ],
)
async def test_final_cancelled_open_cleans_resources_and_is_retryable(
    stage: str,
    expects_close_session: bool,
) -> None:
    entered = asyncio.Event()
    gate = asyncio.Event()
    if stage == "connect":
        FakeClient.connect_entered = entered
        FakeClient.connect_gate = gate
    elif stage == "initialize":
        FakeClient.initialize_entered = entered
        FakeClient.initialize_gate = gate
    else:
        FakeClient.remote_session_created = entered
        FakeClient.remote_session_gate = gate

    session = Session(runtime=runtime())
    opening = asyncio.create_task(session.open())
    await entered.wait()
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening

    client = FakeClient.instances[0]
    assert client.close_calls == 1
    assert client.close_session_calls == int(expects_close_session)
    assert session._state is session_module._State.LAZY

    FakeClient.connect_gate = None
    FakeClient.initialize_gate = None
    FakeClient.remote_session_gate = None
    await session.open()
    await session.close()


@pytest.mark.asyncio
async def test_cancelled_open_before_client_construction_closes_sdk_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = create_sdk_mcp_server("gated", [])
    entered = asyncio.Event()
    gate = asyncio.Event()
    close_calls = 0

    async def gated_start(_server: object) -> HttpMcpServerConfig:
        entered.set()
        await gate.wait()
        return HttpMcpServerConfig(name="gated", url="http://127.0.0.1:1/mcp")

    async def tracked_close(_server: object) -> None:
        nonlocal close_calls
        close_calls += 1

    monkeypatch.setattr(type(server), "start", gated_start)
    monkeypatch.setattr(type(server), "close", tracked_close)
    session = Session(
        runtime=runtime(),
        config=SessionConfig(mcp_servers=[server]),
    )
    opening = asyncio.create_task(session.open())
    await entered.wait()
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening

    assert FakeClient.instances == []
    assert close_calls == 1
    assert session._state is session_module._State.LAZY
    gate.set()
    await session.open()
    await session.close()
    assert len(FakeClient.instances) == 1


@pytest.mark.asyncio
async def test_final_cancelled_open_after_assignment_closes_and_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    gate = asyncio.Event()
    original = Session._open_impl

    async def gated_open(session: Session) -> None:
        await original(session)
        entered.set()
        await gate.wait()

    monkeypatch.setattr(Session, "_open_impl", gated_open)
    session = Session(runtime=runtime())
    opening = asyncio.create_task(session.open())
    await entered.wait()
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening

    client = FakeClient.instances[0]
    assert client.close_session_calls == 1
    assert client.close_calls == 1
    assert session._state is session_module._State.LAZY


@pytest.mark.asyncio
async def test_repeated_open_cancellation_cannot_abort_startup_cleanup() -> None:
    FakeClient.connect_entered = asyncio.Event()
    FakeClient.connect_gate = asyncio.Event()
    FakeClient.close_entered = asyncio.Event()
    FakeClient.close_gate = asyncio.Event()
    session = Session(runtime=runtime())
    opening = asyncio.create_task(session.open())
    await FakeClient.connect_entered.wait()

    opening.cancel()
    await FakeClient.close_entered.wait()
    cleanup = session._open_cleanup_task
    assert cleanup is not None
    assert not cleanup.done()

    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening
    assert not cleanup.done()
    assert session._state is not session_module._State.LAZY

    FakeClient.close_gate.set()
    await cleanup
    client = FakeClient.instances[0]
    assert client.close_calls == 1
    assert session._state is session_module._State.LAZY

    FakeClient.connect_gate = None
    FakeClient.close_gate = None
    await session.open()
    await session.close()


@pytest.mark.asyncio
async def test_cancelled_open_racing_close_finishes_closed() -> None:
    FakeClient.connect_entered = asyncio.Event()
    FakeClient.connect_gate = asyncio.Event()
    session = Session(runtime=runtime())
    opening = asyncio.create_task(session.open())
    await FakeClient.connect_entered.wait()
    closing = asyncio.create_task(session.close())
    opening.cancel()

    with pytest.raises(asyncio.CancelledError):
        await opening
    await closing
    client = FakeClient.instances[0]
    assert client.close_calls == 1
    assert session._state is session_module._State.CLOSED
    with pytest.raises(SessionClosedError):
        await session.open()


@pytest.mark.asyncio
async def test_cancelled_and_repeated_close_awaits_one_cleanup() -> None:
    session = Session(runtime=runtime())
    await session.open()
    FakeClient.close_entered = asyncio.Event()
    FakeClient.close_gate = asyncio.Event()

    first_close = asyncio.create_task(session.close())
    await FakeClient.close_entered.wait()
    first_close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_close

    second_close = asyncio.create_task(session.close())
    third_close = asyncio.create_task(session.close())
    assert not second_close.done()
    assert not third_close.done()
    FakeClient.close_gate.set()
    await asyncio.gather(second_close, third_close)

    client = FakeClient.instances[0]
    assert client.close_session_calls == 1
    assert client.close_calls == 1
    await session.close()


@pytest.mark.asyncio
async def test_close_failure_runs_remaining_cleanup_and_is_sticky() -> None:
    failure = RuntimeError("close session failed")
    FakeClient.close_session_error = failure
    session = Session(runtime=runtime())
    await session.open()

    with pytest.raises(RuntimeError, match="close session failed") as first:
        await session.close()
    with pytest.raises(RuntimeError, match="close session failed") as second:
        await session.close()

    client = FakeClient.instances[0]
    assert first.value is failure
    assert second.value is failure
    assert client.close_session_calls == 1
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_stream_serializes_text_and_pdf_through_wire_models() -> None:
    session = Session(runtime=runtime())
    await session.open()
    text = Document(
        TextDocumentSource(
            "notes",
            name="notes.txt",
            mime="application/x-high-level-only",
        )
    )
    pdf = Document.from_bytes(b"%PDF-1.7\n%%EOF\n", name="report.pdf")

    stream = session.stream("review", files=(text, pdf))
    async with stream:
        sent = FakeClient.instances[0].message_calls[-1]["files"]
        wire = [item.model_dump(by_alias=True, exclude_none=True) for item in sent]
        assert wire[0] == {
            "type": "text",
            "mediaType": "text/plain",
            "data": "notes",
            "name": "notes.txt",
            "mime": "application/x-high-level-only",
        }
        assert wire[1]["mediaType"] == "application/pdf"
    await session.close()


@pytest.mark.asyncio
async def test_active_turn_allows_non_turn_operations() -> None:
    session = Session(runtime=runtime())
    await session.open()
    stream = session.stream("waiting")

    await session.update_settings(model="other")
    await session.rename("renamed")
    unsubscribe = session.on_notification(lambda _event: None)
    unsubscribe()
    with pytest.raises(SessionBusyError):
        session.stream("second")
    with pytest.raises(SessionBusyError):
        await session.fork()

    await stream.aclose()
    await session.close()


@pytest.mark.asyncio
async def test_early_break_releases_turn_and_emits_safe_terminal_observability() -> (
    None
):
    sink = ObservabilitySink()
    observed_runtime = Runtime(
        transport=cast("DroidClientTransport", FakeTransport()),
        observability=Observability(logger=sink, metrics=sink),
    )
    session = Session(runtime=observed_runtime)
    await session.open()
    stream = session.stream("private prompt")

    async with stream:
        stream.queue_error_event(ErrorEvent("safe", ErrorType.PROTOCOL_ERROR))
        async for _event in stream:
            break

    assert session._active_stream is None
    terminal_logs = [
        event for event in sink.logs if event.name == "droid.sdk.run.terminal"
    ]
    terminal_metrics = [
        event for event in sink.metrics if event.name == "droid.sdk.run.terminal"
    ]
    assert len(terminal_logs) == 1
    assert terminal_logs[0].attributes == {
        "session_id": "session-1",
        "status": "interrupted",
    }
    assert "private prompt" not in repr(sink.logs)
    assert len(terminal_metrics) == 1
    await session.close()


@pytest.mark.asyncio
async def test_replacement_race_rejects_work_and_close_owns_successor() -> None:
    gate = asyncio.Event()
    FakeClient.replacement_gate = gate
    FakeClient.replacement_entered = asyncio.Event()
    session = Session(runtime=runtime())
    await session.open()

    replacement = asyncio.create_task(session.fork())
    await FakeClient.replacement_entered.wait()
    with pytest.raises(SessionBusyError):
        session.stream("blocked")
    with pytest.raises(SessionBusyError):
        await session.fork()
    with pytest.raises(SessionBusyError):
        await session.open()
    close = asyncio.create_task(session.close())
    assert not close.done()

    gate.set()
    successor = await replacement
    await close
    with pytest.raises(SessionClosedError):
        await successor.rename("closed")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["fork", "compact", "rewind"])
async def test_close_on_already_retired_source_does_not_close_successor(
    operation: str,
) -> None:
    session = Session(runtime=runtime())
    await session.open()
    if operation == "fork":
        successor = await session.fork()
    elif operation == "compact":
        successor = (await session.compact()).session
    else:
        successor = (await session.rewind("message", title="rewound")).session
    client = FakeClient.instances[0]

    await session.close()
    assert client.close_session_calls == 0
    assert client.close_calls == 0
    await successor.rename("still open")

    await successor.close()
    assert client.close_session_calls == 1
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_close_intent_survives_lock_race_with_replacement_completion() -> None:
    FakeClient.replacement_gate = asyncio.Event()
    FakeClient.replacement_entered = asyncio.Event()
    session = Session(runtime=runtime())
    await session.open()
    replacement = asyncio.create_task(session.fork())
    await FakeClient.replacement_entered.wait()

    await session._lifecycle_lock.acquire()
    try:
        closing = asyncio.create_task(session.close())
        while not session._replacement_close_requested:
            await asyncio.sleep(0)
        FakeClient.replacement_gate.set()
        successor = await replacement
    finally:
        session._lifecycle_lock.release()

    await closing
    with pytest.raises(SessionClosedError):
        await successor.rename("closed")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["fork", "compact", "rewind"])
async def test_cancelled_replacement_rpc_restores_open_source(operation: str) -> None:
    FakeClient.replacement_entered = asyncio.Event()
    FakeClient.replacement_gate = asyncio.Event()
    session = Session(runtime=runtime())
    await session.open()

    if operation == "fork":
        replacement = asyncio.create_task(session.fork())
    elif operation == "compact":
        replacement = asyncio.create_task(session.compact())
    else:
        replacement = asyncio.create_task(session.rewind("message", title="rewound"))
    await FakeClient.replacement_entered.wait()
    replacement.cancel()
    with pytest.raises(asyncio.CancelledError):
        await replacement

    client = FakeClient.instances[0]
    assert client.load_calls == []
    await session.rename("still open")
    await session.close()
    assert client.close_session_calls == 1
    assert client.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["fork", "compact", "rewind"])
async def test_cancelled_replacement_after_successor_creation_restores_source(
    operation: str,
) -> None:
    config = SessionConfig(
        additional_tools={"Custom"},
        enabled_tools={"Read"},
        disabled_tools={"Execute"},
        restrict_tools={"Read"},
        auto_reject_permission_requests=True,
        disable_builtin_skills=True,
    )
    session = Session(config=config, runtime=runtime())
    await session.open()
    entered = asyncio.Event()
    gate = asyncio.Event()

    async def gated_handoff() -> None:
        entered.set()
        await gate.wait()

    session._replacement_checkpoint = gated_handoff
    if operation == "fork":
        replacement = asyncio.create_task(session.fork())
    elif operation == "compact":
        replacement = asyncio.create_task(session.compact())
    else:
        replacement = asyncio.create_task(session.rewind("message", title="rewound"))
    await entered.wait()
    replacement.cancel()
    with pytest.raises(asyncio.CancelledError):
        await replacement

    client = FakeClient.instances[0]
    assert [call["session_id"] for call in client.load_calls] == [
        "session-2",
        "session-1",
    ]
    restored = client.load_calls[-1]
    assert restored["additional_tool_ids"] == ["Custom"]
    assert restored["enabled_tool_ids"] == ["Read"]
    assert restored["disabled_tool_ids"] == ["Execute"]
    assert restored["auto_reject_permission_requests"] is True
    assert restored["disable_builtin_skills"] is True
    assert client.update_calls[-1]["restrict_tool_ids"] == ["Read"]
    await session.rename("restored")
    await session.close()
    assert client.close_session_calls == 1
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_cancelled_replacement_racing_close_cleans_successor() -> None:
    session = Session(runtime=runtime())
    await session.open()
    entered = asyncio.Event()
    gate = asyncio.Event()

    async def gated_handoff() -> None:
        entered.set()
        await gate.wait()
        await cancellation_checkpoint()

    session._replacement_checkpoint = gated_handoff
    replacement = asyncio.create_task(session.fork())
    await entered.wait()
    closing = asyncio.create_task(session.close())
    while not session._replacement_close_requested:
        await asyncio.sleep(0)
    replacement.cancel()
    with pytest.raises(asyncio.CancelledError):
        await replacement
    await closing

    client = FakeClient.instances[0]
    assert client.close_session_calls == 1
    assert client.close_calls == 1
    assert session._state is session_module._State.CLOSED


@pytest.mark.asyncio
async def test_replacement_reattaches_policies_and_rolls_back() -> None:
    config = SessionConfig(
        additional_tools={"Custom"},
        enabled_tools={"Read"},
        disabled_tools={"Execute"},
        restrict_tools={"Read"},
        auto_reject_permission_requests=True,
        disable_builtin_skills=True,
    )
    session = Session(config=config, runtime=runtime())
    await session.open()
    FakeClient.fail_replacement_load = True

    with pytest.raises(SessionReplacementError):
        await session.fork()

    client = FakeClient.instances[0]
    assert [call["session_id"] for call in client.load_calls] == [
        "session-2",
        "session-1",
    ]
    for call in client.load_calls:
        assert call["additional_tool_ids"] == ["Custom"]
        assert call["enabled_tool_ids"] == ["Read"]
        assert call["disabled_tool_ids"] == ["Execute"]
        assert call["auto_reject_permission_requests"] is True
        assert call["disable_builtin_skills"] is True
    assert client.update_calls[-1]["restrict_tool_ids"] == ["Read"]
    await session.rename("restored")
    await session.close()


@pytest.mark.asyncio
async def test_replacement_success_reattaches_policies() -> None:
    config = SessionConfig(
        additional_tools={"Custom"},
        enabled_tools={"Read"},
        disabled_tools={"Execute"},
        restrict_tools={"Read"},
        auto_reject_permission_requests=True,
        disable_builtin_skills=True,
    )
    session = Session(config=config, runtime=runtime())
    await session.open()

    successor = await session.fork()
    client = FakeClient.instances[0]
    load = client.load_calls[-1]
    assert load["additional_tool_ids"] == ["Custom"]
    assert load["enabled_tool_ids"] == ["Read"]
    assert load["disabled_tool_ids"] == ["Execute"]
    assert load["auto_reject_permission_requests"] is True
    assert load["disable_builtin_skills"] is True
    assert client.update_calls[-1]["restrict_tool_ids"] == ["Read"]
    with pytest.raises(SessionReplacedError):
        await session.rename("retired")
    await successor.close()


@pytest.mark.asyncio
async def test_replacement_rpc_failure_restores_open_state() -> None:
    session = Session(runtime=runtime())
    await session.open()
    FakeClient.fail_fork = True

    with pytest.raises(RuntimeError, match="fork failed"):
        await session.fork()
    await session.rename("still open")
    await session.close()


@pytest.mark.asyncio
async def test_timeout_and_cancellation_ignore_hanging_interrupt() -> None:
    FakeClient.send_gate = asyncio.Event()
    FakeClient.hang_interrupt = True
    session = Session(runtime=runtime())
    await session.open()
    stream = session.stream("slow start", timeout=0.01)

    started = time.monotonic()
    with pytest.raises(RunTimeoutError):
        async with stream:
            pass
    assert time.monotonic() - started < 0.25
    assert session._active_stream is None

    FakeClient.send_gate = None
    waiting = session.stream("wait forever")
    await waiting.__aenter__()
    next_event = asyncio.create_task(anext(waiting.__aiter__()))
    await asyncio.sleep(0)
    next_event.cancel()
    started = time.monotonic()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(next_event, timeout=0.25)
    assert time.monotonic() - started < 0.25
    assert session._active_stream is None
    await session.close()


@pytest.mark.asyncio
async def test_stream_start_failure_releases_subscriptions_and_turn() -> None:
    FakeClient.fail_send = True
    session = Session(runtime=runtime())
    await session.open()
    stream = session.stream("fails")

    with pytest.raises(RuntimeError, match="send failed"):
        async with stream:
            pass

    client = FakeClient.instances[0]
    assert session._active_stream is None
    assert client.error_callbacks == []
    await session.close()


def permission_params() -> dict[str, object]:
    return {
        "toolUses": [
            {
                "toolUse": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Create",
                    "input": {},
                },
                "confirmationType": "create",
                "details": {
                    "type": "create",
                    "filePath": "/repo/a.py",
                    "fileName": "a.py",
                    "content": "private",
                },
            }
        ],
        "options": [{"label": "Proceed", "value": "proceed_once"}],
        "associatedSessionIds": [],
    }


@pytest.mark.asyncio
async def test_interaction_failures_are_sanitized_stream_events() -> None:
    def throwing(_request: object) -> object:
        raise RuntimeError("private handler details")

    session = Session(
        interactions=InteractionHandlers(on_permission=cast("Any", throwing)),
        runtime=runtime(),
    )
    await session.open()
    stream = session.stream("interact")
    await stream.__aenter__()
    handle_permission = FakeClient.instances[0].permission_handler
    assert handle_permission is not None
    assert await handle_permission(permission_params()) == {"selectedOption": "cancel"}

    event = await anext(stream.__aiter__())
    assert isinstance(event, ErrorEvent)
    assert event.message == "Permission interaction handler failed"
    assert "private" not in event.message
    await stream.aclose()
    await session.close()


@pytest.mark.asyncio
async def test_mcp_configs_are_canonically_validated_and_serialized() -> None:
    secret = "do-not-expose"
    invalid = Session(
        config=SessionConfig(
            mcp_servers=(
                HttpMcpServerConfig(
                    name="bad",
                    url="relative",
                    oauth=McpOAuthOptions(client_secret=secret),
                ),
            )
        ),
        runtime=runtime(),
    )
    with pytest.raises(ValueError) as raised:
        await invalid.open()
    assert secret not in str(raised.value)
    assert secret not in repr(raised.value)

    config = HttpMcpServerConfig(
        name="valid",
        url="https://example.com/mcp",
        headers=(HttpHeader("Authorization", "Bearer private"),),
        oauth=McpOAuthOptions(
            scopes=("read",),
            authorization_server_issuer="https://auth.example.com",
            client_id="client",
            client_secret="secret",
        ),
    )
    session = Session(
        config=SessionConfig(mcp_servers=(config,)),
        runtime=runtime(),
    )
    await session.open()
    sent = FakeClient.instances[-1].initialize_calls[0]["mcp_servers"][0]
    assert sent["type"] == "http"
    assert sent["oauth"]["authorizationServerIssuer"] == ("https://auth.example.com")
    await session.add_mcp_server(config)
    assert FakeClient.instances[-1].mcp_calls[-1]["url"] == ("https://example.com/mcp")
    await session.close()
