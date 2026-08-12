"""Tests for DroidQueryOptions dataclass and query() async generator.

Covers: DroidQueryOptions defaults/construction, query() lifecycle
(connect → init → message → yield → close), options merging, kwargs
overrides, proper cleanup on exception, and cleanup after normal
iteration.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any
from unittest.mock import patch

import pytest

import droid_sdk.query  # noqa: F401 — ensure module is loaded
from droid_sdk.schemas.enums import (
    AutonomyLevel,
    DroidInteractionMode,
    ReasoningEffort,
    SessionNotificationType,
)
from droid_sdk.stream import (
    AssistantTextDelta,
    StreamMessage,
    TurnComplete,
)
from tests.helpers import InMemoryTransport, make_notification, make_success_response

# The __init__.py exports a function named 'query' which shadows the module.
# Use sys.modules to get the actual module object for patch.object().
_query_module = sys.modules["droid_sdk.query"]

# Keep strong references to background tasks so they aren't garbage-collected.
_background_tasks: set[asyncio.Task[None]] = set()


def _fire_task(coro: Any) -> None:
    """Schedule *coro* as a background task with a prevent-GC reference."""
    task: asyncio.Task[None] = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Number of event-loop yields to allow receive_response() to subscribe
# its notification listener after add_user_message completes.
_SUBSCRIBE_DELAY_YIELDS = 10


def _make_session_notification(
    notification_type: SessionNotificationType,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-RPC session notification dict."""
    return make_notification(
        method="droid.session_notification",
        params={
            "notification": {"type": notification_type.value, **payload},
        },
    )


def _make_init_response(request_id: str) -> dict[str, Any]:
    """Build a minimal initialize_session success response."""
    return make_success_response(
        request_id=request_id,
        result={
            "sessionId": "test-session",
            "session": {"id": "test-session", "messages": []},
            "settings": {
                "modelId": "claude-sonnet-4",
                "reasoningEffort": "medium",
            },
        },
    )


def _make_add_user_message_response(request_id: str) -> dict[str, Any]:
    """Build a minimal add_user_message success response."""
    return make_success_response(
        request_id=request_id,
        result={},
    )


async def _yield_to_loop(n: int = _SUBSCRIBE_DELAY_YIELDS) -> None:
    """Yield control to the event loop *n* times."""
    for _ in range(n):
        await asyncio.sleep(0)


async def _wait_for_sent(
    transport: InMemoryTransport,
    count: int,
    *,
    max_iters: int = 2000,
) -> None:
    """Wait until ``transport.sent_messages`` has at least *count* entries."""
    for _ in range(max_iters):
        if len(transport.sent_messages) >= count:
            return
        await asyncio.sleep(0)
    msg = f"Timed out waiting for {count} messages, got {len(transport.sent_messages)}"
    raise TimeoutError(msg)


async def _respond_to_init_and_message(transport: InMemoryTransport) -> None:
    """Respond to the initialize_session and add_user_message requests.

    After responding, yields control multiple times so the ``query()``
    generator can enter ``receive_response()`` and subscribe its listener.
    """
    await _wait_for_sent(transport, 1)
    init_req = json.loads(transport.sent_messages[0])
    transport.inject_message(_make_init_response(init_req["id"]))
    await asyncio.sleep(0)

    await _wait_for_sent(transport, 2)
    msg_req = json.loads(transport.sent_messages[1])
    transport.inject_message(_make_add_user_message_response(msg_req["id"]))

    # Give query() time to enter receive_response() and subscribe listener
    await _yield_to_loop()


# ---------------------------------------------------------------------------
# DroidQueryOptions tests
# ---------------------------------------------------------------------------


