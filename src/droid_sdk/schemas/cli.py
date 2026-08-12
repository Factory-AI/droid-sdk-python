# pyright: reportIncompatibleVariableOverride=false

"""Server→client CLI schemas (notifications, permission requests, ask-user).

Ported from TypeScript source:
- packages/common/src/droid/schemas/cli.ts

Includes:
- 20 notification payload types in a discriminated union
- RequestPermissionRequest with tool confirmation details
- AskUserRequest with questions and answers
- CliRequestOrNotification discriminated union over all 3 server→client methods
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from droid_sdk.schemas.enums import (
    AgentTurnCompletionReason,
    AutonomyLevel,
    AutonomyMode,
    DroidClientMethod,
    DroidErrorType,
    DroidInteractionMode,
    DroidWorkingState,
    LlmRetryReason,
    McpAuthOutcome,
    MissionState,
    ReasoningEffort,
    SandboxMode,
    SandboxOperationType,
    SandboxViolationReason,
    SandboxViolationType,
    SessionNotificationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
    ToolExecutionLifecyclePhase,
)
from droid_sdk.schemas.mcp import (  # noqa: TC001
    McpServerStatusInfo,
    McpStatusSummary,
    ToolConfirmationListItem,
)
from droid_sdk.schemas.messages import FactoryDroidMessage
from droid_sdk.schemas.mission import (  # noqa: TC001
    MissionFeature,
    ProgressLogEntry,
)
from droid_sdk.schemas.session import (  # noqa: TC001
    LastCallTokenUsage,
    SessionTag,
    TokenUsage,
)
from droid_sdk.schemas.shared import (
    JsonRpcNotification,
    JsonRpcRequest,
)

__all__ = [
    "AgentTurnCompletedNotification",
    "ApplyPatchToolConfirmationDetails",
    "AskUserCollectedAnswer",
    "AskUserConfirmationDetails",
    "AskUserConfirmationParseError",
    "AskUserConfirmationParsed",
    "AskUserQuestion",
    "AskUserRequest",
    "AskUserRequestParams",
    "AskUserResult",
    "AssistantTextCompleteNotification",
    "AssistantTextDeltaNotification",
    "ChildSessionAvailableNotification",
    "CliRequestOrNotification",
    "CreateMessageNotification",
    "CreateToolConfirmationDetails",
    "DroidShieldViolationConfirmationDetails",
    "DroidWorkingStateChangedNotification",
    "EditToolConfirmationDetails",
    "ErrorDetail",
    "ErrorNotification",
    "ExecuteToolConfirmationDetails",
    "ExitSpecModeConfirmationDetails",
    "FactoryDroidMessage",
    "HookCommand",
    "HookExecutionCompletedNotification",
    "HookExecutionStartedNotification",
    "HookResult",
    "LoopStateChangedNotification",
    "McpAuthCompletedNotification",
    "McpAuthRequiredNotification",
    "McpStatusChangedNotification",
    "McpToolConfirmationDetails",
    "MissionFeaturesChangedNotification",
    "MissionHeartbeatNotification",
    "MissionProgressEntryNotification",
    "MissionStateChangedNotification",
    "MissionWorkerCompletedNotification",
    "MissionWorkerStartedNotification",
    "PermissionResolvedNotification",
    "ProposeMissionConfirmationDetails",
    "QueuedMessagesDiscardedNotification",
    "RequestPermissionRequest",
    "RequestPermissionRequestParams",
    "RequestPermissionResult",
    "SandboxStatus",
    "SandboxViolationConfirmationDetails",
    "SessionCompactedNotification",
    "SessionNotification",
    "SessionNotificationParams",
    "SessionTitleUpdatedNotification",
    "SessionTokenUsageChangedNotification",
    "SessionWorkingDirectoryChangedNotification",
    "SettingsUpdatedNotification",
    "SettingsUpdatedPayload",
    "StartMissionRunConfirmationDetails",
    "StructuredOutputNotification",
    "ThinkingTextCompleteNotification",
    "ThinkingTextDeltaNotification",
    "ToolCallNotification",
    "ToolConfirmationDetails",
    "ToolConfirmationInfo",
    "ToolExecutionHeartbeatNotification",
    "ToolExecutionPhaseChangedNotification",
    "ToolProgressUpdate",
    "ToolProgressUpdateNotification",
    "ToolResultNotification",
    "ToolUse",
]


# ============================================================
# Supporting types for notification payloads
# ============================================================


class ToolUse(BaseModel):
    """Tool use block (from ToolUseSchema in sessionV2/messages)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["tool_use"]
    """Content block type, always 'tool_use'."""

    id: str
    """Tool use identifier."""

    input: dict[str, Any]
    """Tool input parameters."""

    name: str
    """Tool name."""

    thought_signature: str | None = Field(default=None, alias="thoughtSignature")
    """Optional Gemini thought signature."""


