"""Immutable tool, skill, MCP, and lifecycle result values."""

# ruff: noqa: TC001, TC003

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias

from droid_sdk._high_level._immutable import (
    freeze_json_object,
    freeze_secret_mapping,
)
from droid_sdk._high_level.enums import (
    Autonomy,
    McpServerStatus,
    McpServerType,
    Mode,
    OAuthTokenEndpointAuthMethod,
    ToolCategory,
)

if TYPE_CHECKING:
    from droid_sdk._high_level.session import Session


def _empty_str_mapping() -> Mapping[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class ToolInfo:
    id: str
    display_name: str
    description: str
    category: ToolCategory
    default_allowed: bool
    allowed: bool


@dataclass(frozen=True, slots=True)
class ListToolsOptions:
    model: str | None = None
    mode: Mode | None = None
    autonomy: Autonomy | None = None
    spec_model: str | None = None
    additional_tools: set[str] | frozenset[str] | None = None
    enabled_tools: set[str] | frozenset[str] | None = None
    disabled_tools: set[str] | frozenset[str] | None = None
    restrict_tools: set[str] | frozenset[str] | None = None
    skip_permissions_unsafe: bool | None = None

    def __post_init__(self) -> None:
        for name in (
            "additional_tools",
            "enabled_tools",
            "disabled_tools",
            "restrict_tools",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, frozenset(value))


@dataclass(frozen=True, slots=True)
class SkillResource:
    name: str
    path: str
    type: Literal["reference", "asset"]


@dataclass(frozen=True, slots=True)
class SkillInfo:
    name: str
    location: Literal["project", "personal", "builtin", "automation"]
    file_path: str
    description: str | None = None
    enabled: bool | None = None
    user_invocable: bool | None = None
    version: str | None = None
    content: str | None = None
    resources: Sequence[SkillResource] = ()
    disabled_by: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))
        if self.disabled_by is not None:
            object.__setattr__(
                self,
                "disabled_by",
                freeze_json_object(self.disabled_by, where="disabled_by"),
            )


@dataclass(frozen=True, slots=True)
class SkillsResult:
    skills: Sequence[SkillInfo]
    project_available: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(self.skills))


@dataclass(frozen=True, slots=True)
class SkillMutationResult:
    success: bool


