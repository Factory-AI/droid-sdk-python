"""Client→server request/response Pydantic schemas for the Factory Droid protocol.

All 19 client→server RPC method request/response pairs, plus supporting types
and the ClientRequest discriminated union.

Ported from TypeScript source:
- packages/common/src/droid/schemas/client.ts
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from droid_sdk.schemas.enums import (  # noqa: TC001
    AutonomyLevel,
    AutonomyMode,
    DecompSessionType,
    DroidInteractionMode,
    DroidServerMethod,
    McpServerType,
    MissionState,
    ModelProvider,
    ReasoningEffort,
    SettingsLevel,
    SkillLocation,
)
from droid_sdk.schemas.mcp import (  # noqa: TC001
    McpRegistryServer,
    McpServerStatusInfo,
    McpStatusSummary,
    McpToolInfo,
)
from droid_sdk.schemas.mission import (  # noqa: TC001
    MissionFeature,
    ProgressLogEntry,
)
from droid_sdk.schemas.shared import (
    JsonRpcRequest,
    JsonRpcResponseFailure,
    JsonRpcResponseSuccess,
)

__all__ = [
    # Request schemas
    "AddMcpServerRequest",
    # Supporting types
    "AddMcpServerRequestParams",
    # Response schemas
    "AddMcpServerResponse",
    # Result schemas
    "AddMcpServerResult",
    "AddUserMessageRequest",
    "AddUserMessageRequestParams",
    "AddUserMessageResponse",
    "AddUserMessageResult",
    "AuthenticateMcpServerRequest",
    "AuthenticateMcpServerRequestParams",
    "AuthenticateMcpServerResponse",
    "AuthenticateMcpServerResult",
    "AvailableModelConfig",
    "Base64ImageSource",
    "CancelMcpAuthRequest",
    "CancelMcpAuthRequestParams",
    "CancelMcpAuthResponse",
    "CancelMcpAuthResult",
    "ClearMcpAuthRequest",
    "ClearMcpAuthRequestParams",
    "ClearMcpAuthResponse",
    "ClearMcpAuthResult",
    "ClientRequest",
    "DocumentSource",
    "GitRepoInfo",
    "HttpHeader",
    "HttpMcpConfig",
    "InitializeSessionRequest",
    "InitializeSessionRequestParams",
    "InitializeSessionResponse",
    "InitializeSessionResult",
    "InterruptSessionRequest",
    "InterruptSessionRequestParams",
    "InterruptSessionResponse",
    "InterruptSessionResult",
    "KillWorkerSessionRequest",
    "KillWorkerSessionRequestParams",
    "KillWorkerSessionResponse",
    "KillWorkerSessionResult",
    "ListMcpRegistryRequest",
    "ListMcpRegistryRequestParams",
    "ListMcpRegistryResponse",
    "ListMcpRegistryResult",
    "ListMcpServersRequest",
    "ListMcpServersRequestParams",
    "ListMcpServersResponse",
    "ListMcpServersResult",
    "ListMcpToolsRequest",
    "ListMcpToolsRequestParams",
    "ListMcpToolsResponse",
    "ListMcpToolsResult",
    "ListSkillsRequest",
    "ListSkillsRequestParams",
    "ListSkillsResponse",
    "ListSkillsResult",
    "LoadSessionRequest",
    "LoadSessionRequestParams",
    "LoadSessionResponse",
    "LoadSessionResult",
    "MissionSnapshot",
    "RemoveMcpServerRequest",
    "RemoveMcpServerRequestParams",
    "RemoveMcpServerResponse",
    "RemoveMcpServerResult",
    "SessionSettings",
    "SessionSource",
    "SessionTag",
    "SkillInfo",
    "SkillResource",
    "SseMcpConfig",
    "StdioMcpConfig",
    "SubmitBugReportRequest",
    "SubmitBugReportRequestParams",
    "SubmitBugReportResponse",
    "SubmitBugReportResult",
    "SubmitMcpAuthCodeRequest",
    "SubmitMcpAuthCodeRequestParams",
    "SubmitMcpAuthCodeResponse",
    "SubmitMcpAuthCodeResult",
    "ToggleMcpServerRequest",
    "ToggleMcpServerRequestParams",
    "ToggleMcpServerResponse",
    "ToggleMcpServerResult",
    "ToggleMcpToolRequest",
    "ToggleMcpToolRequestParams",
    "ToggleMcpToolResponse",
    "ToggleMcpToolResult",
    "TokenUsage",
    "UpdateSessionSettingsRequest",
    "UpdateSessionSettingsRequestParams",
    "UpdateSessionSettingsResponse",
    "UpdateSessionSettingsResult",
    "WorkerStateInfo",
]


# ============================================================
# Supporting types (used in request params and result schemas)
# ============================================================


class Base64ImageSource(BaseModel):
    """Base64-encoded image source for user messages."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["base64"]
    """Source type, always 'base64'."""

    data: str
    """Base64-encoded image data."""

    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = Field(
        alias="mediaType"
    )
    """MIME type of the image."""