class ErrorDetail(BaseModel):
    """Error detail object within an ErrorNotification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Error name."""

    message: str
    """Error message."""


class ToolProgressUpdate(BaseModel):
    """Streaming update from subagent tool calls."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["tool_call", "tool_result", "error", "status", "message"]
    """Update type."""

    tool_name: str | None = Field(default=None, alias="toolName")
    """Optional tool name."""

    status: str | None = None
    """Optional status string."""

    details: str | None = None
    """Optional details."""

    text: str | None = None
    """Optional text content."""

    error: str | None = None
    """Optional error message."""

    timestamp: float | None = None
    """Optional timestamp."""

    parameters: dict[str, Any] | None = None
    """Optional tool parameters."""

    value_snippet: str | None = Field(default=None, alias="valueSnippet")
    """Optional value snippet."""

    subagent_session_id: str | None = Field(default=None, alias="subagentSessionId")
    """Optional spawned subagent session ID."""

    terminal_id: str | None = Field(default=None, alias="terminalId")
    full_output: str | None = Field(default=None, alias="fullOutput")


class SettingsUpdatedPayload(BaseModel):
    """Settings payload within SettingsUpdatedNotification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    autonomy_mode: AutonomyMode | None = Field(default=None, alias="autonomyMode")
    """Deprecated: use interaction_mode + autonomy_level instead."""

    interaction_mode: DroidInteractionMode | None = Field(
        default=None, alias="interactionMode"
    )
    """Current interaction mode."""

    autonomy_level: AutonomyLevel | None = Field(default=None, alias="autonomyLevel")
    """Current autonomy level."""

    model_id: str | None = Field(default=None, alias="modelId")
    """Active model identifier."""

    reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="reasoningEffort"
    )
    """Current reasoning effort level."""

    spec_mode_model_id: str | None = Field(default=None, alias="specModeModelId")
    """Optional spec mode model override."""

    spec_mode_reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="specModeReasoningEffort"
    )
    """Optional spec mode reasoning effort override."""

    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    restrict_tool_ids: list[str] | None = Field(default=None, alias="restrictToolIds")
    tags: list[SessionTag] | None = None
    compaction_threshold_check_enabled: bool | None = Field(
        default=None, alias="compactionThresholdCheckEnabled"
    )


# ============================================================
# 20 notification payload types
# ============================================================


class ToolResultNotification(BaseModel):
    """Tool result notification (extends ToolResult with type and messageId).

    Inherits conceptual fields from ToolResultSchema:
    toolUseId, content, isError (all from the base tool result).
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.TOOL_RESULT]
    """Notification type discriminator."""

    message_id: str = Field(alias="messageId")
    """Message ID this result belongs to."""

    tool_use_id: str = Field(alias="toolUseId")
    """Tool use ID this result corresponds to."""

    content: Any | None = None
    """Tool result content (string or array of content blocks)."""

    is_error: bool | None = Field(default=None, alias="isError")
    """Whether this result represents an error."""

    id: str | None = None
    """Optional content block ID (from BaseContentBlock)."""


class ToolProgressUpdateNotification(BaseModel):
    """Tool progress update notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.TOOL_PROGRESS_UPDATE]
    """Notification type discriminator."""

    tool_use_id: str = Field(alias="toolUseId")
    """Tool use ID being updated."""

    tool_name: str = Field(alias="toolName")
    """Tool name."""

    update: ToolProgressUpdate
    """Progress update payload."""


