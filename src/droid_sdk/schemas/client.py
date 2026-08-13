# pyright: reportIncompatibleVariableOverride=false

"""Client→server request/response Pydantic schemas for the Factory Droid protocol.

All supported client→server RPC method request/response pairs, plus supporting types
and the ClientRequest discriminated union.

Ported from TypeScript source:
- packages/droid-sdk-core/src/protocol/droid/schemas/client.ts
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from droid_sdk.schemas.cli import (
    AskUserRequestParams,
    RequestPermissionRequestParams,
)
from droid_sdk.schemas.enums import (
    AutonomyLevel,
    AutonomyMode,
    ContextStatsAccuracy,
    DecompSessionType,
    DroidInteractionMode,
    DroidServerMethod,
    DroidWorkingState,
    McpOAuthTokenEndpointAuthMethod,
    McpServerType,
    MissionState,
    ModelProvider,
    ReasoningEffort,
    SandboxMode,
    SessionPlatform,
    SettingsLevel,
    SkillLocation,
)
from droid_sdk.schemas.mcp import (  # noqa: TC001
    McpRegistryServer,
    McpServerStatusInfo,
    McpStatusSummary,
    McpToolInfo,
)
from droid_sdk.schemas.messages import (
    DocumentSource,
    FactoryDroidMessage,
)
from droid_sdk.schemas.mission import (  # noqa: TC001
    MissionFeature,
    ProgressLogEntry,
)
from droid_sdk.schemas.session import (
    LastCallTokenUsage,
    SessionTag,
    TokenUsage,
)
from droid_sdk.schemas.shared import (
    JsonRpcRequest,
    JsonRpcResponseFailure,
    JsonRpcResponseSuccess,
)

_MCP_OAUTH_CLIENT_METADATA_DOT_SEGMENT_RE = re.compile(
    r"(?:^|/)(?:\.\.|\.(?:%2e)?|%2e(?:\.|%2e)?)(?:/|$|[?#])",
    re.IGNORECASE,
)

__all__ = [  # noqa: RUF022
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
    "CloseSessionRequest",
    "CloseSessionRequestParams",
    "CloseSessionResponse",
    "CloseSessionResult",
    "CompactSessionRequest",
    "CompactSessionRequestParams",
    "CompactSessionResponse",
    "CompactSessionResult",
    "ContextBreakdownCategory",
    "ContextBreakdownDroidEntry",
    "ContextBreakdownMcpServerEntry",
    "ContextBreakdownSkillEntry",
    "CustomCommandInfo",
    "DocumentSource",
    "ExecToolInfo",
    "ExecuteRewindRequest",
    "ExecuteRewindRequestParams",
    "ExecuteRewindResponse",
    "ExecuteRewindResult",
    "ForkSessionRequest",
    "ForkSessionRequestParams",
    "ForkSessionResponse",
    "ForkSessionResult",
    "GetContextBreakdownRequest",
    "GetContextBreakdownRequestParams",
    "GetContextBreakdownResponse",
    "GetContextBreakdownResult",
    "GetContextStatsRequest",
    "GetContextStatsRequestParams",
    "GetContextStatsResponse",
    "GetContextStatsResult",
    "GetRewindInfoRequest",
    "GetRewindInfoRequestParams",
    "GetRewindInfoResponse",
    "GetRewindInfoResult",
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
    "ListCommandsRequest",
    "ListCommandsRequestParams",
    "ListCommandsResponse",
    "ListCommandsResult",
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
    "ListToolsRequest",
    "ListToolsRequestParams",
    "ListToolsResponse",
    "ListToolsResult",
    "LoadSessionRequest",
    "LoadSessionRequestParams",
    "LoadSessionResponse",
    "LoadSessionResult",
    "McpOAuthOptions",
    "MissionSnapshot",
    "OutputFormat",
    "PendingAskUserRequest",
    "PendingPermissionRequest",
    "QueuedUserMessage",
    "RemoveMcpServerRequest",
    "RemoveMcpServerRequestParams",
    "RemoveMcpServerResponse",
    "RemoveMcpServerResult",
    "RenameSessionRequest",
    "RenameSessionRequestParams",
    "RenameSessionResponse",
    "RenameSessionResult",
    "RewindEvictedFile",
    "RewindFileCreation",
    "RewindFileSnapshot",
    "SandboxStatus",
    "SessionSettings",
    "SessionData",
    "SessionSource",
    "SessionPlatform",
    "SlackSessionSource",
    "WebSessionSource",
    "ApiSessionSource",
    "SessionsApiSessionSource",
    "LinearSessionSource",
    "JiraSessionSource",
    "MicrosoftTeamsSessionSource",
    "ReadinessRemediationSessionSource",
    "ReadinessEvaluationSessionSource",
    "AutomationSessionSource",
    "WikiGenerationSessionSource",
    "WikiCISetupSessionSource",
    "TuiSessionSource",
    "DesktopSessionSource",
    "AcpSessionSource",
    "UnknownSessionSource",
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
    "SubmitMcpAuthErrorRequest",
    "SubmitMcpAuthErrorRequestParams",
    "SubmitMcpAuthErrorResponse",
    "SubmitMcpAuthErrorResult",
    "SetSkillDisabledRequest",
    "SetSkillDisabledRequestParams",
    "SetSkillDisabledResponse",
    "SetSkillDisabledResult",
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


class OutputFormat(BaseModel):
    """Structured-output contract for a user message or session.

    Constrains the assistant's reply to a JSON value matching the given
    JSON Schema.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["json_schema"]
    """Output format type, always 'json_schema'."""

    schema_: dict[str, Any] = Field(alias="schema")
    """JSON Schema describing the required output shape."""