class DocumentSource(BaseModel):
    """Document source for user messages (PDF or plain text).

    Simplified schema — captures all document source fields.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: str
    """Document source type ('base64' for PDF, 'text' for plain text)."""

    media_type: str = Field(alias="mediaType")
    """MIME type (e.g., 'application/pdf', 'text/plain')."""

    data: str
    """Document data (base64-encoded for PDF, raw text for plain text)."""

    name: str | None = None
    """Optional file name."""

    mime: str | None = None
    """Optional additional MIME type info."""


class SessionTag(BaseModel):
    """Session tag metadata."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    """Tag name."""

    metadata: dict[str, str] | None = None
    """Optional key-value metadata."""


class SessionSource(BaseModel):
    """Session source information.

    Simplified schema that accepts any session source platform.
    Uses ``extra='allow'`` to accept platform-specific fields.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    platform: str
    """Source platform identifier (e.g. 'slack', 'web', 'api', 'linear')."""


class StdioMcpConfig(BaseModel):
    """Stdio MCP server configuration for initialization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    """Server name identifier."""

    command: str
    """Command to spawn the MCP server process."""

    args: list[str] = Field(default_factory=list)
    """Arguments passed to the command."""

    env: dict[str, str] = Field(default_factory=dict)
    """Environment variables for the server process."""


class HttpHeader(BaseModel):
    """HTTP header for MCP server configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    """Header name."""

    value: str
    """Header value."""


class HttpMcpConfig(BaseModel):
    """HTTP MCP server configuration for initialization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["http"]
    """Transport type, always 'http'."""

    name: str
    """Server name identifier."""

    url: str
    """URL endpoint for the MCP server."""

    headers: list[HttpHeader] = Field(default_factory=list)
    """HTTP headers for authentication."""


class SseMcpConfig(BaseModel):
    """SSE MCP server configuration for initialization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["sse"]
    """Transport type, always 'sse'."""

    name: str
    """Server name identifier."""

    url: str
    """URL endpoint for the MCP server."""

    headers: list[HttpHeader] = Field(default_factory=list)
    """HTTP headers for authentication."""


class SessionSettings(BaseModel):
    """Session settings returned in init/load results."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    model_id: str = Field(alias="modelId")
    """Active model identifier."""

    reasoning_effort: ReasoningEffort = Field(alias="reasoningEffort")
    """Current reasoning effort level."""

    autonomy_mode: AutonomyMode | None = Field(default=None, alias="autonomyMode")
    """Deprecated: use interaction_mode + autonomy_level instead."""

    interaction_mode: DroidInteractionMode | None = Field(
        default=None, alias="interactionMode"
    )
    """Current interaction mode."""

    autonomy_level: AutonomyLevel | None = Field(default=None, alias="autonomyLevel")
    """Current autonomy level."""

    spec_mode_model_id: str | None = Field(default=None, alias="specModeModelId")
    """Optional spec mode model override."""

    spec_mode_reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="specModeReasoningEffort"
    )
    """Optional spec mode reasoning effort override."""


class GitRepoInfo(BaseModel):
    """Git repository information."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    owner: str | None = None
    """Repository owner (optional)."""

    repo_name: str = Field(alias="repoName")
    """Repository name."""


