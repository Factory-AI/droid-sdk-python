"""Tests for DroidClient.receive_response() async iterator.

Covers: text delta sequences, tool use + result sequences, turn
complete on idle, concurrent rapid notifications (100+), token usage
included in TurnComplete, cleanup of notification subscription on exit.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from droid_sdk.client import DroidClient
from droid_sdk.schemas.enums import (
    DroidWorkingState,
    SessionNotificationType,
)
from droid_sdk.stream import (
    AssistantTextDelta,
    ErrorEvent,
    StreamMessage,
    ThinkingTextDelta,
    ToolProgress,
    ToolResult,
    ToolUse,
    TurnComplete,
    WorkingStateChanged,
)
from tests.helpers import InMemoryTransport, make_notification, make_success_response

# Keep strong references to background tasks so they aren't garbage-collected.
# See https://docs.python.org/3/library/asyncio-task.html#creating-tasks
_background_tasks: set[asyncio.Task[None]] = set()


def _fire_task(coro: Any) -> None:
    """Schedule *coro* as a background task with a prevent-GC reference."""
    task: asyncio.Task[None] = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
            "session": {"id": "test-session"},
            "settings": {
                "modelId": "claude-sonnet-4",
                "reasoningEffort": "medium",
            },
        },
    )


async def _setup_client(transport: InMemoryTransport) -> DroidClient:
    """Create and connect a DroidClient, faking initialize_session."""
    client = DroidClient(transport=transport)
    await client.connect()

    # Start initialize_session in background
    init_task = asyncio.create_task(
        client.initialize_session(machine_id="test", cwd="/tmp")
    )
    await asyncio.sleep(0)

    # Respond to the init request
    sent = transport.get_last_sent_parsed()
    transport.inject_message(_make_init_response(sent["id"]))
    await init_task

    return client


# ---------------------------------------------------------------------------
# Text delta sequence
# ---------------------------------------------------------------------------


class TestTextDeltaSequence:
    """Test receive_response() with a sequence of text deltas."""

    @pytest.mark.asyncio
    async def test_yields_text_deltas_then_turn_complete(self) -> None:
        """Text deltas are yielded followed by TurnComplete on idle."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject_notifications() -> None:
            await asyncio.sleep(0)
            # Working state → streaming
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Text deltas
            for text in ["Hello", " ", "World", "!"]:
                transport.inject_message(
                    _make_session_notification(
                        SessionNotificationType.ASSISTANT_TEXT_DELTA,
                        {
                            "messageId": "msg1",
                            "blockIndex": 0,
                            "textDelta": text,
                        },
                    )
                )
                await asyncio.sleep(0)
            # Back to idle → triggers TurnComplete
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject_notifications())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        # Should have: WorkingStateChanged(streaming), 4 text deltas,
        # WorkingStateChanged(idle), TurnComplete
        assert len(messages) == 7
        assert isinstance(messages[0], WorkingStateChanged)
        assert messages[0].state == DroidWorkingState.StreamingAssistantMessage
        assert isinstance(messages[1], AssistantTextDelta)
        assert messages[1].text == "Hello"
        assert isinstance(messages[2], AssistantTextDelta)
        assert messages[2].text == " "
        assert isinstance(messages[3], AssistantTextDelta)
        assert messages[3].text == "World"
        assert isinstance(messages[4], AssistantTextDelta)
        assert messages[4].text == "!"
        assert isinstance(messages[5], WorkingStateChanged)
        assert messages[5].state == DroidWorkingState.Idle
        assert isinstance(messages[6], TurnComplete)
        assert messages[6].token_usage is None

        await client.close()


# ---------------------------------------------------------------------------
# Thinking text delta sequence
# ---------------------------------------------------------------------------


