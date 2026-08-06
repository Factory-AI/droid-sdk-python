"""Opt-in integration tests against the installed ``droid exec`` CLI.

These tests create real sessions and consume model usage. They are excluded
from normal test runs; set ``DROID_LIVE_TESTS=1`` to enable them.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

from droid_sdk import (
    AssistantTextDelta,
    DroidClient,
    ProcessTransport,
    ToolConfirmationOutcome,
    TurnComplete,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    os.environ.get("DROID_LIVE_TESTS") != "1",
    reason="set DROID_LIVE_TESTS=1 to run tests against droid exec",
)

_EXEC_PATH = os.environ.get("DROID_EXEC_PATH", "droid")
_TURN_TIMEOUT = 180.0
_RPC_TIMEOUT = 180.0


@asynccontextmanager
async def _client(cwd: Path) -> AsyncIterator[DroidClient]:
    transport = ProcessTransport(exec_path=_EXEC_PATH, cwd=str(cwd))
    async with DroidClient(transport=transport) as client:
        client.set_permission_handler(
            lambda _: ToolConfirmationOutcome.ProceedOnce.value
        )
        yield client


async def _initialize(client: DroidClient, cwd: Path) -> str:
    result = await asyncio.wait_for(
        client.initialize_session(
            machine_id="droid-sdk-python-live-tests",
            cwd=str(cwd),
        ),
        timeout=_RPC_TIMEOUT,
    )
    return result.session_id


async def _run_turn(client: DroidClient, text: str) -> str:
    chunks: list[str] = []

    async def consume() -> None:
        async for message in client.receive_response():
            if isinstance(message, AssistantTextDelta):
                chunks.append(message.text)
            elif isinstance(message, TurnComplete):
                return

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await client.add_user_message(text=text)
    await asyncio.wait_for(consumer, timeout=_TURN_TIMEOUT)
    return "".join(chunks)


def _inner_notification(raw: dict[str, Any]) -> dict[str, Any] | None:
    params = raw.get("params")
    if not isinstance(params, dict):
        return None
    notification = params.get("notification")
    return notification if isinstance(notification, dict) else None


@pytest.mark.asyncio
async def test_live_load_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        session_id = await _initialize(client, tmp_path)

    async with _client(tmp_path) as client:
        result = await asyncio.wait_for(
            client.load_session(session_id=session_id),
            timeout=_RPC_TIMEOUT,
        )

        assert result.session
        assert client.session_id == session_id


@pytest.mark.asyncio
async def test_live_interrupt_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _initialize(client, tmp_path)
        became_busy = asyncio.Event()

        def capture_state(raw: dict[str, Any]) -> None:
            notification = _inner_notification(raw)
            if (
                notification is not None
                and notification.get("type") == "droid_working_state_changed"
                and notification.get("newState") != "idle"
            ):
                became_busy.set()

        client.on_notification(capture_state)

        consumer = asyncio.create_task(_run_turn(client, "Count slowly to 10000."))
        await asyncio.wait_for(became_busy.wait(), timeout=30)
        await asyncio.wait_for(client.interrupt_session(), timeout=_RPC_TIMEOUT)
        await asyncio.wait_for(consumer, timeout=_TURN_TIMEOUT)


@pytest.mark.asyncio
async def test_live_update_session_tool_settings(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        tools = await asyncio.wait_for(client.list_tools(), timeout=_RPC_TIMEOUT)
        assert tools.tools
        tool_id = tools.tools[0].id

        await _initialize(client, tmp_path)
        await asyncio.wait_for(
            client.update_session_settings(
                enabled_tool_ids=[],
                disabled_tool_ids=[tool_id],
            ),
            timeout=_RPC_TIMEOUT,
        )


@pytest.mark.asyncio
async def test_live_close_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _initialize(client, tmp_path)
        result = await asyncio.wait_for(
            client.close_session(reason="other"),
            timeout=_RPC_TIMEOUT,
        )

        assert result is not None


@pytest.mark.asyncio
async def test_live_compact_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _initialize(client, tmp_path)
        await _run_turn(client, "Reply exactly COMPACTION_READY.")

        result = await asyncio.wait_for(
            client.compact_session(
                custom_instructions="Preserve the COMPACTION_READY fact."
            ),
            timeout=_RPC_TIMEOUT,
        )

        assert result.new_session_id
        assert result.removed_count >= 0


@pytest.mark.asyncio
async def test_live_fork_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        session_id = await _initialize(client, tmp_path)
        result = await asyncio.wait_for(
            client.fork_session(
                title="droid-sdk-python live fork",
                tags=[{"name": "live-test", "metadata": {"source": "sdk"}}],
            ),
            timeout=_RPC_TIMEOUT,
        )

        assert result.new_session_id
        assert result.new_session_id != session_id


@pytest.mark.asyncio
async def test_live_rewind_info_and_execute(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _initialize(client, tmp_path)
        user_message_ids: list[str] = []

        def capture_user_message(raw: dict[str, Any]) -> None:
            notification = _inner_notification(raw)
            if notification is None or notification.get("type") != "create_message":
                return
            message = notification.get("message")
            if not isinstance(message, dict) or message.get("role") != "user":
                return
            content = message.get("content")
            if isinstance(content, list) and content:
                message_id = message.get("id")
                if isinstance(message_id, str):
                    user_message_ids.append(message_id)

        client.on_notification(capture_user_message)
        await _run_turn(client, "Reply exactly REWIND_READY.")
        assert user_message_ids
        message_id = user_message_ids[-1]

        info = await asyncio.wait_for(
            client.get_rewind_info(message_id=message_id),
            timeout=_RPC_TIMEOUT,
        )
        assert isinstance(info.available_files, list)
        assert isinstance(info.created_files, list)
        assert isinstance(info.evicted_files, list)

        result = await asyncio.wait_for(
            client.execute_rewind(
                message_id=message_id,
                files_to_restore=[],
                files_to_delete=[],
                fork_title="droid-sdk-python live rewind",
            ),
            timeout=_RPC_TIMEOUT,
        )
        assert result.new_session_id
        assert result.restored_count == 0
        assert result.deleted_count == 0


@pytest.mark.asyncio
async def test_live_kill_worker_session(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _initialize(client, tmp_path)
        worker_session_ids: list[str] = []

        def capture_worker(raw: dict[str, Any]) -> None:
            notification = _inner_notification(raw)
            if notification is None or notification.get("type") != "tool_result":
                return
            content = notification.get("content")
            if (
                not isinstance(content, str)
                or "Task launched in background" not in content
            ):
                return
            match = re.search(r"session_id: ([0-9a-f-]+)", content)
            if match is not None:
                worker_session_ids.append(match.group(1))

        client.on_notification(capture_worker)
        response = await _run_turn(
            client,
            "Use the Task tool exactly once with run_in_background=true. "
            "Ask the worker to run `python -c 'import time; time.sleep(60)'` "
            "and then finish. After launching it, reply exactly WORKER_STARTED "
            "without waiting for it.",
        )

        assert worker_session_ids
        worker_session_id = worker_session_ids[-1]
        try:
            assert "WORKER_STARTED" in response
        finally:
            await asyncio.wait_for(
                client.kill_worker_session(worker_session_id=worker_session_id),
                timeout=_RPC_TIMEOUT,
            )