class AvailableModelConfig(BaseModel):
    """Available model configuration returned in session init/load responses.

    Uses ``extra='allow'`` because the available models list is server-driven
    and can include fields not yet in the SDK. This prevents ``ValidationError``
    when the server adds new fields during protocol evolution.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    """Model identifier."""

    model_id: str | None = Field(default=None, alias="modelId")
    """Model ID (server-provided, may differ from ``id``)."""

    display_name: str = Field(alias="displayName")
    """Human-readable display name."""

    short_display_name: str = Field(alias="shortDisplayName")
    """Short display name."""

    model_provider: ModelProvider = Field(alias="modelProvider")
    """Model provider."""

    supported_reasoning_efforts: list[ReasoningEffort] = Field(
        alias="supportedReasoningEfforts"
    )
    """List of supported reasoning effort levels."""

    default_reasoning_effort: ReasoningEffort = Field(alias="defaultReasoningEffort")
    """Default reasoning effort level."""

    is_custom: bool = Field(default=False, alias="isCustom")
    """Whether this is a custom BYOK model."""

    no_image_support: bool | None = Field(default=None, alias="noImageSupport")
    """Whether the model lacks image support."""

    supports_pdfs: bool | None = Field(default=None, alias="supportsPDFs")
    """Whether the model supports PDF input."""

    tier: str | None = None
    """Optional model tier (e.g. 'standard', 'premium')."""

    token_multiplier: float | None = Field(default=None, alias="tokenMultiplier")
    """Optional token billing multiplier."""

    promo_label: str | None = Field(default=None, alias="promoLabel")
    """Optional promotional label."""

    feature_flag: dict[str, Any] | None = Field(default=None, alias="featureFlag")
    """Optional feature flag gating information."""

    uses_us_based_inference: bool | None = Field(
        default=None, alias="usesUSBasedInference"
    )
    """Whether this model uses US-based inference."""


class TokenUsage(BaseModel):
    """Token usage information for a session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    input_tokens: int = Field(alias="inputTokens")
    """Number of input tokens consumed."""

    output_tokens: int = Field(alias="outputTokens")
    """Number of output tokens generated."""

    cache_creation_tokens: int = Field(alias="cacheCreationTokens")
    """Number of tokens used for cache creation."""

    cache_read_tokens: int = Field(alias="cacheReadTokens")
    """Number of tokens read from cache."""

    thinking_tokens: int = Field(alias="thinkingTokens")
    """Number of tokens used for thinking/reasoning."""


class WorkerStateInfo(BaseModel):
    """Worker state information for mission snapshots."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    started_at: str = Field(alias="startedAt")
    """ISO 8601 timestamp when the worker started."""

    completed_at: str | None = Field(default=None, alias="completedAt")
    """ISO 8601 timestamp when the worker completed (if done)."""

    exit_code: int | None = Field(default=None, alias="exitCode")
    """Worker process exit code (if completed)."""


class SkillResource(BaseModel):
    """Resource file in a skill folder."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Resource file name."""

    path: str
    """Resource file path."""

    type: Literal["reference", "asset"]
    """Resource type ('reference' for .md files, 'asset' for other files)."""


class SkillInfo(BaseModel):
    """Skill information returned by list_skills."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Skill name."""

    description: str | None = None
    """Human-readable description."""

    location: SkillLocation
    """Skill file location type."""

    file_path: str = Field(alias="filePath")
    """Path to the skill file."""

    enabled: bool | None = None
    """Whether the skill is currently enabled."""

    user_invocable: bool | None = Field(default=None, alias="userInvocable")
    """Whether the skill can be invoked by users."""

    version: str | None = None
    """Optional skill version."""

    content: str | None = None
    """Full SKILL.md content (markdown)."""

    resources: list[SkillResource] | None = None
    """Other files in the skill folder."""


# ============================================================
# Request params schemas
# ============================================================