class CreateMessageNotification(BaseModel):
    """Create message notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.CREATE_MESSAGE]
    """Notification type discriminator."""

    message: FactoryDroidMessage
    """Factory droid message."""

    parent_id: str | None = Field(default=None, alias="parentId")
    """Optional parent message ID."""

    request_id: str | None = Field(default=None, alias="requestId")
    """Optional request ID."""


class ErrorNotification(BaseModel):
    """Error notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.ERROR]
    """Notification type discriminator."""

    message: str
    """Error message."""

    error_type: DroidErrorType = Field(alias="errorType")
    """Error type."""

    timestamp: str
    """ISO 8601 timestamp."""

    error: ErrorDetail | None = None
    """Optional error detail object."""


class DroidWorkingStateChangedNotification(BaseModel):
    """Droid working state changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.DROID_WORKING_STATE_CHANGED]
    """Notification type discriminator."""

    new_state: DroidWorkingState = Field(alias="newState")
    """New working state."""


class SessionCompactedNotification(BaseModel):
    """Conversation compaction boundary update."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_COMPACTED]
    summary_id: str = Field(alias="summaryId")
    removed_count: int = Field(alias="removedCount", ge=0)
    visible_boundary_message_id: str | None = Field(alias="visibleBoundaryMessageId")


class LoopStateChangedNotification(BaseModel):
    """Deprecated loop-state update retained for wire compatibility."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.LOOP_STATE_CHANGED]
    loop_state: dict[str, Any] = Field(alias="loopState")


class PermissionResolvedNotification(BaseModel):
    """Permission resolved notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.PERMISSION_RESOLVED]
    """Notification type discriminator."""

    request_id: str = Field(alias="requestId")
    """Request ID that was resolved."""

    tool_use_ids: list[str] = Field(alias="toolUseIds")
    """Array of tool use IDs (batched permission requests)."""

    selected_option: ToolConfirmationOutcome = Field(alias="selectedOption")
    """Selected permission outcome."""


class SettingsUpdatedNotification(BaseModel):
    """Settings updated notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SETTINGS_UPDATED]
    """Notification type discriminator."""

    request_id: str | None = Field(default=None, alias="requestId")
    settings: SettingsUpdatedPayload
    """Updated settings."""


class SessionTitleUpdatedNotification(BaseModel):
    """Session title updated notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_TITLE_UPDATED]
    """Notification type discriminator."""

    request_id: str | None = Field(default=None, alias="requestId")
    title: str
    """New session title."""


class SessionWorkingDirectoryChangedNotification(BaseModel):
    """Working-directory update."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_WORKING_DIRECTORY_CHANGED]
    cwd: str


class ChildSessionAvailableNotification(BaseModel):
    """Notification that a delegated child session is available."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.CHILD_SESSION_AVAILABLE]
    child_session_id: str = Field(alias="childSessionId")
    tool_use_id: str | None = Field(default=None, alias="toolUseId")
    subagent_type: str | None = Field(default=None, alias="subagentType")
    description: str | None = None
    timestamp: float


class McpStatusChangedNotification(BaseModel):
    """MCP status changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MCP_STATUS_CHANGED]
    """Notification type discriminator."""

    servers: list[McpServerStatusInfo]
    """MCP server status information."""

    summary: McpStatusSummary
    """MCP status summary."""


class AssistantTextDeltaNotification(BaseModel):
    """Assistant text delta notification (streaming token)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.ASSISTANT_TEXT_DELTA]
    """Notification type discriminator."""

    message_id: str = Field(alias="messageId")
    """Message ID being streamed."""

    block_index: int = Field(alias="blockIndex")
    """Content block index."""

    text_delta: str = Field(alias="textDelta")
    """Text delta content."""