class TestDroidQueryOptionsDefaults:
    """Test DroidQueryOptions has correct defaults."""

    def test_default_values(self) -> None:
        """All optional fields default to None; cwd='.', machine_id='default'."""
        from droid_sdk.query import DroidQueryOptions

        opts = DroidQueryOptions()
        assert opts.cwd == "."
        assert opts.machine_id == "default"
        assert opts.model_id is None
        assert opts.autonomy_level is None
        assert opts.interaction_mode is None
        assert opts.reasoning_effort is None
        assert opts.mcp_servers is None
        assert opts.enabled_tool_ids is None
        assert opts.exec_path is None

    def test_construct_with_all_fields(self) -> None:
        """Can construct with all fields set."""
        from droid_sdk.query import DroidQueryOptions

        opts = DroidQueryOptions(
            cwd="/tmp",
            machine_id="my-machine",
            model_id="claude-sonnet-4",
            autonomy_level=AutonomyLevel.High,
            interaction_mode=DroidInteractionMode.Auto,
            reasoning_effort=ReasoningEffort.Medium,
            mcp_servers=[{"name": "test", "type": "stdio"}],
            enabled_tool_ids=["tool1", "tool2"],
            exec_path="/usr/local/bin/droid",
        )
        assert opts.cwd == "/tmp"
        assert opts.machine_id == "my-machine"
        assert opts.model_id == "claude-sonnet-4"
        assert opts.autonomy_level == AutonomyLevel.High
        assert opts.interaction_mode == DroidInteractionMode.Auto
        assert opts.reasoning_effort == ReasoningEffort.Medium
        assert opts.mcp_servers == [{"name": "test", "type": "stdio"}]
        assert opts.enabled_tool_ids == ["tool1", "tool2"]
        assert opts.exec_path == "/usr/local/bin/droid"

    def test_is_dataclass(self) -> None:
        """DroidQueryOptions is a dataclass."""
        import dataclasses

        from droid_sdk.query import DroidQueryOptions

        assert dataclasses.is_dataclass(DroidQueryOptions)


# ---------------------------------------------------------------------------
# query() lifecycle tests
# ---------------------------------------------------------------------------


class TestQueryLifecycle:
    """Test that query() creates full lifecycle and yields StreamMessage."""

    @pytest.mark.asyncio
    async def test_query_yields_messages_and_cleans_up(self) -> None:
        """query() connects, inits, sends, yields, and closes."""
        from droid_sdk.query import DroidQueryOptions, query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.ASSISTANT_TEXT_DELTA,
                    {
                        "messageId": "msg1",
                        "blockIndex": 0,
                        "textDelta": "Hello!",
                    },
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            messages: list[StreamMessage] = []
            async for msg in query(
                prompt="Hello",
                options=DroidQueryOptions(cwd="/tmp"),
            ):
                messages.append(msg)

        assert len(messages) > 0
        assert any(isinstance(m, AssistantTextDelta) for m in messages)
        assert isinstance(messages[-1], TurnComplete)
        # Transport should be closed after iteration
        assert not transport.is_connected

    @pytest.mark.asyncio
    async def test_query_default_exec_path(self) -> None:
        """query() uses 'droid' as default exec_path when not specified."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ) as mock_cls:
            _fire_task(handle_requests())

            async for _ in query(prompt="Hello"):
                pass

            # ProcessTransport was called with exec_path="droid"
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["exec_path"] == "droid"


class TestQueryOptionsPassthrough:
    """Test that query() passes options to initialize_session correctly."""

    @pytest.mark.asyncio
    async def test_options_mapped_to_init_params(self) -> None:
        """DroidQueryOptions fields are mapped to initialize_session params."""
        from droid_sdk.query import DroidQueryOptions, query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(
                prompt="Hello",
                options=DroidQueryOptions(
                    cwd="/myproject",
                    machine_id="my-machine",
                    model_id="claude-sonnet-4",
                    autonomy_level=AutonomyLevel.High,
                    reasoning_effort=ReasoningEffort.Medium,
                    interaction_mode=DroidInteractionMode.Auto,
                    mcp_servers=[{"name": "test", "command": "server"}],
                    enabled_tool_ids=["tool1"],
                ),
            ):
                pass

        # Check initialize_session request
        init_req = json.loads(transport.sent_messages[0])
        params = init_req["params"]
        assert params["cwd"] == "/myproject"
        assert params["machineId"] == "my-machine"
        assert params["modelId"] == "claude-sonnet-4"
        assert params["autonomyLevel"] == "high"
        assert params["reasoningEffort"] == "medium"
        assert params["interactionMode"] == "auto"
        assert params["mcpServers"] == [
            {"name": "test", "command": "server", "args": [], "env": {}}
        ]
        assert params["enabledToolIds"] == ["tool1"]

    @pytest.mark.asyncio
    async def test_none_options_omitted(self) -> None:
        """Options with None values are omitted from initialize_session params."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(prompt="Hello"):
                pass

        init_req = json.loads(transport.sent_messages[0])
        params = init_req["params"]
        assert "cwd" in params
        assert "machineId" in params
        assert "modelId" not in params
        assert "autonomyLevel" not in params
        assert "reasoningEffort" not in params
        assert "interactionMode" not in params
        assert "mcpServers" not in params
        assert "enabledToolIds" not in params


