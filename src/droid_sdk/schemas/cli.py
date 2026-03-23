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

from pydantic import BaseModel, ConfigDict, Field, RootModel

# Re-use TokenUsage from client module
from droid_sdk.schemas.client import TokenUsage  # noqa: TC001
from droid_sdk.schemas.enums import (  # noqa: TC001
    AutonomyLevel,
    AutonomyMode,
    DroidClientMethod,
    DroidErrorType,
    DroidInteractionMode,
    DroidWorkingState,
    McpAuthOutcome,
    MissionState,
    ReasoningEffort,
    SessionNotificationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
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
from droid_sdk.schemas.shared import (
    JsonRpcNotification,
    JsonRpcRequest,
)

__all__ = [
    "ApplyPatchToolConfirmationDetails",
    "AskUserCollectedAnswer",
    "AskUserConfirmationDetails",
    "AskUserConfirmationParseError",
    "AskUserConfirmationParsed",
    "AskUserQuestion",
    "AskUserRequest",
    "AskUserRequestParams",
    "AskUserResult",
    "AssistantTextDeltaNotification",
    "CliRequestOrNotification",
    "CreateMessageNotification",
    "CreateToolConfirmationDetails",
    "DroidWorkingStateChangedNotification",
    "EditToolConfirmationDetails",
    "ErrorDetail",
    "ErrorNotification",
    "ExecuteToolConfirmationDetails",
    "ExitSpecModeConfirmationDetails",
    "FactoryDroidMessage",
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
    "RequestPermissionRequest",
    "RequestPermissionRequestParams",
    "RequestPermissionResult",
    "SessionNotification",
    "SessionNotificationParams",
    "SessionTitleUpdatedNotification",
    "SessionTokenUsageChangedNotification",
    "SettingsUpdatedNotification",
    "SettingsUpdatedPayload",
    "StartMissionRunConfirmationDetails",
    "ThinkingTextDeltaNotification",
    "ToolConfirmationDetails",
    "ToolConfirmationInfo",
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

    settings: SettingsUpdatedPayload
    """Updated settings."""


class SessionTitleUpdatedNotification(BaseModel):
    """Session title updated notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_TITLE_UPDATED]
    """Notification type discriminator."""

    title: str
    """New session title."""


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


class SessionTokenUsageChangedNotification(BaseModel):
    """Session token usage changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.SESSION_TOKEN_USAGE_CHANGED]
    """Notification type discriminator."""

    session_id: str = Field(alias="sessionId")
    """Session ID."""

    token_usage: TokenUsage = Field(alias="tokenUsage")
    """Updated token usage."""


class MissionStateChangedNotification(BaseModel):
    """Mission state changed notification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[SessionNotificationType.MISSION_STATE_CHANGED]
    """Notification type discriminator."""

    state: MissionState
    """New mission state."""


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


# ============================================================
# SessionNotification discriminated union
# ============================================================

SessionNotificationUnion = Annotated[
    ToolResultNotification
    | ToolProgressUpdateNotification
    | CreateMessageNotification
    | ErrorNotification
    | DroidWorkingStateChangedNotification
    | PermissionResolvedNotification
    | SettingsUpdatedNotification
    | SessionTitleUpdatedNotification
    | McpStatusChangedNotification
    | AssistantTextDeltaNotification
    | ThinkingTextDeltaNotification
    | SessionTokenUsageChangedNotification
    | MissionStateChangedNotification
    | MissionFeaturesChangedNotification
    | MissionProgressEntryNotification
    | MissionHeartbeatNotification
    | MissionWorkerStartedNotification
    | MissionWorkerCompletedNotification
    | McpAuthRequiredNotification
    | McpAuthCompletedNotification,
    Field(discriminator="type"),
]


class SessionNotificationParams(BaseModel):
    """Parameters for session notification (wraps the discriminated union)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    notification: SessionNotificationUnion
    """Discriminated notification payload."""


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


class McpToolConfirmationDetails(BaseModel):
    """MCP tool confirmation details."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[ToolConfirmationType.McpTool]
    """Confirmation type discriminator."""

    tool_name: str = Field(alias="toolName")
    """MCP tool name."""

    impact_level: str = Field(alias="impactLevel")
    """Impact level assessment."""


ToolConfirmationDetailsUnion = Annotated[
    EditToolConfirmationDetails
    | ExecuteToolConfirmationDetails
    | CreateToolConfirmationDetails
    | AskUserConfirmationDetails
    | ExitSpecModeConfirmationDetails
    | ProposeMissionConfirmationDetails
    | StartMissionRunConfirmationDetails
    | ApplyPatchToolConfirmationDetails
    | McpToolConfirmationDetails,
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
