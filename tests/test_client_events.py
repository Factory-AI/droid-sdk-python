"""Tests for DroidClient notification event system and server→client request handlers.

Covers:
- VAL-CLIENT-009: Notification events delivered to all registered listeners
- VAL-CLIENT-010: Permission handler lifecycle
- VAL-CLIENT-011: Ask-user handler lifecycle
- VAL-CLIENT-019: Listener removal and exception isolation

Tests notification types: tool_result, assistant_text_delta, error, create_message,
droid_working_state_changed, mcp_status_changed, mission_state_changed.

Tests handler lifecycle: registration, replacement, clearing, async handlers,
exception → error response, default behavior, close cancellation.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.schemas.enums import (
    DroidClientMethod,
    JsonRpcErrorCode,
    SessionNotificationType,
    ToolConfirmationOutcome,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_SENTINEL = object()


class MockTransport:
    """In-memory transport for testing DroidClient event handlers."""

    def __init__(self) -> None:
        self._is_connected: bool = False
        self.sent_messages: list[str] = []
        self._closed: bool = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._error: Exception | None = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def send(self, message: str) -> None:
        if not self._is_connected:
            raise DroidConnectionError("Transport not connected")
        self.sent_messages.append(message)

    async def connect(self) -> None:
        self._is_connected = True
        self._closed = False
        self._error = None
        self._queue = asyncio.Queue()

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    async def close(self) -> None:
        self._is_connected = False
        self._closed = True
        self._queue.put_nowait(_SENTINEL)

    def inject_message(self, message: dict[str, Any]) -> None:
        self._queue.put_nowait(message)

    def inject_error(self, error: Exception) -> None:
        self._error = error
        self._queue.put_nowait(_SENTINEL)

    def get_last_sent_parsed(self) -> dict[str, Any]:
        assert len(self.sent_messages) > 0, "No messages sent"
        return json.loads(self.sent_messages[-1])  # type: ignore[no-any-return]

    def get_sent_parsed(self, index: int) -> dict[str, Any]:
        return json.loads(self.sent_messages[index])  # type: ignore[no-any-return]


def make_success_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "response",
        "id": request_id,
        "result": result,
    }


INIT_SESSION_RESULT: dict[str, Any] = {
    "sessionId": "sess-123",
    "session": {"messages": []},
    "settings": {
        "modelId": "claude-sonnet-4",
        "reasoningEffort": "medium",
    },
}


async def create_connected_client() -> tuple[DroidClient, MockTransport]:
    transport = MockTransport()
    client = DroidClient(transport=transport)
    await client.connect()
    return client, transport


async def create_client_with_session() -> tuple[DroidClient, MockTransport]:
    client, transport = await create_connected_client()

    async def do_init() -> Any:
        return await client.initialize_session(
            machine_id="test-machine",
            cwd="/tmp/test",
        )

    task = asyncio.create_task(do_init())
    await asyncio.sleep(0.01)

    sent = transport.get_last_sent_parsed()
    transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
    await task

    return client, transport


# ============================================================
# Helpers to create notification messages
# ============================================================


def make_notification(
    notification_type: str,
    notification_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a session notification JSON-RPC notification dict."""
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "notification",
        "method": DroidClientMethod.SESSION_NOTIFICATION.value,
        "params": {
            "notification": {
                "type": notification_type,
                **notification_payload,
            }
        },
    }


