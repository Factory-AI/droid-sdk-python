"""Tests for MCP entity schemas."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from droid_sdk.schemas.enums import (
    McpServerStatus,
    McpServerType,
    SettingsLevel,
    ToolConfirmationOutcome,
)
from droid_sdk.schemas.mcp import (
    McpHttpServerConfigFields,
    McpRegistryServer,
    McpServerStatusInfo,
    McpSseServerConfigFields,
    McpStatusSummary,
    McpStdioServerConfigFields,
    McpToolInfo,
    ToolConfirmationListItem,
)

# ============================================================
# McpStdioServerConfigFields
# ============================================================


class TestMcpStdioServerConfigFields:
    """Tests for McpStdioServerConfigFields schema."""

    def test_construction_all_fields(self) -> None:
        """Construct with all optional fields."""
        config = McpStdioServerConfigFields(
            command="npx",
            args=["-y", "server"],
            env={"NODE_ENV": "production"},
        )
        assert config.command == "npx"
        assert config.args == ["-y", "server"]
        assert config.env == {"NODE_ENV": "production"}

    def test_optional_fields_default_to_none(self) -> None:
        """All fields are optional and default to None."""
        config = McpStdioServerConfigFields()
        assert config.command is None
        assert config.args is None
        assert config.env is None

    def test_env_field_present(self) -> None:
        """env field is in model_fields."""
        assert "env" in McpStdioServerConfigFields.model_fields

    def test_env_field_json_roundtrip(self) -> None:
        """env field roundtrips through JSON."""
        config = McpStdioServerConfigFields(
            command="node",
            args=["server.js"],
            env={"API_KEY": "secret", "DEBUG": "true"},
        )
        roundtripped = McpStdioServerConfigFields.model_validate_json(
            config.model_dump_json(by_alias=True)
        )
        assert roundtripped == config
        assert roundtripped.env == {"API_KEY": "secret", "DEBUG": "true"}

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        config = McpStdioServerConfigFields(command="node", args=["index.js"])
        roundtripped = McpStdioServerConfigFields.model_validate_json(
            config.model_dump_json(by_alias=True)
        )
        assert roundtripped == config

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError):
            McpStdioServerConfigFields.model_validate({"extra_field": "bad"})


# ============================================================
# McpHttpServerConfigFields
# ============================================================


class TestMcpHttpServerConfigFields:
    """Tests for McpHttpServerConfigFields schema."""

    def test_construction_with_url(self) -> None:
        """Construct with url field."""
        config = McpHttpServerConfigFields(url="https://example.com/mcp")
        assert config.url == "https://example.com/mcp"

    def test_construction_with_headers(self) -> None:
        """Construct with url and headers fields."""
        config = McpHttpServerConfigFields(
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.url == "https://example.com/mcp"
        assert config.headers == {"Authorization": "Bearer token123"}

    def test_optional_url_defaults_to_none(self) -> None:
        """url is optional and defaults to None."""
        config = McpHttpServerConfigFields()
        assert config.url is None
        assert config.headers is None

    def test_headers_field_present(self) -> None:
        """headers field is in model_fields."""
        assert "headers" in McpHttpServerConfigFields.model_fields

    def test_headers_field_json_roundtrip(self) -> None:
        """headers field roundtrips through JSON."""
        config = McpHttpServerConfigFields(
            url="https://example.com",
            headers={"X-Custom": "value", "Authorization": "Bearer abc"},
        )
        roundtripped = McpHttpServerConfigFields.model_validate_json(
            config.model_dump_json(by_alias=True)
        )
        assert roundtripped == config
        assert roundtripped.headers == {
            "X-Custom": "value",
            "Authorization": "Bearer abc",
        }

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        config = McpHttpServerConfigFields(url="https://example.com")
        roundtripped = McpHttpServerConfigFields.model_validate_json(
            config.model_dump_json(by_alias=True)
        )
        assert roundtripped == config

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError):
            McpHttpServerConfigFields.model_validate({"extra_field": "bad"})


# ============================================================
# McpSseServerConfigFields
# ============================================================


class TestMcpSseServerConfigFields:
    """Tests for McpSseServerConfigFields schema."""

    def test_construction_with_url(self) -> None:
        """Construct with required url field."""
        config = McpSseServerConfigFields(url="https://example.com/sse")
        assert config.url == "https://example.com/sse"
        assert config.headers is None

    def test_construction_with_headers(self) -> None:
        """Construct with url and headers."""
        config = McpSseServerConfigFields(
            url="https://example.com/sse",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.url == "https://example.com/sse"
        assert config.headers == {"Authorization": "Bearer token123"}

    def test_url_is_required(self) -> None:
        """url is required."""
        with pytest.raises(ValidationError):
            McpSseServerConfigFields.model_validate({})

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        config = McpSseServerConfigFields(
            url="https://example.com/sse",
            headers={"X-Custom": "value"},
        )
        roundtripped = McpSseServerConfigFields.model_validate_json(
            config.model_dump_json(by_alias=True)
        )
        assert roundtripped == config

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError):
            McpSseServerConfigFields.model_validate(
                {"url": "https://example.com", "extra_field": "bad"}
            )


# ============================================================
# McpServerStatusInfo
# ============================================================


class TestMcpServerStatusInfo:
    """Tests for McpServerStatusInfo schema."""

    def test_construction_minimal(self) -> None:
        """Construct with required fields only."""
        info = McpServerStatusInfo(
            name="my-server",
            status=McpServerStatus.Connected,
            source=SettingsLevel.User,
            is_managed=True,
            server_type=McpServerType.Stdio,
        )
        assert info.name == "my-server"
        assert info.status == McpServerStatus.Connected
        assert info.source == SettingsLevel.User
        assert info.is_managed is True
        assert info.error is None
        assert info.tool_count is None
        assert info.server_type == McpServerType.Stdio
        assert info.has_auth_tokens is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields."""
        info = McpServerStatusInfo(
            name="my-server",
            status=McpServerStatus.Failed,
            source=SettingsLevel.Project,
            is_managed=False,
            error="Connection timeout",
            tool_count=5,
            server_type=McpServerType.Stdio,
            has_auth_tokens=True,
        )
        assert info.error == "Connection timeout"
        assert info.tool_count == 5
        assert info.server_type == McpServerType.Stdio
        assert info.has_auth_tokens is True

    def test_camel_case_serialization(self) -> None:
        """Serialization with by_alias=True produces camelCase keys."""
        info = McpServerStatusInfo(
            name="my-server",
            status=McpServerStatus.Connected,
            source=SettingsLevel.User,
            is_managed=True,
            tool_count=3,
            server_type=McpServerType.Http,
            has_auth_tokens=False,
        )
        data = info.model_dump(by_alias=True)
        assert "isManaged" in data
        assert "toolCount" in data
        assert "serverType" in data
        assert "hasAuthTokens" in data

    def test_deserialization_from_camel_case(self) -> None:
        """Parse from camelCase JSON."""
        raw = {
            "name": "my-server",
            "status": "connected",
            "source": "user",
            "isManaged": True,
            "error": None,
            "toolCount": 10,
            "serverType": "stdio",
            "hasAuthTokens": False,
        }
        info = McpServerStatusInfo.model_validate(raw)
        assert info.is_managed is True
        assert info.tool_count == 10
        assert info.server_type == McpServerType.Stdio

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        info = McpServerStatusInfo(
            name="server",
            status=McpServerStatus.Connecting,
            source=SettingsLevel.Runtime,
            is_managed=False,
            server_type=McpServerType.Stdio,
            tool_count=0,
        )
        roundtripped = McpServerStatusInfo.model_validate_json(
            info.model_dump_json(by_alias=True)
        )
        assert roundtripped == info

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        info = McpServerStatusInfo.model_validate(
            {
                "name": "s",
                "status": "connected",
                "source": "user",
                "isManaged": True,
                "serverType": "stdio",
                "unknown": "tolerated",
            }
        )
        assert info.name == "s"

    def test_invalid_status_rejected(self) -> None:
        """Invalid enum value is rejected."""
        with pytest.raises(ValidationError):
            McpServerStatusInfo.model_validate(
                {
                    "name": "s",
                    "status": "bogus",
                    "source": "user",
                    "isManaged": True,
                }
            )