class TestQueryKwargsOverrides:
    """Test that query() accepts direct kwargs for convenience."""

    @pytest.mark.asyncio
    async def test_direct_kwargs_override_options(self) -> None:
        """Direct kwargs override DroidQueryOptions fields."""
        from droid_sdk.query import DroidQueryOptions, query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(
                prompt="Hello",
                options=DroidQueryOptions(cwd="/original", model_id="model-a"),
                cwd="/override",
                model_id="model-b",
            ):
                pass

        init_req = json.loads(transport.sent_messages[0])
        params = init_req["params"]
        assert params["cwd"] == "/override"
        assert params["modelId"] == "model-b"

    @pytest.mark.asyncio
    async def test_kwargs_without_options(self) -> None:
        """Direct kwargs work without providing an options object."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(
                prompt="Hello",
                cwd="/from-kwarg",
                machine_id="kwarg-machine",
                model_id="kwarg-model",
            ):
                pass

        init_req = json.loads(transport.sent_messages[0])
        params = init_req["params"]
        assert params["cwd"] == "/from-kwarg"
        assert params["machineId"] == "kwarg-machine"
        assert params["modelId"] == "kwarg-model"


class TestQueryCleanup:
    """Test proper cleanup on exception and normal exit."""

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self) -> None:
        """Transport and client are closed via aclose() when an exception occurs.

        In Python, raising inside ``async for`` does not automatically call
        ``aclose()`` on the async generator.  Proper usage wraps the loop
        in ``try / finally: await gen.aclose()``, which triggers the
        generator's ``finally`` block and releases resources.
        """
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.ASSISTANT_TEXT_DELTA,
                    {
                        "messageId": "msg1",
                        "blockIndex": 0,
                        "textDelta": "Hello",
                    },
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            gen = query(prompt="Hello")
            with pytest.raises(RuntimeError, match="test error"):
                try:
                    async for msg in gen:
                        if isinstance(msg, AssistantTextDelta):
                            raise RuntimeError("test error")
                finally:
                    await gen.aclose()

        # Transport should be closed because aclose() triggers the finally block
        assert not transport.is_connected

    @pytest.mark.asyncio
    async def test_cleanup_on_normal_exit(self) -> None:
        """Transport is closed after normal iteration completes."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(prompt="Hello"):
                pass

        assert not transport.is_connected

    @pytest.mark.asyncio
    async def test_cleanup_on_break(self) -> None:
        """Transport is closed when caller breaks out of iteration early."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            for i in range(10):
                transport.inject_message(
                    _make_session_notification(
                        SessionNotificationType.ASSISTANT_TEXT_DELTA,
                        {
                            "messageId": "msg1",
                            "blockIndex": 0,
                            "textDelta": f"token_{i}",
                        },
                    )
                )
                await asyncio.sleep(0)

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            count = 0
            gen = query(prompt="Hello")
            try:
                async for _msg in gen:
                    count += 1
                    if count >= 3:
                        break
            finally:
                await gen.aclose()

        assert not transport.is_connected


class TestQueryExecPath:
    """Test that query() passes exec_path to ProcessTransport."""

    @pytest.mark.asyncio
    async def test_custom_exec_path(self) -> None:
        """exec_path from options is passed to ProcessTransport."""
        from droid_sdk.query import DroidQueryOptions, query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ) as mock_cls:
            _fire_task(handle_requests())

            async for _ in query(
                prompt="Hello",
                options=DroidQueryOptions(exec_path="/custom/droid"),
            ):
                pass

            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["exec_path"] == "/custom/droid"

    @pytest.mark.asyncio
    async def test_exec_path_from_kwargs(self) -> None:
        """exec_path can be passed as a direct kwarg."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ) as mock_cls:
            _fire_task(handle_requests())

            async for _ in query(prompt="Hello", exec_path="/kwarg/droid"):
                pass

            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["exec_path"] == "/kwarg/droid"


class TestQueryPromptSent:
    """Test that query() sends the prompt as a user message."""

    @pytest.mark.asyncio
    async def test_prompt_sent_as_user_message(self) -> None:
        """The prompt text is sent via add_user_message."""
        from droid_sdk.query import query

        transport = InMemoryTransport()

        async def handle_requests() -> None:
            await _respond_to_init_and_message(transport)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        with patch.object(
            _query_module,
            "ProcessTransport",
            return_value=transport,
        ):
            _fire_task(handle_requests())

            async for _ in query(prompt="Fix the bug in main.py"):
                pass

        # Second sent message should be add_user_message
        msg_req = json.loads(transport.sent_messages[1])
        assert msg_req["method"] == "droid.add_user_message"
        assert msg_req["params"]["text"] == "Fix the bug in main.py"
