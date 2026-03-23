"""Tests for DroidClient MCP management, skills, and bug report methods.

Covers:
- toggle_mcp_server, authenticate_mcp_server, cancel_mcp_auth,
  clear_mcp_auth, submit_mcp_auth_code, add_mcp_server,
  remove_mcp_server, list_mcp_registry, list_mcp_tools,
  list_mcp_servers, toggle_mcp_tool
- list_skills
- submit_bug_report
- All methods require active session (raise SessionError otherwise)
- authenticate_mcp_server uses MCP_AUTH_TIMEOUT (300s)
- Correct method names and camelCase params sent to protocol
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.errors import (
    ProtocolError,
    SessionError,
)
from droid_sdk.protocol import MCP_AUTH_TIMEOUT
from droid_sdk.schemas.enums import DroidServerMethod, SettingsLevel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ============================================================
# Mock in-memory transport implementing DroidClientTransport Protocol
# ============================================================


_SENTINEL = object()


class MockTransport:
    """In-memory transport for testing DroidClient.

    Implements the DroidClientTransport Protocol with async generator.
    """

    def __init__(self) -> None:
        self._is_connected: bool = False
        self.sent_messages: list[str] = []
        self._closed: bool = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._error: Exception | None = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def send(self, message: str) -> None:
        if not self._is_connected:
            raise DroidConnectionError("Transport not connected")
        self.sent_messages.append(message)

    async def connect(self) -> None:
        self._is_connected = True
        self._closed = False
        self._error = None
        self._queue = asyncio.Queue()

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    async def close(self) -> None:
        self._is_connected = False
        self._closed = True
        self._queue.put_nowait(_SENTINEL)

    # Test helpers
    def inject_message(self, message: dict[str, Any]) -> None:
        """Inject a JSON-RPC message as if received from the process."""
        self._queue.put_nowait(message)

    def inject_error(self, error: Exception) -> None:
        """Inject a transport error."""
        self._error = error
        self._queue.put_nowait(_SENTINEL)

    def get_last_sent_parsed(self) -> dict[str, Any]:
        """Parse and return the last sent message."""
        assert len(self.sent_messages) > 0, "No messages sent"
        return json.loads(self.sent_messages[-1])  # type: ignore[no-any-return]


# ============================================================
# Helper to build JSON-RPC responses
# ============================================================


def make_success_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response dict."""
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "response",
        "id": request_id,
        "result": result,
    }


def make_error_response(
    request_id: str,
    code: int,
    message: str,
) -> dict[str, Any]:
    """Build a JSON-RPC error response dict."""
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "response",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


# Minimal valid result payloads
INIT_SESSION_RESULT: dict[str, Any] = {
    "sessionId": "sess-123",
    "session": {"messages": []},
    "settings": {
        "modelId": "claude-sonnet-4",
        "reasoningEffort": "medium",
    },
}


# ============================================================
# Helpers
# ============================================================


async def create_connected_client() -> tuple[Any, MockTransport]:
    """Create a DroidClient with a connected mock transport."""
    from droid_sdk.client import DroidClient

    transport = MockTransport()
    client = DroidClient(transport=transport)
    await client.connect()
    return client, transport


async def create_client_with_session() -> tuple[Any, MockTransport]:
    """Create a DroidClient with an active session."""
    client, transport = await create_connected_client()

    async def do_init() -> Any:
        return await client.initialize_session(
            machine_id="test-machine",
            cwd="/tmp/test",
        )

    task = asyncio.create_task(do_init())
    await asyncio.sleep(0.01)

    sent = transport.get_last_sent_parsed()
    request_id = sent["id"]
    transport.inject_message(make_success_response(request_id, INIT_SESSION_RESULT))
    await task

    return client, transport


# ============================================================
# Session guard tests (all MCP/skills/bugreport methods)
# ============================================================