# ============================================================
# McpStatusSummary
# ============================================================


class TestMcpStatusSummary:
    """Tests for McpStatusSummary schema."""

    def test_construction_required(self) -> None:
        """Construct with required fields only."""
        summary = McpStatusSummary(
            total=10,
            connected=5,
            connecting=2,
            failed=3,
        )
        assert summary.total == 10
        assert summary.connected == 5
        assert summary.connecting == 2
        assert summary.failed == 3
        assert summary.disabled is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields including optional disabled."""
        summary = McpStatusSummary(
            total=10,
            connected=5,
            connecting=2,
            failed=2,
            disabled=1,
        )
        assert summary.disabled == 1

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        summary = McpStatusSummary(total=4, connected=2, connecting=1, failed=1)
        roundtripped = McpStatusSummary.model_validate_json(
            summary.model_dump_json(by_alias=True)
        )
        assert roundtripped == summary

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        summary = McpStatusSummary.model_validate(
            {
                "total": 1,
                "connected": 1,
                "connecting": 0,
                "failed": 0,
                "extra": True,
            }
        )
        assert summary.total == 1


# ============================================================
# McpRegistryServer
# ============================================================


class TestMcpRegistryServer:
    """Tests for McpRegistryServer schema."""

    def test_construction_stdio_server(self) -> None:
        """Construct a stdio-type registry server."""
        server = McpRegistryServer(
            name="my-mcp",
            description="A test MCP server",
            type=McpServerType.Stdio,
            command="npx",
            args=["-y", "@my/server"],
        )
        assert server.name == "my-mcp"
        assert server.description == "A test MCP server"
        assert server.type == McpServerType.Stdio
        assert server.command == "npx"
        assert server.args == ["-y", "@my/server"]
        assert server.url is None
        assert server.note is None
        assert server.logo_url is None

    def test_construction_http_server(self) -> None:
        """Construct an http-type registry server."""
        server = McpRegistryServer(
            name="remote-mcp",
            description="An HTTP MCP server",
            type=McpServerType.Http,
            url="https://mcp.example.com",
        )
        assert server.url == "https://mcp.example.com"
        assert server.command is None

    def test_construction_all_fields(self) -> None:
        """Construct with all optional fields."""
        server = McpRegistryServer(
            name="full-server",
            description="Fully loaded",
            type=McpServerType.Stdio,
            command="cmd",
            args=["--flag"],
            url="https://alt.example.com",
            note="Some note",
            logo_url="https://logo.example.com/logo.png",
        )
        assert server.note == "Some note"
        assert server.logo_url == "https://logo.example.com/logo.png"

    def test_camel_case_serialization(self) -> None:
        """Serialization with by_alias=True produces camelCase keys."""
        server = McpRegistryServer(
            name="s",
            description="d",
            type=McpServerType.Http,
            logo_url="https://logo.png",
        )
        data = server.model_dump(by_alias=True)
        assert "logoUrl" in data

    def test_deserialization_from_camel_case(self) -> None:
        """Parse from camelCase JSON."""
        raw = {
            "name": "test",
            "description": "desc",
            "type": "stdio",
            "command": "npx",
            "args": [],
            "logoUrl": "https://logo.png",
        }
        server = McpRegistryServer.model_validate(raw)
        assert server.logo_url == "https://logo.png"

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        server = McpRegistryServer(
            name="test",
            description="desc",
            type=McpServerType.Stdio,
            command="npx",
        )
        roundtripped = McpRegistryServer.model_validate_json(
            server.model_dump_json(by_alias=True)
        )
        assert roundtripped == server

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        server = McpRegistryServer.model_validate(
            {
                "name": "s",
                "description": "d",
                "type": "stdio",
                "extra_key": "tolerated",
            }
        )
        assert server.name == "s"


# ============================================================
# McpToolInfo
# ============================================================


class TestMcpToolInfo:
    """Tests for McpToolInfo schema."""

    def test_construction_minimal(self) -> None:
        """Construct with required fields only."""
        tool = McpToolInfo(
            server_name="my-server",
            name="my-tool",
            is_enabled=True,
        )
        assert tool.server_name == "my-server"
        assert tool.name == "my-tool"
        assert tool.is_enabled is True
        assert tool.description is None
        assert tool.is_read_only is None
        assert tool.input_schema is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields including input_schema."""
        input_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        tool = McpToolInfo(
            server_name="my-server",
            name="read_file",
            description="Read a file from disk",
            is_enabled=True,
            is_read_only=True,
            input_schema=input_schema,
        )
        assert tool.description == "Read a file from disk"
        assert tool.is_read_only is True
        assert tool.input_schema is not None
        assert tool.input_schema.type == "object"
        assert tool.input_schema.properties == {"path": {"type": "string"}}
        assert tool.input_schema.required == ["path"]

    def test_camel_case_serialization(self) -> None:
        """Serialization with by_alias=True produces camelCase keys."""
        tool = McpToolInfo(
            server_name="s",
            name="t",
            is_enabled=True,
            is_read_only=False,
            input_schema={"type": "object"},
        )
        data = tool.model_dump(by_alias=True)
        assert "serverName" in data
        assert "isEnabled" in data
        assert "isReadOnly" in data
        assert "inputSchema" in data

    def test_deserialization_from_camel_case(self) -> None:
        """Parse from camelCase JSON."""
        raw = {
            "serverName": "my-server",
            "name": "tool",
            "isEnabled": False,
            "isReadOnly": True,
            "inputSchema": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
                "required": ["x"],
            },
        }
        tool = McpToolInfo.model_validate(raw)
        assert tool.server_name == "my-server"
        assert tool.is_enabled is False
        assert tool.is_read_only is True
        assert tool.input_schema is not None
        assert tool.input_schema.type == "object"

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        tool = McpToolInfo(
            server_name="s",
            name="t",
            is_enabled=True,
        )
        roundtripped = McpToolInfo.model_validate_json(
            tool.model_dump_json(by_alias=True)
        )
        assert roundtripped == tool

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        tool = McpToolInfo.model_validate(
            {
                "serverName": "s",
                "name": "t",
                "isEnabled": True,
                "extra": "tolerated",
            }
        )
        assert tool.name == "t"