class TestThinkingTextDeltaSequence:
    """Test receive_response() with thinking text deltas."""

    @pytest.mark.asyncio
    async def test_yields_thinking_deltas(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.THINKING_TEXT_DELTA,
                    {
                        "messageId": "msg1",
                        "blockIndex": 0,
                        "textDelta": "Let me think...",
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        assert any(isinstance(m, ThinkingTextDelta) for m in messages)
        thinking = [m for m in messages if isinstance(m, ThinkingTextDelta)]
        assert thinking[0].text == "Let me think..."
        assert isinstance(messages[-1], TurnComplete)

        await client.close()


# ---------------------------------------------------------------------------
# Tool use + result sequence
# ---------------------------------------------------------------------------


class TestToolUseAndResultSequence:
    """Test receive_response() with tool use and tool result."""

    @pytest.mark.asyncio
    async def test_tool_use_then_result_then_idle(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            # Working → streaming
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Tool use (CREATE_MESSAGE with tool_use block)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.CREATE_MESSAGE,
                    {
                        "message": {
                            "id": "msg1",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tu_123",
                                    "name": "read_file",
                                    "input": {"path": "/tmp/test.txt"},
                                },
                            ],
                            "createdAt": 1700000000.0,
                            "updatedAt": 1700000000.0,
                        },
                    },
                )
            )
            await asyncio.sleep(0)
            # Working → executing tool
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "executing_tool"},
                )
            )
            await asyncio.sleep(0)
            # Tool result
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.TOOL_RESULT,
                    {
                        "messageId": "msg2",
                        "toolUseId": "tu_123",
                        "content": "file contents here",
                        "isError": False,
                    },
                )
            )
            await asyncio.sleep(0)
            # Back to idle
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        tool_uses = [m for m in messages if isinstance(m, ToolUse)]
        assert len(tool_uses) == 1
        assert tool_uses[0].tool_name == "read_file"
        assert tool_uses[0].tool_use_id == "tu_123"

        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_results) == 1
        assert tool_results[0].content == "file contents here"
        assert tool_results[0].is_error is False

        assert isinstance(messages[-1], TurnComplete)

        await client.close()

    @pytest.mark.asyncio
    async def test_tool_progress_during_execution(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "executing_tool"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.TOOL_PROGRESS_UPDATE,
                    {
                        "toolUseId": "tu_1",
                        "toolName": "execute",
                        "update": {
                            "type": "status",
                            "text": "Running step 1...",
                        },
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        progress = [m for m in messages if isinstance(m, ToolProgress)]
        assert len(progress) == 1
        assert progress[0].tool_name == "execute"
        assert progress[0].content == "Running step 1..."

        await client.close()


# ---------------------------------------------------------------------------
# Turn complete on idle
# ---------------------------------------------------------------------------


class TestTurnCompleteOnIdle:
    """Test that TurnComplete is yielded when working state transitions to Idle."""

    @pytest.mark.asyncio
    async def test_initial_idle_does_not_trigger_turn_complete(self) -> None:
        """If the first state change is Idle (agent was never non-idle),
        receive_response should NOT immediately terminate."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            # Initial idle — should be skipped
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )
            await asyncio.sleep(0)
            # Now go non-idle
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
            await asyncio.sleep(0)
            # Back to idle — NOW we should terminate
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        # Should have streaming state, text delta, idle state, TurnComplete
        assert len(messages) == 4
        assert isinstance(messages[0], WorkingStateChanged)
        assert messages[0].state == DroidWorkingState.StreamingAssistantMessage
        assert isinstance(messages[1], AssistantTextDelta)
        assert isinstance(messages[2], WorkingStateChanged)
        assert messages[2].state == DroidWorkingState.Idle
        assert isinstance(messages[3], TurnComplete)

        await client.close()

    @pytest.mark.asyncio
    async def test_multiple_non_idle_states_before_idle(self) -> None:
        """Multiple non-idle transitions followed by idle should terminate once."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
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
                    {"newState": "executing_tool"},
                )
            )
            await asyncio.sleep(0)
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        # 3 non-idle states + idle state + TurnComplete = 5
        assert len(messages) == 5
        assert isinstance(messages[-1], TurnComplete)

        await client.close()


# ---------------------------------------------------------------------------
# Token usage included in TurnComplete
# ---------------------------------------------------------------------------


