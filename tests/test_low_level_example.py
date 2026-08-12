"""Offline test for the public low-level example."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from examples.low_level_session import run_session

from droid_sdk.low_level import DroidClient, ListToolsResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_STOP = object()


class ExampleTransport:
    """Deterministic in-memory responder for the example flow."""

    def __init__(self) -> None:
        self._connected = False
        self._queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
        self.methods: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def send(self, message: str) -> None:
        request = json.loads(message)
        method = request["method"]
        self.methods.append(method)
        if method == "droid.initialize_session":
            result: dict[str, Any] = {
                "sessionId": "example-session",
                "session": {"messages": []},
                "settings": {
                    "modelId": "example-model",
                    "reasoningEffort": "medium",
                },
            }
        elif method == "droid.list_tools":
            result = {
                "tools": [
                    {
                        "id": "read",
                        "displayName": "Read",
                        "defaultAllowed": True,
                        "currentlyAllowed": True,
                    }
                ]
            }
        else:
            raise AssertionError(f"Unexpected method: {method}")
        self._queue.put_nowait(
            {
                "jsonrpc": "2.0",
                "factoryApiVersion": "1.0.0",
                "factoryProtocolVersion": "1.1.0",
                "type": "response",
                "id": request["id"],
                "result": result,
            }
        )

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            message = await self._queue.get()
            if message is _STOP:
                return
            assert isinstance(message, dict)
            yield message

    async def close(self) -> None:
        self._connected = False
        self._queue.put_nowait(_STOP)


@pytest.mark.asyncio
async def test_low_level_example_flow(capsys: pytest.CaptureFixture[str]) -> None:
    transport = ExampleTransport()
    result = await run_session(
        DroidClient(transport=transport),
        cwd="/tmp/example",
        machine_id="test-machine",
    )

    assert isinstance(result, ListToolsResult)
    assert result.tools[0].id == "read"
    assert transport.methods == ["droid.initialize_session", "droid.list_tools"]
    output = capsys.readouterr().out
    assert "Session: example-session" in output
    assert "Available tools: 1" in output
