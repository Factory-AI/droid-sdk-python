"""Tests for stream message dataclasses and notification-to-stream-message converter."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, get_args

import pytest

from droid_sdk.schemas.enums import (
    DroidWorkingState,
    SessionNotificationType,
)

# ---------------------------------------------------------------------------
# Dataclass construction tests
# ---------------------------------------------------------------------------


class TestAssistantTextDelta:
    """Tests for AssistantTextDelta dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import AssistantTextDelta

        msg = AssistantTextDelta(text="hello")
        assert msg.text == "hello"

    def test_field_names(self) -> None:
        from droid_sdk.stream import AssistantTextDelta

        names = {f.name for f in fields(AssistantTextDelta)}
        assert names == {"text"}


class TestThinkingTextDelta:
    """Tests for ThinkingTextDelta dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import ThinkingTextDelta

        msg = ThinkingTextDelta(text="reasoning...")
        assert msg.text == "reasoning..."

    def test_field_names(self) -> None:
        from droid_sdk.stream import ThinkingTextDelta

        names = {f.name for f in fields(ThinkingTextDelta)}
        assert names == {"text"}


class TestToolUseStream:
    """Tests for ToolUse stream dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import ToolUse

        msg = ToolUse(
            tool_name="read_file",
            tool_input={"path": "/tmp/test.txt"},
            tool_use_id="tu_123",
        )
        assert msg.tool_name == "read_file"
        assert msg.tool_input == {"path": "/tmp/test.txt"}
        assert msg.tool_use_id == "tu_123"

    def test_field_names(self) -> None:
        from droid_sdk.stream import ToolUse

        names = {f.name for f in fields(ToolUse)}
        assert names == {"tool_name", "tool_input", "tool_use_id"}


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_legacy_constructor_remains_compatible(self) -> None:
        from droid_sdk.stream import ToolResult

        msg = ToolResult("read_file", "file contents", False)

        assert msg.tool_name == "read_file"
        assert msg.content == "file contents"
        assert msg.is_error is False
        assert msg.tool_use_id is None

    def test_construction_string_content(self) -> None:
        from droid_sdk.stream import ToolResult

        msg = ToolResult(
            tool_name="read_file",
            tool_use_id="tu_1",
            content="file contents",
            is_error=False,
        )
        assert msg.tool_name == "read_file"
        assert msg.tool_use_id == "tu_1"
        assert msg.content == "file contents"
        assert msg.is_error is False

    def test_construction_list_content(self) -> None:
        from droid_sdk.stream import ToolResult

        content: list[Any] = [{"type": "text", "text": "result"}]
        msg = ToolResult(
            tool_name="execute",
            tool_use_id="tu_2",
            content=content,
            is_error=True,
        )
        assert msg.content == content
        assert msg.is_error is True

    def test_tool_name_optional(self) -> None:
        from droid_sdk.stream import ToolResult

        msg = ToolResult(
            tool_name=None,
            tool_use_id="tu_3",
            content="x",
            is_error=False,
        )
        assert msg.tool_name is None

    def test_field_names(self) -> None:
        from droid_sdk.stream import ToolResult

        names = {f.name for f in fields(ToolResult)}
        assert names == {"tool_name", "tool_use_id", "content", "is_error"}


class TestToolProgress:
    """Tests for ToolProgress dataclass."""

    def test_legacy_constructor_remains_compatible(self) -> None:
        from droid_sdk.stream import ToolProgress

        msg = ToolProgress("execute", "running step 2...")

        assert msg.tool_name == "execute"
        assert msg.content == "running step 2..."
        assert msg.tool_use_id is None

    def test_construction(self) -> None:
        from droid_sdk.stream import ToolProgress

        msg = ToolProgress(
            tool_name="execute",
            tool_use_id="tu_1",
            content="running step 2...",
        )
        assert msg.tool_name == "execute"
        assert msg.tool_use_id == "tu_1"
        assert msg.content == "running step 2..."

    def test_field_names(self) -> None:
        from droid_sdk.stream import ToolProgress

        names = {f.name for f in fields(ToolProgress)}
        assert names == {"tool_name", "tool_use_id", "content"}