class RewindFileSnapshot(BaseModel):
    """A file snapshot that can be restored during a rewind."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    file_path: str = Field(alias="filePath")
    """Path to the file."""

    content_hash: str = Field(alias="contentHash")
    """Content hash of the snapshot."""

    size: int
    """File size in bytes."""


class RewindFileCreation(BaseModel):
    """A file created after the rewind point (deleted on rewind)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    file_path: str = Field(alias="filePath")
    """Path to the file."""


class RewindEvictedFile(BaseModel):
    """A file that cannot be restored, with the reason why."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    file_path: str = Field(alias="filePath")
    """Path to the file."""

    reason: str
    """Why the file cannot be restored."""


class _SessionSourceBase(BaseModel):
    """Base for authority-recognized session source variants."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SlackSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Slack]
    delegation_session_id: str = Field(alias="delegationSessionId")
    team_id: str | None = Field(default=None, alias="teamId")
    channel: str | None = None
    thread_ts: str | None = Field(default=None, alias="threadTs")
    user_id: str | None = Field(default=None, alias="userId")
    automation_id: str | None = Field(default=None, alias="automationId")


class WebSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Web]
    delegation_session_id: str = Field(alias="delegationSessionId")


class ApiSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Api]
    delegation_session_id: str = Field(alias="delegationSessionId")


class SessionsApiSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.SessionsApi]
    delegation_session_id: str = Field(alias="delegationSessionId")


class LinearSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Linear]
    delegation_session_id: str = Field(alias="delegationSessionId")
    agent_session_id: str = Field(alias="agentSessionId")
    issue_id: str | None = Field(default=None, alias="issueId")
    issue_url: str | None = Field(default=None, alias="issueUrl")
    issue_identifier: str | None = Field(default=None, alias="issueIdentifier")
    organization_id: str | None = Field(default=None, alias="organizationId")
    user_id: str | None = Field(default=None, alias="userId")


class JiraSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Jira]
    delegation_session_id: str = Field(alias="delegationSessionId")
    cloud_id: str = Field(alias="cloudId")
    issue_id: str = Field(alias="issueId")
    issue_key: str | None = Field(default=None, alias="issueKey")
    site_id: str | None = Field(default=None, alias="siteId")
    project_id: str | None = Field(default=None, alias="projectId")
    comment_id: str | None = Field(default=None, alias="commentId")
    user_id: str | None = Field(default=None, alias="userId")
    task_id: str | None = Field(default=None, alias="taskId")


class MicrosoftTeamsSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.MicrosoftTeams]
    delegation_session_id: str = Field(alias="delegationSessionId")
    tenant_id: str = Field(alias="tenantId")
    conversation_id: str = Field(alias="conversationId")
    service_url: str = Field(alias="serviceUrl")
    conversation_type: Literal["personal", "groupChat", "channel"] | None = Field(
        default=None, alias="conversationType"
    )
    root_message_id: str | None = Field(default=None, alias="rootMessageId")
    team_id: str | None = Field(default=None, alias="teamId")
    channel_id: str | None = Field(default=None, alias="channelId")
    user_id: str | None = Field(default=None, alias="userId")
    aad_object_id: str | None = Field(default=None, alias="aadObjectId")


class ReadinessRemediationSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.ReadinessRemediation]
    report_id: str = Field(alias="reportId")
    repo_url: str = Field(alias="repoUrl")
    criterion_id: str = Field(alias="criterionId")


class ReadinessEvaluationSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.ReadinessEvaluation]
    repo_url: str = Field(alias="repoUrl")


class AutomationSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Automation]
    automation_id: str = Field(alias="automationId")
    computer_id: str = Field(alias="computerId")


class WikiGenerationSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.WikiGeneration]
    repo_url: str = Field(alias="repoUrl")


class WikiCISetupSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.WikiCISetup]
    repo_url: str = Field(alias="repoUrl")


class TuiSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Tui]


class DesktopSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Desktop]


class AcpSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Acp]


class UnknownSessionSource(_SessionSourceBase):
    platform: Literal[SessionPlatform.Unknown]


SessionSourceUnion = Annotated[
    SlackSessionSource
    | WebSessionSource
    | ApiSessionSource
    | SessionsApiSessionSource
    | LinearSessionSource
    | JiraSessionSource
    | MicrosoftTeamsSessionSource
    | ReadinessRemediationSessionSource
    | ReadinessEvaluationSessionSource
    | AutomationSessionSource
    | WikiGenerationSessionSource
    | WikiCISetupSessionSource
    | TuiSessionSource
    | DesktopSessionSource
    | AcpSessionSource
    | UnknownSessionSource,
    Field(discriminator="platform"),
]


class SessionSource(RootModel[SessionSourceUnion]):
    """Discriminated authority session-source union."""

    @property
    def platform(self) -> SessionPlatform:
        """Return the selected source platform."""
        return self.root.platform


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

    @field_validator("name", "command")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("MCP server name and command cannot be blank")
        return value


class HttpHeader(BaseModel):
    """HTTP header for MCP server configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    """Header name."""

    value: str
    """Header value."""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value or any(character.isspace() for character in value):
            raise ValueError("MCP header name cannot be blank or contain whitespace")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("MCP header value cannot contain line breaks")
        return value


class McpOAuthOptions(BaseModel):
    """OAuth options for HTTP and SSE MCP transports."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    scopes: list[str] | None = None
    resource: str | Literal[False] | None = None
    authorization_server_issuer: str | None = Field(
        default=None, alias="authorizationServerIssuer"
    )
    client_metadata_url: str | None = Field(default=None, alias="clientMetadataUrl")
    client_id: str | None = Field(default=None, alias="clientId")
    client_secret: str | None = Field(default=None, alias="clientSecret")
    callback_port: int | None = Field(
        default=None, alias="callbackPort", ge=1, le=65535
    )
    token_endpoint_auth_method: McpOAuthTokenEndpointAuthMethod | None = Field(
        default=None, alias="tokenEndpointAuthMethod"
    )

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("OAuth scopes cannot be blank")
        return scopes

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("clientId cannot be blank")
        return value

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("clientSecret cannot be blank")
        return value

    @field_validator("resource", "authorization_server_issuer")
    @classmethod
    def validate_oauth_url_or_false(
        cls, value: str | Literal[False] | None
    ) -> str | Literal[False] | None:
        if value is None or value is False:
            return value
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Expected an absolute URL")
        return value

    @field_validator("client_metadata_url")
    @classmethod
    def validate_client_metadata_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _MCP_OAUTH_CLIENT_METADATA_DOT_SEGMENT_RE.search(value):
            raise ValueError("clientMetadataUrl cannot contain dot segments")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path == "/"
            or not parsed.path
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "clientMetadataUrl must be an HTTPS URL with a non-root "
                "pathname, no credentials, query, fragment, or dot segments"
            )
        return value

    @model_validator(mode="after")
    def validate_oauth_configuration(self) -> McpOAuthOptions:
        has_credentials = self.client_id is not None or self.client_secret is not None
        if self.client_metadata_url is not None and has_credentials:
            raise ValueError(
                "clientMetadataUrl cannot be combined with configured OAuth "
                "client credentials"
            )
        if (
            self.client_metadata_url is not None
            and self.token_endpoint_auth_method
            not in {None, McpOAuthTokenEndpointAuthMethod.None_}
        ):
            raise ValueError(
                "clientMetadataUrl requires public OAuth token endpoint authentication"
            )
        if has_credentials and self.authorization_server_issuer is None:
            raise ValueError(
                "authorizationServerIssuer is required with configured OAuth "
                "client credentials"
            )
        return self