@dataclass(frozen=True, slots=True)
class HttpHeader:
    name: str
    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class McpOAuthOptions:
    scopes: Sequence[str] | None = None
    resource: str | Literal[False] | None = None
    authorization_server_issuer: str | None = None
    client_metadata_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = field(default=None, repr=False)
    callback_port: int | None = None
    token_endpoint_auth_method: OAuthTokenEndpointAuthMethod | None = None

    def __post_init__(self) -> None:
        if self.scopes is not None:
            object.__setattr__(self, "scopes", tuple(self.scopes))
        if self.callback_port is not None and not 1 <= self.callback_port <= 65535:
            raise ValueError("callback_port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class StdioMcpServerConfig:
    name: str
    command: str
    args: Sequence[str] = ()
    env: Mapping[str, str] = field(default_factory=_empty_str_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env", freeze_secret_mapping(self.env))


@dataclass(frozen=True, slots=True)
class HttpMcpServerConfig:
    name: str
    url: str
    headers: Sequence[HttpHeader] = ()
    oauth: McpOAuthOptions | Literal[False] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", tuple(self.headers))


@dataclass(frozen=True, slots=True)
class SseMcpServerConfig:
    name: str
    url: str
    headers: Sequence[HttpHeader] = ()
    oauth: McpOAuthOptions | Literal[False] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", tuple(self.headers))


@dataclass(frozen=True, slots=True)
class DroidTool:
    name: str
    description: str
    input_schema: Mapping[str, object]
    handler: Callable[..., object] = field(repr=False, compare=False)
    output_schema: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_schema",
            freeze_json_object(self.input_schema, where="input_schema"),
        )
        if self.output_schema is not None:
            object.__setattr__(
                self,
                "output_schema",
                freeze_json_object(self.output_schema, where="output_schema"),
            )


# No slots and identity equality: droid_sdk.mcp keys its per-server runtime
# state on weak references to this handle, which needs __weakref__ and an
# identity hash (the field-based hash would also choke on the unhashable
# tool schemas).
@dataclass(frozen=True, eq=False)
class SdkMcpServer:
    name: str
    version: str
    tools: Sequence[DroidTool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", tuple(self.tools))

    @property
    def config(self) -> HttpMcpServerConfig | None:
        from droid_sdk.mcp import sdk_server_config

        return sdk_server_config(self)

    async def start(self) -> HttpMcpServerConfig:
        from droid_sdk.mcp import start_sdk_server

        return await start_sdk_server(self)

    async def close(self) -> None:
        from droid_sdk.mcp import close_sdk_server

        await close_sdk_server(self)


McpServerConfig: TypeAlias = (
    StdioMcpServerConfig | HttpMcpServerConfig | SseMcpServerConfig | SdkMcpServer
)


@dataclass(frozen=True, slots=True)
class ToolResponse:
    content: str
    is_error: bool = False
    structured_content: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.structured_content is not None:
            object.__setattr__(
                self,
                "structured_content",
                freeze_json_object(self.structured_content, where="structured_content"),
            )


@dataclass(frozen=True, slots=True)
class McpConfigError:
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class McpStatusSummary:
    total: int
    connected: int
    connecting: int
    failed: int
    disabled: int | None = None
    config_error: McpConfigError | None = None


@dataclass(frozen=True, slots=True)
class McpServerStatusInfo:
    name: str
    status: McpServerStatus
    source: str
    is_managed: bool
    server_type: McpServerType
    error: str | None = None
    tool_count: int | None = None
    has_auth_tokens: bool | None = None
    requires_auth: bool | None = None
    pending_auth_url: str | None = None
    pending_auth_message: str | None = None
    pending_auth_state: str | None = None


@dataclass(frozen=True, slots=True)
class McpServersResult:
    servers: Sequence[McpServerStatusInfo]
    summary: McpStatusSummary

    def __post_init__(self) -> None:
        object.__setattr__(self, "servers", tuple(self.servers))


@dataclass(frozen=True, slots=True)
class McpToolInputSchema:
    type: str | None = None
    properties: Mapping[str, object] | None = None
    required: Sequence[str] | None = None

    def __post_init__(self) -> None:
        if self.properties is not None:
            object.__setattr__(
                self,
                "properties",
                freeze_json_object(self.properties, where="properties"),
            )
        if self.required is not None:
            object.__setattr__(self, "required", tuple(self.required))


@dataclass(frozen=True, slots=True)
class McpToolInfo:
    server_name: str
    name: str
    is_enabled: bool
    description: str | None = None
    is_read_only: bool | None = None
    input_schema: McpToolInputSchema | None = None


@dataclass(frozen=True, slots=True)
class McpMutationResult:
    success: bool


@dataclass(frozen=True, slots=True)
class RewindFileSnapshot:
    file_path: str
    content_hash: str
    size: int


@dataclass(frozen=True, slots=True)
class RewindFileCreation:
    file_path: str


@dataclass(frozen=True, slots=True)
class RewindEvictedFile:
    file_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class RewindInfo:
    available_files: Sequence[RewindFileSnapshot]
    created_files: Sequence[RewindFileCreation]
    evicted_files: Sequence[RewindEvictedFile]

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_files", tuple(self.available_files))
        object.__setattr__(self, "created_files", tuple(self.created_files))
        object.__setattr__(self, "evicted_files", tuple(self.evicted_files))


@dataclass(frozen=True, slots=True)
class CompactOutcome:
    session: Session
    removed_count: int


@dataclass(frozen=True, slots=True)
class RewindOutcome:
    session: Session
    restored_count: int
    deleted_count: int
    failed_restore_count: int
    failed_delete_count: int