class InitializeSessionRequestParams(BaseModel):
    """Parameters for droid.initialize_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    machine_id: str = Field(alias="machineId")
    """Machine identifier."""

    cwd: str
    """Current working directory."""

    workspace_id: str | None = Field(default=None, alias="workspaceId")
    """Optional workspace to attach the session to."""

    session_id: str | None = Field(default=None, alias="sessionId")
    """Optional specific session ID to create."""

    mcp_servers: list[StdioMcpConfig | HttpMcpConfig | SseMcpConfig] | None = Field(
        default=None, alias="mcpServers"
    )
    """Optional MCP server configurations."""

    autonomy_mode: AutonomyMode | None = Field(default=None, alias="autonomyMode")
    """Deprecated: use interaction_mode + autonomy_level instead."""

    interaction_mode: DroidInteractionMode | None = Field(
        default=None, alias="interactionMode"
    )
    """Interaction mode setting."""

    autonomy_level: AutonomyLevel | None = Field(default=None, alias="autonomyLevel")
    """Autonomy level setting."""

    model_id: str | None = Field(default=None, alias="modelId")
    """Optional model ID to use."""

    reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="reasoningEffort"
    )
    """Optional reasoning effort level."""

    spec_mode_model_id: str | None = Field(default=None, alias="specModeModelId")
    """Optional spec mode model ID."""

    spec_mode_reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="specModeReasoningEffort"
    )
    """Optional spec mode reasoning effort."""

    decomp_session_type: DecompSessionType | None = Field(
        default=None, alias="decompSessionType"
    )
    """Session type for mission decomposition."""

    decomp_mission_id: str | None = Field(default=None, alias="decompMissionId")
    """Mission ID for worker sessions."""

    skip_permissions_unsafe: bool | None = Field(
        default=None, alias="skipPermissionsUnsafe"
    )
    """Skip permission checks (worker sessions)."""

    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    """Additional tool IDs to enable beyond defaults."""

    session_location: str | None = Field(default=None, alias="sessionLocation")
    """Session metadata location."""

    session_source: SessionSource | None = Field(default=None, alias="sessionSource")
    """Session source information."""

    tags: list[SessionTag] | None = None
    """Optional session tags."""

    mcp_oauth_callback_uri: str | None = Field(
        default=None, alias="mcpOAuthCallbackUri"
    )
    """OAuth callback URI for MCP auth relay."""


class LoadSessionRequestParams(BaseModel):
    """Parameters for droid.load_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    session_id: str = Field(alias="sessionId")
    """Session ID to load."""

    mcp_servers: list[StdioMcpConfig | HttpMcpConfig | SseMcpConfig] | None = Field(
        default=None, alias="mcpServers"
    )
    """Optional MCP server configurations."""

    mcp_oauth_callback_uri: str | None = Field(
        default=None, alias="mcpOAuthCallbackUri"
    )
    """OAuth callback URI for MCP auth relay."""


class AddUserMessageRequestParams(BaseModel):
    """Parameters for droid.add_user_message request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    message_id: str | None = Field(default=None, alias="messageId")
    """Optional message identifier."""

    text: str
    """Message text content."""

    images: list[Base64ImageSource] | None = None
    """Optional attached images."""

    files: list[DocumentSource] | None = None
    """Optional attached files."""


class InterruptSessionRequestParams(BaseModel):
    """Parameters for droid.interrupt_session request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class KillWorkerSessionRequestParams(BaseModel):
    """Parameters for droid.kill_worker_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session ID to kill."""


class UpdateSessionSettingsRequestParams(BaseModel):
    """Parameters for droid.update_session_settings request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    model_id: str | None = Field(default=None, alias="modelId")
    """Optional model ID to set."""

    reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="reasoningEffort"
    )
    """Optional reasoning effort level."""

    autonomy_mode: AutonomyMode | None = Field(default=None, alias="autonomyMode")
    """Deprecated: use interaction_mode + autonomy_level instead."""

    interaction_mode: DroidInteractionMode | None = Field(
        default=None, alias="interactionMode"
    )
    """Optional interaction mode."""

    autonomy_level: AutonomyLevel | None = Field(default=None, alias="autonomyLevel")
    """Optional autonomy level."""

    spec_mode_model_id: str | None = Field(default=None, alias="specModeModelId")
    """Optional spec mode model ID (nullable to clear)."""

    spec_mode_reasoning_effort: ReasoningEffort | None = Field(
        default=None, alias="specModeReasoningEffort"
    )
    """Optional spec mode reasoning effort (nullable to clear)."""


class ToggleMcpServerRequestParams(BaseModel):
    """Parameters for droid.toggle_mcp_server request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name."""

    enabled: bool
    """Whether to enable or disable the server."""

    settings_level: Literal[SettingsLevel.User] = Field(alias="settingsLevel")
    """Settings level (always 'user' for MCP config mutations)."""


class AuthenticateMcpServerRequestParams(BaseModel):
    """Parameters for droid.authenticate_mcp_server request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name to authenticate."""


class CancelMcpAuthRequestParams(BaseModel):
    """Parameters for droid.cancel_mcp_auth request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name."""


class ClearMcpAuthRequestParams(BaseModel):
    """Parameters for droid.clear_mcp_auth request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name."""


class SubmitMcpAuthCodeRequestParams(BaseModel):
    """Parameters for droid.submit_mcp_auth_code request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name."""

    code: str
    """Authentication code."""

    state: str
    """Authentication state token."""


class AddMcpServerRequestParams(BaseModel):
    """Parameters for droid.add_mcp_server request.

    Merges stdio and http config fields — only relevant fields
    need to be populated based on the ``type`` field.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    """Server name identifier."""

    type: McpServerType
    """Transport type (stdio or http)."""

    # HTTP config fields
    url: str | None = None
    """URL endpoint (for http servers)."""

    headers: dict[str, str] | None = None
    """HTTP headers (for http servers)."""

    # Stdio config fields
    command: str | None = None
    """Command to spawn (for stdio servers)."""

    args: list[str] | None = None
    """Command arguments (for stdio servers)."""

    env: dict[str, str] | None = None
    """Environment variables (for stdio servers)."""


