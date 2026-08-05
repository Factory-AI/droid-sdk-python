"""Tests for protocol enums and constants."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from enum import Enum

from droid_sdk.schemas.constants import (
    FACTORY_CLIENT_HEADER,
    FACTORY_CLIENT_VERSION,
    FACTORY_PROTOCOL_VERSION,
    JSONRPC_VERSION,
    LEGACY_FACTORY_API_VERSION,
)
from droid_sdk.schemas.enums import (
    AutonomyLevel,
    AutonomyMode,
    ClientType,
    DecompSessionType,
    DismissalType,
    DroidClientMethod,
    DroidErrorType,
    DroidInteractionMode,
    DroidMode,
    DroidServerMethod,
    DroidSubMode,
    DroidWorkingState,
    FeatureStatus,
    FeatureSuccessState,
    IssueSeverity,
    JsonRpcErrorCode,
    JsonRpcMessageType,
    McpAuthOutcome,
    McpServerStatus,
    McpServerType,
    McpStatus,
    MissionState,
    ModelProvider,
    Platform,
    ProgressLogEntryType,
    ReasoningEffort,
    SessionNotificationType,
    SettingsLevel,
    SkillLocation,
    ToolConfirmationOutcome,
    ToolConfirmationType,
)

# --- Constants Tests ---


class TestConstants:
    """Tests for protocol version constants."""

    def test_jsonrpc_version(self) -> None:
        assert JSONRPC_VERSION == "2.0"

    def test_legacy_factory_api_version(self) -> None:
        assert LEGACY_FACTORY_API_VERSION == "1.0.0"

    def test_factory_protocol_version(self) -> None:
        assert FACTORY_PROTOCOL_VERSION == "1.1.0"

    def test_factory_client_header(self) -> None:
        assert FACTORY_CLIENT_HEADER == "X-Factory-Client"

    def test_factory_client_version(self) -> None:
        assert FACTORY_CLIENT_VERSION == "X-Client-Version"


# --- Enum Member Count Tests ---


ENUM_MEMBER_COUNTS: list[tuple[type[Enum], int]] = [
    (DroidServerMethod, 29),
    (DroidClientMethod, 3),
    (SessionNotificationType, 20),
    (ToolConfirmationOutcome, 8),
    (ToolConfirmationType, 9),
    (DroidWorkingState, 5),
    (DroidErrorType, 7),
    (McpServerStatus, 5),
    (McpServerType, 2),
    (McpStatus, 5),
    (McpAuthOutcome, 3),
    (DecompSessionType, 2),
    (MissionState, 6),
    (FeatureStatus, 4),
    (FeatureSuccessState, 3),
    (IssueSeverity, 3),
    (DismissalType, 3),
    (ProgressLogEntryType, 11),
    (JsonRpcErrorCode, 8),
    (JsonRpcMessageType, 3),
    (ClientType, 6),
    (DroidMode, 4),
    (DroidSubMode, 2),
    (DroidInteractionMode, 3),
    (AutonomyLevel, 4),
    (AutonomyMode, 5),
    (Platform, 3),
    (ReasoningEffort, 9),
    (ModelProvider, 7),
    (SettingsLevel, 7),
    (SkillLocation, 3),
]


@pytest.mark.parametrize(
    ("enum_class", "expected_count"),
    ENUM_MEMBER_COUNTS,
    ids=[e[0].__name__ for e in ENUM_MEMBER_COUNTS],
)
def test_enum_member_count(enum_class: type[Enum], expected_count: int) -> None:
    """Verify each enum has the exact expected number of members."""
    actual = len(enum_class)
    assert actual == expected_count, (
        f"{enum_class.__name__} has {actual} members, expected {expected_count}"
    )


# --- String Enum JSON Serialization Tests ---

STRING_ENUMS: list[type[Enum]] = [
    DroidServerMethod,
    DroidClientMethod,
    SessionNotificationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
    DroidWorkingState,
    DroidErrorType,
    McpServerStatus,
    McpServerType,
    McpStatus,
    McpAuthOutcome,
    DecompSessionType,
    MissionState,
    FeatureStatus,
    FeatureSuccessState,
    IssueSeverity,
    DismissalType,
    ProgressLogEntryType,
    JsonRpcMessageType,
    ClientType,
    DroidMode,
    DroidSubMode,
    DroidInteractionMode,
    AutonomyLevel,
    AutonomyMode,
    Platform,
    ReasoningEffort,
    ModelProvider,
    SettingsLevel,
    SkillLocation,
]


@pytest.mark.parametrize(
    "enum_class",
    STRING_ENUMS,
    ids=[e.__name__ for e in STRING_ENUMS],
)
def test_string_enum_json_serialization(enum_class: type[Enum]) -> None:
    """Verify string enums serialize as raw strings in JSON via (str, Enum) mixin."""
    for member in enum_class:
        serialized = json.dumps(member)
        # Should be a quoted string, not "ClassName.MemberName"
        assert serialized == json.dumps(member.value), (
            f"{enum_class.__name__}.{member.name} serialized as {serialized}, "
            f"expected {json.dumps(member.value)}"
        )


@pytest.mark.parametrize(
    "enum_class",
    STRING_ENUMS,
    ids=[e.__name__ for e in STRING_ENUMS],
)
def test_string_enum_str_mixin(enum_class: type[Enum]) -> None:
    """Verify all string enums inherit from (str, Enum)."""
    assert issubclass(enum_class, str), (
        f"{enum_class.__name__} does not inherit from str"
    )


def test_json_rpc_error_code_int_mixin() -> None:
    """Verify JsonRpcErrorCode inherits from (int, Enum)."""
    assert issubclass(JsonRpcErrorCode, int)


# --- Representative Value Tests ---


REPRESENTATIVE_VALUES: list[tuple[type[Enum], str, Any]] = [
    # DroidServerMethod
    (DroidServerMethod, "INITIALIZE_SESSION", "droid.initialize_session"),
    (DroidServerMethod, "LOAD_SESSION", "droid.load_session"),
    (DroidServerMethod, "ADD_USER_MESSAGE", "droid.add_user_message"),
    (DroidServerMethod, "INTERRUPT_SESSION", "droid.interrupt_session"),
    (DroidServerMethod, "KILL_WORKER_SESSION", "droid.kill_worker_session"),
    (DroidServerMethod, "UPDATE_SESSION_SETTINGS", "droid.update_session_settings"),
    (DroidServerMethod, "TOGGLE_MCP_SERVER", "droid.toggle_mcp_server"),
    (DroidServerMethod, "AUTHENTICATE_MCP_SERVER", "droid.authenticate_mcp_server"),
    (DroidServerMethod, "CANCEL_MCP_AUTH", "droid.cancel_mcp_auth"),
    (DroidServerMethod, "CLEAR_MCP_AUTH", "droid.clear_mcp_auth"),
    (DroidServerMethod, "ADD_MCP_SERVER", "droid.add_mcp_server"),
    (DroidServerMethod, "REMOVE_MCP_SERVER", "droid.remove_mcp_server"),
    (DroidServerMethod, "LIST_MCP_REGISTRY", "droid.list_mcp_registry"),
    (DroidServerMethod, "LIST_MCP_TOOLS", "droid.list_mcp_tools"),
    (DroidServerMethod, "LIST_MCP_SERVERS", "droid.list_mcp_servers"),
    (DroidServerMethod, "TOGGLE_MCP_TOOL", "droid.toggle_mcp_tool"),
    (DroidServerMethod, "SUBMIT_MCP_AUTH_CODE", "droid.submit_mcp_auth_code"),
    (DroidServerMethod, "LIST_SKILLS", "droid.list_skills"),
    (DroidServerMethod, "SUBMIT_BUG_REPORT", "droid.submit_bug_report"),
    (DroidServerMethod, "LIST_TOOLS", "droid.list_tools"),
    (DroidServerMethod, "LIST_COMMANDS", "droid.list_commands"),
    (DroidServerMethod, "CLOSE_SESSION", "droid.close_session"),
    (DroidServerMethod, "COMPACT_SESSION", "droid.compact_session"),
    (DroidServerMethod, "FORK_SESSION", "droid.fork_session"),
    (DroidServerMethod, "RENAME_SESSION", "droid.rename_session"),
    (DroidServerMethod, "GET_CONTEXT_STATS", "droid.get_context_stats"),
    (DroidServerMethod, "GET_CONTEXT_BREAKDOWN", "droid.get_context_breakdown"),
    (DroidServerMethod, "GET_REWIND_INFO", "droid.get_rewind_info"),
    (DroidServerMethod, "EXECUTE_REWIND", "droid.execute_rewind"),
    # DroidClientMethod
    (DroidClientMethod, "SESSION_NOTIFICATION", "droid.session_notification"),
    (DroidClientMethod, "REQUEST_PERMISSION", "droid.request_permission"),
    (DroidClientMethod, "ASK_USER", "droid.ask_user"),
    # SessionNotificationType
    (SessionNotificationType, "TOOL_RESULT", "tool_result"),
    (SessionNotificationType, "TOOL_PROGRESS_UPDATE", "tool_progress_update"),
    (SessionNotificationType, "CREATE_MESSAGE", "create_message"),
    (SessionNotificationType, "ERROR", "error"),
    (
        SessionNotificationType,
        "DROID_WORKING_STATE_CHANGED",
        "droid_working_state_changed",
    ),
    (SessionNotificationType, "PERMISSION_RESOLVED", "permission_resolved"),
    (SessionNotificationType, "SETTINGS_UPDATED", "settings_updated"),
    (SessionNotificationType, "SESSION_TITLE_UPDATED", "session_title_updated"),
    (SessionNotificationType, "MCP_STATUS_CHANGED", "mcp_status_changed"),
    (SessionNotificationType, "ASSISTANT_TEXT_DELTA", "assistant_text_delta"),
    (SessionNotificationType, "THINKING_TEXT_DELTA", "thinking_text_delta"),
    (
        SessionNotificationType,
        "SESSION_TOKEN_USAGE_CHANGED",
        "session_token_usage_changed",
    ),
    (SessionNotificationType, "MISSION_STATE_CHANGED", "mission_state_changed"),
    (SessionNotificationType, "MISSION_FEATURES_CHANGED", "mission_features_changed"),
    (SessionNotificationType, "MISSION_PROGRESS_ENTRY", "mission_progress_entry"),
    (SessionNotificationType, "MISSION_HEARTBEAT", "mission_heartbeat"),
    (SessionNotificationType, "MISSION_WORKER_STARTED", "mission_worker_started"),
    (SessionNotificationType, "MISSION_WORKER_COMPLETED", "mission_worker_completed"),
    (SessionNotificationType, "MCP_AUTH_REQUIRED", "mcp_auth_required"),
    (SessionNotificationType, "MCP_AUTH_COMPLETED", "mcp_auth_completed"),
    # ToolConfirmationOutcome
    (ToolConfirmationOutcome, "ProceedOnce", "proceed_once"),
    (ToolConfirmationOutcome, "ProceedAlways", "proceed_always"),
    (ToolConfirmationOutcome, "ProceedAutoRun", "proceed_auto_run"),
    (ToolConfirmationOutcome, "ProceedAutoRunLow", "proceed_auto_run_low"),
    (ToolConfirmationOutcome, "ProceedAutoRunMedium", "proceed_auto_run_medium"),
    (ToolConfirmationOutcome, "ProceedAutoRunHigh", "proceed_auto_run_high"),
    (ToolConfirmationOutcome, "ProceedEdit", "proceed_edit"),
    (ToolConfirmationOutcome, "Cancel", "cancel"),
    # ToolConfirmationType
    (ToolConfirmationType, "Edit", "edit"),
    (ToolConfirmationType, "Execute", "exec"),
    (ToolConfirmationType, "Create", "create"),
    (ToolConfirmationType, "AskUser", "ask_user"),
    (ToolConfirmationType, "ExitSpecMode", "exit_spec_mode"),
    (ToolConfirmationType, "ProposeMission", "propose_mission"),
    (ToolConfirmationType, "StartMissionRun", "start_mission_run"),
    (ToolConfirmationType, "ApplyPatch", "apply_patch"),
    (ToolConfirmationType, "McpTool", "mcp_tool"),
    # DroidWorkingState
    (DroidWorkingState, "Idle", "idle"),
    (DroidWorkingState, "StreamingAssistantMessage", "streaming_assistant_message"),
    (DroidWorkingState, "WaitingForToolConfirmation", "waiting_for_tool_confirmation"),
    (DroidWorkingState, "ExecutingTool", "executing_tool"),
    (DroidWorkingState, "CompactingConversation", "compacting_conversation"),
    # DroidErrorType
    (DroidErrorType, "CONNECTION_ERROR", "ConnectionError"),
    (DroidErrorType, "PROTOCOL_ERROR", "ProtocolError"),
    (DroidErrorType, "SESSION_ERROR", "SessionError"),
    (DroidErrorType, "TIMEOUT_ERROR", "TimeoutError"),
    (DroidErrorType, "DROID_CLIENT_ERROR", "DroidClientError"),
    (DroidErrorType, "PROCESS_EXIT_ERROR", "ProcessExitError"),
    (DroidErrorType, "ERROR", "Error"),
    # McpServerStatus
    (McpServerStatus, "Connecting", "connecting"),
    (McpServerStatus, "Connected", "connected"),
    (McpServerStatus, "Disconnected", "disconnected"),
    (McpServerStatus, "Failed", "failed"),
    (McpServerStatus, "Disabled", "disabled"),
    # McpServerType
    (McpServerType, "Stdio", "stdio"),
    (McpServerType, "Http", "http"),
    # McpStatus
    (McpStatus, "NotInitialized", "not-initialized"),
    (McpStatus, "Initializing", "initializing"),
    (McpStatus, "Ready", "ready"),
    (McpStatus, "NoServers", "no-servers"),
    (McpStatus, "Failed", "failed"),
    # McpAuthOutcome
    (McpAuthOutcome, "Success", "success"),
    (McpAuthOutcome, "Cancelled", "cancelled"),
    (McpAuthOutcome, "Failed", "failed"),
    # DecompSessionType
    (DecompSessionType, "Orchestrator", "orchestrator"),
    (DecompSessionType, "Worker", "worker"),
    # MissionState
    (MissionState, "AwaitingInput", "awaiting_input"),
    (MissionState, "Initializing", "initializing"),
    (MissionState, "Running", "running"),
    (MissionState, "Paused", "paused"),
    (MissionState, "OrchestratorTurn", "orchestrator_turn"),
    (MissionState, "Completed", "completed"),
    # FeatureStatus
    (FeatureStatus, "Pending", "pending"),
    (FeatureStatus, "InProgress", "in_progress"),
    (FeatureStatus, "Completed", "completed"),
    (FeatureStatus, "Cancelled", "cancelled"),
    # FeatureSuccessState
    (FeatureSuccessState, "Success", "success"),
    (FeatureSuccessState, "Partial", "partial"),
    (FeatureSuccessState, "Failure", "failure"),
    # IssueSeverity
    (IssueSeverity, "Blocking", "blocking"),
    (IssueSeverity, "NonBlocking", "non_blocking"),
    (IssueSeverity, "Suggestion", "suggestion"),
    # DismissalType
    (DismissalType, "DiscoveredIssue", "discovered_issue"),
    (DismissalType, "CriticalContext", "critical_context"),
    (DismissalType, "IncompleteWork", "incomplete_work"),
    # ProgressLogEntryType
    (ProgressLogEntryType, "MissionAccepted", "mission_accepted"),
    (ProgressLogEntryType, "MissionPaused", "mission_paused"),
    (ProgressLogEntryType, "MissionResumed", "mission_resumed"),
    (ProgressLogEntryType, "MissionRunStarted", "mission_run_started"),
    (ProgressLogEntryType, "WorkerStarted", "worker_started"),
    (ProgressLogEntryType, "WorkerSelectedFeature", "worker_selected_feature"),
    (ProgressLogEntryType, "WorkerCompleted", "worker_completed"),
    (ProgressLogEntryType, "WorkerFailed", "worker_failed"),
    (ProgressLogEntryType, "WorkerPaused", "worker_paused"),
    (ProgressLogEntryType, "HandoffItemsDismissed", "handoff_items_dismissed"),
    (
        ProgressLogEntryType,
        "MilestoneValidationTriggered",
        "milestone_validation_triggered",
    ),
    # JsonRpcErrorCode (int enum)
    (JsonRpcErrorCode, "PARSE_ERROR", -32700),
    (JsonRpcErrorCode, "INVALID_REQUEST", -32600),
    (JsonRpcErrorCode, "METHOD_NOT_FOUND", -32601),
    (JsonRpcErrorCode, "INVALID_PARAMS", -32602),
    (JsonRpcErrorCode, "INTERNAL_ERROR", -32603),
    (JsonRpcErrorCode, "AUTHENTICATION_ERROR", -32001),
    (JsonRpcErrorCode, "ENTITY_NOT_FOUND", -32004),
    (JsonRpcErrorCode, "SESSION_DISCONNECTED", -32005),
    # JsonRpcMessageType
    (JsonRpcMessageType, "Request", "request"),
    (JsonRpcMessageType, "Response", "response"),
    (JsonRpcMessageType, "Notification", "notification"),
    # ClientType
    (ClientType, "WebDesktop", "web-desktop"),
    (ClientType, "WebApp", "web-app"),
    (ClientType, "WebWorkspace", "web-workspace"),
    (ClientType, "Daemon", "daemon"),
    (ClientType, "CLI", "cli"),
    (ClientType, "Backend", "backend"),
    # DroidMode
    (DroidMode, "TerminalUI", "terminal-ui"),
    (DroidMode, "NonInteractiveCLI", "non-interactive-cli"),
    (DroidMode, "InteractiveCLI", "interactive-cli"),
    (DroidMode, "Headless", "headless"),
    # DroidSubMode
    (DroidSubMode, "JsonRpc", "json-rpc"),
    (DroidSubMode, "ACP", "acp"),
    # DroidInteractionMode
    (DroidInteractionMode, "Auto", "auto"),
    (DroidInteractionMode, "Spec", "spec"),
    (DroidInteractionMode, "AGI", "agi"),
    # AutonomyLevel
    (AutonomyLevel, "Off", "off"),
    (AutonomyLevel, "Low", "low"),
    (AutonomyLevel, "Medium", "medium"),
    (AutonomyLevel, "High", "high"),
    # AutonomyMode
    (AutonomyMode, "Normal", "normal"),
    (AutonomyMode, "Spec", "spec"),
    (AutonomyMode, "AutoLow", "auto-low"),
    (AutonomyMode, "AutoMedium", "auto-medium"),
    (AutonomyMode, "AutoHigh", "auto-high"),
    # Platform
    (Platform, "Darwin", "darwin"),
    (Platform, "Windows", "win32"),
    (Platform, "Linux", "linux"),
    # ReasoningEffort
    (ReasoningEffort, "NONE", "none"),
    (ReasoningEffort, "Dynamic", "dynamic"),
    (ReasoningEffort, "Off", "off"),
    (ReasoningEffort, "Minimal", "minimal"),
    (ReasoningEffort, "Low", "low"),
    (ReasoningEffort, "Medium", "medium"),
    (ReasoningEffort, "High", "high"),
    (ReasoningEffort, "ExtraHigh", "xhigh"),
    (ReasoningEffort, "Max", "max"),
    # ModelProvider
    (ModelProvider, "ANTHROPIC", "anthropic"),
    (ModelProvider, "OPENAI", "openai"),
    (ModelProvider, "GENERIC_CHAT_COMPLETION_API", "generic-chat-completion-api"),
    (ModelProvider, "FACTORY", "factory"),
    (ModelProvider, "GOOGLE", "google"),
    (ModelProvider, "XAI", "xai"),
    (ModelProvider, "VOYAGE", "voyage"),
    # SettingsLevel
    (SettingsLevel, "Org", "org"),
    (SettingsLevel, "Runtime", "runtime"),
    (SettingsLevel, "User", "user"),
    (SettingsLevel, "Project", "project"),
    (SettingsLevel, "Folder", "folder"),
    (SettingsLevel, "Dynamic", "dynamic"),
    (SettingsLevel, "BuiltIn", "builtin"),
    # SkillLocation
    (SkillLocation, "Project", "project"),
    (SkillLocation, "Personal", "personal"),
    (SkillLocation, "Builtin", "builtin"),
]


@pytest.mark.parametrize(
    ("enum_class", "member_name", "expected_value"),
    REPRESENTATIVE_VALUES,
    ids=[f"{e[0].__name__}.{e[1]}" for e in REPRESENTATIVE_VALUES],
)
def test_enum_member_value(
    enum_class: type[Enum], member_name: str, expected_value: Any
) -> None:
    """Verify each enum member has the exact expected value."""
    member = enum_class[member_name]
    assert member.value == expected_value, (
        f"{enum_class.__name__}.{member_name}.value == {member.value!r}, "
        f"expected {expected_value!r}"
    )


# --- JsonRpcErrorCode Integer Behavior Tests ---


class TestJsonRpcErrorCode:
    """Tests specific to JsonRpcErrorCode integer behavior."""

    def test_int_comparison(self) -> None:
        """Verify int enum members compare correctly with raw integers."""
        assert JsonRpcErrorCode.PARSE_ERROR == -32700
        assert JsonRpcErrorCode.ENTITY_NOT_FOUND == -32004

    def test_int_arithmetic(self) -> None:
        """Verify int enum members can be used in arithmetic (int mixin)."""
        result = JsonRpcErrorCode.PARSE_ERROR + 100
        assert result == -32600

    def test_json_serialization(self) -> None:
        """Verify int enum serializes as integer in JSON."""
        serialized = json.dumps({"code": JsonRpcErrorCode.PARSE_ERROR})
        assert serialized == '{"code": -32700}'


# --- DroidWorkingState JSON Serialization Test ---


class TestDroidWorkingStateJsonSerialization:
    """Tests for DroidWorkingState JSON serialization."""

    def test_idle_json_dumps(self) -> None:
        """json.dumps(DroidWorkingState.Idle) should produce '"idle"'."""
        assert json.dumps(DroidWorkingState.Idle) == '"idle"'

    def test_all_states_serialize_as_raw_strings(self) -> None:
        """All DroidWorkingState members serialize as raw string values."""
        for state in DroidWorkingState:
            serialized = json.dumps(state)
            assert serialized == f'"{state.value}"'


# --- Enum Lookup by Value Tests ---


class TestEnumLookupByValue:
    """Tests for looking up enum members by their string/int values."""

    def test_string_enum_lookup(self) -> None:
        """Verify string enums can be constructed from string values."""
        method = DroidServerMethod("droid.initialize_session")
        assert method is DroidServerMethod.INITIALIZE_SESSION
        assert DroidWorkingState("idle") is DroidWorkingState.Idle
        assert McpStatus("not-initialized") is McpStatus.NotInitialized

    def test_int_enum_lookup(self) -> None:
        """Verify JsonRpcErrorCode can be constructed from integer values."""
        assert JsonRpcErrorCode(-32700) is JsonRpcErrorCode.PARSE_ERROR
        assert JsonRpcErrorCode(-32004) is JsonRpcErrorCode.ENTITY_NOT_FOUND

    def test_invalid_string_value_raises(self) -> None:
        """Verify invalid string values raise ValueError."""
        with pytest.raises(ValueError, match="not_a_real_method"):
            DroidServerMethod("not_a_real_method")

    def test_invalid_int_value_raises(self) -> None:
        """Verify invalid int values raise ValueError."""
        with pytest.raises(ValueError, match="9999"):
            JsonRpcErrorCode(9999)