class AssistantTextCompleteNotification(BaseModel):
    """Marks completion of a streamed assistant text block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.ASSISTANT_TEXT_COMPLETE]
    message_id: str = Field(alias="messageId")
    block_index: int = Field(alias="blockIndex")


class StructuredOutputNotification(BaseModel):
    """Structured output produced for a message."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.STRUCTURED_OUTPUT]
    message_id: str = Field(alias="messageId")
    structured_output: dict[str, Any] | None = Field(alias="structuredOutput")


class ThinkingTextDeltaNotification(BaseModel):
    """Thinking text delta notification (streaming thinking token)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.THINKING_TEXT_DELTA]
    """Notification type discriminator."""

    message_id: str = Field(alias="messageId")
    """Message ID being streamed."""

    block_index: int = Field(alias="blockIndex")
    """Content block index."""

    text_delta: str = Field(alias="textDelta")
    """Text delta content."""


class ThinkingTextCompleteNotification(BaseModel):
    """Marks completion of a streamed thinking block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.THINKING_TEXT_COMPLETE]
    message_id: str = Field(alias="messageId")
    block_index: int = Field(alias="blockIndex")
    duration_ms: float | None = Field(default=None, alias="durationMs", ge=0)


class SessionTokenUsageChangedNotification(BaseModel):
    """Session token usage changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED]
    """Notification type discriminator."""

    session_id: str = Field(alias="sessionId")
    """Session ID."""

    token_usage: TokenUsage = Field(alias="tokenUsage")
    """Updated token usage."""

    inclusive_token_usage: TokenUsage | None = Field(
        default=None, alias="inclusiveTokenUsage"
    )
    last_call_token_usage: LastCallTokenUsage | None = Field(
        default=None, alias="lastCallTokenUsage"
    )


class AgentTurnCompletedNotification(BaseModel):
    """Terminal notification for an agent turn."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.AGENT_TURN_COMPLETED]
    reason: AgentTurnCompletionReason
    turn_id: str | None = Field(default=None, alias="turnId")
    token_usage: TokenUsage = Field(alias="tokenUsage")
    cumulative_token_usage: TokenUsage | None = Field(
        default=None, alias="cumulativeTokenUsage"
    )
    child_token_usage: TokenUsage | None = Field(default=None, alias="childTokenUsage")
    cumulative_child_token_usage: TokenUsage | None = Field(
        default=None, alias="cumulativeChildTokenUsage"
    )
    duration_ms: float | None = Field(default=None, alias="durationMs", ge=0)


class MissionStateChangedNotification(BaseModel):
    """Mission state changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_STATE_CHANGED]
    """Notification type discriminator."""

    state: MissionState
    """New mission state."""

    updated_at: str | None = Field(default=None, alias="updatedAt")


class MissionFeaturesChangedNotification(BaseModel):
    """Mission features changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_FEATURES_CHANGED]
    """Notification type discriminator."""

    features: list[MissionFeature]
    """Updated mission features."""


class MissionProgressEntryNotification(BaseModel):
    """Mission progress entry notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_PROGRESS_ENTRY]
    """Notification type discriminator."""

    progress_log: list[ProgressLogEntry] = Field(alias="progressLog")
    """Progress log entries."""


class MissionHeartbeatNotification(BaseModel):
    """Mission heartbeat notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_HEARTBEAT]
    """Notification type discriminator."""

    timestamp: str
    """ISO 8601 heartbeat timestamp."""


class MissionWorkerStartedNotification(BaseModel):
    """Mission worker started notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_WORKER_STARTED]
    """Notification type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""