class RemoveMcpServerRequestParams(BaseModel):
    """Parameters for droid.remove_mcp_server request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name to remove."""

    settings_level: Literal[SettingsLevel.User] = Field(alias="settingsLevel")
    """Settings level (always 'user')."""


class ListMcpRegistryRequestParams(BaseModel):
    """Parameters for droid.list_mcp_registry request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ListMcpToolsRequestParams(BaseModel):
    """Parameters for droid.list_mcp_tools request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ListMcpServersRequestParams(BaseModel):
    """Parameters for droid.list_mcp_servers request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ToggleMcpToolRequestParams(BaseModel):
    """Parameters for droid.toggle_mcp_tool request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    """MCP server name."""

    tool_name: str = Field(alias="toolName")
    """Tool name to toggle."""

    enabled: bool
    """Whether to enable or disable the tool."""


class ListSkillsRequestParams(BaseModel):
    """Parameters for droid.list_skills request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubmitBugReportRequestParams(BaseModel):
    """Parameters for droid.submit_bug_report request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    user_comment: str = Field(alias="userComment")
    """User's bug report comment."""

    client_logs: str | None = Field(default=None, alias="clientLogs")
    """Optional client log data."""


# ============================================================
# Request schemas (JsonRpcRequest + method literal + typed params)
# ============================================================


class InitializeSessionRequest(JsonRpcRequest):
    """Request to initialize a new session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.INITIALIZE_SESSION]
    """Method name literal."""

    params: InitializeSessionRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class LoadSessionRequest(JsonRpcRequest):
    """Request to load an existing session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.LOAD_SESSION]
    """Method name literal."""

    params: LoadSessionRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class AddUserMessageRequest(JsonRpcRequest):
    """Request to add a user message to the session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.ADD_USER_MESSAGE]
    """Method name literal."""

    params: AddUserMessageRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class InterruptSessionRequest(JsonRpcRequest):
    """Request to interrupt the current session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.INTERRUPT_SESSION]
    """Method name literal."""

    params: InterruptSessionRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class KillWorkerSessionRequest(JsonRpcRequest):
    """Request to kill a worker session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.KILL_WORKER_SESSION]
    """Method name literal."""

    params: KillWorkerSessionRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class UpdateSessionSettingsRequest(JsonRpcRequest):
    """Request to update session settings."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.UPDATE_SESSION_SETTINGS]
    """Method name literal."""

    params: UpdateSessionSettingsRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ToggleMcpServerRequest(JsonRpcRequest):
    """Request to toggle an MCP server."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.TOGGLE_MCP_SERVER]
    """Method name literal."""

    params: ToggleMcpServerRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class AuthenticateMcpServerRequest(JsonRpcRequest):
    """Request to authenticate an MCP server."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.AUTHENTICATE_MCP_SERVER]
    """Method name literal."""

    params: AuthenticateMcpServerRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class CancelMcpAuthRequest(JsonRpcRequest):
    """Request to cancel MCP authentication."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.CANCEL_MCP_AUTH]
    """Method name literal."""

    params: CancelMcpAuthRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ClearMcpAuthRequest(JsonRpcRequest):
    """Request to clear MCP auth tokens."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.CLEAR_MCP_AUTH]
    """Method name literal."""

    params: ClearMcpAuthRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class SubmitMcpAuthCodeRequest(JsonRpcRequest):
    """Request to submit an MCP auth code."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.SUBMIT_MCP_AUTH_CODE]
    """Method name literal."""

    params: SubmitMcpAuthCodeRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class AddMcpServerRequest(JsonRpcRequest):
    """Request to add an MCP server."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.ADD_MCP_SERVER]
    """Method name literal."""

    params: AddMcpServerRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class RemoveMcpServerRequest(JsonRpcRequest):
    """Request to remove an MCP server."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.REMOVE_MCP_SERVER]
    """Method name literal."""

    params: RemoveMcpServerRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ListMcpRegistryRequest(JsonRpcRequest):
    """Request to list MCP registry servers."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.LIST_MCP_REGISTRY]
    """Method name literal."""

    params: ListMcpRegistryRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ListMcpToolsRequest(JsonRpcRequest):
    """Request to list MCP tools."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.LIST_MCP_TOOLS]
    """Method name literal."""

    params: ListMcpToolsRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ListMcpServersRequest(JsonRpcRequest):
    """Request to list MCP servers."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.LIST_MCP_SERVERS]
    """Method name literal."""

    params: ListMcpServersRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ToggleMcpToolRequest(JsonRpcRequest):
    """Request to toggle an MCP tool."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.TOGGLE_MCP_TOOL]
    """Method name literal."""

    params: ToggleMcpToolRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ListSkillsRequest(JsonRpcRequest):
    """Request to list available skills."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.LIST_SKILLS]
    """Method name literal."""

    params: ListSkillsRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class SubmitBugReportRequest(JsonRpcRequest):
    """Request to submit a bug report."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.SUBMIT_BUG_REPORT]
    """Method name literal."""

    params: SubmitBugReportRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


# ============================================================
# Result schemas
#
# All result/response models use extra="allow" so the SDK tolerates
# new fields the server may add during protocol evolution.  Request
# schemas (what the SDK sends) keep extra="forbid" for strictness.
# ============================================================


class InitializeSessionResult(BaseModel):
    """Result for droid.initialize_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    session_id: str = Field(alias="sessionId")
    """Created session ID."""

    session: dict[str, Any]
    """Session data (messages, etc.)."""

    mcp_servers: list[StdioMcpConfig | HttpMcpConfig | SseMcpConfig] | None = Field(
        default=None, alias="mcpServers"
    )
    """MCP server configurations."""

    settings: SessionSettings
    """Session settings."""

    git_repo: GitRepoInfo | None = Field(default=None, alias="gitRepo")
    """Optional git repository info."""

    available_models: list[AvailableModelConfig] | None = Field(
        default=None, alias="availableModels"
    )
    """Optional available model configurations."""