# ============================================================
# ToolConfirmationListItem
# ============================================================


class TestToolConfirmationListItem:
    """Tests for ToolConfirmationListItem schema."""

    def test_construction(self) -> None:
        """Construct with required fields."""
        item = ToolConfirmationListItem(
            label="Allow once",
            value=ToolConfirmationOutcome.ProceedOnce,
        )
        assert item.label == "Allow once"
        assert item.value == ToolConfirmationOutcome.ProceedOnce

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        item = ToolConfirmationListItem(
            label="Cancel",
            value=ToolConfirmationOutcome.Cancel,
        )
        roundtripped = ToolConfirmationListItem.model_validate_json(
            item.model_dump_json(by_alias=True)
        )
        assert roundtripped == item

    def test_enum_serialization(self) -> None:
        """Value serializes as raw string."""
        item = ToolConfirmationListItem(
            label="Auto-run",
            value=ToolConfirmationOutcome.ProceedAutoRun,
        )
        data = json.loads(item.model_dump_json(by_alias=True))
        assert data["value"] == "proceed_auto_run"

    def test_deserialization_from_string_value(self) -> None:
        """Parse enum from string value."""
        raw = {"label": "Test", "value": "cancel"}
        item = ToolConfirmationListItem.model_validate(raw)
        assert item.value == ToolConfirmationOutcome.Cancel

    def test_invalid_value_rejected(self) -> None:
        """Invalid enum value is rejected."""
        with pytest.raises(ValidationError):
            ToolConfirmationListItem.model_validate({"label": "Test", "value": "bogus"})

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        item = ToolConfirmationListItem.model_validate(
            {"label": "Test", "value": "cancel", "extra": "tolerated"}
        )
        assert item.label == "Test"