class MissionWorkerCompletedNotification(BaseModel):
    """Mission worker completed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_WORKER_COMPLETED]
    """Notification type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""

    exit_code: int = Field(alias="exitCode")
    """Worker process exit code."""


class McpAuthRequiredNotification(BaseModel):
    """MCP authentication required notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MCP_AUTH_REQUIRED]
    """Notification type discriminator."""

    server_name: str = Field(alias="serverName")
    """MCP server name."""

    auth_url: str = Field(alias="authUrl")
    """Authentication URL."""

    message: str
    """Authentication message."""

    state: str
    """Authentication state token."""


class McpAuthCompletedNotification(BaseModel):
    """MCP authentication completed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MCP_AUTH_COMPLETED]
    """Notification type discriminator."""

    server_name: str = Field(alias="serverName")
    """MCP server name."""

    outcome: McpAuthOutcome
    """Authentication outcome."""

    message: str
    """Authentication result message."""


class HookCommand(BaseModel):
    """Command configured for a hook."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    command: str
    timeout: float | None = None


class HookResult(BaseModel):
    """Result of a hook command."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    exit_code: int = Field(alias="exitCode")
    stdout: str
    stderr: str
    command: str | None = None
    timeout: float | None = None
    suppress_output: bool | None = Field(default=None, alias="suppressOutput")


class HookExecutionStartedNotification(BaseModel):
    """Hook execution began."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.HOOK_EXECUTION_STARTED]
    hook_id: str = Field(alias="hookId")
    hook_event_name: str = Field(alias="hookEventName")
    hook_matcher: str | None = Field(default=None, alias="hookMatcher")
    hook_commands: list[HookCommand] = Field(alias="hookCommands")
    hook_tool_call_id: str | None = Field(default=None, alias="hookToolCallId")
    hook_parent_id: str | None = Field(default=None, alias="hookParentId")
    hook_order: int | None = Field(default=None, alias="hookOrder")
    hidden_from_user_views: bool | None = Field(
        default=None, alias="hiddenFromUserViews"
    )
    is_parallel_execution: bool | None = Field(
        default=None, alias="isParallelExecution"
    )
    parallel_group_id: str | None = Field(default=None, alias="parallelGroupId")


class HookExecutionCompletedNotification(BaseModel):
    """Hook execution completed."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.HOOK_EXECUTION_COMPLETED]
    hook_id: str = Field(alias="hookId")
    hook_event_name: str | None = Field(default=None, alias="hookEventName")
    hook_matcher: str | None = Field(default=None, alias="hookMatcher")
    hook_tool_call_id: str | None = Field(default=None, alias="hookToolCallId")
    hook_parent_id: str | None = Field(default=None, alias="hookParentId")
    hook_order: int | None = Field(default=None, alias="hookOrder")
    hook_prevented_action: bool | None = Field(
        default=None, alias="hookPreventedAction"
    )
    hidden_from_user_views: bool | None = Field(
        default=None, alias="hiddenFromUserViews"
    )
    hook_status: Literal["completed", "error"] = Field(alias="hookStatus")
    hook_results: list[HookResult] | None = Field(default=None, alias="hookResults")


class ToolCallNotification(BaseModel):
    """Completed tool-call input notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.TOOL_CALL]
    tool_use: ToolUse = Field(alias="toolUse")


class QueuedMessagesDiscardedNotification(BaseModel):
    """Queued messages were discarded."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.QUEUED_MESSAGES_DISCARDED]
    text: str
    request_id: str | None = Field(default=None, alias="requestId")


class ToolExecutionHeartbeatNotification(BaseModel):
    """Internal heartbeat for a long-running tool."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.TOOL_EXECUTION_HEARTBEAT]
    tool_use_id: str = Field(alias="toolUseId")
    tool_name: str = Field(alias="toolName")


class ToolExecutionPhaseChangedNotification(BaseModel):
    """Tool execution lifecycle update."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.TOOL_EXECUTION_PHASE_CHANGED]
    tool_use_id: str = Field(alias="toolUseId")
    tool_name: str = Field(alias="toolName")
    phase: ToolExecutionLifecyclePhase