class MissionSnapshot(BaseModel):
    """Mission state snapshot (for orchestrator sessions)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    state: MissionState
    """Current mission state."""

    features: list[MissionFeature]
    """Mission features."""

    progress_log: list[ProgressLogEntry] = Field(alias="progressLog")
    """Progress log entries."""

    worker_session_ids: list[str] = Field(alias="workerSessionIds")
    """Active worker session IDs."""

    worker_states: dict[str, WorkerStateInfo] | None = Field(
        default=None, alias="workerStates"
    )
    """Optional worker state map."""

    token_usage: TokenUsage | None = Field(default=None, alias="tokenUsage")
    """Optional token usage for the mission."""

    token_usage_by_session_id: dict[str, TokenUsage] | None = Field(
        default=None, alias="tokenUsageBySessionId"
    )
    """Optional per-session token usage."""


class LoadSessionResult(BaseModel):
    """Result for droid.load_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    session: dict[str, Any]
    """Session data (messages, etc.)."""

    mcp_servers: list[StdioMcpConfig | HttpMcpConfig | SseMcpConfig] | None = Field(
        default=None, alias="mcpServers"
    )
    """MCP server configurations."""

    pending_permissions: list[dict[str, Any]] | None = Field(
        default=None, alias="pendingPermissions"
    )
    """Pending permission requests."""

    pending_ask_user_requests: list[dict[str, Any]] | None = Field(
        default=None, alias="pendingAskUserRequests"
    )
    """Pending ask-user requests."""

    settings: SessionSettings
    """Session settings."""

    is_agent_loop_in_progress: bool | None = Field(
        default=None, alias="isAgentLoopInProgress"
    )
    """Whether the agent loop is currently running."""

    queued_messages: list[dict[str, Any]] | None = Field(
        default=None, alias="queuedMessages"
    )
    """Queued user messages."""

    git_repo: GitRepoInfo | None = Field(default=None, alias="gitRepo")
    """Optional git repository info."""

    cwd: str | None = None
    """Current working directory."""

    calling_session_id: str | None = Field(default=None, alias="callingSessionId")
    """Optional calling session ID (for delegation)."""

    calling_tool_use_id: str | None = Field(default=None, alias="callingToolUseId")
    """Optional calling tool use ID (for delegation)."""

    available_models: list[AvailableModelConfig] | None = Field(
        default=None, alias="availableModels"
    )
    """Optional available model configurations."""

    token_usage: TokenUsage | None = Field(default=None, alias="tokenUsage")
    """Optional token usage for the session."""

    mission: MissionSnapshot | None = None
    """Optional mission state (orchestrator sessions only)."""

    decomp_session_type: DecompSessionType | None = Field(
        default=None, alias="decompSessionType"
    )
    """Session type for mission decomposition."""