def make_permission_request(
    request_id: str,
    tool_uses: list[dict[str, Any]] | None = None,
    options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a droid.request_permission server→client request."""
    if tool_uses is None:
        tool_uses = [
            {
                "toolUse": {
                    "type": "tool_use",
                    "id": "tu-1",
                    "input": {"command": "ls"},
                    "name": "execute",
                },
                "confirmationType": "exec",
                "details": {
                    "type": "exec",
                    "fullCommand": "ls -la",
                    "command": "ls",
                },
            }
        ]
    if options is None:
        options = [
            {"value": "proceed_once", "label": "Allow Once"},
            {"value": "cancel", "label": "Cancel"},
        ]
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "request",
        "id": request_id,
        "method": DroidClientMethod.REQUEST_PERMISSION.value,
        "params": {
            "toolUses": tool_uses,
            "options": options,
        },
    }


def make_ask_user_request(
    request_id: str,
    tool_call_id: str = "tc-1",
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a droid.ask_user server→client request."""
    if questions is None:
        questions = [
            {
                "index": 1,
                "topic": "Color",
                "question": "What color?",
                "options": ["Red", "Blue"],
            }
        ]
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "request",
        "id": request_id,
        "method": DroidClientMethod.ASK_USER.value,
        "params": {
            "toolCallId": tool_call_id,
            "questions": questions,
        },
    }


# ============================================================
# Notification event system tests (VAL-CLIENT-009, VAL-CLIENT-019)
# ============================================================