class LlmRetryNotification(BaseModel):
    """Coarse LLM retry status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.LLM_RETRY]
    attempt: int
    reason: LlmRetryReason


class SandboxStatus(BaseModel):
    """Current sandbox status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    enabled: bool
    mode: SandboxMode | None = None


# ============================================================
# SessionNotification discriminated union
# ============================================================

SessionNotificationUnion = Annotated[
    ToolResultNotification
    | ToolProgressUpdateNotification
    | CreateMessageNotification
    | ErrorNotification
    | DroidWorkingStateChangedNotification
    | SessionCompactedNotification
    | LoopStateChangedNotification
    | PermissionResolvedNotification
    | SettingsUpdatedNotification
    | SessionTitleUpdatedNotification
    | SessionWorkingDirectoryChangedNotification
    | ChildSessionAvailableNotification
    | McpStatusChangedNotification
    | AssistantTextDeltaNotification
    | AssistantTextCompleteNotification
    | StructuredOutputNotification
    | ThinkingTextDeltaNotification
    | ThinkingTextCompleteNotification
    | SessionTokenUsageChangedNotification
    | AgentTurnCompletedNotification
    | MissionStateChangedNotification
    | MissionFeaturesChangedNotification
    | MissionProgressEntryNotification
    | MissionHeartbeatNotification
    | MissionWorkerStartedNotification
    | MissionWorkerCompletedNotification
    | McpAuthRequiredNotification
    | McpAuthCompletedNotification
    | HookExecutionStartedNotification
    | HookExecutionCompletedNotification
    | ToolCallNotification
    | QueuedMessagesDiscardedNotification
    | ToolExecutionHeartbeatNotification
    | ToolExecutionPhaseChangedNotification
    | LlmRetryNotification,
    Field(discriminator="type"),
]


class SessionNotificationParams(BaseModel):
    """Parameters for session notification (wraps the discriminated union)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    notification: SessionNotificationUnion
    """Discriminated notification payload."""

    session_id: str | None = Field(default=None, alias="sessionId")


class SessionNotification(JsonRpcNotification):
    """Full session notification with JSON-RPC envelope.

    Dispatches on ``params.notification.type`` to one of 20 payload types.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    method: Literal[DroidClientMethod.SESSION_NOTIFICATION]
    """Method name literal."""

    params: SessionNotificationParams  # type: ignore[assignment]
    """Typed notification parameters."""


# ============================================================
# Tool confirmation details discriminated union
# ============================================================


class EditToolConfirmationDetails(BaseModel):
    """Edit tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.Edit]
    """Confirmation type discriminator."""

    file_path: str = Field(alias="filePath")
    """File path being edited."""

    file_name: str = Field(alias="fileName")
    """File name being edited."""

    old_content: str | None = Field(default=None, alias="oldContent")
    """Optional old content."""

    new_content: str | None = Field(default=None, alias="newContent")
    """Optional new content."""


class ExecuteToolConfirmationDetails(BaseModel):
    """Execute tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.Execute]
    """Confirmation type discriminator."""

    full_command: str = Field(alias="fullCommand")
    """Full command string."""

    command: str
    """Command name."""

    extracted_commands: list[str] | None = Field(
        default=None, alias="extractedCommands"
    )
    """Optional extracted sub-commands."""

    impact_level: str | None = Field(default=None, alias="impactLevel")
    """Optional impact level assessment."""

    risk_level_reason: str | None = Field(default=None, alias="riskLevelReason")


class CreateToolConfirmationDetails(BaseModel):
    """Create tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.Create]
    """Confirmation type discriminator."""

    file_path: str = Field(alias="filePath")
    """File path being created."""

    file_name: str = Field(alias="fileName")
    """File name being created."""

    content: str
    """File content."""


class AskUserConfirmationParsed(BaseModel):
    """Parsed ask-user questionnaire within confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    questions: list[AskUserQuestion]
    """Parsed questions (index, topic, question, options)."""