class TestTokenUsageInTurnComplete:
    """Test that TurnComplete carries token_usage from the last update."""

    @pytest.mark.asyncio
    async def test_turn_complete_includes_token_usage(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Token usage update
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED,
                    {
                        "sessionId": "sess_1",
                        "tokenUsage": {
                            "inputTokens": 500,
                            "outputTokens": 200,
                            "cacheCreationTokens": 10,
                            "cacheReadTokens": 100,
                            "thinkingTokens": 50,
                        },
                    },
                )
            )
            await asyncio.sleep(0)
            # Another token usage update (should use latest)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED,
                    {
                        "sessionId": "sess_1",
                        "tokenUsage": {
                            "inputTokens": 1000,
                            "outputTokens": 400,
                            "cacheCreationTokens": 20,
                            "cacheReadTokens": 200,
                            "thinkingTokens": 100,
                        },
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        turn_complete = messages[-1]
        assert isinstance(turn_complete, TurnComplete)
        assert turn_complete.token_usage is not None
        assert turn_complete.token_usage.input_tokens == 1000
        assert turn_complete.token_usage.output_tokens == 400
        assert turn_complete.token_usage.cache_read_tokens == 200
        assert turn_complete.token_usage.cache_write_tokens == 20

        await client.close()

    @pytest.mark.asyncio
    async def test_turn_complete_without_token_usage(self) -> None:
        """If no token usage was received, TurnComplete has None."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        turn_complete = messages[-1]
        assert isinstance(turn_complete, TurnComplete)
        assert turn_complete.token_usage is None

        await client.close()


# ---------------------------------------------------------------------------
# Concurrent rapid notifications
# ---------------------------------------------------------------------------


class TestConcurrentRapidNotifications:
    """Test that receive_response() handles 100+ rapid notifications."""

    @pytest.mark.asyncio
    async def test_100_rapid_text_deltas(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        num_deltas = 150

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Inject 150 text deltas rapidly (no awaits between them)
            for i in range(num_deltas):
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
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        text_deltas = [m for m in messages if isinstance(m, AssistantTextDelta)]
        assert len(text_deltas) == num_deltas

        # Verify order preserved
        for i, delta in enumerate(text_deltas):
            assert delta.text == f"token_{i}"

        assert isinstance(messages[-1], TurnComplete)

        await client.close()

    @pytest.mark.asyncio
    async def test_mixed_rapid_notifications(self) -> None:
        """Mix of different notification types at high speed."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            # Rapid mixed notifications
            for i in range(50):
                transport.inject_message(
                    _make_session_notification(
                        SessionNotificationType.ASSISTANT_TEXT_DELTA,
                        {
                            "messageId": "msg1",
                            "blockIndex": 0,
                            "textDelta": f"t{i}",
                        },
                    )
                )
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "executing_tool"},
                )
            )
            for i in range(50):
                transport.inject_message(
                    _make_session_notification(
                        SessionNotificationType.TOOL_PROGRESS_UPDATE,
                        {
                            "toolUseId": "tu_1",
                            "toolName": "execute",
                            "update": {
                                "type": "status",
                                "text": f"step_{i}",
                            },
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        text_deltas = [m for m in messages if isinstance(m, AssistantTextDelta)]
        tool_progress = [m for m in messages if isinstance(m, ToolProgress)]
        assert len(text_deltas) == 50
        assert len(tool_progress) == 50
        assert isinstance(messages[-1], TurnComplete)

        await client.close()


# ---------------------------------------------------------------------------
# Cleanup of notification subscription
# ---------------------------------------------------------------------------


class TestSubscriptionCleanup:
    """Test that the notification subscription is cleaned up on exit."""

    @pytest.mark.asyncio
    async def test_unsubscribes_after_normal_iteration(self) -> None:
        """After async for completes, the listener is removed."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        # Track listener count before
        listeners_before = len(client._notification_listeners)

        async def inject() -> None:
            await asyncio.sleep(0)
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

        _fire_task(inject())

        async for _ in client.receive_response():
            pass

        # After iteration, listener should be removed
        assert len(client._notification_listeners) == listeners_before

        await client.close()

    @pytest.mark.asyncio
    async def test_unsubscribes_on_break(self) -> None:
        """If the caller breaks out early, the listener is still removed."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        listeners_before = len(client._notification_listeners)

        async def inject() -> None:
            await asyncio.sleep(0)
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

        _fire_task(inject())

        count = 0
        ait = client.receive_response()
        try:
            async for _ in ait:
                count += 1
                if count >= 3:
                    break
        finally:
            await ait.aclose()

        assert len(client._notification_listeners) == listeners_before

        await client.close()


# ---------------------------------------------------------------------------
# Error event in stream
# ---------------------------------------------------------------------------


class TestErrorEventInStream:
    """Test that error notifications are yielded as ErrorEvent."""

    @pytest.mark.asyncio
    async def test_error_event_yielded(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.ERROR,
                    {
                        "message": "Something went wrong",
                        "errorType": "ConnectionError",
                        "timestamp": "2025-01-01T00:00:00Z",
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

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        errors = [m for m in messages if isinstance(m, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].message == "Something went wrong"
        assert errors[0].error_type == "ConnectionError"

        await client.close()


# ---------------------------------------------------------------------------
# Unmapped notification types are silently skipped
# ---------------------------------------------------------------------------


class TestUnmappedNotificationsSkipped:
    """Test that unmapped notification types are silently skipped."""

    @pytest.mark.asyncio
    async def test_settings_updated_skipped(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # This should be skipped
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.SETTINGS_UPDATED,
                    {"settings": {}},
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
            await asyncio.sleep(0)
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        # No SettingsUpdated in messages
        text_deltas = [m for m in messages if isinstance(m, AssistantTextDelta)]
        assert len(text_deltas) == 1
        assert isinstance(messages[-1], TurnComplete)

        await client.close()


# ---------------------------------------------------------------------------
# Works with async for loop syntax
# ---------------------------------------------------------------------------


class TestAsyncForLoopSyntax:
    """Verify receive_response() works with standard async for."""

    @pytest.mark.asyncio
    async def test_async_for_collects_all_messages(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
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
                        "textDelta": "test",
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

        _fire_task(inject())

        collected: list[StreamMessage] = []
        async for msg in client.receive_response():
            collected.append(msg)

        assert len(collected) > 0
        assert isinstance(collected[-1], TurnComplete)

        await client.close()


# ---------------------------------------------------------------------------
# receive_response() raises if client is closed
# ---------------------------------------------------------------------------


class TestReceiveResponseGuards:
    """Test that receive_response() respects client state."""

    @pytest.mark.asyncio
    async def test_raises_when_client_closed(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)
        await client.close()

        from droid_sdk.errors import ConnectionError as DroidConnectionError

        with pytest.raises(DroidConnectionError):
            async for _ in client.receive_response():
                pass


# ---------------------------------------------------------------------------
# Complete flow: text + tool + text + idle
# ---------------------------------------------------------------------------


class TestCompleteFlow:
    """Test a realistic flow with text, tools, and completion."""

    @pytest.mark.asyncio
    async def test_full_agent_turn(self) -> None:
        """Simulates: text → tool use → tool result → more text → idle."""
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        async def inject() -> None:
            await asyncio.sleep(0)
            # Start streaming
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Text delta
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.ASSISTANT_TEXT_DELTA,
                    {
                        "messageId": "msg1",
                        "blockIndex": 0,
                        "textDelta": "Let me check the file.",
                    },
                )
            )
            await asyncio.sleep(0)
            # Tool use
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.CREATE_MESSAGE,
                    {
                        "message": {
                            "id": "msg2",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tu_1",
                                    "name": "read_file",
                                    "input": {"path": "/test.py"},
                                },
                            ],
                            "createdAt": 1700000000.0,
                            "updatedAt": 1700000000.0,
                        },
                    },
                )
            )
            await asyncio.sleep(0)
            # Executing tool
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "executing_tool"},
                )
            )
            await asyncio.sleep(0)
            # Tool result
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.TOOL_RESULT,
                    {
                        "messageId": "msg3",
                        "toolUseId": "tu_1",
                        "content": "print('hello world')",
                        "isError": False,
                    },
                )
            )
            await asyncio.sleep(0)
            # Back to streaming
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "streaming_assistant_message"},
                )
            )
            await asyncio.sleep(0)
            # Token usage
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED,
                    {
                        "sessionId": "sess_1",
                        "tokenUsage": {
                            "inputTokens": 100,
                            "outputTokens": 50,
                            "cacheCreationTokens": 5,
                            "cacheReadTokens": 10,
                            "thinkingTokens": 0,
                        },
                    },
                )
            )
            await asyncio.sleep(0)
            # More text
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.ASSISTANT_TEXT_DELTA,
                    {
                        "messageId": "msg4",
                        "blockIndex": 0,
                        "textDelta": "The file contains a hello world script.",
                    },
                )
            )
            await asyncio.sleep(0)
            # Done
            transport.inject_message(
                _make_session_notification(
                    SessionNotificationType.DROID_WORKING_STATE_CHANGED,
                    {"newState": "idle"},
                )
            )

        _fire_task(inject())

        messages: list[StreamMessage] = []
        async for msg in client.receive_response():
            messages.append(msg)

        # Verify message types in order
        types = [type(m).__name__ for m in messages]
        assert "WorkingStateChanged" in types
        assert "AssistantTextDelta" in types
        assert "ToolUse" in types
        assert "ToolResult" in types
        assert "TokenUsageUpdate" in types
        assert types[-1] == "TurnComplete"

        # TurnComplete should have token usage
        turn_complete = messages[-1]
        assert isinstance(turn_complete, TurnComplete)
        assert turn_complete.token_usage is not None
        assert turn_complete.token_usage.input_tokens == 100
        assert turn_complete.token_usage.output_tokens == 50

        await client.close()