# ============================================================
# Cross-model behavior tests
# ============================================================


class TestMcpCrossModelBehavior:
    """Cross-model behavior tests for MCP schemas."""

    def test_mcp_server_status_info_enum_serialization(self) -> None:
        """Enum fields serialize as raw strings in JSON."""
        info = McpServerStatusInfo(
            name="s",
            status=McpServerStatus.Disabled,
            source=SettingsLevel.Org,
            is_managed=False,
            server_type=McpServerType.Stdio,
        )
        data = json.loads(info.model_dump_json(by_alias=True))
        assert data["status"] == "disabled"
        assert data["source"] == "org"

    def test_mcp_tool_info_input_schema_optional(self) -> None:
        """inputSchema is fully optional at all levels."""
        tool = McpToolInfo(
            server_name="s",
            name="t",
            is_enabled=True,
            input_schema=None,
        )
        assert tool.input_schema is None

    def test_mcp_tool_info_input_schema_partial(self) -> None:
        """inputSchema can have only some subfields."""
        tool = McpToolInfo(
            server_name="s",
            name="t",
            is_enabled=True,
            input_schema={"type": "object"},
        )
        assert tool.input_schema is not None
        assert tool.input_schema.type == "object"
        assert tool.input_schema.properties is None
        assert tool.input_schema.required is None