class TestWorkingStateChanged:
    """Tests for WorkingStateChanged dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import WorkingStateChanged

        msg = WorkingStateChanged(state=DroidWorkingState.Idle)
        assert msg.state == DroidWorkingState.Idle

    def test_all_states(self) -> None:
        from droid_sdk.stream import WorkingStateChanged

        for state in DroidWorkingState:
            msg = WorkingStateChanged(state=state)
            assert msg.state == state

    def test_field_names(self) -> None:
        from droid_sdk.stream import WorkingStateChanged

        names = {f.name for f in fields(WorkingStateChanged)}
        assert names == {"state"}


class TestTokenUsageUpdate:
    """Tests for TokenUsageUpdate dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import TokenUsageUpdate

        msg = TokenUsageUpdate(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=20,
            cache_write_tokens=10,
        )
        assert msg.input_tokens == 100
        assert msg.output_tokens == 50
        assert msg.cache_read_tokens == 20
        assert msg.cache_write_tokens == 10

    def test_field_names(self) -> None:
        from droid_sdk.stream import TokenUsageUpdate

        names = {f.name for f in fields(TokenUsageUpdate)}
        assert names == {
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        }


class TestTurnComplete:
    """Tests for TurnComplete dataclass."""

    def test_construction_without_token_usage(self) -> None:
        from droid_sdk.stream import TurnComplete

        msg = TurnComplete()
        assert msg.token_usage is None

    def test_construction_with_token_usage(self) -> None:
        from droid_sdk.stream import TokenUsageUpdate, TurnComplete

        usage = TokenUsageUpdate(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=20,
            cache_write_tokens=10,
        )
        msg = TurnComplete(token_usage=usage)
        assert msg.token_usage is usage
        assert msg.token_usage.input_tokens == 100

    def test_field_names(self) -> None:
        from droid_sdk.stream import TurnComplete

        names = {f.name for f in fields(TurnComplete)}
        assert names == {"token_usage"}


class TestErrorEvent:
    """Tests for ErrorEvent dataclass."""

    def test_construction(self) -> None:
        from droid_sdk.stream import ErrorEvent

        msg = ErrorEvent(message="Something went wrong", error_type="ConnectionError")
        assert msg.message == "Something went wrong"
        assert msg.error_type == "ConnectionError"
        assert msg.error_name is None
        assert msg.error_detail is None

    def test_construction_with_nested_error(self) -> None:
        from droid_sdk.stream import ErrorEvent

        msg = ErrorEvent(
            message="Requested model was not found on the API provider",
            error_type="Error",
            error_name="LLMInvalidRequestError",
            error_detail={"name": "LLMInvalidRequestError", "message": "..."},
        )
        assert msg.error_name == "LLMInvalidRequestError"
        assert msg.error_detail == {
            "name": "LLMInvalidRequestError",
            "message": "...",
        }

    def test_field_names(self) -> None:
        from droid_sdk.stream import ErrorEvent

        names = {f.name for f in fields(ErrorEvent)}
        assert names == {"message", "error_type", "error_name", "error_detail"}


# ---------------------------------------------------------------------------
# StreamMessage union type tests
# ---------------------------------------------------------------------------


class TestStreamMessageUnion:
    """Tests for the StreamMessage union type."""

    def test_stream_message_is_union_of_all_types(self) -> None:
        from droid_sdk.stream import (
            AssistantTextDelta,
            ErrorEvent,
            StreamMessage,
            ThinkingTextDelta,
            TokenUsageUpdate,
            ToolProgress,
            ToolResult,
            ToolUse,
            TurnComplete,
            WorkingStateChanged,
        )

        args = set(get_args(StreamMessage))
        expected = {
            AssistantTextDelta,
            ThinkingTextDelta,
            ToolUse,
            ToolResult,
            ToolProgress,
            WorkingStateChanged,
            TokenUsageUpdate,
            TurnComplete,
            ErrorEvent,
        }
        assert args == expected

    def test_all_types_importable_from_stream(self) -> None:
        from droid_sdk import stream

        expected_names = [
            "AssistantTextDelta",
            "ThinkingTextDelta",
            "ToolUse",
            "ToolResult",
            "ToolProgress",
            "WorkingStateChanged",
            "TokenUsageUpdate",
            "TurnComplete",
            "ErrorEvent",
            "StreamMessage",
        ]
        for name in expected_names:
            assert hasattr(stream, name), f"{name} not found in stream module"


# ---------------------------------------------------------------------------
# _notification_to_stream_message converter tests
# ---------------------------------------------------------------------------