class HttpMcpConfig(BaseModel):
    """HTTP MCP server configuration for initialization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["http"]
    """Transport type, always 'http'."""

    name: str
    """Server name identifier."""

    url: str
    """URL endpoint for the MCP server."""

    headers: list[HttpHeader] = Field(default_factory=lambda: list[HttpHeader]())
    """HTTP headers for authentication."""

    oauth: McpOAuthOptions | Literal[False] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("MCP server name cannot be blank")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("MCP URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("MCP URL cannot contain credentials")
        return value


class SseMcpConfig(BaseModel):
    """SSE MCP server configuration for initialization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["sse"]
    """Transport type, always 'sse'."""

    name: str
    """Server name identifier."""

    url: str
    """URL endpoint for the MCP server."""

    headers: list[HttpHeader] = Field(default_factory=lambda: list[HttpHeader]())
    """HTTP headers for authentication."""

    oauth: McpOAuthOptions | Literal[False] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return HttpMcpConfig.validate_name(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return HttpMcpConfig.validate_url(value)


class SandboxStatus(BaseModel):
    """Session sandbox status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    enabled: bool
    mode: SandboxMode | None = None


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

    tags: list[SessionTag] | None = None
    sandbox: SandboxStatus | None = None
    compaction_threshold_check_enabled: bool | None = Field(
        default=None, alias="compactionThresholdCheckEnabled"
    )
    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    restrict_tool_ids: list[str] | None = Field(default=None, alias="restrictToolIds")


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

    disabled_by: dict[str, Any] | None = Field(default=None, alias="disabledBy")


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

    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    """Tool IDs to disable (subtractive; applied on top of the default set)."""

    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    """Additional tool IDs to add to the catalog."""

    restrict_tool_ids: list[str] | None = Field(default=None, alias="restrictToolIds")
    """Restrictive tool allowlist."""

    compaction_threshold_check_enabled: bool | None = Field(
        default=None, alias="compactionThresholdCheckEnabled"
    )
    auto_reject_permission_requests: bool | None = Field(
        default=None, alias="autoRejectPermissionRequests"
    )
    disable_builtin_skills: bool | None = Field(
        default=None, alias="disableBuiltinSkills"
    )

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

    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    auto_reject_permission_requests: bool | None = Field(
        default=None, alias="autoRejectPermissionRequests"
    )
    disable_builtin_skills: bool | None = Field(
        default=None, alias="disableBuiltinSkills"
    )
    session_location: str | None = Field(default=None, alias="sessionLocation")
    session_source: SessionSource | None = Field(default=None, alias="sessionSource")


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

    output_format: OutputFormat | None = Field(default=None, alias="outputFormat")
    """Optional structured-output (JSON Schema) contract for the reply."""


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

    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    """Additional tool IDs to enable beyond defaults."""

    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    """Tool IDs to disable (subtractive)."""

    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    restrict_tool_ids: list[str] | None = Field(default=None, alias="restrictToolIds")
    tags: list[SessionTag] | None = None
    compaction_token_limit: int | None = Field(
        default=None, alias="compactionTokenLimit"
    )
    compaction_threshold_check_enabled: bool | None = Field(
        default=None, alias="compactionThresholdCheckEnabled"
    )


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


class SubmitMcpAuthErrorRequestParams(BaseModel):
    """Parameters for reporting an MCP OAuth callback error."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    server_name: str = Field(alias="serverName")
    error: str
    error_description: str | None = Field(default=None, alias="errorDescription")
    state: str


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

    oauth: McpOAuthOptions | Literal[False] | None = None

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


class SetSkillDisabledRequestParams(BaseModel):
    """Parameters for enabling or disabling a skill."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    skill_name: str = Field(alias="skillName")
    disabled: bool
    settings_level: Literal[SettingsLevel.User, SettingsLevel.Project] | None = Field(
        default=None, alias="settingsLevel"
    )


class SubmitBugReportRequestParams(BaseModel):
    """Parameters for droid.submit_bug_report request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    user_comment: str = Field(alias="userComment")
    """User's bug report comment."""

    client_logs: str | None = Field(default=None, alias="clientLogs")
    """Optional client log data."""


class ListToolsRequestParams(BaseModel):
    """Parameters for droid.list_tools request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    enabled_tool_ids: list[str] | None = Field(default=None, alias="enabledToolIds")
    """Optional hypothetical additional tool IDs."""

    disabled_tool_ids: list[str] | None = Field(default=None, alias="disabledToolIds")
    """Optional hypothetical disabled tool IDs."""

    model_id: str | None = Field(default=None, alias="modelId")
    autonomy_mode: AutonomyMode | None = Field(default=None, alias="autonomyMode")
    interaction_mode: DroidInteractionMode | None = Field(
        default=None, alias="interactionMode"
    )
    autonomy_level: AutonomyLevel | None = Field(default=None, alias="autonomyLevel")
    spec_mode_model_id: str | None = Field(default=None, alias="specModeModelId")
    additional_tool_ids: list[str] | None = Field(
        default=None, alias="additionalToolIds"
    )
    restrict_tool_ids: list[str] | None = Field(default=None, alias="restrictToolIds")
    skip_permissions_unsafe: bool | None = Field(
        default=None, alias="skipPermissionsUnsafe"
    )


class ListCommandsRequestParams(BaseModel):
    """Parameters for droid.list_commands request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CloseSessionRequestParams(BaseModel):
    """Parameters for droid.close_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    reason: Literal["clear", "logout", "prompt_input_exit", "other"] | None = None
    """Optional reason for closing the session."""


class CompactSessionRequestParams(BaseModel):
    """Parameters for droid.compact_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    custom_instructions: str | None = Field(default=None, alias="customInstructions")
    """Optional instructions for the compaction summary."""


class ForkSessionRequestParams(BaseModel):
    """Parameters for droid.fork_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = None
    """Optional title for the fork."""

    tags: list[SessionTag] | None = None
    """Optional tags for the fork."""


class RenameSessionRequestParams(BaseModel):
    """Parameters for droid.rename_session request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str
    """New session title."""


class GetContextStatsRequestParams(BaseModel):
    """Parameters for droid.get_context_stats request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class GetContextBreakdownRequestParams(BaseModel):
    """Parameters for droid.get_context_breakdown request (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class GetRewindInfoRequestParams(BaseModel):
    """Parameters for droid.get_rewind_info request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    session_id: str = Field(alias="sessionId")
    """Session containing the rewind point."""

    message_id: str = Field(alias="messageId")
    """Message identifying the rewind point."""


class ExecuteRewindRequestParams(BaseModel):
    """Parameters for droid.execute_rewind request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    session_id: str = Field(alias="sessionId")
    """Session containing the rewind point."""

    message_id: str = Field(alias="messageId")
    """Message identifying the rewind point."""

    files_to_restore: list[RewindFileSnapshot] = Field(alias="filesToRestore")
    """File snapshots to restore."""

    files_to_delete: list[RewindFileCreation] = Field(alias="filesToDelete")
    """Files to delete."""

    fork_title: str = Field(alias="forkTitle")
    """Title for the rewind fork."""


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


class SubmitMcpAuthErrorRequest(JsonRpcRequest):
    """Request to report an MCP OAuth callback error."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.SUBMIT_MCP_AUTH_ERROR]
    params: SubmitMcpAuthErrorRequestParams  # type: ignore[assignment]


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


class SetSkillDisabledRequest(JsonRpcRequest):
    """Request to enable or disable a skill."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.SET_SKILL_DISABLED]
    params: SetSkillDisabledRequestParams  # type: ignore[assignment]


class SubmitBugReportRequest(JsonRpcRequest):
    """Request to submit a bug report."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    method: Literal[DroidServerMethod.SUBMIT_BUG_REPORT]
    """Method name literal."""

    params: SubmitBugReportRequestParams  # type: ignore[assignment]
    """Typed request parameters."""


class ListToolsRequest(JsonRpcRequest):
    """Request to list native CLI tools."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.LIST_TOOLS]
    params: ListToolsRequestParams  # type: ignore[assignment]


class ListCommandsRequest(JsonRpcRequest):
    """Request to list custom slash commands."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.LIST_COMMANDS]
    params: ListCommandsRequestParams  # type: ignore[assignment]


class CloseSessionRequest(JsonRpcRequest):
    """Request to close the active session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.CLOSE_SESSION]
    params: CloseSessionRequestParams  # type: ignore[assignment]


class CompactSessionRequest(JsonRpcRequest):
    """Request to compact the active session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.COMPACT_SESSION]
    params: CompactSessionRequestParams  # type: ignore[assignment]


class ForkSessionRequest(JsonRpcRequest):
    """Request to fork the active session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.FORK_SESSION]
    params: ForkSessionRequestParams  # type: ignore[assignment]