class AskUserConfirmationParseError(BaseModel):
    """Parse error for ask-user questionnaire."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    message: str
    """Error message."""

    line: int | None = None
    """Optional line number where error occurred."""


class AskUserConfirmationDetails(BaseModel):
    """Ask user confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.AskUser]
    """Confirmation type discriminator."""

    questionnaire: str
    """Raw questionnaire text."""

    parsed: AskUserConfirmationParsed | None = None
    """Optional parsed questionnaire."""

    parse_error: AskUserConfirmationParseError | None = Field(
        default=None, alias="parseError"
    )
    """Optional parse error."""


class ExitSpecModeConfirmationDetails(BaseModel):
    """Exit spec mode confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.ExitSpecMode]
    """Confirmation type discriminator."""

    plan: str
    """Plan text."""

    title: str | None = None
    """Optional title."""

    option_names: list[str] | None = Field(default=None, alias="optionNames")
    """Optional option names."""


class ProposeMissionConfirmationDetails(BaseModel):
    """Propose mission confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.ProposeMission]
    """Confirmation type discriminator."""

    proposal: str
    """Mission proposal text."""

    title: str | None = None
    """Optional title."""


class StartMissionRunConfirmationDetails(BaseModel):
    """Start mission run confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.StartMissionRun]
    """Confirmation type discriminator."""

    running_mission_count: int = Field(alias="runningMissionCount")
    """Number of currently running missions."""

    running_mission_session_ids: list[str] = Field(alias="runningMissionSessionIds")
    """Session IDs of running missions."""


class ApplyPatchToolConfirmationDetails(BaseModel):
    """Apply patch tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.ApplyPatch]
    """Confirmation type discriminator."""

    file_path: str = Field(alias="filePath")
    """File path being patched."""

    file_name: str = Field(alias="fileName")
    """File name being patched."""

    patch_content: str = Field(alias="patchContent")
    """Patch content."""

    old_content: str | None = Field(default=None, alias="oldContent")
    """Optional old content."""

    new_content: str | None = Field(default=None, alias="newContent")
    """Optional new content."""

    files: list[dict[str, Any]] | None = None


class McpToolConfirmationDetails(BaseModel):
    """MCP tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.McpTool]
    """Confirmation type discriminator."""

    tool_name: str = Field(alias="toolName")
    """MCP tool name."""

    impact_level: str = Field(alias="impactLevel")
    """Impact level assessment."""

    server_name: str | None = Field(default=None, alias="serverName")
    actual_tool_name: str | None = Field(default=None, alias="actualToolName")


class SandboxViolationConfirmationDetails(BaseModel):
    """Sandbox policy violation confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.SandboxViolation]
    violating_tool_name: str = Field(alias="violatingToolName")
    target: str
    operation_type: SandboxOperationType = Field(alias="operationType")
    violation_type: SandboxViolationType = Field(alias="violationType")
    reason: str
    violation_reason: SandboxViolationReason | None = Field(
        default=None, alias="violationReason"
    )
    is_org_deny: bool = Field(alias="isOrgDeny")


