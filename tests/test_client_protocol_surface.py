"""Tests for the extended protocol surface added for issue #3.

Covers the new typed ``DroidClient`` methods (tool/command discovery,
session lifecycle, context introspection, rewind) plus the new
``disabled_tool_ids`` and ``output_format`` request fields.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from droid_sdk.client import DroidClient
from droid_sdk.errors import SessionError
from droid_sdk.protocol import COMPACTION_TIMEOUT
from droid_sdk.schemas.client import (
    OutputFormat,
    RewindFileCreation,
    RewindFileSnapshot,
    SessionTag,
)
from droid_sdk.schemas.enums import DroidServerMethod
from tests.helpers import InMemoryTransport, make_success_response

_background_tasks: set[asyncio.Task[Any]] = set()


def _fire(coro: Any) -> asyncio.Task[Any]:
    task: asyncio.Task[Any] = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _setup_client(transport: InMemoryTransport) -> DroidClient:
    """Create a connected client with an active session."""
    client = DroidClient(transport=transport)
    await client.connect()

    init_task = asyncio.create_task(
        client.initialize_session(machine_id="test", cwd="/tmp")
    )
    await asyncio.sleep(0)
    sent = transport.get_last_sent_parsed()
    transport.inject_message(
        make_success_response(
            sent["id"],
            {
                "sessionId": "sess-1",
                "session": {"id": "sess-1"},
                "settings": {"modelId": "claude-sonnet-4", "reasoningEffort": "medium"},
            },
        )
    )
    await init_task
    return client


async def _call(
    transport: InMemoryTransport,
    coro: Any,
    result: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    """Run *coro*, capture the sent request, inject *result*, return both."""
    task = _fire(coro)
    await asyncio.sleep(0.01)
    sent = transport.get_last_sent_parsed()
    transport.inject_message(make_success_response(sent["id"], result))
    value = await task
    return sent, value


# ---------------------------------------------------------------------------
# Tool / command discovery
# ---------------------------------------------------------------------------


class TestListTools:
    @pytest.mark.asyncio
    async def test_works_before_session_initialization(self) -> None:
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        sent, result = await _call(
            transport,
            client.list_tools(),
            {"tools": []},
        )

        assert sent["method"] == DroidServerMethod.LIST_TOOLS.value
        assert result.tools == []

        await client.close()

    @pytest.mark.asyncio
    async def test_sends_method_and_parses_result(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.list_tools(),
            {
                "tools": [
                    {
                        "id": "read-cli",
                        "llmId": "Read",
                        "displayName": "Read",
                        "description": "Read a file",
                        "category": "filesystem",
                        "defaultAllowed": True,
                        "currentlyAllowed": False,
                    }
                ]
            },
        )

        assert sent["method"] == DroidServerMethod.LIST_TOOLS.value
        assert len(result.tools) == 1
        assert result.tools[0].id == "read-cli"
        assert result.tools[0].default_allowed is True
        assert result.tools[0].currently_allowed is False

        await client.close()

    @pytest.mark.asyncio
    async def test_forwards_tool_id_filters(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, _ = await _call(
            transport,
            client.list_tools(enabled_tool_ids=[], disabled_tool_ids=["read-cli"]),
            {"tools": []},
        )

        assert sent["params"]["enabledToolIds"] == []
        assert sent["params"]["disabledToolIds"] == ["read-cli"]

        await client.close()


class TestListCommands:
    @pytest.mark.asyncio
    async def test_sends_method_and_parses_result(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.list_commands(),
            {"commands": [{"name": "deploy", "description": "Deploy the app"}]},
        )

        assert sent["method"] == DroidServerMethod.LIST_COMMANDS.value
        assert result.commands[0].name == "deploy"

        await client.close()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_close_session(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, _ = await _call(transport, client.close_session(reason="clear"), {})

        assert sent["method"] == DroidServerMethod.CLOSE_SESSION.value
        assert sent["params"]["reason"] == "clear"
        assert client.session_id is None

        sent_count = len(transport.sent_messages)
        with pytest.raises(SessionError):
            await client.get_context_stats()
        assert len(transport.sent_messages) == sent_count

        await client.close()

    @pytest.mark.asyncio
    async def test_close_session_rejects_invalid_reason_locally(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)
        sent_count = len(transport.sent_messages)

        with pytest.raises(ValidationError):
            await client.close_session(reason="invalid")  # type: ignore[arg-type]

        assert client.session_id == "sess-1"
        assert len(transport.sent_messages) == sent_count

        await client.close()

    @pytest.mark.asyncio
    async def test_compact_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)
        protocol = client._protocol
        assert protocol is not None
        send_request = protocol.send_request
        captured_timeout: float | None = None

        async def capture_timeout(**kwargs: Any) -> dict[str, Any]:
            nonlocal captured_timeout
            captured_timeout = kwargs.get("timeout")
            return await send_request(**kwargs)

        monkeypatch.setattr(protocol, "send_request", capture_timeout)

        sent, result = await _call(
            transport,
            client.compact_session(custom_instructions="keep decisions"),
            {"newSessionId": "sess-2", "removedCount": 12},
        )

        assert sent["method"] == DroidServerMethod.COMPACT_SESSION.value
        assert sent["params"]["customInstructions"] == "keep decisions"
        assert result.new_session_id == "sess-2"
        assert result.removed_count == 12
        assert captured_timeout == COMPACTION_TIMEOUT == 240.0

        await client.close()

    @pytest.mark.asyncio
    async def test_fork_session(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.fork_session(title="experiment"),
            {"newSessionId": "sess-3"},
        )

        assert sent["method"] == DroidServerMethod.FORK_SESSION.value
        assert sent["params"]["title"] == "experiment"
        assert result.new_session_id == "sess-3"

        await client.close()

    @pytest.mark.asyncio
    async def test_rename_session(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.rename_session(title="New title"),
            {"success": True},
        )

        assert sent["method"] == DroidServerMethod.RENAME_SESSION.value
        assert sent["params"]["title"] == "New title"
        assert result.success is True

        await client.close()


# ---------------------------------------------------------------------------
# Context introspection
# ---------------------------------------------------------------------------


class TestContextIntrospection:
    @pytest.mark.asyncio
    async def test_get_context_stats(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.get_context_stats(),
            {
                "used": 1000,
                "remaining": 199000,
                "limit": 200000,
                "accuracy": "exact",
                "updatedAt": "2026-08-04T00:00:00Z",
            },
        )

        assert sent["method"] == DroidServerMethod.GET_CONTEXT_STATS.value
        assert result.used == 1000
        assert result.remaining == 199000
        assert result.limit == 200000

        await client.close()

    @pytest.mark.asyncio
    async def test_get_context_breakdown(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.get_context_breakdown(),
            {
                "modelId": "claude-sonnet-4",
                "modelDisplayName": "Claude Sonnet 4",
                "contextBudget": 200000,
                "usedTokens": 1000,
                "freeTokens": 199000,
                "categories": [{"name": "System", "tokens": 500, "colorKey": "blue"}],
                "skills": [],
                "mcpServers": [],
                "droids": [],
            },
        )

        assert sent["method"] == DroidServerMethod.GET_CONTEXT_BREAKDOWN.value
        assert result.model_id == "claude-sonnet-4"
        assert result.categories[0].name == "System"
        assert result.categories[0].color_key == "blue"

        await client.close()


# ---------------------------------------------------------------------------
# Rewind
# ---------------------------------------------------------------------------


class TestRewind:
    @pytest.mark.asyncio
    async def test_get_rewind_info(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.get_rewind_info(message_id="msg-7"),
            {
                "availableFiles": [
                    {"filePath": "a.py", "contentHash": "abc", "size": 10}
                ],
                "createdFiles": [{"filePath": "b.py"}],
                "evictedFiles": [{"filePath": "c.py", "reason": "too large"}],
            },
        )

        assert sent["method"] == DroidServerMethod.GET_REWIND_INFO.value
        assert sent["params"]["sessionId"] == "sess-1"
        assert sent["params"]["messageId"] == "msg-7"
        assert result.available_files[0].file_path == "a.py"
        assert result.created_files[0].file_path == "b.py"
        assert result.evicted_files[0].reason == "too large"

        await client.close()

    @pytest.mark.asyncio
    async def test_execute_rewind(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, result = await _call(
            transport,
            client.execute_rewind(
                message_id="msg-7",
                files_to_restore=[
                    {"filePath": "a.py", "contentHash": "abc", "size": 10}
                ],
                files_to_delete=[{"filePath": "b.py"}],
                fork_title="rewound",
            ),
            {
                "newSessionId": "sess-9",
                "restoredCount": 1,
                "deletedCount": 1,
                "failedRestoreCount": 0,
                "failedDeleteCount": 0,
            },
        )

        assert sent["method"] == DroidServerMethod.EXECUTE_REWIND.value
        assert sent["params"]["messageId"] == "msg-7"
        assert sent["params"]["forkTitle"] == "rewound"
        assert result.new_session_id == "sess-9"
        assert result.restored_count == 1

        await client.close()

    @pytest.mark.asyncio
    async def test_execute_rewind_serializes_typed_files(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, _ = await _call(
            transport,
            client.execute_rewind(
                message_id="msg-7",
                files_to_restore=[
                    RewindFileSnapshot(
                        filePath="a.py",
                        contentHash="abc",
                        size=10,
                    )
                ],
                files_to_delete=[RewindFileCreation(filePath="b.py")],
                fork_title="rewound",
            ),
            {
                "newSessionId": "sess-9",
                "restoredCount": 1,
                "deletedCount": 1,
                "failedRestoreCount": 0,
                "failedDeleteCount": 0,
            },
        )

        assert sent["params"]["filesToRestore"] == [
            {"filePath": "a.py", "contentHash": "abc", "size": 10}
        ]
        assert sent["params"]["filesToDelete"] == [{"filePath": "b.py"}]

        await client.close()

    @pytest.mark.asyncio
    async def test_execute_rewind_rejects_malformed_files_locally(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)
        sent_count = len(transport.sent_messages)

        with pytest.raises(ValidationError):
            await client.execute_rewind(
                message_id="msg-7",
                files_to_restore=[{"filePath": "a.py", "size": 10}],
                files_to_delete=[],
                fork_title="rewound",
            )

        assert len(transport.sent_messages) == sent_count

        await client.close()


# ---------------------------------------------------------------------------
# New request fields (disabled_tool_ids, output_format)
# ---------------------------------------------------------------------------


class TestNewRequestFields:
    @pytest.mark.asyncio
    async def test_initialize_session_sends_disabled_tool_ids(self) -> None:
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        sent, _ = await _call(
            transport,
            client.initialize_session(
                machine_id="m",
                cwd="/tmp",
                enabled_tool_ids=[],
                disabled_tool_ids=["read-cli", "execute-cli"],
            ),
            {
                "sessionId": "sess-1",
                "session": {"id": "sess-1"},
                "settings": {"modelId": "claude-sonnet-4", "reasoningEffort": "medium"},
            },
        )

        assert sent["params"]["disabledToolIds"] == ["read-cli", "execute-cli"]
        assert sent["params"]["enabledToolIds"] == []

        await client.close()

    @pytest.mark.asyncio
    async def test_update_session_settings_sends_disabled_tool_ids(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, _ = await _call(
            transport,
            client.update_session_settings(disabled_tool_ids=["read-cli"]),
            {},
        )

        assert sent["params"]["disabledToolIds"] == ["read-cli"]

        await client.close()

    @pytest.mark.asyncio
    async def test_add_user_message_output_format_dict(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
        sent, _ = await _call(
            transport,
            client.add_user_message(
                text="Return an answer.",
                output_format={"type": "json_schema", "schema": schema},
            ),
            {},
        )

        assert sent["params"]["outputFormat"]["type"] == "json_schema"
        assert sent["params"]["outputFormat"]["schema"] == schema

        await client.close()

    @pytest.mark.asyncio
    async def test_add_user_message_output_format_model(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        schema = {"type": "object"}
        sent, _ = await _call(
            transport,
            client.add_user_message(
                text="Return an answer.",
                output_format=OutputFormat(type="json_schema", schema=schema),
            ),
            {},
        )

        assert sent["params"]["outputFormat"] == {
            "type": "json_schema",
            "schema": schema,
        }

        await client.close()

    @pytest.mark.asyncio
    async def test_add_user_message_rejects_invalid_output_format_locally(
        self,
    ) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)
        sent_count = len(transport.sent_messages)

        with pytest.raises(ValidationError):
            await client.add_user_message(
                text="Return an answer.",
                output_format={"type": "text", "schema": {}},
            )

        assert len(transport.sent_messages) == sent_count

        await client.close()

    @pytest.mark.asyncio
    async def test_fork_session_serializes_typed_tags(self) -> None:
        transport = InMemoryTransport()
        client = await _setup_client(transport)

        sent, _ = await _call(
            transport,
            client.fork_session(
                tags=[SessionTag(name="live-test", metadata={"source": "sdk"})]
            ),
            {"newSessionId": "sess-3"},
        )

        assert sent["params"]["tags"] == [
            {"name": "live-test", "metadata": {"source": "sdk"}}
        ]

        await client.close()