class TestNotificationEvents:
    """Notification events delivered to all registered listeners."""

    @pytest.mark.asyncio
    async def test_listener_receives_notification(self) -> None:
        """A registered notification listener receives notifications."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda payload: received.append(payload))

        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1
        notif = received[0]
        assert notif["params"]["notification"]["type"] == "droid_working_state_changed"

    @pytest.mark.asyncio
    async def test_multiple_listeners_all_receive_notification(self) -> None:
        """Multiple registered listeners all receive the same notification."""
        client, transport = await create_connected_client()
        received_1: list[dict[str, Any]] = []
        received_2: list[dict[str, Any]] = []

        client.on_notification(lambda p: received_1.append(p))
        client.on_notification(lambda p: received_2.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.ERROR.value,
                {
                    "message": "Something failed",
                    "errorType": "Error",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received_1) == 1
        assert len(received_2) == 1

    @pytest.mark.asyncio
    async def test_tool_result_notification(self) -> None:
        """tool_result notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.TOOL_RESULT.value,
                {
                    "messageId": "msg-1",
                    "toolUseId": "tu-1",
                    "content": "file created",
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1
        assert (
            received[0]["params"]["notification"]["type"]
            == SessionNotificationType.TOOL_RESULT.value
        )

    @pytest.mark.asyncio
    async def test_assistant_text_delta_notification(self) -> None:
        """assistant_text_delta notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.ASSISTANT_TEXT_DELTA.value,
                {
                    "messageId": "msg-1",
                    "blockIndex": 0,
                    "textDelta": "Hello",
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1
        assert (
            received[0]["params"]["notification"]["type"]
            == SessionNotificationType.ASSISTANT_TEXT_DELTA.value
        )

    @pytest.mark.asyncio
    async def test_error_notification(self) -> None:
        """error notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.ERROR.value,
                {
                    "message": "Connection failed",
                    "errorType": "ConnectionError",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "error": {
                        "name": "ConnectionError",
                        "message": "Connection failed",
                    },
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_create_message_notification(self) -> None:
        """create_message notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.CREATE_MESSAGE.value,
                {
                    "message": {
                        "id": "msg-1",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Hello from assistant"}],
                        "model": "claude-sonnet-4",
                        "type": "message",
                        "stopReason": "end_turn",
                        "usage": {
                            "inputTokens": 10,
                            "outputTokens": 5,
                        },
                    },
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_droid_working_state_changed_notification(self) -> None:
        """droid_working_state_changed notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "executing_tool"},
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1
        assert received[0]["params"]["notification"]["newState"] == "executing_tool"

    @pytest.mark.asyncio
    async def test_mcp_status_changed_notification(self) -> None:
        """mcp_status_changed notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.MCP_STATUS_CHANGED.value,
                {
                    "servers": [
                        {
                            "name": "my-server",
                            "type": "stdio",
                            "status": "connected",
                            "enabled": True,
                        }
                    ],
                    "summary": {
                        "status": "ready",
                        "totalCount": 1,
                        "connectedCount": 1,
                        "failedCount": 0,
                    },
                },
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_mission_state_changed_notification(self) -> None:
        """mission_state_changed notification type is delivered correctly."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.MISSION_STATE_CHANGED.value,
                {"state": "running"},
            )
        )

        await asyncio.sleep(0.02)
        assert len(received) == 1
        assert received[0]["params"]["notification"]["state"] == "running"

    @pytest.mark.asyncio
    async def test_filtered_listener_receives_matching_type(self) -> None:
        """on_notification with type filter receives only matching notifications."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(
            lambda p: received.append(p),
            notification_type=SessionNotificationType.ERROR,
        )

        # Send non-matching notification
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 0

        # Send matching notification
        transport.inject_message(
            make_notification(
                SessionNotificationType.ERROR.value,
                {
                    "message": "test error",
                    "errorType": "Error",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1


class TestListenerRemoval:
    """Listener removal via returned unsubscribe function (VAL-CLIENT-019)."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_listener(self) -> None:
        """Calling unsubscribe function removes the listener."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        unsubscribe = client.on_notification(lambda p: received.append(p))

        # First notification is received
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1

        # Unsubscribe
        unsubscribe()

        # Second notification is NOT received
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "executing_tool"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_unsubscribe_only_removes_target_listener(self) -> None:
        """Unsubscribing one listener does not affect others."""
        client, transport = await create_connected_client()
        received_1: list[dict[str, Any]] = []
        received_2: list[dict[str, Any]] = []

        unsub_1 = client.on_notification(lambda p: received_1.append(p))
        client.on_notification(lambda p: received_2.append(p))

        # Remove first listener
        unsub_1()

        # Both should receive first, only second after unsub
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received_1) == 0
        assert len(received_2) == 1

    @pytest.mark.asyncio
    async def test_double_unsubscribe_is_safe(self) -> None:
        """Calling unsubscribe twice does not raise an error."""
        client, _transport = await create_connected_client()

        unsubscribe = client.on_notification(lambda p: None)
        unsubscribe()
        unsubscribe()  # Should not raise


class TestListenerExceptionIsolation:
    """Exception in one listener doesn't affect others (VAL-CLIENT-019)."""

    @pytest.mark.asyncio
    async def test_exception_in_listener_does_not_affect_others(self) -> None:
        """If one listener raises, other listeners still receive the notification."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        def bad_listener(p: dict[str, Any]) -> None:
            raise ValueError("listener error!")

        client.on_notification(bad_listener)
        client.on_notification(lambda p: received.append(p))

        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1  # Second listener still receives it

    @pytest.mark.asyncio
    async def test_exception_in_listener_does_not_break_read_loop(self) -> None:
        """After a listener raises, subsequent notifications are still delivered."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        def bad_listener(p: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        client.on_notification(bad_listener)
        client.on_notification(lambda p: received.append(p))

        # First notification
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1

        # Second notification — read loop should continue
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "executing_tool"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 2


# ============================================================
# Permission handler tests (VAL-CLIENT-010)
# ============================================================