def _make_session_notification(
    notification_type: SessionNotificationType,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a minimal SessionNotification-shaped dict for testing."""
    return {
        "jsonrpc": "2.0",
        "type": "notification",
        "factoryApiVersion": "1.0.0",
        "method": "droid.session_notification",
        "params": {
            "notification": {"type": notification_type.value, **payload},
        },
    }


class TestNotificationToStreamMessage:
    """Tests for _notification_to_stream_message converter."""

    def test_assistant_text_delta(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            AssistantTextDelta,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.ASSISTANT_TEXT_DELTA,
            {"messageId": "msg1", "blockIndex": 0, "textDelta": "Hello "},
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, AssistantTextDelta)
        assert result.text == "Hello "

    def test_thinking_text_delta(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ThinkingTextDelta,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.THINKING_TEXT_DELTA,
            {"messageId": "msg2", "blockIndex": 0, "textDelta": "Let me think..."},
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ThinkingTextDelta)
        assert result.text == "Let me think..."

    def test_tool_result(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ToolResult,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.TOOL_RESULT,
            {
                "messageId": "msg3",
                "toolUseId": "tu_1",
                "content": "file contents here",
                "isError": False,
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ToolResult)
        assert result.content == "file contents here"
        assert result.is_error is False

    def test_tool_result_with_missing_tool_name(self) -> None:
        """ToolResultNotification has no toolName; converter yields None."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ToolResult,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.TOOL_RESULT,
            {
                "messageId": "msg3",
                "toolUseId": "tu_1",
                "content": "result",
                "isError": True,
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ToolResult)
        # ToolResultNotification doesn't carry tool_name; None means "unknown"
        # (distinct from a tool that reported an empty name).
        assert result.tool_name is None
        assert result.tool_use_id == "tu_1"
        assert result.is_error is True

    def test_tool_progress_update(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ToolProgress,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.TOOL_PROGRESS_UPDATE,
            {
                "toolUseId": "tu_2",
                "toolName": "execute",
                "update": {
                    "type": "status",
                    "text": "Compiling...",
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ToolProgress)
        assert result.tool_name == "execute"
        assert result.tool_use_id == "tu_2"
        assert result.content == "Compiling..."

    def test_tool_progress_update_fallback_content(self) -> None:
        """When update.text is None, fall back to other fields."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ToolProgress,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.TOOL_PROGRESS_UPDATE,
            {
                "toolUseId": "tu_2",
                "toolName": "execute",
                "update": {
                    "type": "status",
                    "status": "Running tests...",
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ToolProgress)
        assert result.tool_name == "execute"
        assert result.content == "Running tests..."

    def test_working_state_changed(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            WorkingStateChanged,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.DROID_WORKING_STATE_CHANGED,
            {"newState": "idle"},
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, WorkingStateChanged)
        assert result.state == DroidWorkingState.Idle

    def test_session_token_usage_changed(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            TokenUsageUpdate,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED,
            {
                "sessionId": "sess_1",
                "tokenUsage": {
                    "inputTokens": 500,
                    "outputTokens": 200,
                    "cacheCreationTokens": 0,
                    "cacheReadTokens": 100,
                    "thinkingTokens": 50,
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, TokenUsageUpdate)
        assert result.input_tokens == 500
        assert result.output_tokens == 200
        assert result.cache_read_tokens == 100
        assert result.cache_write_tokens == 0

    def test_error_notification(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ErrorEvent,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.ERROR,
            {
                "message": "Something went wrong",
                "errorType": "ConnectionError",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ErrorEvent)
        assert result.message == "Something went wrong"
        assert result.error_type == "ConnectionError"
        assert result.error_name is None
        assert result.error_detail is None

    def test_error_notification_with_nested_error(self) -> None:
        """The nested error.name is surfaced as error_name plus raw detail."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import (
            ErrorEvent,
            _notification_to_stream_message,
        )

        raw = _make_session_notification(
            SessionNotificationType.ERROR,
            {
                "message": "Requested model was not found on the API provider",
                "errorType": "Error",
                "timestamp": "2026-08-02T11:00:13.647Z",
                "error": {
                    "name": "LLMInvalidRequestError",
                    "message": "Requested model was not found on the API provider",
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, ErrorEvent)
        assert result.error_type == "Error"
        assert result.error_name == "LLMInvalidRequestError"
        assert result.error_detail is not None
        assert result.error_detail["name"] == "LLMInvalidRequestError"

    def test_create_message_with_tool_use_blocks(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import ToolUse, _notification_to_stream_message

        raw = _make_session_notification(
            SessionNotificationType.CREATE_MESSAGE,
            {
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu_abc",
                            "name": "read_file",
                            "input": {"path": "/tmp/test.txt"},
                        },
                    ],
                    "createdAt": 1700000000.0,
                    "updatedAt": 1700000000.0,
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, list)
        assert len(result) == 1
        tool_use = result[0]
        assert isinstance(tool_use, ToolUse)
        assert tool_use.tool_name == "read_file"
        assert tool_use.tool_input == {"path": "/tmp/test.txt"}
        assert tool_use.tool_use_id == "tu_abc"

    def test_create_message_with_multiple_tool_use_blocks(self) -> None:
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import ToolUse, _notification_to_stream_message

        raw = _make_session_notification(
            SessionNotificationType.CREATE_MESSAGE,
            {
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu_1",
                            "name": "read_file",
                            "input": {"path": "/a.txt"},
                        },
                        {
                            "type": "text",
                            "text": "some text",
                        },
                        {
                            "type": "tool_use",
                            "id": "tu_2",
                            "name": "write_file",
                            "input": {"path": "/b.txt", "content": "hi"},
                        },
                    ],
                    "createdAt": 1700000000.0,
                    "updatedAt": 1700000000.0,
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(t, ToolUse) for t in result)
        assert result[0].tool_name == "read_file"
        assert result[1].tool_name == "write_file"

    def test_create_message_without_tool_use_returns_none(self) -> None:
        """CREATE_MESSAGE with only text blocks returns None."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import _notification_to_stream_message

        raw = _make_session_notification(
            SessionNotificationType.CREATE_MESSAGE,
            {
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Hello world"},
                    ],
                    "createdAt": 1700000000.0,
                    "updatedAt": 1700000000.0,
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert result is None

    def test_unknown_notification_type_returns_none(self) -> None:
        """Unmapped notification types return None."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import _notification_to_stream_message

        # SETTINGS_UPDATED is not in the mapping
        raw = _make_session_notification(
            SessionNotificationType.SETTINGS_UPDATED,
            {
                "settings": {},
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert result is None

    def test_permission_resolved_returns_none(self) -> None:
        """PERMISSION_RESOLVED is not mapped."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import _notification_to_stream_message

        raw = _make_session_notification(
            SessionNotificationType.PERMISSION_RESOLVED,
            {
                "requestId": "req_1",
                "toolUseIds": ["tu_1"],
                "selectedOption": "proceed_once",
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert result is None

    def test_mcp_status_changed_returns_none(self) -> None:
        """MCP_STATUS_CHANGED is not mapped."""
        from droid_sdk.schemas.cli import SessionNotification
        from droid_sdk.stream import _notification_to_stream_message

        raw = _make_session_notification(
            SessionNotificationType.MCP_STATUS_CHANGED,
            {
                "servers": [],
                "summary": {
                    "total": 0,
                    "connected": 0,
                    "connecting": 0,
                    "failed": 0,
                },
            },
        )
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert result is None

    @pytest.mark.parametrize(
        "notification_type",
        [
            SessionNotificationType.SESSION_TITLE_UPDATED,
            SessionNotificationType.MISSION_STATE_CHANGED,
            SessionNotificationType.MISSION_HEARTBEAT,
        ],
    )
    def test_other_unmapped_types_return_none(
        self, notification_type: SessionNotificationType
    ) -> None:
        """Various unmapped notification types return None."""
        from droid_sdk.stream import _notification_to_stream_message

        # Build minimal notification payloads
        payloads: dict[SessionNotificationType, dict[str, Any]] = {
            SessionNotificationType.SESSION_TITLE_UPDATED: {"title": "Test"},
            SessionNotificationType.MISSION_STATE_CHANGED: {
                "state": "running",
            },
            SessionNotificationType.MISSION_HEARTBEAT: {
                "timestamp": "2025-01-01T00:00:00Z"
            },
        }

        from droid_sdk.schemas.cli import SessionNotification

        raw = _make_session_notification(notification_type, payloads[notification_type])
        notif = SessionNotification.model_validate(raw)
        result = _notification_to_stream_message(notif.params.notification)
        assert result is None
