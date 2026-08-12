"""MCP entity schemas for the Factory Droid protocol.

Ported from TypeScript source:
- packages/common/src/droid/schemas/mcp.ts
- packages/common/src/droid/schemas/selectable-list-item.ts
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from droid_sdk.schemas.enums import (  # noqa: TC001
    McpServerStatus,
    McpServerType,
    SettingsLevel,
    ToolConfirmationOutcome,
)

__all__ = [
    "McpConfigError",
    "McpHttpServerConfigFields",
    "McpRegistryServer",
    "McpServerStatusInfo",
    "McpSseServerConfigFields",
    "McpStatusSummary",
    "McpStdioServerConfigFields",
    "McpToolInfo",
    "McpToolInputSchema",
    "ToolConfirmationListItem",
]


# ============================================================
# MCP server config field schemas
# ============================================================


class McpStdioServerConfigFields(BaseModel):
    """Stdio MCP server configuration fields.

    Used by registry and add-server requests for stdio-type servers.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    command: str | None = None
    """Command to spawn the MCP server process."""

    args: list[str] | None = None
    """Arguments passed to the command."""

    env: dict[str, str] | None = None
    """Environment variables for the MCP server process."""


class McpHttpServerConfigFields(BaseModel):
    """HTTP MCP server configuration fields.

    Used by registry and add-server requests for HTTP-type servers.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    url: str | None = None
    """URL endpoint for the MCP server."""

    headers: dict[str, str] | None = None
    """HTTP headers for the MCP server."""


class McpSseServerConfigFields(BaseModel):
    """SSE MCP server configuration fields.

    Used by registry and add-server requests for SSE-type servers.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    url: str
    """URL endpoint for the SSE MCP server."""

    headers: dict[str, str] | None = None
    """HTTP headers for the SSE MCP server."""


# ============================================================
# MCP server status and summary
# ============================================================


class McpServerStatusInfo(BaseModel):
    """MCP server status information.

    Shared between LIST_MCP_SERVERS result and MCP_STATUS_CHANGED notification.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Server name identifier."""

    status: McpServerStatus
    """Current connection status."""

    source: SettingsLevel
    """Settings level where this server is configured."""

    is_managed: bool = Field(alias="isManaged")
    """Whether the server is managed by Factory."""

    error: str | None = None
    """Error message if status is failed."""

    tool_count: int | None = Field(default=None, alias="toolCount")
    """Number of tools provided by this server."""

    server_type: McpServerType = Field(alias="serverType")
    """Transport type (stdio or http)."""

    has_auth_tokens: bool | None = Field(default=None, alias="hasAuthTokens")
    """Whether authentication tokens are stored for this server."""

    requires_auth: bool | None = Field(default=None, alias="requiresAuth")
    pending_auth_url: str | None = Field(default=None, alias="pendingAuthUrl")
    pending_auth_message: str | None = Field(default=None, alias="pendingAuthMessage")
    pending_auth_state: str | None = Field(default=None, alias="pendingAuthState")


class McpConfigError(BaseModel):
    """MCP configuration parse error."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    path: str
    message: str


class McpStatusSummary(BaseModel):
    """MCP status summary.

    Shared between LIST_MCP_SERVERS result and MCP_STATUS_CHANGED notification.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    total: int
    """Total number of configured servers."""

    connected: int
    """Number of connected servers."""

    connecting: int
    """Number of servers currently connecting."""

    failed: int
    """Number of failed servers."""

    disabled: int | None = None
    """Number of disabled servers."""

    config_error: McpConfigError | None = Field(default=None, alias="configError")


# ============================================================
# MCP registry server
# ============================================================


class McpRegistryServer(BaseModel):
    """MCP registry server entity.

    Combines base fields, stdio config, http config, and additional metadata.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    # Base fields
    name: str
    """Server name identifier."""

    description: str
    """Human-readable description of the server."""

    type: McpServerType
    """Transport type (stdio or http)."""

    # Stdio config fields (merged from McpStdioServerConfigFieldsSchema)
    command: str | None = None
    """Command to spawn the MCP server process (stdio servers)."""

    args: list[str] | None = None
    """Arguments passed to the command (stdio servers)."""

    # HTTP config fields (merged from McpHttpServerConfigFieldsSchema)
    url: str | None = None
    """URL endpoint for the MCP server (http servers)."""

    # Additional metadata
    note: str | None = None
    """Optional note about the server."""

    logo_url: str | None = Field(default=None, alias="logoUrl")
    """Optional URL for the server's logo."""


# ============================================================
# MCP tool info
# ============================================================


class McpToolInputSchema(BaseModel):
    """JSON Schema subset for MCP tool input parameters."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: str | None = None
    """JSON Schema type (e.g. 'object')."""

    properties: dict[str, object] | None = None
    """JSON Schema properties mapping."""

    required: list[str] | None = None
    """List of required property names."""


class McpToolInfo(BaseModel):
    """MCP tool information entity."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    server_name: str = Field(alias="serverName")
    """Name of the server providing this tool."""

    name: str
    """Tool name."""

    description: str | None = None
    """Human-readable description of the tool."""

    is_enabled: bool = Field(alias="isEnabled")
    """Whether the tool is currently enabled."""

    is_read_only: bool | None = Field(default=None, alias="isReadOnly")
    """Whether this tool only performs read operations."""

    input_schema: McpToolInputSchema | None = Field(default=None, alias="inputSchema")
    """JSON Schema for the tool's input parameters."""


# ============================================================
# Tool confirmation list item (from selectable-list-item.ts)
# ============================================================


class ToolConfirmationListItem(BaseModel):
    """Selectable list item for tool confirmation prompts.

    Used to provide structured options that can be rendered with
    visual feedback (colors, prefixes, etc.) in CLI UI.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    label: str
    """Display label for this option."""

    value: ToolConfirmationOutcome
    """The confirmation outcome this option represents."""