class TestPermissionHandler:
    """Permission handler lifecycle (VAL-CLIENT-010)."""

    @pytest.mark.asyncio
    async def test_default_no_handler_returns_cancel(self) -> None:
        """Without a permission handler, default response is cancel."""
        _client, transport = await create_connected_client()

        transport.inject_message(make_permission_request("perm-1"))
        await asyncio.sleep(0.05)

        # Should have sent a response
        responses = [
            json.loads(m)
            for m in transport.sent_messages
            if "result" in json.loads(m) or "error" in json.loads(m)
        ]
        assert len(responses) >= 1
        last_resp = responses[-1]
        assert last_resp["id"] == "perm-1"
        assert last_resp["result"]["selectedOption"] == "cancel"

    @pytest.mark.asyncio
    async def test_sync_handler_returns_outcome(self) -> None:
        """Sync permission handler returns ToolConfirmationOutcome."""
        client, transport = await create_connected_client()

        def my_handler(params: dict[str, Any]) -> str:
            return ToolConfirmationOutcome.ProceedOnce.value

        client.set_permission_handler(my_handler)

        transport.inject_message(make_permission_request("perm-2"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["selectedOption"] == "proceed_once"

    @pytest.mark.asyncio
    async def test_async_handler_is_awaited(self) -> None:
        """Async permission handler is properly awaited."""
        client, transport = await create_connected_client()

        async def my_handler(params: dict[str, Any]) -> str:
            await asyncio.sleep(0.01)
            return ToolConfirmationOutcome.ProceedAlways.value

        client.set_permission_handler(my_handler)

        transport.inject_message(make_permission_request("perm-3"))
        await asyncio.sleep(0.1)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["selectedOption"] == "proceed_always"

    @pytest.mark.asyncio
    async def test_handler_replacement(self) -> None:
        """Second set_permission_handler replaces the first."""
        client, transport = await create_connected_client()

        def handler_1(params: dict[str, Any]) -> str:
            return ToolConfirmationOutcome.ProceedOnce.value

        def handler_2(params: dict[str, Any]) -> str:
            return ToolConfirmationOutcome.Cancel.value

        client.set_permission_handler(handler_1)
        client.set_permission_handler(handler_2)

        transport.inject_message(make_permission_request("perm-4"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["selectedOption"] == "cancel"

    @pytest.mark.asyncio
    async def test_clear_permission_handler_restores_default(self) -> None:
        """clear_permission_handler restores default Cancel behavior."""
        client, transport = await create_connected_client()

        def handler(params: dict[str, Any]) -> str:
            return ToolConfirmationOutcome.ProceedOnce.value

        client.set_permission_handler(handler)
        client.clear_permission_handler()

        transport.inject_message(make_permission_request("perm-5"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["selectedOption"] == "cancel"

    @pytest.mark.asyncio
    async def test_handler_exception_sends_internal_error(self) -> None:
        """Permission handler exception sends INTERNAL_ERROR response."""
        client, transport = await create_connected_client()

        def bad_handler(params: dict[str, Any]) -> str:
            raise ValueError("Handler crashed!")

        client.set_permission_handler(bad_handler)

        transport.inject_message(make_permission_request("perm-6"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "error" in json.loads(m)
        ]
        assert len(responses) >= 1
        error_resp = responses[-1]
        assert error_resp["id"] == "perm-6"
        assert error_resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_async_handler_exception_sends_internal_error(self) -> None:
        """Async permission handler exception sends INTERNAL_ERROR response."""
        client, transport = await create_connected_client()

        async def bad_handler(params: dict[str, Any]) -> str:
            raise RuntimeError("Async handler crashed!")

        client.set_permission_handler(bad_handler)

        transport.inject_message(make_permission_request("perm-7"))
        await asyncio.sleep(0.1)

        responses = [
            json.loads(m) for m in transport.sent_messages if "error" in json.loads(m)
        ]
        assert len(responses) >= 1
        error_resp = responses[-1]
        assert error_resp["id"] == "perm-7"
        assert error_resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_handler_receives_typed_params(self) -> None:
        """Permission handler receives the request params."""
        client, transport = await create_connected_client()
        captured_params: list[dict[str, Any]] = []

        def my_handler(params: dict[str, Any]) -> str:
            captured_params.append(params)
            return ToolConfirmationOutcome.Cancel.value

        client.set_permission_handler(my_handler)

        transport.inject_message(make_permission_request("perm-8"))
        await asyncio.sleep(0.05)

        assert len(captured_params) == 1
        assert "toolUses" in captured_params[0]
        assert "options" in captured_params[0]


# ============================================================
# Ask-user handler tests (VAL-CLIENT-011)
# ============================================================


class TestAskUserHandler:
    """Ask-user handler lifecycle (VAL-CLIENT-011)."""

    @pytest.mark.asyncio
    async def test_default_no_handler_returns_cancelled(self) -> None:
        """Without an ask-user handler, default returns cancelled=True, answers=[]."""
        _client, transport = await create_connected_client()

        transport.inject_message(make_ask_user_request("ask-1"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        result = responses[-1]["result"]
        assert result["cancelled"] is True
        assert result["answers"] == []

    @pytest.mark.asyncio
    async def test_sync_handler_returns_result(self) -> None:
        """Sync ask-user handler returns custom result."""
        client, transport = await create_connected_client()

        def my_handler(params: dict[str, Any]) -> dict[str, Any]:
            return {
                "cancelled": False,
                "answers": [{"index": 1, "question": "What color?", "answer": "Blue"}],
            }

        client.set_ask_user_handler(my_handler)

        transport.inject_message(make_ask_user_request("ask-2"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        result = responses[-1]["result"]
        assert result["cancelled"] is False
        assert len(result["answers"]) == 1
        assert result["answers"][0]["answer"] == "Blue"

    @pytest.mark.asyncio
    async def test_async_handler_is_awaited(self) -> None:
        """Async ask-user handler is properly awaited."""
        client, transport = await create_connected_client()

        async def my_handler(params: dict[str, Any]) -> dict[str, Any]:
            await asyncio.sleep(0.01)
            return {
                "cancelled": False,
                "answers": [{"index": 1, "question": "What color?", "answer": "Red"}],
            }

        client.set_ask_user_handler(my_handler)

        transport.inject_message(make_ask_user_request("ask-3"))
        await asyncio.sleep(0.1)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        result = responses[-1]["result"]
        assert result["cancelled"] is False
        assert result["answers"][0]["answer"] == "Red"

    @pytest.mark.asyncio
    async def test_handler_replacement(self) -> None:
        """Second set_ask_user_handler replaces the first."""
        client, transport = await create_connected_client()

        def handler_1(params: dict[str, Any]) -> dict[str, Any]:
            return {"cancelled": False, "answers": []}

        def handler_2(params: dict[str, Any]) -> dict[str, Any]:
            return {"cancelled": True, "answers": []}

        client.set_ask_user_handler(handler_1)
        client.set_ask_user_handler(handler_2)

        transport.inject_message(make_ask_user_request("ask-4"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["cancelled"] is True

    @pytest.mark.asyncio
    async def test_clear_ask_user_handler_restores_default(self) -> None:
        """clear_ask_user_handler restores default cancelled=True behavior."""
        client, transport = await create_connected_client()

        def handler(params: dict[str, Any]) -> dict[str, Any]:
            return {"cancelled": False, "answers": []}

        client.set_ask_user_handler(handler)
        client.clear_ask_user_handler()

        transport.inject_message(make_ask_user_request("ask-5"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        assert len(responses) >= 1
        assert responses[-1]["result"]["cancelled"] is True

    @pytest.mark.asyncio
    async def test_handler_exception_sends_internal_error(self) -> None:
        """Ask-user handler exception sends INTERNAL_ERROR response."""
        client, transport = await create_connected_client()

        def bad_handler(params: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("Handler crashed!")

        client.set_ask_user_handler(bad_handler)

        transport.inject_message(make_ask_user_request("ask-6"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "error" in json.loads(m)
        ]
        assert len(responses) >= 1
        error_resp = responses[-1]
        assert error_resp["id"] == "ask-6"
        assert error_resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_async_handler_exception_sends_internal_error(self) -> None:
        """Async ask-user handler exception sends INTERNAL_ERROR response."""
        client, transport = await create_connected_client()

        async def bad_handler(params: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("Async handler crashed!")

        client.set_ask_user_handler(bad_handler)

        transport.inject_message(make_ask_user_request("ask-7"))
        await asyncio.sleep(0.1)

        responses = [
            json.loads(m) for m in transport.sent_messages if "error" in json.loads(m)
        ]
        assert len(responses) >= 1
        error_resp = responses[-1]
        assert error_resp["id"] == "ask-7"
        assert error_resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_handler_receives_typed_params(self) -> None:
        """Ask-user handler receives the request params."""
        client, transport = await create_connected_client()
        captured_params: list[dict[str, Any]] = []

        def my_handler(params: dict[str, Any]) -> dict[str, Any]:
            captured_params.append(params)
            return {"cancelled": True, "answers": []}

        client.set_ask_user_handler(my_handler)

        transport.inject_message(
            make_ask_user_request(
                "ask-8",
                tool_call_id="tc-99",
                questions=[
                    {
                        "index": 1,
                        "topic": "Language",
                        "question": "Which language?",
                        "options": ["Python", "Rust"],
                    }
                ],
            )
        )
        await asyncio.sleep(0.05)

        assert len(captured_params) == 1
        assert captured_params[0]["toolCallId"] == "tc-99"
        assert len(captured_params[0]["questions"]) == 1


# ============================================================
# Close cancellation tests (VAL-CLIENT-010, VAL-CLIENT-011)
# ============================================================


class TestHandlersCancelledOnClose:
    """Handlers cancelled on close()."""

    @pytest.mark.asyncio
    async def test_close_clears_permission_handler(self) -> None:
        """close() clears the permission handler."""
        client, transport = await create_connected_client()
        handler = AsyncMock(return_value=ToolConfirmationOutcome.ProceedOnce.value)
        client.set_permission_handler(handler)

        await client.close()

        # After close, the handler should be cleared — reconnect and verify
        # that the default behavior (cancel) is restored
        await client.connect()
        transport.inject_message(make_permission_request("perm-close-1"))
        await asyncio.sleep(0.05)

        # The handler should NOT have been called after close
        # Instead, default cancel should be sent
        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        if len(responses) > 0:
            assert responses[-1]["result"]["selectedOption"] == "cancel"

    @pytest.mark.asyncio
    async def test_close_clears_ask_user_handler(self) -> None:
        """close() clears the ask-user handler."""
        client, transport = await create_connected_client()
        handler = AsyncMock(return_value={"cancelled": False, "answers": []})
        client.set_ask_user_handler(handler)

        await client.close()

        # After close, the handler should be cleared
        await client.connect()
        transport.inject_message(make_ask_user_request("ask-close-1"))
        await asyncio.sleep(0.05)

        responses = [
            json.loads(m) for m in transport.sent_messages if "result" in json.loads(m)
        ]
        if len(responses) > 0:
            assert responses[-1]["result"]["cancelled"] is True

    @pytest.mark.asyncio
    async def test_close_clears_notification_listeners(self) -> None:
        """close() removes all notification listeners."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        await client.close()

        # After close, reconnect and verify listener is gone
        await client.connect()
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 0  # Listener was cleared


# ============================================================
# Edge cases
# ============================================================


class TestNotificationBeforeSession:
    """Notifications delivered before initialize_session."""

    @pytest.mark.asyncio
    async def test_notification_before_init_is_delivered(self) -> None:
        """Notifications received before init are delivered to listeners."""
        client, transport = await create_connected_client()
        received: list[dict[str, Any]] = []

        client.on_notification(lambda p: received.append(p))

        # Send notification BEFORE initializing a session
        transport.inject_message(
            make_notification(
                SessionNotificationType.DROID_WORKING_STATE_CHANGED.value,
                {"newState": "idle"},
            )
        )
        await asyncio.sleep(0.02)
        assert len(received) == 1

        # Now initialize session should still work
        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test",
                cwd="/tmp",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        result = await task
        assert result.session_id == "sess-123"
