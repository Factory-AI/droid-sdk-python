"""Observe a deterministic Session operation without a model turn."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from droid_sdk import Runtime, Session
from droid_sdk.observability import (
    LogEvent,
    MetricEvent,
    Observability,
    TraceContext,
)


class Sinks:
    def __init__(self) -> None:
        self.logs = 0
        self.metrics = 0
        self.traces = 0

    def log(self, event: LogEvent) -> None:
        self.logs += 1
        raise RuntimeError("a throwing logger must not break SDK operations")

    def record(self, event: MetricEvent) -> None:
        self.metrics += 1

    def inject(self, carrier: TraceContext) -> None:
        self.traces += 1
        carrier.traceparent = "00-" + ("1" * 32) + "-" + ("2" * 16) + "-01"


class LoopbackTransport:
    """Minimal connected transport for an offline Session lifecycle."""

    def __init__(self) -> None:
        self.is_connected = True
        self._messages: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def connect(self) -> None:
        self.is_connected = True

    async def send(self, message: str) -> None:
        request = json.loads(message)
        method = request["method"]
        if method == "droid.initialize_session":
            result: dict[str, Any] = {
                "sessionId": "offline-session",
                "session": {
                    "id": "offline-session",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "settings": {},
                    "messages": [],
                },
                "settings": {
                    "modelId": "offline-model",
                    "reasoningEffort": "medium",
                },
            }
        else:
            result = {}
        await self._messages.put(
            {"jsonrpc": "2.0", "id": request["id"], "result": result}
        )

    async def read_messages(self) -> Any:
        while (message := await self._messages.get()) is not None:
            yield message

    async def close(self) -> None:
        if self.is_connected:
            self.is_connected = False
            await self._messages.put(None)


async def main() -> None:
    sinks = Sinks()
    observability = Observability(logger=sinks, metrics=sinks, tracing=sinks)
    runtime = Runtime(
        transport=LoopbackTransport(),
        observability=observability,
    )

    async with Session(runtime=runtime) as session:
        assert session.id == "offline-session"

    assert sinks.logs >= 4
    assert sinks.metrics >= 2
    assert sinks.traces >= 2
    print(
        f"logs={sinks.logs} metrics={sinks.metrics} traces={sinks.traces} isolated=True"
    )


if __name__ == "__main__":
    asyncio.run(main())
