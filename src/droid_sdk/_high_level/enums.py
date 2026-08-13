"""Enums on the stable high-level SDK surface."""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    AUTO = "auto"
    SPEC = "spec"


class Autonomy(str, Enum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningEffort(str, Enum):
    NONE = "none"
    DYNAMIC = "dynamic"
    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTRA_HIGH = "xhigh"
    MAX = "max"


class ToolConfirmationOutcome(str, Enum):
    PROCEED_ONCE = "proceed_once"
    PROCEED_ALWAYS = "proceed_always"
    PROCEED_ALWAYS_EXACT_PATH = "proceed_always_file"
    PROCEED_AUTO_RUN = "proceed_auto_run"
    PROCEED_AUTO_RUN_LOW = "proceed_auto_run_low"
    PROCEED_AUTO_RUN_MEDIUM = "proceed_auto_run_medium"
    PROCEED_AUTO_RUN_HIGH = "proceed_auto_run_high"
    PROCEED_NEW_SESSION = "proceed_new_session"
    PROCEED_NEW_SESSION_LOW = "proceed_new_session_low"
    PROCEED_NEW_SESSION_MEDIUM = "proceed_new_session_medium"
    PROCEED_NEW_SESSION_HIGH = "proceed_new_session_high"
    PROCEED_EDIT = "proceed_edit"
    PROCEED_ALWAYS_TOOLS = "proceed_always_tools"
    PROCEED_ALWAYS_SERVER = "proceed_always_server"
    CANCEL = "cancel"


class ToolConfirmationType(str, Enum):
    EDIT = "edit"
    EXECUTE = "exec"
    CREATE = "create"
    ASK_USER = "ask_user"
    EXIT_SPEC_MODE = "exit_spec_mode"
    APPLY_PATCH = "apply_patch"
    MCP_TOOL = "mcp_tool"
    SANDBOX_VIOLATION = "sandbox_violation"
    DROID_SHIELD_VIOLATION = "droid_shield_violation"


class WorkingState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    STREAMING_ASSISTANT_MESSAGE = "streaming_assistant_message"
    WAITING_FOR_TOOL_CONFIRMATION = "waiting_for_tool_confirmation"
    EXECUTING_TOOL = "executing_tool"
    COMPACTING_CONVERSATION = "compacting_conversation"


class ContextAccuracy(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"


class ToolCategory(str, Enum):
    READ = "read"
    EDIT = "edit"
    EXECUTE = "execute"
    OTHER = "other"


class McpServerType(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class McpServerStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    DISABLED = "disabled"


class McpAuthOutcome(str, Enum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ErrorType(str, Enum):
    CONNECTION_ERROR = "ConnectionError"
    PROTOCOL_ERROR = "ProtocolError"
    SESSION_ERROR = "SessionError"
    TIMEOUT_ERROR = "TimeoutError"
    DROID_CLIENT_ERROR = "DroidClientError"
    PROCESS_EXIT_ERROR = "ProcessExitError"
    ERROR = "Error"


class SessionPlatform(str, Enum):
    SLACK = "slack"
    WEB = "web"
    API = "api"
    SESSIONS_API = "sessions_api"
    JIRA = "jira"
    LINEAR = "linear"
    MICROSOFT_TEAMS = "microsoft-teams"
    READINESS_REMEDIATION = "readiness-remediation"
    READINESS_EVALUATION = "readiness-evaluation"
    AUTOMATION = "automation"
    WIKI_GENERATION = "wiki-generation"
    WIKI_CI_SETUP = "wiki-ci-setup"
    TUI = "tui"
    DESKTOP = "desktop"
    ACP = "acp"
    UNKNOWN = "unknown"


class SandboxOperation(str, Enum):
    READ = "read"
    WRITE = "write"
    NETWORK = "network"
    TOOL = "tool"


class SandboxViolationType(str, Enum):
    FILESYSTEM_READ = "filesystem-read"
    FILESYSTEM_WRITE = "filesystem-write"
    NETWORK = "network"
    TOOL = "tool"


class SandboxViolationReason(str, Enum):
    DENY_LIST = "deny-list"
    NOT_ALLOWED = "not-allowed"


class OAuthTokenEndpointAuthMethod(str, Enum):
    NONE = "none"
    CLIENT_SECRET_BASIC = "client_secret_basic"
    CLIENT_SECRET_POST = "client_secret_post"