class DroidShieldViolationConfirmationDetails(BaseModel):
    """DroidShield command-policy violation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.DroidShieldViolation]
    command: str
    reason: str


ToolConfirmationDetailsUnion = Annotated[
    EditToolConfirmationDetails
    | ExecuteToolConfirmationDetails
    | CreateToolConfirmationDetails
    | AskUserConfirmationDetails
    | ExitSpecModeConfirmationDetails
    | ProposeMissionConfirmationDetails
    | StartMissionRunConfirmationDetails
    | ApplyPatchToolConfirmationDetails
    | McpToolConfirmationDetails
    | SandboxViolationConfirmationDetails
    | DroidShieldViolationConfirmationDetails,
    Field(discriminator="type"),
]


class ToolConfirmationDetails(RootModel[ToolConfirmationDetailsUnion]):
    """Discriminated union over tool confirmation detail types.

    Dispatches on the ``type`` field to the appropriate detail model.
    """


class ToolConfirmationInfo(BaseModel):
    """Tool confirmation information (toolUse + confirmationType + details)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tool_use: ToolUse = Field(alias="toolUse")
    """The tool use that requires confirmation."""

    confirmation_type: ToolConfirmationType = Field(alias="confirmationType")
    """Type of confirmation required."""

    details: ToolConfirmationDetails
    """Confirmation details (discriminated union)."""


# ============================================================
# RequestPermissionRequest
# ============================================================


class RequestPermissionRequestParams(BaseModel):
    """Parameters for droid.request_permission request."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tool_uses: list[ToolConfirmationInfo] = Field(alias="toolUses")
    """Tool uses requiring permission."""

    options: list[ToolConfirmationListItem]
    """Available permission options."""

    associated_session_ids: list[str] | None = Field(
        default=None, alias="associatedSessionIds"
    )


class RequestPermissionRequest(JsonRpcRequest):
    """Request for permission from the server (server→client)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    method: Literal[DroidClientMethod.REQUEST_PERMISSION]
    """Method name literal."""

    params: RequestPermissionRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class RequestPermissionResult(BaseModel):
    """Result for droid.request_permission response."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    selected_option: ToolConfirmationOutcome = Field(alias="selectedOption")
    """Selected permission outcome."""

    comment: str | None = None
    edited_spec_content: str | None = Field(default=None, alias="editedSpecContent")

    @model_validator(mode="after")
    def require_edited_spec_content(self) -> RequestPermissionResult:
        """Require edited content for the proceed-edit outcome."""
        if (
            self.selected_option == ToolConfirmationOutcome.ProceedEdit
            and self.edited_spec_content is None
        ):
            raise ValueError(
                "editedSpecContent is required when selectedOption is proceed_edit"
            )
        return self


# ============================================================
# AskUserRequest
# ============================================================


class AskUserQuestion(BaseModel):
    """A question in the ask-user questionnaire."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    index: int
    """1-based question index."""

    topic: str
    """Topic label for UI navigation."""

    question: str
    """Question text."""

    options: list[str]
    """Available options."""

    multi_select: bool | None = Field(default=None, alias="multiSelect")


class AskUserRequestParams(BaseModel):
    """Parameters for droid.ask_user request."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tool_call_id: str = Field(alias="toolCallId")
    """Tool call ID that initiated this request."""

    questions: list[AskUserQuestion]
    """Questions to present to the user."""


class AskUserRequest(JsonRpcRequest):
    """Ask user request from the server (server→client)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    method: Literal[DroidClientMethod.ASK_USER]
    """Method name literal."""

    params: AskUserRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class AskUserCollectedAnswer(BaseModel):
    """A collected answer from the user."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    index: int
    """1-based answer index."""

    question: str
    """Original question text."""

    answer: str
    """User's answer."""


class AskUserResult(BaseModel):
    """Result for droid.ask_user response."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    cancelled: bool | None = None
    """Whether the user cancelled the questionnaire."""

    answers: list[AskUserCollectedAnswer]
    """Collected answers."""


# ============================================================
# CliRequestOrNotification discriminated union
# ============================================================

CliRequestOrNotificationUnion = Annotated[
    SessionNotification | RequestPermissionRequest | AskUserRequest,
    Field(discriminator="method"),
]


class CliRequestOrNotification(RootModel[CliRequestOrNotificationUnion]):
    """Discriminated union over all 3 server→client methods.

    Dispatches on the ``method`` field:
    - ``droid.session_notification`` → SessionNotification
    - ``droid.request_permission`` → RequestPermissionRequest
    - ``droid.ask_user`` → AskUserRequest
    """