class RenameSessionRequest(JsonRpcRequest):
    """Request to rename the active session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.RENAME_SESSION]
    params: RenameSessionRequestParams  # type: ignore[assignment]


class GetContextStatsRequest(JsonRpcRequest):
    """Request for context-window usage statistics."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.GET_CONTEXT_STATS]
    params: GetContextStatsRequestParams  # type: ignore[assignment]


class GetContextBreakdownRequest(JsonRpcRequest):
    """Request for detailed context-window usage."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.GET_CONTEXT_BREAKDOWN]
    params: GetContextBreakdownRequestParams  # type: ignore[assignment]


class GetRewindInfoRequest(JsonRpcRequest):
    """Request for file restore information at a rewind point."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.GET_REWIND_INFO]
    params: GetRewindInfoRequestParams  # type: ignore[assignment]


class ExecuteRewindRequest(JsonRpcRequest):
    """Request to execute a rewind and fork the session."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    method: Literal[DroidServerMethod.EXECUTE_REWIND]
    params: ExecuteRewindRequestParams  # type: ignore[assignment]


# ============================================================
# Result schemas
#
# All result/response models use extra="allow" so the SDK tolerates
# new fields the server may add during protocol evolution.  Request
# schemas (what the SDK sends) keep extra="forbid" for strictness.
# ============================================================


class SessionData(BaseModel):
    """Typed session snapshot returned by initialize and load."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    messages: list[FactoryDroidMessage]
    title: str | None = None