class AddUserMessageResult(BaseModel):
    """Result for droid.add_user_message response (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class InterruptSessionResult(BaseModel):
    """Result for droid.interrupt_session response (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class KillWorkerSessionResult(BaseModel):
    """Result for droid.kill_worker_session response (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class UpdateSessionSettingsResult(BaseModel):
    """Result for droid.update_session_settings response (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ToggleMcpServerResult(BaseModel):
    """Result for droid.toggle_mcp_server response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class AuthenticateMcpServerResult(BaseModel):
    """Result for droid.authenticate_mcp_server response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class CancelMcpAuthResult(BaseModel):
    """Result for droid.cancel_mcp_auth response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class ClearMcpAuthResult(BaseModel):
    """Result for droid.clear_mcp_auth response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class SubmitMcpAuthCodeResult(BaseModel):
    """Result for droid.submit_mcp_auth_code response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class AddMcpServerResult(BaseModel):
    """Result for droid.add_mcp_server response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class RemoveMcpServerResult(BaseModel):
    """Result for droid.remove_mcp_server response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class ListMcpRegistryResult(BaseModel):
    """Result for droid.list_mcp_registry response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    servers: list[McpRegistryServer]
    """Available MCP registry servers."""


class ListMcpToolsResult(BaseModel):
    """Result for droid.list_mcp_tools response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tools: list[McpToolInfo]
    """Available MCP tools."""


class ListMcpServersResult(BaseModel):
    """Result for droid.list_mcp_servers response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    servers: list[McpServerStatusInfo]
    """MCP server status information."""

    summary: McpStatusSummary
    """MCP status summary."""


class ToggleMcpToolResult(BaseModel):
    """Result for droid.toggle_mcp_tool response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the operation succeeded."""


class ListSkillsResult(BaseModel):
    """Result for droid.list_skills response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    skills: list[SkillInfo]
    """Available skills."""


class SubmitBugReportResult(BaseModel):
    """Result for droid.submit_bug_report response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bug_report_id: str = Field(alias="bugReportId")
    """Created bug report ID."""


# ============================================================
# Response schemas (union of success + failure)
# ============================================================


class _InitializeSessionResponseSuccess(JsonRpcResponseSuccess):
    """Success response for initialize_session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: InitializeSessionResult  # type: ignore[assignment]


class _LoadSessionResponseSuccess(JsonRpcResponseSuccess):
    """Success response for load_session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: LoadSessionResult  # type: ignore[assignment]


class _AddUserMessageResponseSuccess(JsonRpcResponseSuccess):
    """Success response for add_user_message."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: AddUserMessageResult  # type: ignore[assignment]


class _InterruptSessionResponseSuccess(JsonRpcResponseSuccess):
    """Success response for interrupt_session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: InterruptSessionResult  # type: ignore[assignment]


class _KillWorkerSessionResponseSuccess(JsonRpcResponseSuccess):
    """Success response for kill_worker_session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: KillWorkerSessionResult  # type: ignore[assignment]


class _UpdateSessionSettingsResponseSuccess(JsonRpcResponseSuccess):
    """Success response for update_session_settings."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: UpdateSessionSettingsResult  # type: ignore[assignment]


class _ToggleMcpServerResponseSuccess(JsonRpcResponseSuccess):
    """Success response for toggle_mcp_server."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ToggleMcpServerResult  # type: ignore[assignment]


class _AuthenticateMcpServerResponseSuccess(JsonRpcResponseSuccess):
    """Success response for authenticate_mcp_server."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: AuthenticateMcpServerResult  # type: ignore[assignment]


class _CancelMcpAuthResponseSuccess(JsonRpcResponseSuccess):
    """Success response for cancel_mcp_auth."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: CancelMcpAuthResult  # type: ignore[assignment]


class _ClearMcpAuthResponseSuccess(JsonRpcResponseSuccess):
    """Success response for clear_mcp_auth."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ClearMcpAuthResult  # type: ignore[assignment]


class _SubmitMcpAuthCodeResponseSuccess(JsonRpcResponseSuccess):
    """Success response for submit_mcp_auth_code."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: SubmitMcpAuthCodeResult  # type: ignore[assignment]


class _AddMcpServerResponseSuccess(JsonRpcResponseSuccess):
    """Success response for add_mcp_server."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: AddMcpServerResult  # type: ignore[assignment]


class _RemoveMcpServerResponseSuccess(JsonRpcResponseSuccess):
    """Success response for remove_mcp_server."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: RemoveMcpServerResult  # type: ignore[assignment]


class _ListMcpRegistryResponseSuccess(JsonRpcResponseSuccess):
    """Success response for list_mcp_registry."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListMcpRegistryResult  # type: ignore[assignment]


class _ListMcpToolsResponseSuccess(JsonRpcResponseSuccess):
    """Success response for list_mcp_tools."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListMcpToolsResult  # type: ignore[assignment]


class _ListMcpServersResponseSuccess(JsonRpcResponseSuccess):
    """Success response for list_mcp_servers."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListMcpServersResult  # type: ignore[assignment]


class _ToggleMcpToolResponseSuccess(JsonRpcResponseSuccess):
    """Success response for toggle_mcp_tool."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ToggleMcpToolResult  # type: ignore[assignment]


class _ListSkillsResponseSuccess(JsonRpcResponseSuccess):
    """Success response for list_skills."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListSkillsResult  # type: ignore[assignment]


class _SubmitBugReportResponseSuccess(JsonRpcResponseSuccess):
    """Success response for submit_bug_report."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: SubmitBugReportResult  # type: ignore[assignment]


# Union response types (success | failure)

InitializeSessionResponse = _InitializeSessionResponseSuccess | JsonRpcResponseFailure
LoadSessionResponse = _LoadSessionResponseSuccess | JsonRpcResponseFailure
AddUserMessageResponse = _AddUserMessageResponseSuccess | JsonRpcResponseFailure
InterruptSessionResponse = _InterruptSessionResponseSuccess | JsonRpcResponseFailure
KillWorkerSessionResponse = _KillWorkerSessionResponseSuccess | JsonRpcResponseFailure
UpdateSessionSettingsResponse = (
    _UpdateSessionSettingsResponseSuccess | JsonRpcResponseFailure
)
ToggleMcpServerResponse = _ToggleMcpServerResponseSuccess | JsonRpcResponseFailure
AuthenticateMcpServerResponse = (
    _AuthenticateMcpServerResponseSuccess | JsonRpcResponseFailure
)
CancelMcpAuthResponse = _CancelMcpAuthResponseSuccess | JsonRpcResponseFailure
ClearMcpAuthResponse = _ClearMcpAuthResponseSuccess | JsonRpcResponseFailure
SubmitMcpAuthCodeResponse = _SubmitMcpAuthCodeResponseSuccess | JsonRpcResponseFailure
AddMcpServerResponse = _AddMcpServerResponseSuccess | JsonRpcResponseFailure
RemoveMcpServerResponse = _RemoveMcpServerResponseSuccess | JsonRpcResponseFailure
ListMcpRegistryResponse = _ListMcpRegistryResponseSuccess | JsonRpcResponseFailure
ListMcpToolsResponse = _ListMcpToolsResponseSuccess | JsonRpcResponseFailure
ListMcpServersResponse = _ListMcpServersResponseSuccess | JsonRpcResponseFailure
ToggleMcpToolResponse = _ToggleMcpToolResponseSuccess | JsonRpcResponseFailure
ListSkillsResponse = _ListSkillsResponseSuccess | JsonRpcResponseFailure
SubmitBugReportResponse = _SubmitBugReportResponseSuccess | JsonRpcResponseFailure


# ============================================================
# ClientRequest discriminated union over all 19 request types
# ============================================================

ClientRequestUnion = Annotated[
    InitializeSessionRequest
    | LoadSessionRequest
    | AddUserMessageRequest
    | InterruptSessionRequest
    | KillWorkerSessionRequest
    | UpdateSessionSettingsRequest
    | ToggleMcpServerRequest
    | AuthenticateMcpServerRequest
    | CancelMcpAuthRequest
    | ClearMcpAuthRequest
    | SubmitMcpAuthCodeRequest
    | AddMcpServerRequest
    | RemoveMcpServerRequest
    | ListMcpRegistryRequest
    | ListMcpToolsRequest
    | ListMcpServersRequest
    | ToggleMcpToolRequest
    | ListSkillsRequest
    | SubmitBugReportRequest,
    Field(discriminator="method"),
]


class ClientRequest(RootModel[ClientRequestUnion]):
    """Discriminated union over all 19 client→server request types.

    Dispatches on the ``method`` field to the appropriate request model.
    """