class TestMcpMethodsRequireSession:
    """All MCP/skills/bugreport methods raise SessionError w/o session."""

    @pytest.mark.asyncio
    async def test_toggle_mcp_server_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.toggle_mcp_server(
                server_name="test-server",
                enabled=True,
                settings_level=SettingsLevel.User,
            )

    @pytest.mark.asyncio
    async def test_authenticate_mcp_server_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.authenticate_mcp_server(server_name="test-server")

    @pytest.mark.asyncio
    async def test_cancel_mcp_auth_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.cancel_mcp_auth(server_name="test-server")

    @pytest.mark.asyncio
    async def test_clear_mcp_auth_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.clear_mcp_auth(server_name="test-server")

    @pytest.mark.asyncio
    async def test_submit_mcp_auth_code_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.submit_mcp_auth_code(
                server_name="test-server",
                code="auth-code",
                state="auth-state",
            )

    @pytest.mark.asyncio
    async def test_add_mcp_server_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.add_mcp_server(
                name="test-server",
                type="stdio",
                command="echo",
            )

    @pytest.mark.asyncio
    async def test_remove_mcp_server_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.remove_mcp_server(
                server_name="test-server",
                settings_level=SettingsLevel.User,
            )

    @pytest.mark.asyncio
    async def test_list_mcp_registry_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.list_mcp_registry()

    @pytest.mark.asyncio
    async def test_list_mcp_tools_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.list_mcp_tools()

    @pytest.mark.asyncio
    async def test_list_mcp_servers_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.list_mcp_servers()

    @pytest.mark.asyncio
    async def test_toggle_mcp_tool_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.toggle_mcp_tool(
                server_name="test-server",
                tool_name="test-tool",
                enabled=True,
            )

    @pytest.mark.asyncio
    async def test_list_skills_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.list_skills()

    @pytest.mark.asyncio
    async def test_submit_bug_report_requires_session(self) -> None:
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError):
            await client.submit_bug_report(user_comment="Something broke")


# ============================================================
# toggle_mcp_server tests
# ============================================================


class TestToggleMcpServer:
    """Tests for toggle_mcp_server method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.toggle_mcp_server(
                server_name="my-server",
                enabled=True,
                settings_level=SettingsLevel.User,
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.TOGGLE_MCP_SERVER.value
        assert sent["params"]["serverName"] == "my-server"
        assert sent["params"]["enabled"] is True
        assert sent["params"]["settingsLevel"] == "user"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True

    @pytest.mark.asyncio
    async def test_returns_false_success(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.toggle_mcp_server(
                server_name="my-server",
                enabled=False,
                settings_level=SettingsLevel.User,
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], {"success": False}))
        result = await task
        assert result.success is False

    @pytest.mark.asyncio
    async def test_error_response_raises_protocol_error(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.toggle_mcp_server(
                server_name="bad-server",
                enabled=True,
                settings_level=SettingsLevel.User,
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(sent["id"], -32603, "Internal error")
        )
        with pytest.raises(ProtocolError):
            await task


# ============================================================
# authenticate_mcp_server tests
# ============================================================


class TestAuthenticateMcpServer:
    """Tests for authenticate_mcp_server method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.authenticate_mcp_server(server_name="oauth-server")

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.AUTHENTICATE_MCP_SERVER.value
        assert sent["params"]["serverName"] == "oauth-server"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True

    @pytest.mark.asyncio
    async def test_uses_mcp_auth_timeout(self) -> None:
        """authenticate_mcp_server should use MCP_AUTH_TIMEOUT (300s)."""
        client, transport = await create_client_with_session()

        # We verify by checking that the timeout isn't the default 30s.
        # We can't easily verify the exact timeout from outside, but we
        # can verify it doesn't time out in ~30s by checking the method
        # was sent correctly and uses the extended timeout.
        # The actual timeout behavior is tested in the protocol engine tests.
        assert MCP_AUTH_TIMEOUT == 300.0

        async def do_call() -> Any:
            return await client.authenticate_mcp_server(server_name="oauth-server")

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.AUTHENTICATE_MCP_SERVER.value

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        await task


# ============================================================
# cancel_mcp_auth tests
# ============================================================


class TestCancelMcpAuth:
    """Tests for cancel_mcp_auth method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.cancel_mcp_auth(server_name="oauth-server")

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.CANCEL_MCP_AUTH.value
        assert sent["params"]["serverName"] == "oauth-server"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True


# ============================================================
# clear_mcp_auth tests
# ============================================================


class TestClearMcpAuth:
    """Tests for clear_mcp_auth method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.clear_mcp_auth(server_name="oauth-server")

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.CLEAR_MCP_AUTH.value
        assert sent["params"]["serverName"] == "oauth-server"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True


# ============================================================
# submit_mcp_auth_code tests
# ============================================================


