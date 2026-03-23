"""Tests for server→client CLI schemas (notifications, requests, union).

Covers:
- All 20 SessionNotification discriminated union types
- RequestPermissionRequest validation
- AskUserRequest validation
- CliRequestOrNotification discriminated union dispatch
- camelCase aliasing and round-trip serialization
- Unknown/invalid type rejection
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from droid_sdk.schemas.cli import (
    AskUserCollectedAnswer,
    AskUserQuestion,
    AskUserRequest,
    AskUserRequestParams,
    AskUserResult,
    AssistantTextDeltaNotification,
    CliRequestOrNotification,
    CreateMessageNotification,
    DroidWorkingStateChangedNotification,
    EditToolConfirmationDetails,
    ErrorNotification,
    ExecuteToolConfirmationDetails,
    McpAuthCompletedNotification,
    McpAuthRequiredNotification,
    McpStatusChangedNotification,
    MissionFeaturesChangedNotification,
    MissionHeartbeatNotification,
    MissionProgressEntryNotification,
    MissionStateChangedNotification,
    MissionWorkerCompletedNotification,
    MissionWorkerStartedNotification,
    PermissionResolvedNotification,
    RequestPermissionRequest,
    RequestPermissionRequestParams,
    RequestPermissionResult,
    SessionNotification,
    SessionTitleUpdatedNotification,
    SessionTokenUsageChangedNotification,
    SettingsUpdatedNotification,
    ThinkingTextDeltaNotification,
    ToolConfirmationDetails,
    ToolConfirmationInfo,
    ToolProgressUpdate,
    ToolProgressUpdateNotification,
    ToolResultNotification,
    ToolUse,
)
from droid_sdk.schemas.enums import (
    DroidClientMethod,
    DroidErrorType,
    DroidWorkingState,
    McpAuthOutcome,
    MissionState,
    SessionNotificationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
)

# ============================================================
# Helpers
# ============================================================

_ENVELOPE_FIELDS: dict[str, Any] = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
}


def _make_notification(notification_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a full SessionNotification JSON envelope."""
    return {
        **_ENVELOPE_FIELDS,
        "type": "notification",
        "method": "droid.session_notification",
        "params": {"notification": notification_payload},
    }


def _make_request(
    method: str, params: dict[str, Any], request_id: str = "req-1"
) -> dict[str, Any]:
    """Build a full JSON-RPC request envelope."""
    return {
        **_ENVELOPE_FIELDS,
        "type": "request",
        "id": request_id,
        "method": method,
        "params": params,
    }


# ============================================================
# Individual notification payload tests
# ============================================================


class TestToolResultNotification:
    """Tests for ToolResultNotification payload."""

    def test_valid_tool_result(self) -> None:
        data = {
            "type": "tool_result",
            "messageId": "msg-1",
            "toolUseId": "tu-1",
            "content": "Tool output text",
            "isError": False,
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ToolResultNotification)
        assert payload.type == SessionNotificationType.TOOL_RESULT
        assert payload.message_id == "msg-1"
        assert payload.tool_use_id == "tu-1"
        assert payload.content == "Tool output text"
        assert payload.is_error is False

    def test_tool_result_minimal(self) -> None:
        data = {
            "type": "tool_result",
            "messageId": "msg-2",
            "toolUseId": "tu-2",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ToolResultNotification)
        assert payload.content is None
        assert payload.is_error is None