class PendingPermissionRequest(RequestPermissionRequestParams):
    """Pending permission request restored with its JSON-RPC request ID."""

    request_id: str = Field(alias="requestId")


class PendingAskUserRequest(AskUserRequestParams):
    """Pending ask-user request restored with its JSON-RPC request ID."""

    request_id: str = Field(alias="requestId")


class QueuedUserMessage(AddUserMessageRequestParams):
    """Queued user message restored with its queue request ID."""

    request_id: str = Field(alias="requestId")


class InitializeSessionResult(BaseModel):
    """Result for droid.initialize_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    session_id: str = Field(alias="sessionId")
    """Created session ID."""

    session: SessionData
    """Typed session snapshot."""

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

    session: SessionData
    """Typed session snapshot."""

    mcp_servers: list[StdioMcpConfig | HttpMcpConfig | SseMcpConfig] | None = Field(
        default=None, alias="mcpServers"
    )
    """MCP server configurations."""

    pending_permissions: list[PendingPermissionRequest] | None = Field(
        default=None, alias="pendingPermissions"
    )
    """Pending permission requests."""

    pending_ask_user_requests: list[PendingAskUserRequest] | None = Field(
        default=None, alias="pendingAskUserRequests"
    )
    """Pending ask-user requests."""

    settings: SessionSettings
    """Session settings."""

    is_agent_loop_in_progress: bool | None = Field(
        default=None, alias="isAgentLoopInProgress"
    )
    """Whether the agent loop is currently running."""

    queued_messages: list[QueuedUserMessage] | None = Field(
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

    working_state: DroidWorkingState | None = Field(default=None, alias="workingState")
    inclusive_token_usage: TokenUsage | None = Field(
        default=None, alias="inclusiveTokenUsage"
    )
    last_call_token_usage: LastCallTokenUsage | None = Field(
        default=None, alias="lastCallTokenUsage"
    )


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


class SubmitMcpAuthErrorResult(BaseModel):
    """Result for droid.submit_mcp_auth_error response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool


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

    project_available: bool | None = Field(default=None, alias="projectAvailable")


class SetSkillDisabledResult(BaseModel):
    """Result for droid.set_skill_disabled response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool


class SubmitBugReportResult(BaseModel):
    """Result for droid.submit_bug_report response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bug_report_id: str = Field(alias="bugReportId")
    """Created bug report ID."""


# ============================================================
# Tool / command discovery (droid.list_tools, droid.list_commands)
# ============================================================


class ExecToolInfo(BaseModel):
    """A native CLI tool entry returned by droid.list_tools."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    """Tool identifier (the ID used in enabled/disabled tool lists)."""

    llm_id: str | None = Field(default=None, alias="llmId")
    """Identifier presented to the model."""

    display_name: str | None = Field(default=None, alias="displayName")
    """Human-readable display name."""

    description: str | None = None
    """Tool description."""

    category: str | None = None
    """Tool catalog category."""

    default_allowed: bool = Field(alias="defaultAllowed")
    """Whether the tool is allowed by default."""

    currently_allowed: bool = Field(alias="currentlyAllowed")
    """Whether the tool is currently allowed given the session config."""


class ListToolsResult(BaseModel):
    """Result for droid.list_tools response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tools: list[ExecToolInfo]
    """Available native CLI tools with their allow-state."""


class CustomCommandInfo(BaseModel):
    """A custom slash command entry returned by droid.list_commands."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Command name."""

    description: str
    """Command description."""

    argument_hint: str | None = Field(default=None, alias="argumentHint")
    """Optional argument hint."""

    is_executable: bool | None = Field(default=None, alias="isExecutable")
    """Whether the command is backed by an executable script."""