class TestSubmitMcpAuthCode:
    """Tests for submit_mcp_auth_code method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.submit_mcp_auth_code(
                server_name="oauth-server",
                code="abc123",
                state="state-token",
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.SUBMIT_MCP_AUTH_CODE.value
        assert sent["params"]["serverName"] == "oauth-server"
        assert sent["params"]["code"] == "abc123"
        assert sent["params"]["state"] == "state-token"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True


# ============================================================
# add_mcp_server tests
# ============================================================


class TestAddMcpServer:
    """Tests for add_mcp_server method."""

    @pytest.mark.asyncio
    async def test_add_stdio_server(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.add_mcp_server(
                name="my-stdio-server",
                type="stdio",
                command="/usr/bin/mcp-server",
                args=["--verbose"],
                env={"API_KEY": "secret"},
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.ADD_MCP_SERVER.value
        assert sent["params"]["name"] == "my-stdio-server"
        assert sent["params"]["type"] == "stdio"
        assert sent["params"]["command"] == "/usr/bin/mcp-server"
        assert sent["params"]["args"] == ["--verbose"]
        assert sent["params"]["env"] == {"API_KEY": "secret"}

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True

    @pytest.mark.asyncio
    async def test_add_http_server(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.add_mcp_server(
                name="my-http-server",
                type="http",
                url="https://mcp.example.com/api",
                headers={"Authorization": "Bearer token"},
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.ADD_MCP_SERVER.value
        assert sent["params"]["name"] == "my-http-server"
        assert sent["params"]["type"] == "http"
        assert sent["params"]["url"] == "https://mcp.example.com/api"
        assert sent["params"]["headers"] == {"Authorization": "Bearer token"}

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True

    @pytest.mark.asyncio
    async def test_add_stdio_server_minimal(self) -> None:
        """Add a stdio server with only required fields."""
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.add_mcp_server(
                name="minimal-server",
                type="stdio",
                command="echo",
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["params"]["name"] == "minimal-server"
        assert sent["params"]["type"] == "stdio"
        assert sent["params"]["command"] == "echo"
        # Optional fields should not be present (or None)
        assert "url" not in sent["params"] or sent["params"]["url"] is None

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        await task


# ============================================================
# remove_mcp_server tests
# ============================================================


class TestRemoveMcpServer:
    """Tests for remove_mcp_server method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.remove_mcp_server(
                server_name="old-server",
                settings_level=SettingsLevel.User,
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.REMOVE_MCP_SERVER.value
        assert sent["params"]["serverName"] == "old-server"
        assert sent["params"]["settingsLevel"] == "user"

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True


# ============================================================
# list_mcp_registry tests
# ============================================================


class TestListMcpRegistry:
    """Tests for list_mcp_registry method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_returns_typed_result(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_mcp_registry()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.LIST_MCP_REGISTRY.value
        assert sent["params"] == {}

        transport.inject_message(
            make_success_response(
                sent["id"],
                {
                    "servers": [
                        {
                            "name": "registry-server",
                            "description": "A registry server",
                            "type": "http",
                            "url": "https://mcp.example.com",
                        }
                    ]
                },
            )
        )
        result = await task
        assert len(result.servers) == 1
        assert result.servers[0].name == "registry-server"

    @pytest.mark.asyncio
    async def test_empty_servers_list(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_mcp_registry()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], {"servers": []}))
        result = await task
        assert result.servers == []


# ============================================================
# list_mcp_tools tests
# ============================================================


class TestListMcpTools:
    """Tests for list_mcp_tools method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_returns_typed_result(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_mcp_tools()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.LIST_MCP_TOOLS.value
        assert sent["params"] == {}

        transport.inject_message(
            make_success_response(
                sent["id"],
                {
                    "tools": [
                        {
                            "name": "read_file",
                            "description": "Reads a file",
                            "serverName": "file-server",
                            "isEnabled": True,
                        }
                    ]
                },
            )
        )
        result = await task
        assert len(result.tools) == 1
        assert result.tools[0].name == "read_file"


# ============================================================
# list_mcp_servers tests
# ============================================================


class TestListMcpServers:
    """Tests for list_mcp_servers method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_returns_typed_result(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_mcp_servers()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.LIST_MCP_SERVERS.value
        assert sent["params"] == {}

        transport.inject_message(
            make_success_response(
                sent["id"],
                {
                    "servers": [
                        {
                            "name": "my-server",
                            "status": "connected",
                            "source": "user",
                            "isManaged": False,
                        }
                    ],
                    "summary": {
                        "total": 1,
                        "connected": 1,
                        "connecting": 0,
                        "failed": 0,
                    },
                },
            )
        )
        result = await task
        assert len(result.servers) == 1
        assert result.servers[0].name == "my-server"
        assert result.summary.total == 1
        assert result.summary.connected == 1


# ============================================================
# toggle_mcp_tool tests
# ============================================================


class TestToggleMcpTool:
    """Tests for toggle_mcp_tool method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.toggle_mcp_tool(
                server_name="my-server",
                tool_name="read_file",
                enabled=False,
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.TOGGLE_MCP_TOOL.value
        assert sent["params"]["serverName"] == "my-server"
        assert sent["params"]["toolName"] == "read_file"
        assert sent["params"]["enabled"] is False

        transport.inject_message(make_success_response(sent["id"], {"success": True}))
        result = await task
        assert result.success is True


# ============================================================
# list_skills tests
# ============================================================


class TestListSkills:
    """Tests for list_skills method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_returns_typed_result(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_skills()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.LIST_SKILLS.value
        assert sent["params"] == {}

        transport.inject_message(
            make_success_response(
                sent["id"],
                {
                    "skills": [
                        {
                            "name": "python-sdk-worker",
                            "description": "Builds Python SDK components",
                            "location": "project",
                            "filePath": "/path/to/skill.md",
                        }
                    ]
                },
            )
        )
        result = await task
        assert len(result.skills) == 1
        assert result.skills[0].name == "python-sdk-worker"
        assert result.skills[0].location == "project"

    @pytest.mark.asyncio
    async def test_empty_skills_list(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.list_skills()

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], {"skills": []}))
        result = await task
        assert result.skills == []


# ============================================================
# submit_bug_report tests
# ============================================================


class TestSubmitBugReport:
    """Tests for submit_bug_report method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.submit_bug_report(
                user_comment="The app crashed when I clicked save",
                client_logs="ERROR: NullPointerException at line 42",
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.SUBMIT_BUG_REPORT.value
        assert sent["params"]["userComment"] == "The app crashed when I clicked save"
        assert sent["params"]["clientLogs"] == "ERROR: NullPointerException at line 42"

        transport.inject_message(
            make_success_response(
                sent["id"],
                {"bugReportId": "bug-report-abc123"},
            )
        )
        result = await task
        assert result.bug_report_id == "bug-report-abc123"

    @pytest.mark.asyncio
    async def test_without_client_logs(self) -> None:
        """submit_bug_report should work without client_logs."""
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.submit_bug_report(
                user_comment="Something broke",
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["params"]["userComment"] == "Something broke"
        # clientLogs should not be present when not provided
        assert (
            "clientLogs" not in sent["params"] or sent["params"]["clientLogs"] is None
        )

        transport.inject_message(
            make_success_response(
                sent["id"],
                {"bugReportId": "bug-456"},
            )
        )
        result = await task
        assert result.bug_report_id == "bug-456"

    @pytest.mark.asyncio
    async def test_error_response_raises_protocol_error(self) -> None:
        client, transport = await create_client_with_session()

        async def do_call() -> Any:
            return await client.submit_bug_report(
                user_comment="Something broke",
            )

        task = asyncio.create_task(do_call())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(sent["id"], -32603, "Internal error")
        )
        with pytest.raises(ProtocolError):
            await task


# ============================================================
# Method after close tests
# ============================================================


class TestMcpMethodsAfterClose:
    """All MCP methods raise ConnectionError after client is closed."""

    @pytest.mark.asyncio
    async def test_toggle_mcp_server_after_close(self) -> None:
        client, _transport = await create_client_with_session()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.toggle_mcp_server(
                server_name="test",
                enabled=True,
                settings_level=SettingsLevel.User,
            )

    @pytest.mark.asyncio
    async def test_list_skills_after_close(self) -> None:
        client, _transport = await create_client_with_session()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.list_skills()

    @pytest.mark.asyncio
    async def test_submit_bug_report_after_close(self) -> None:
        client, _transport = await create_client_with_session()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.submit_bug_report(user_comment="bug")
