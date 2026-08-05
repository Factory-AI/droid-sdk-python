"""All protocol enums for the Factory Droid SDK.

Ported from TypeScript sources:
- packages/common/src/droid/enums.ts
- packages/common/src/shared/enums.ts
- packages/common/src/llm/enums.ts
- packages/common/src/settings/enums.ts
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "AutonomyLevel",
    # AutonomyMode intentionally excluded — deprecated in favor of
    # DroidInteractionMode + AutonomyLevel.  Kept for protocol compat only.
    "ClientType",
    "DecompSessionType",
    "DismissalType",
    "DroidClientMethod",
    "DroidErrorType",
    "DroidInteractionMode",
    "DroidMode",
    "DroidServerMethod",
    "DroidSubMode",
    "DroidWorkingState",
    "FeatureStatus",
    "FeatureSuccessState",
    "IssueSeverity",
    "JsonRpcErrorCode",
    "JsonRpcMessageType",
    "McpAuthOutcome",
    "McpServerStatus",
    "McpServerType",
    "McpStatus",
    "MissionState",
    "ModelProvider",
    "Platform",
    "ProgressLogEntryType",
    "ReasoningEffort",
    "SessionNotificationType",
    "SettingsLevel",
    "SkillLocation",
    "ToolConfirmationOutcome",
    "ToolConfirmationType",
]


class DroidServerMethod(str, Enum):
    """Droid server methods (client to server communication)."""

    INITIALIZE_SESSION = "droid.initialize_session"
    LOAD_SESSION = "droid.load_session"
    ADD_USER_MESSAGE = "droid.add_user_message"
    INTERRUPT_SESSION = "droid.interrupt_session"
    KILL_WORKER_SESSION = "droid.kill_worker_session"
    UPDATE_SESSION_SETTINGS = "droid.update_session_settings"
    TOGGLE_MCP_SERVER = "droid.toggle_mcp_server"
    AUTHENTICATE_MCP_SERVER = "droid.authenticate_mcp_server"
    CANCEL_MCP_AUTH = "droid.cancel_mcp_auth"
    CLEAR_MCP_AUTH = "droid.clear_mcp_auth"
    ADD_MCP_SERVER = "droid.add_mcp_server"
    REMOVE_MCP_SERVER = "droid.remove_mcp_server"
    LIST_MCP_REGISTRY = "droid.list_mcp_registry"
    LIST_MCP_TOOLS = "droid.list_mcp_tools"
    LIST_MCP_SERVERS = "droid.list_mcp_servers"
    TOGGLE_MCP_TOOL = "droid.toggle_mcp_tool"
    SUBMIT_MCP_AUTH_CODE = "droid.submit_mcp_auth_code"
    LIST_SKILLS = "droid.list_skills"
    SUBMIT_BUG_REPORT = "droid.submit_bug_report"
    LIST_TOOLS = "droid.list_tools"
    LIST_COMMANDS = "droid.list_commands"
    CLOSE_SESSION = "droid.close_session"
    COMPACT_SESSION = "droid.compact_session"
    FORK_SESSION = "droid.fork_session"
    RENAME_SESSION = "droid.rename_session"
    GET_CONTEXT_STATS = "droid.get_context_stats"
    GET_CONTEXT_BREAKDOWN = "droid.get_context_breakdown"
    GET_REWIND_INFO = "droid.get_rewind_info"
    EXECUTE_REWIND = "droid.execute_rewind"


class DroidClientMethod(str, Enum):
    """Droid client methods (server to client communication)."""

    SESSION_NOTIFICATION = "droid.session_notification"
    REQUEST_PERMISSION = "droid.request_permission"
    ASK_USER = "droid.ask_user"


class SessionNotificationType(str, Enum):
    """Session notification types."""

    TOOL_RESULT = "tool_result"
    TOOL_PROGRESS_UPDATE = "tool_progress_update"
    CREATE_MESSAGE = "create_message"
    ERROR = "error"
    DROID_WORKING_STATE_CHANGED = "droid_working_state_changed"
    PERMISSION_RESOLVED = "permission_resolved"
    SETTINGS_UPDATED = "settings_updated"
    SESSION_TITLE_UPDATED = "session_title_updated"
    MCP_STATUS_CHANGED = "mcp_status_changed"
    ASSISTANT_TEXT_DELTA = "assistant_text_delta"
    THINKING_TEXT_DELTA = "thinking_text_delta"
    SESSION_TOKEN_USAGE_CHANGED = "session_token_usage_changed"
    MISSION_STATE_CHANGED = "mission_state_changed"
    MISSION_FEATURES_CHANGED = "mission_features_changed"
    MISSION_PROGRESS_ENTRY = "mission_progress_entry"
    MISSION_HEARTBEAT = "mission_heartbeat"
    MISSION_WORKER_STARTED = "mission_worker_started"
    MISSION_WORKER_COMPLETED = "mission_worker_completed"
    MCP_AUTH_REQUIRED = "mcp_auth_required"
    MCP_AUTH_COMPLETED = "mcp_auth_completed"


class ToolConfirmationOutcome(str, Enum):
    """Tool confirmation outcome options.

    Possible user responses to permission requests.
    """

    ProceedOnce = "proceed_once"
    ProceedAlways = "proceed_always"
    ProceedAutoRun = "proceed_auto_run"
    ProceedAutoRunLow = "proceed_auto_run_low"
    ProceedAutoRunMedium = "proceed_auto_run_medium"
    ProceedAutoRunHigh = "proceed_auto_run_high"
    ProceedEdit = "proceed_edit"
    Cancel = "cancel"


class ToolConfirmationType(str, Enum):
    """Tool confirmation type (which tool is requesting permission)."""

    Edit = "edit"
    Execute = "exec"
    Create = "create"
    AskUser = "ask_user"
    ExitSpecMode = "exit_spec_mode"
    ProposeMission = "propose_mission"
    StartMissionRun = "start_mission_run"
    ApplyPatch = "apply_patch"
    McpTool = "mcp_tool"


class DroidWorkingState(str, Enum):
    """Droid working state (represents what the agent is currently doing)."""

    Idle = "idle"
    StreamingAssistantMessage = "streaming_assistant_message"
    WaitingForToolConfirmation = "waiting_for_tool_confirmation"
    ExecutingTool = "executing_tool"
    CompactingConversation = "compacting_conversation"


class DroidErrorType(str, Enum):
    """Error types for error notifications."""

    CONNECTION_ERROR = "ConnectionError"
    PROTOCOL_ERROR = "ProtocolError"
    SESSION_ERROR = "SessionError"
    TIMEOUT_ERROR = "TimeoutError"
    DROID_CLIENT_ERROR = "DroidClientError"
    PROCESS_EXIT_ERROR = "ProcessExitError"
    ERROR = "Error"


class McpServerStatus(str, Enum):
    """MCP server connection status."""

    Connecting = "connecting"
    Connected = "connected"
    Disconnected = "disconnected"
    Failed = "failed"
    Disabled = "disabled"


class McpServerType(str, Enum):
    """MCP server transport type."""

    Stdio = "stdio"
    Http = "http"


class McpStatus(str, Enum):
    """Overall MCP initialization status."""

    NotInitialized = "not-initialized"
    Initializing = "initializing"
    Ready = "ready"
    NoServers = "no-servers"
    Failed = "failed"


class McpAuthOutcome(str, Enum):
    """MCP authentication outcome."""

    Success = "success"
    Cancelled = "cancelled"
    Failed = "failed"


class DecompSessionType(str, Enum):
    """Session type for mission decomposition (orchestrator manages workers)."""

    Orchestrator = "orchestrator"
    Worker = "worker"


class MissionState(str, Enum):
    """Mission state enum (used by orchestrator mission runner)."""

    AwaitingInput = "awaiting_input"
    Initializing = "initializing"
    Running = "running"
    Paused = "paused"
    OrchestratorTurn = "orchestrator_turn"
    Completed = "completed"


class FeatureStatus(str, Enum):
    """Feature status enum (mirrors orchestrator feature lifecycle)."""

    Pending = "pending"
    InProgress = "in_progress"
    Completed = "completed"
    Cancelled = "cancelled"


class FeatureSuccessState(str, Enum):
    """Success state for feature completion."""

    Success = "success"
    Partial = "partial"
    Failure = "failure"


class IssueSeverity(str, Enum):
    """Issue severity for discovered issues."""

    Blocking = "blocking"
    NonBlocking = "non_blocking"
    Suggestion = "suggestion"


class DismissalType(str, Enum):
    """Dismissal item type."""

    DiscoveredIssue = "discovered_issue"
    CriticalContext = "critical_context"
    IncompleteWork = "incomplete_work"


class ProgressLogEntryType(str, Enum):
    """Progress log entry type."""

    MissionAccepted = "mission_accepted"
    MissionPaused = "mission_paused"
    MissionResumed = "mission_resumed"
    MissionRunStarted = "mission_run_started"
    WorkerStarted = "worker_started"
    WorkerSelectedFeature = "worker_selected_feature"
    WorkerCompleted = "worker_completed"
    WorkerFailed = "worker_failed"
    WorkerPaused = "worker_paused"
    HandoffItemsDismissed = "handoff_items_dismissed"
    MilestoneValidationTriggered = "milestone_validation_triggered"


class JsonRpcErrorCode(int, Enum):
    """Standard JSON-RPC 2.0 error codes.

    See: https://www.jsonrpc.org/specification#error_object
    """

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    AUTHENTICATION_ERROR = -32001
    ENTITY_NOT_FOUND = -32004
    SESSION_DISCONNECTED = -32005


class JsonRpcMessageType(str, Enum):
    """JSON-RPC message type discriminator."""

    Request = "request"
    Response = "response"
    Notification = "notification"


class ClientType(str, Enum):
    """Client type identifier."""

    WebDesktop = "web-desktop"
    WebApp = "web-app"
    WebWorkspace = "web-workspace"
    Daemon = "daemon"
    CLI = "cli"
    Backend = "backend"


class DroidMode(str, Enum):
    """Droid operating mode."""

    TerminalUI = "terminal-ui"
    NonInteractiveCLI = "non-interactive-cli"
    InteractiveCLI = "interactive-cli"
    Headless = "headless"
    """.. deprecated:: Headless will be decommissioned."""


class DroidSubMode(str, Enum):
    """Sub-mode discriminator for InteractiveCLI mode.

    Used to differentiate between JSON-RPC (daemon/web) and ACP (Zed) protocols.
    """

    JsonRpc = "json-rpc"
    ACP = "acp"


class DroidInteractionMode(str, Enum):
    """The interaction mode determines how Droid operates.

    - Auto: Droid can execute actions based on autonomy level
    - Spec: Droid is in planning/research mode only (read-only operations)
    - AGI: Droid orchestrates missions with read-only tools and orchestrator controls
    """

    Auto = "auto"
    Spec = "spec"
    AGI = "agi"


class AutonomyLevel(str, Enum):
    """Autonomy level for Droid actions.

    Determines what Droid can do without user confirmation.
    - Off: User controls all actions (confirmation required for everything)
    - Low: Allow file edits and read-only commands
    - Medium: Allow reversible commands
    - High: Allow all commands without prompts
    """

    Off = "off"
    Low = "low"
    Medium = "medium"
    High = "high"


class AutonomyMode(str, Enum):
    """Combined autonomy mode for backward compatibility.

    .. deprecated::
        Use :class:`DroidInteractionMode` + :class:`AutonomyLevel` instead.
        Retained for protocol compatibility — the server still sends/expects
        this field in ``SessionSettings`` and ``SettingsUpdatedPayload``.

    Derived from DroidInteractionMode + AutonomyLevel.
    """

    Normal = "normal"
    Spec = "spec"
    AutoLow = "auto-low"
    AutoMedium = "auto-medium"
    AutoHigh = "auto-high"


class Platform(str, Enum):
    """Supported operating system platforms."""

    Darwin = "darwin"
    Windows = "win32"
    Linux = "linux"


class ReasoningEffort(str, Enum):
    """Reasoning effort levels for LLMs.

    Determines how much "thinking" the model does before responding.
    """

    NONE = "none"
    Dynamic = "dynamic"
    Off = "off"
    Minimal = "minimal"
    Low = "low"
    Medium = "medium"
    High = "high"
    ExtraHigh = "xhigh"
    Max = "max"


class ModelProvider(str, Enum):
    """Model provider identifiers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GENERIC_CHAT_COMPLETION_API = "generic-chat-completion-api"
    FACTORY = "factory"
    GOOGLE = "google"
    XAI = "xai"
    VOYAGE = "voyage"


class SettingsLevel(str, Enum):
    """Settings hierarchy level enum.

    Precedence order (highest to lowest): Org -> Runtime -> Folder -> Project -> User
    """

    Org = "org"
    Runtime = "runtime"
    User = "user"
    Project = "project"
    Folder = "folder"
    Dynamic = "dynamic"
    BuiltIn = "builtin"


class SkillLocation(str, Enum):
    """Skill file location type."""

    Project = "project"
    Personal = "personal"
    Builtin = "builtin"