class ListCommandsResult(BaseModel):
    """Result for droid.list_commands response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    commands: list[CustomCommandInfo]
    """Available custom slash commands."""


# ============================================================
# Session lifecycle (close / compact / fork / rename)
# ============================================================


class CloseSessionResult(BaseModel):
    """Result for droid.close_session response (empty)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class CompactSessionResult(BaseModel):
    """Result for droid.compact_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    new_session_id: str = Field(alias="newSessionId")
    """Session ID created by the compaction."""

    removed_count: int = Field(alias="removedCount")
    """Number of messages removed by the compaction."""


class ForkSessionResult(BaseModel):
    """Result for droid.fork_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    new_session_id: str = Field(alias="newSessionId")
    """Session ID of the fork."""


class RenameSessionResult(BaseModel):
    """Result for droid.rename_session response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    success: bool
    """Whether the rename succeeded."""


# ============================================================
# Context stats / breakdown
# ============================================================


class GetContextStatsResult(BaseModel):
    """Result for droid.get_context_stats response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    used: int
    """Tokens used in the context window."""

    remaining: int
    """Tokens remaining in the context window."""

    limit: int
    """Total context window size."""

    accuracy: ContextStatsAccuracy
    """Accuracy of the context measurement."""

    updated_at: str = Field(alias="updatedAt")
    """ISO 8601 timestamp of the last update."""


class ContextBreakdownCategory(BaseModel):
    """A top-level context usage category."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Category name."""

    tokens: int
    """Tokens attributed to the category."""

    color_key: str = Field(alias="colorKey")
    """UI color key for the category."""


class ContextBreakdownSkillEntry(BaseModel):
    """A per-skill context usage entry."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Skill name."""

    location: str
    """Skill location."""

    tokens: int
    """Tokens attributed to the skill."""


class ContextBreakdownMcpServerEntry(BaseModel):
    """A per-MCP-server context usage entry."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """MCP server name."""

    tool_count: int = Field(alias="toolCount")
    """Number of tools contributed by the server."""

    tokens: int
    """Tokens attributed to the server."""


class ContextBreakdownDroidEntry(BaseModel):
    """A per-droid context usage entry."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Droid name."""

    location: str
    """Droid location."""

    tokens: int
    """Tokens attributed to the droid."""


class GetContextBreakdownResult(BaseModel):
    """Result for droid.get_context_breakdown response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    model_id: str = Field(alias="modelId")
    """Active model identifier."""

    model_display_name: str = Field(alias="modelDisplayName")
    """Human-readable model name."""

    context_budget: int = Field(alias="contextBudget")
    """Total context budget in tokens."""

    last_call_compaction_tokens: int | None = Field(
        default=None, alias="lastCallCompactionTokens"
    )
    """Tokens saved by compaction on the last call, if any."""

    used_tokens: int = Field(alias="usedTokens")
    """Total tokens used."""

    free_tokens: int = Field(alias="freeTokens")
    """Total tokens free."""

    categories: list[ContextBreakdownCategory]
    """Top-level usage categories."""

    skills: list[ContextBreakdownSkillEntry]
    """Per-skill usage."""

    mcp_servers: list[ContextBreakdownMcpServerEntry] = Field(alias="mcpServers")
    """Per-MCP-server usage."""

    droids: list[ContextBreakdownDroidEntry]
    """Per-droid usage."""


# ============================================================
# Rewind (droid.get_rewind_info, droid.execute_rewind)
# ============================================================


class GetRewindInfoResult(BaseModel):
    """Result for droid.get_rewind_info response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    available_files: list[RewindFileSnapshot] = Field(alias="availableFiles")
    """Files that can be restored."""

    created_files: list[RewindFileCreation] = Field(alias="createdFiles")
    """Files created after the rewind point (candidates for deletion)."""

    evicted_files: list[RewindEvictedFile] = Field(alias="evictedFiles")
    """Files that cannot be restored."""


class ExecuteRewindResult(BaseModel):
    """Result for droid.execute_rewind response."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    new_session_id: str = Field(alias="newSessionId")
    """Session ID created by the rewind (a fork)."""

    restored_count: int = Field(alias="restoredCount")
    """Number of files restored."""

    deleted_count: int = Field(alias="deletedCount")
    """Number of files deleted."""

    failed_restore_count: int = Field(alias="failedRestoreCount")
    """Number of files that failed to restore."""

    failed_delete_count: int = Field(alias="failedDeleteCount")
    """Number of files that failed to delete."""


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


class _SubmitMcpAuthErrorResponseSuccess(JsonRpcResponseSuccess):
    """Success response for submit_mcp_auth_error."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: SubmitMcpAuthErrorResult  # type: ignore[assignment]


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