class TestToolProgressUpdateNotification:
    """Tests for ToolProgressUpdateNotification payload."""

    def test_valid_progress_update(self) -> None:
        data = {
            "type": "tool_progress_update",
            "toolUseId": "tu-1",
            "toolName": "Execute",
            "update": {
                "type": "tool_call",
                "toolName": "Execute",
                "status": "running",
                "details": "executing command",
                "timestamp": 1700000000,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ToolProgressUpdateNotification)
        assert payload.tool_use_id == "tu-1"
        assert payload.tool_name == "Execute"
        assert isinstance(payload.update, ToolProgressUpdate)
        assert payload.update.type == "tool_call"
        assert payload.update.tool_name == "Execute"
        assert payload.update.timestamp == 1700000000


class TestCreateMessageNotification:
    """Tests for CreateMessageNotification payload."""

    def test_valid_create_message(self) -> None:
        data = {
            "type": "create_message",
            "message": {
                "id": "msg-1",
                "role": "assistant",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            },
            "parentId": "parent-1",
            "requestId": "req-1",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, CreateMessageNotification)
        assert payload.message.id == "msg-1"
        assert payload.message.role.value == "assistant"
        assert payload.message.content == []
        assert payload.message.created_at == 1700000000
        assert payload.message.updated_at == 1700000000
        assert payload.parent_id == "parent-1"
        assert payload.request_id == "req-1"

    def test_create_message_minimal(self) -> None:
        data = {
            "type": "create_message",
            "message": {
                "id": "msg-1",
                "role": "user",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, CreateMessageNotification)
        assert payload.parent_id is None
        assert payload.request_id is None

    def test_create_message_with_content_blocks(self) -> None:
        """Test message with text content blocks."""
        data = {
            "type": "create_message",
            "message": {
                "id": "msg-2",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Hello world"},
                    {
                        "type": "tool_use",
                        "id": "tu-1",
                        "input": {"command": "ls"},
                        "name": "Execute",
                    },
                ],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, CreateMessageNotification)
        assert len(payload.message.content) == 2
        assert payload.message.content[0].type.value == "text"  # type: ignore[union-attr]
        assert payload.message.content[1].type.value == "tool_use"  # type: ignore[union-attr]

    def test_create_message_with_optional_fields(self) -> None:
        """Test message with optional fields like visibility, isError."""
        data = {
            "type": "create_message",
            "message": {
                "id": "msg-3",
                "role": "user",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
                "parentId": "p-1",
                "visibility": "both",
                "isError": False,
                "openaiMessageId": "oai-1",
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, CreateMessageNotification)
        assert payload.message.parent_id == "p-1"
        assert payload.message.visibility is not None
        assert payload.message.visibility.value == "both"
        assert payload.message.is_error is False
        assert payload.message.openai_message_id == "oai-1"

    def test_create_message_serialization_camel_case(self) -> None:
        """Test that FactoryDroidMessage serializes to camelCase."""
        data = {
            "type": "create_message",
            "message": {
                "id": "msg-4",
                "role": "assistant",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, CreateMessageNotification)
        dumped = payload.message.model_dump(by_alias=True)
        assert "createdAt" in dumped
        assert "updatedAt" in dumped


class TestErrorNotification:
    """Tests for ErrorNotification payload."""

    def test_valid_error(self) -> None:
        data = {
            "type": "error",
            "message": "Something went wrong",
            "errorType": "ConnectionError",
            "timestamp": "2024-01-01T00:00:00Z",
            "error": {
                "name": "ConnectionError",
                "message": "Connection refused",
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ErrorNotification)
        assert payload.error_type == DroidErrorType.CONNECTION_ERROR
        assert payload.error is not None
        assert payload.error.name == "ConnectionError"

    def test_error_minimal(self) -> None:
        data = {
            "type": "error",
            "message": "Error occurred",
            "errorType": "Error",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ErrorNotification)
        assert payload.error is None


class TestDroidWorkingStateChangedNotification:
    """Tests for DroidWorkingStateChangedNotification payload."""

    def test_valid_state_changed(self) -> None:
        data = {
            "type": "droid_working_state_changed",
            "newState": "idle",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, DroidWorkingStateChangedNotification)
        assert payload.new_state == DroidWorkingState.Idle

    def test_all_states(self) -> None:
        for state in DroidWorkingState:
            data = {
                "type": "droid_working_state_changed",
                "newState": state.value,
            }
            notif = SessionNotification.model_validate(_make_notification(data))
            payload = notif.params.notification
            assert isinstance(payload, DroidWorkingStateChangedNotification)
            assert payload.new_state == state


class TestPermissionResolvedNotification:
    """Tests for PermissionResolvedNotification payload."""

    def test_valid_permission_resolved(self) -> None:
        data = {
            "type": "permission_resolved",
            "requestId": "req-1",
            "toolUseIds": ["tu-1", "tu-2"],
            "selectedOption": "proceed_once",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, PermissionResolvedNotification)
        assert payload.request_id == "req-1"
        assert payload.tool_use_ids == ["tu-1", "tu-2"]
        assert payload.selected_option == ToolConfirmationOutcome.ProceedOnce


class TestSettingsUpdatedNotification:
    """Tests for SettingsUpdatedNotification payload."""

    def test_valid_settings_updated(self) -> None:
        data = {
            "type": "settings_updated",
            "settings": {
                "autonomyMode": "normal",
                "interactionMode": "auto",
                "autonomyLevel": "medium",
                "modelId": "claude-sonnet-4",
                "reasoningEffort": "high",
                "specModeModelId": "claude-opus-4",
                "specModeReasoningEffort": "max",
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, SettingsUpdatedNotification)
        assert payload.settings.model_id == "claude-sonnet-4"

    def test_settings_updated_minimal(self) -> None:
        data = {
            "type": "settings_updated",
            "settings": {},
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, SettingsUpdatedNotification)
        assert payload.settings.model_id is None


class TestSessionTitleUpdatedNotification:
    """Tests for SessionTitleUpdatedNotification payload."""

    def test_valid_title_updated(self) -> None:
        data = {
            "type": "session_title_updated",
            "title": "New Session Title",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, SessionTitleUpdatedNotification)
        assert payload.title == "New Session Title"


class TestMcpStatusChangedNotification:
    """Tests for McpStatusChangedNotification payload."""

    def test_valid_mcp_status_changed(self) -> None:
        data = {
            "type": "mcp_status_changed",
            "servers": [
                {
                    "name": "test-server",
                    "status": "connected",
                    "source": "user",
                    "isManaged": False,
                }
            ],
            "summary": {
                "total": 1,
                "connected": 1,
                "connecting": 0,
                "failed": 0,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, McpStatusChangedNotification)
        assert len(payload.servers) == 1
        assert payload.summary.total == 1


class TestAssistantTextDeltaNotification:
    """Tests for AssistantTextDeltaNotification payload."""

    def test_valid_assistant_text_delta(self) -> None:
        data = {
            "type": "assistant_text_delta",
            "messageId": "msg-1",
            "blockIndex": 0,
            "textDelta": "Hello, ",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, AssistantTextDeltaNotification)
        assert payload.message_id == "msg-1"
        assert payload.block_index == 0
        assert payload.text_delta == "Hello, "


class TestThinkingTextDeltaNotification:
    """Tests for ThinkingTextDeltaNotification payload."""

    def test_valid_thinking_text_delta(self) -> None:
        data = {
            "type": "thinking_text_delta",
            "messageId": "msg-1",
            "blockIndex": 0,
            "textDelta": "Let me think...",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, ThinkingTextDeltaNotification)
        assert payload.text_delta == "Let me think..."


class TestSessionTokenUsageChangedNotification:
    """Tests for SessionTokenUsageChangedNotification payload."""

    def test_valid_token_usage(self) -> None:
        data = {
            "type": "session_token_usage_changed",
            "sessionId": "sess-1",
            "tokenUsage": {
                "inputTokens": 100,
                "outputTokens": 200,
                "cacheCreationTokens": 10,
                "cacheReadTokens": 20,
                "thinkingTokens": 50,
            },
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, SessionTokenUsageChangedNotification)
        assert payload.session_id == "sess-1"
        assert payload.token_usage.input_tokens == 100


class TestMissionStateChangedNotification:
    """Tests for MissionStateChangedNotification payload."""

    def test_valid_mission_state(self) -> None:
        data = {
            "type": "mission_state_changed",
            "state": "running",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionStateChangedNotification)
        assert payload.state == MissionState.Running

    def test_all_states(self) -> None:
        for state in MissionState:
            data = {
                "type": "mission_state_changed",
                "state": state.value,
            }
            notif = SessionNotification.model_validate(_make_notification(data))
            payload = notif.params.notification
            assert isinstance(payload, MissionStateChangedNotification)
            assert payload.state == state


class TestMissionFeaturesChangedNotification:
    """Tests for MissionFeaturesChangedNotification payload."""

    def test_valid_features_changed(self) -> None:
        data = {
            "type": "mission_features_changed",
            "features": [
                {
                    "id": "feat-1",
                    "description": "Feature 1",
                    "status": "pending",
                    "skillName": "python-sdk-worker",
                    "preconditions": [],
                    "expectedBehavior": ["works"],
                    "verificationSteps": ["test"],
                }
            ],
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionFeaturesChangedNotification)
        assert len(payload.features) == 1
        assert payload.features[0].id == "feat-1"


class TestMissionProgressEntryNotification:
    """Tests for MissionProgressEntryNotification payload."""

    def test_valid_progress_entry(self) -> None:
        data = {
            "type": "mission_progress_entry",
            "progressLog": [
                {
                    "type": "mission_accepted",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "title": "Build SDK",
                }
            ],
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionProgressEntryNotification)
        assert len(payload.progress_log) == 1


class TestMissionHeartbeatNotification:
    """Tests for MissionHeartbeatNotification payload."""

    def test_valid_heartbeat(self) -> None:
        data = {
            "type": "mission_heartbeat",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionHeartbeatNotification)
        assert payload.timestamp == "2024-01-01T00:00:00Z"


class TestMissionWorkerStartedNotification:
    """Tests for MissionWorkerStartedNotification payload."""

    def test_valid_worker_started(self) -> None:
        data = {
            "type": "mission_worker_started",
            "workerSessionId": "ws-1",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionWorkerStartedNotification)
        assert payload.worker_session_id == "ws-1"


class TestMissionWorkerCompletedNotification:
    """Tests for MissionWorkerCompletedNotification payload."""

    def test_valid_worker_completed(self) -> None:
        data = {
            "type": "mission_worker_completed",
            "workerSessionId": "ws-1",
            "exitCode": 0,
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, MissionWorkerCompletedNotification)
        assert payload.worker_session_id == "ws-1"
        assert payload.exit_code == 0


class TestMcpAuthRequiredNotification:
    """Tests for McpAuthRequiredNotification payload."""

    def test_valid_auth_required(self) -> None:
        data = {
            "type": "mcp_auth_required",
            "serverName": "github-mcp",
            "authUrl": "https://auth.example.com/oauth",
            "message": "Please authenticate",
            "state": "state-token-abc",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, McpAuthRequiredNotification)
        assert payload.server_name == "github-mcp"
        assert payload.auth_url == "https://auth.example.com/oauth"
        assert payload.state == "state-token-abc"


class TestMcpAuthCompletedNotification:
    """Tests for McpAuthCompletedNotification payload."""

    def test_valid_auth_completed(self) -> None:
        data = {
            "type": "mcp_auth_completed",
            "serverName": "github-mcp",
            "outcome": "success",
            "message": "Authentication successful",
        }
        notif = SessionNotification.model_validate(_make_notification(data))
        payload = notif.params.notification
        assert isinstance(payload, McpAuthCompletedNotification)
        assert payload.server_name == "github-mcp"
        assert payload.outcome == McpAuthOutcome.Success

    def test_all_outcomes(self) -> None:
        for outcome in McpAuthOutcome:
            data = {
                "type": "mcp_auth_completed",
                "serverName": "srv",
                "outcome": outcome.value,
                "message": "msg",
            }
            notif = SessionNotification.model_validate(_make_notification(data))
            payload = notif.params.notification
            assert isinstance(payload, McpAuthCompletedNotification)
            assert payload.outcome == outcome


# ============================================================
# Discriminated union dispatch test (all 20 types)
# ============================================================


_NOTIFICATION_TYPE_PAYLOADS: list[tuple[str, type[Any], dict[str, Any]]] = [
    (
        "tool_result",
        ToolResultNotification,
        {"messageId": "m1", "toolUseId": "t1"},
    ),
    (
        "tool_progress_update",
        ToolProgressUpdateNotification,
        {
            "toolUseId": "t1",
            "toolName": "Exec",
            "update": {"type": "status"},
        },
    ),
    (
        "create_message",
        CreateMessageNotification,
        {
            "message": {
                "id": "m1",
                "role": "assistant",
                "content": [],
                "createdAt": 0,
                "updatedAt": 0,
            }
        },
    ),
    (
        "error",
        ErrorNotification,
        {"message": "err", "errorType": "Error", "timestamp": "2024-01-01T00:00:00Z"},
    ),
    (
        "droid_working_state_changed",
        DroidWorkingStateChangedNotification,
        {"newState": "idle"},
    ),
    (
        "permission_resolved",
        PermissionResolvedNotification,
        {
            "requestId": "r1",
            "toolUseIds": ["t1"],
            "selectedOption": "cancel",
        },
    ),
    (
        "settings_updated",
        SettingsUpdatedNotification,
        {"settings": {}},
    ),
    (
        "session_title_updated",
        SessionTitleUpdatedNotification,
        {"title": "Title"},
    ),
    (
        "mcp_status_changed",
        McpStatusChangedNotification,
        {
            "servers": [],
            "summary": {"total": 0, "connected": 0, "connecting": 0, "failed": 0},
        },
    ),
    (
        "assistant_text_delta",
        AssistantTextDeltaNotification,
        {"messageId": "m1", "blockIndex": 0, "textDelta": "hi"},
    ),
    (
        "thinking_text_delta",
        ThinkingTextDeltaNotification,
        {"messageId": "m1", "blockIndex": 0, "textDelta": "thinking"},
    ),
    (
        "session_token_usage_changed",
        SessionTokenUsageChangedNotification,
        {
            "sessionId": "s1",
            "tokenUsage": {
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheCreationTokens": 0,
                "cacheReadTokens": 0,
                "thinkingTokens": 0,
            },
        },
    ),
    (
        "mission_state_changed",
        MissionStateChangedNotification,
        {"state": "running"},
    ),
    (
        "mission_features_changed",
        MissionFeaturesChangedNotification,
        {"features": []},
    ),
    (
        "mission_progress_entry",
        MissionProgressEntryNotification,
        {"progressLog": []},
    ),
    (
        "mission_heartbeat",
        MissionHeartbeatNotification,
        {"timestamp": "2024-01-01T00:00:00Z"},
    ),
    (
        "mission_worker_started",
        MissionWorkerStartedNotification,
        {"workerSessionId": "ws-1"},
    ),
    (
        "mission_worker_completed",
        MissionWorkerCompletedNotification,
        {"workerSessionId": "ws-1", "exitCode": 0},
    ),
    (
        "mcp_auth_required",
        McpAuthRequiredNotification,
        {
            "serverName": "srv",
            "authUrl": "https://example.com",
            "message": "auth",
            "state": "st",
        },
    ),
    (
        "mcp_auth_completed",
        McpAuthCompletedNotification,
        {"serverName": "srv", "outcome": "success", "message": "ok"},
    ),
]


class TestSessionNotificationDispatch:
    """Tests for the SessionNotification discriminated union dispatch."""

    @pytest.mark.parametrize(
        ("type_value", "expected_class", "extra_fields"),
        _NOTIFICATION_TYPE_PAYLOADS,
        ids=[t[0] for t in _NOTIFICATION_TYPE_PAYLOADS],
    )
    def test_dispatch_all_20_types(
        self,
        type_value: str,
        expected_class: type[Any],
        extra_fields: dict[str, Any],
    ) -> None:
        payload = {"type": type_value, **extra_fields}
        notif = SessionNotification.model_validate(_make_notification(payload))
        assert isinstance(notif.params.notification, expected_class)

    def test_exactly_20_types_covered(self) -> None:
        """Ensure we test all 20 SessionNotificationType values."""
        tested_types = {t[0] for t in _NOTIFICATION_TYPE_PAYLOADS}
        all_types = {member.value for member in SessionNotificationType}
        assert tested_types == all_types, (
            f"Missing: {all_types - tested_types}, Extra: {tested_types - all_types}"
        )

    def test_unknown_type_rejected(self) -> None:
        payload = {"type": "unknown_type", "data": "test"}
        with pytest.raises(ValidationError):
            SessionNotification.model_validate(_make_notification(payload))


# ============================================================
# RequestPermissionRequest tests
# ============================================================


class TestRequestPermissionRequest:
    """Tests for RequestPermissionRequest."""

    def test_valid_request_permission(self) -> None:
        data = _make_request(
            "droid.request_permission",
            {
                "toolUses": [
                    {
                        "toolUse": {
                            "type": "tool_use",
                            "id": "tu-1",
                            "input": {"command": "ls"},
                            "name": "Execute",
                        },
                        "confirmationType": "exec",
                        "details": {
                            "type": "exec",
                            "fullCommand": "ls -la",
                            "command": "ls",
                        },
                    }
                ],
                "options": [
                    {"label": "Proceed", "value": "proceed_once"},
                    {"label": "Cancel", "value": "cancel"},
                ],
            },
        )
        req = RequestPermissionRequest.model_validate(data)
        assert req.method == DroidClientMethod.REQUEST_PERMISSION
        assert len(req.params.tool_uses) == 1
        assert len(req.params.options) == 2
        assert req.params.options[0].value == ToolConfirmationOutcome.ProceedOnce

    def test_request_permission_method_literal(self) -> None:
        """Wrong method should raise ValidationError."""
        data = _make_request(
            "droid.wrong_method",
            {
                "toolUses": [],
                "options": [],
            },
        )
        with pytest.raises(ValidationError):
            RequestPermissionRequest.model_validate(data)

    def test_tool_confirmation_details_discriminated_union(self) -> None:
        """Test that different confirmation detail types work."""
        edit_details = {"type": "edit", "filePath": "/test.py", "fileName": "test.py"}
        detail = ToolConfirmationDetails.model_validate(edit_details)
        assert isinstance(detail.root, EditToolConfirmationDetails)

        exec_details = {"type": "exec", "fullCommand": "ls", "command": "ls"}
        detail2 = ToolConfirmationDetails.model_validate(exec_details)
        assert isinstance(detail2.root, ExecuteToolConfirmationDetails)

    def test_request_permission_round_trip(self) -> None:
        """JSON round-trip for RequestPermissionRequest."""
        data = _make_request(
            "droid.request_permission",
            {
                "toolUses": [
                    {
                        "toolUse": {
                            "type": "tool_use",
                            "id": "tu-1",
                            "input": {},
                            "name": "Create",
                        },
                        "confirmationType": "create",
                        "details": {
                            "type": "create",
                            "filePath": "/new.py",
                            "fileName": "new.py",
                            "content": "print('hi')",
                        },
                    }
                ],
                "options": [{"label": "OK", "value": "proceed_once"}],
            },
        )
        req = RequestPermissionRequest.model_validate(data)
        json_str = req.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)
        assert parsed["method"] == "droid.request_permission"
        assert "toolUses" in parsed["params"]

    def test_request_permission_result(self) -> None:
        result = RequestPermissionResult.model_validate(
            {"selectedOption": "proceed_always"}
        )
        assert result.selected_option == ToolConfirmationOutcome.ProceedAlways


# ============================================================
# AskUserRequest tests
# ============================================================


class TestAskUserRequest:
    """Tests for AskUserRequest."""

    def test_valid_ask_user(self) -> None:
        data = _make_request(
            "droid.ask_user",
            {
                "toolCallId": "tc-1",
                "questions": [
                    {
                        "index": 1,
                        "topic": "Features",
                        "question": "Which features to enable?",
                        "options": ["Auth", "Login"],
                    }
                ],
            },
        )
        req = AskUserRequest.model_validate(data)
        assert req.method == DroidClientMethod.ASK_USER
        assert req.params.tool_call_id == "tc-1"
        assert len(req.params.questions) == 1
        assert req.params.questions[0].topic == "Features"

    def test_ask_user_method_literal(self) -> None:
        """Wrong method should raise ValidationError."""
        data = _make_request(
            "droid.wrong_method",
            {"toolCallId": "tc-1", "questions": []},
        )
        with pytest.raises(ValidationError):
            AskUserRequest.model_validate(data)

    def test_ask_user_question_fields(self) -> None:
        q = AskUserQuestion.model_validate(
            {
                "index": 2,
                "topic": "Library",
                "question": "Which library?",
                "options": ["A", "B", "C"],
            }
        )
        assert q.index == 2
        assert q.topic == "Library"
        assert len(q.options) == 3

    def test_ask_user_result(self) -> None:
        result = AskUserResult.model_validate(
            {
                "cancelled": False,
                "answers": [
                    {"index": 1, "question": "Which?", "answer": "Auth"},
                ],
            }
        )
        assert result.cancelled is False
        assert len(result.answers) == 1
        assert isinstance(result.answers[0], AskUserCollectedAnswer)

    def test_ask_user_result_cancelled(self) -> None:
        result = AskUserResult.model_validate({"cancelled": True, "answers": []})
        assert result.cancelled is True
        assert result.answers == []

    def test_ask_user_round_trip(self) -> None:
        data = _make_request(
            "droid.ask_user",
            {
                "toolCallId": "tc-1",
                "questions": [
                    {
                        "index": 1,
                        "topic": "Test",
                        "question": "Q?",
                        "options": ["A"],
                    }
                ],
            },
        )
        req = AskUserRequest.model_validate(data)
        json_str = req.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)
        assert parsed["method"] == "droid.ask_user"
        assert parsed["params"]["toolCallId"] == "tc-1"


# ============================================================
# CliRequestOrNotification discriminated union tests
# ============================================================


class TestCliRequestOrNotification:
    """Tests for CliRequestOrNotification discriminated union."""

    def test_dispatch_session_notification(self) -> None:
        data = _make_notification(
            {
                "type": "assistant_text_delta",
                "messageId": "m1",
                "blockIndex": 0,
                "textDelta": "hi",
            }
        )
        union = CliRequestOrNotification.model_validate(data)
        assert isinstance(union.root, SessionNotification)

    def test_dispatch_request_permission(self) -> None:
        data = _make_request(
            "droid.request_permission",
            {
                "toolUses": [],
                "options": [],
            },
        )
        union = CliRequestOrNotification.model_validate(data)
        assert isinstance(union.root, RequestPermissionRequest)

    def test_dispatch_ask_user(self) -> None:
        data = _make_request(
            "droid.ask_user",
            {
                "toolCallId": "tc-1",
                "questions": [],
            },
        )
        union = CliRequestOrNotification.model_validate(data)
        assert isinstance(union.root, AskUserRequest)

    def test_all_3_methods(self) -> None:
        """Verify all 3 DroidClientMethod values dispatch correctly."""
        methods_tested = set()

        # session_notification
        notif = _make_notification(
            {"type": "mission_heartbeat", "timestamp": "2024-01-01T00:00:00Z"}
        )
        union = CliRequestOrNotification.model_validate(notif)
        assert isinstance(union.root, SessionNotification)
        methods_tested.add(DroidClientMethod.SESSION_NOTIFICATION)

        # request_permission
        perm = _make_request(
            "droid.request_permission",
            {"toolUses": [], "options": []},
        )
        union2 = CliRequestOrNotification.model_validate(perm)
        assert isinstance(union2.root, RequestPermissionRequest)
        methods_tested.add(DroidClientMethod.REQUEST_PERMISSION)

        # ask_user
        ask = _make_request(
            "droid.ask_user",
            {"toolCallId": "tc-1", "questions": []},
        )
        union3 = CliRequestOrNotification.model_validate(ask)
        assert isinstance(union3.root, AskUserRequest)
        methods_tested.add(DroidClientMethod.ASK_USER)

        assert methods_tested == set(DroidClientMethod)

    def test_unknown_method_rejected(self) -> None:
        data = _make_request(
            "droid.unknown_method",
            {"data": "test"},
        )
        with pytest.raises(ValidationError):
            CliRequestOrNotification.model_validate(data)


# ============================================================
# camelCase alias tests
# ============================================================


class TestCamelCaseAliases:
    """Test that models use camelCase aliases for serialization."""

    def test_notification_camel_case_serialization(self) -> None:
        data = _make_notification(
            {
                "type": "mission_worker_started",
                "workerSessionId": "ws-1",
            }
        )
        notif = SessionNotification.model_validate(data)
        dumped = notif.model_dump(by_alias=True)
        assert "workerSessionId" not in json.dumps(
            dumped.get("params", {}).get("notification", {}),
        ).replace("workerSessionId", "")  # The field IS camelCase
        payload = dumped["params"]["notification"]
        assert "workerSessionId" in payload

    def test_tool_progress_camel_case(self) -> None:
        update = ToolProgressUpdate.model_validate(
            {
                "type": "tool_call",
                "toolName": "Execute",
                "valueSnippet": "output",
                "subagentSessionId": "sa-1",
            }
        )
        dumped = update.model_dump(by_alias=True)
        assert "toolName" in dumped
        assert "valueSnippet" in dumped
        assert "subagentSessionId" in dumped

    def test_ask_user_params_camel_case(self) -> None:
        params = AskUserRequestParams.model_validate(
            {
                "toolCallId": "tc-1",
                "questions": [],
            }
        )
        dumped = params.model_dump(by_alias=True)
        assert "toolCallId" in dumped

    def test_request_permission_params_camel_case(self) -> None:
        params = RequestPermissionRequestParams.model_validate(
            {
                "toolUses": [],
                "options": [],
            }
        )
        dumped = params.model_dump(by_alias=True)
        assert "toolUses" in dumped

    def test_camel_case_deserialization(self) -> None:
        """Parsing camelCase JSON should populate snake_case Python attributes."""
        data = {
            "type": "mcp_auth_required",
            "serverName": "test-srv",
            "authUrl": "https://example.com",
            "message": "auth plz",
            "state": "st",
        }
        notif = McpAuthRequiredNotification.model_validate(data)
        assert notif.server_name == "test-srv"
        assert notif.auth_url == "https://example.com"


# ============================================================
# Extra fields rejection
# ============================================================


class TestExtraFieldsAllowed:
    """Server→client models tolerate extra fields for protocol evolution."""

    def test_notification_extra_fields_allowed(self) -> None:
        data = {
            "type": "mission_heartbeat",
            "timestamp": "2024-01-01T00:00:00Z",
            "extraField": "tolerated",
        }
        notif = MissionHeartbeatNotification.model_validate(data)
        assert notif.timestamp == "2024-01-01T00:00:00Z"

    def test_tool_use_extra_fields_allowed(self) -> None:
        data = {
            "type": "tool_use",
            "id": "tu-1",
            "input": {},
            "name": "Test",
            "extraField": "tolerated",
        }
        tu = ToolUse.model_validate(data)
        assert tu.name == "Test"

    def test_ask_user_question_extra_fields_allowed(self) -> None:
        data = {
            "index": 1,
            "topic": "T",
            "question": "Q?",
            "options": [],
            "extra": "tolerated",
        }
        q = AskUserQuestion.model_validate(data)
        assert q.question == "Q?"


# ============================================================
# ToolConfirmationInfo and details tests
# ============================================================


class TestToolConfirmationInfo:
    """Tests for ToolConfirmationInfo and its details discriminated union."""

    def test_edit_confirmation(self) -> None:
        data = {
            "toolUse": {
                "type": "tool_use",
                "id": "tu-1",
                "input": {},
                "name": "Edit",
            },
            "confirmationType": "edit",
            "details": {
                "type": "edit",
                "filePath": "/test.py",
                "fileName": "test.py",
                "oldContent": "old",
                "newContent": "new",
            },
        }
        info = ToolConfirmationInfo.model_validate(data)
        assert info.confirmation_type == ToolConfirmationType.Edit
        detail = info.details.root
        assert isinstance(detail, EditToolConfirmationDetails)
        assert detail.file_path == "/test.py"

    def test_execute_confirmation(self) -> None:
        data = {
            "toolUse": {
                "type": "tool_use",
                "id": "tu-1",
                "input": {},
                "name": "Execute",
            },
            "confirmationType": "exec",
            "details": {
                "type": "exec",
                "fullCommand": "rm -rf /",
                "command": "rm",
                "extractedCommands": ["rm -rf /"],
                "impactLevel": "high",
            },
        }
        info = ToolConfirmationInfo.model_validate(data)
        detail = info.details.root
        assert isinstance(detail, ExecuteToolConfirmationDetails)
        assert detail.full_command == "rm -rf /"
        assert detail.extracted_commands == ["rm -rf /"]


# ============================================================
# AskUserConfirmationParsed typed questions
# ============================================================


class TestAskUserConfirmationParsedTypedQuestions:
    """Tests for AskUserConfirmationParsed with typed AskUserQuestion models."""

    def test_parsed_questions_are_typed(self) -> None:
        """Questions in AskUserConfirmationParsed should be AskUserQuestion models."""
        from droid_sdk.schemas.cli import AskUserConfirmationParsed

        parsed = AskUserConfirmationParsed.model_validate(
            {
                "questions": [
                    {
                        "index": 1,
                        "topic": "Features",
                        "question": "Which features?",
                        "options": ["Auth", "Login"],
                    },
                    {
                        "index": 2,
                        "topic": "Library",
                        "question": "Which library?",
                        "options": ["A", "B", "C"],
                    },
                ]
            }
        )
        assert len(parsed.questions) == 2
        assert isinstance(parsed.questions[0], AskUserQuestion)
        assert parsed.questions[0].index == 1
        assert parsed.questions[0].topic == "Features"
        assert parsed.questions[0].question == "Which features?"
        assert parsed.questions[0].options == ["Auth", "Login"]
        assert parsed.questions[1].index == 2
        assert parsed.questions[1].topic == "Library"

    def test_empty_questions_list(self) -> None:
        from droid_sdk.schemas.cli import AskUserConfirmationParsed

        parsed = AskUserConfirmationParsed.model_validate({"questions": []})
        assert parsed.questions == []

    def test_invalid_question_rejected(self) -> None:
        """Missing required fields in a question should raise ValidationError."""
        from droid_sdk.schemas.cli import AskUserConfirmationParsed

        with pytest.raises(ValidationError):
            AskUserConfirmationParsed.model_validate(
                {
                    "questions": [
                        {"index": 1}  # missing topic, question, options
                    ]
                }
            )