class _SetSkillDisabledResponseSuccess(JsonRpcResponseSuccess):
    """Success response for set_skill_disabled."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: SetSkillDisabledResult  # type: ignore[assignment]


class _SubmitBugReportResponseSuccess(JsonRpcResponseSuccess):
    """Success response for submit_bug_report."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: SubmitBugReportResult  # type: ignore[assignment]


class _ListToolsResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListToolsResult  # type: ignore[assignment]


class _ListCommandsResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ListCommandsResult  # type: ignore[assignment]


class _CloseSessionResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: CloseSessionResult  # type: ignore[assignment]


class _CompactSessionResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: CompactSessionResult  # type: ignore[assignment]


class _ForkSessionResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ForkSessionResult  # type: ignore[assignment]


class _RenameSessionResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: RenameSessionResult  # type: ignore[assignment]


class _GetContextStatsResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: GetContextStatsResult  # type: ignore[assignment]


class _GetContextBreakdownResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: GetContextBreakdownResult  # type: ignore[assignment]


class _GetRewindInfoResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: GetRewindInfoResult  # type: ignore[assignment]


class _ExecuteRewindResponseSuccess(JsonRpcResponseSuccess):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    result: ExecuteRewindResult  # type: ignore[assignment]


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
SubmitMcpAuthErrorResponse = _SubmitMcpAuthErrorResponseSuccess | JsonRpcResponseFailure
AddMcpServerResponse = _AddMcpServerResponseSuccess | JsonRpcResponseFailure
RemoveMcpServerResponse = _RemoveMcpServerResponseSuccess | JsonRpcResponseFailure
ListMcpRegistryResponse = _ListMcpRegistryResponseSuccess | JsonRpcResponseFailure
ListMcpToolsResponse = _ListMcpToolsResponseSuccess | JsonRpcResponseFailure
ListMcpServersResponse = _ListMcpServersResponseSuccess | JsonRpcResponseFailure
ToggleMcpToolResponse = _ToggleMcpToolResponseSuccess | JsonRpcResponseFailure
ListSkillsResponse = _ListSkillsResponseSuccess | JsonRpcResponseFailure
SetSkillDisabledResponse = _SetSkillDisabledResponseSuccess | JsonRpcResponseFailure
SubmitBugReportResponse = _SubmitBugReportResponseSuccess | JsonRpcResponseFailure
ListToolsResponse = _ListToolsResponseSuccess | JsonRpcResponseFailure
ListCommandsResponse = _ListCommandsResponseSuccess | JsonRpcResponseFailure
CloseSessionResponse = _CloseSessionResponseSuccess | JsonRpcResponseFailure
CompactSessionResponse = _CompactSessionResponseSuccess | JsonRpcResponseFailure
ForkSessionResponse = _ForkSessionResponseSuccess | JsonRpcResponseFailure
RenameSessionResponse = _RenameSessionResponseSuccess | JsonRpcResponseFailure
GetContextStatsResponse = _GetContextStatsResponseSuccess | JsonRpcResponseFailure
GetContextBreakdownResponse = (
    _GetContextBreakdownResponseSuccess | JsonRpcResponseFailure
)
GetRewindInfoResponse = _GetRewindInfoResponseSuccess | JsonRpcResponseFailure
ExecuteRewindResponse = _ExecuteRewindResponseSuccess | JsonRpcResponseFailure


# ============================================================
# ClientRequest discriminated union over all request types
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
    | SubmitMcpAuthErrorRequest
    | AddMcpServerRequest
    | RemoveMcpServerRequest
    | ListMcpRegistryRequest
    | ListMcpToolsRequest
    | ListMcpServersRequest
    | ToggleMcpToolRequest
    | ListSkillsRequest
    | SetSkillDisabledRequest
    | SubmitBugReportRequest
    | ListToolsRequest
    | ListCommandsRequest
    | CloseSessionRequest
    | CompactSessionRequest
    | ForkSessionRequest
    | RenameSessionRequest
    | GetContextStatsRequest
    | GetContextBreakdownRequest
    | GetRewindInfoRequest
    | ExecuteRewindRequest,
    Field(discriminator="method"),
]


class ClientRequest(RootModel[ClientRequestUnion]):
    """Discriminated union over all client→server request types.

    Dispatches on the ``method`` field to the appropriate request model.
    """
