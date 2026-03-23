"""Reusable test helpers for the Factory Droid SDK test suite.

Provides ``InMemoryTransport``, a mock transport implementing the
``DroidClientTransport`` Protocol for testing ``DroidClient`` with
arbitrary transport implementations.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Sentinel object used to signal the read_messages iterator to stop
_SENTINEL = object()


class InMemoryTransport:
    """In-memory transport implementing the ``DroidClientTransport`` Protocol.

    Designed for use in tests to prove ``DroidClient`` works with any
    transport, not just ``ProcessTransport``.

    Uses an ``asyncio.Queue`` to deliver messages to the
    ``read_messages()`` async generator.

    Capabilities:

    - **Capture sent messages**: All messages passed to ``send()`` are
      recorded in ``sent_messages`` for assertion.
    - **Inject responses/notifications**: Call ``inject_message()`` to
      simulate incoming JSON-RPC responses or notifications.
    - **Simulate errors**: Call ``inject_error()`` to simulate transport
      errors (e.g., process crash).
    - **Connection lifecycle**: ``connect()`` / ``close()`` track state
      via ``is_connected``.

    Example::

        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()
        # ... use client, then assert on transport.sent_messages
    """

    def __init__(self) -> None:
        self._is_connected: bool = False
        self._closed: bool = False
        self._error: Exception | None = None
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self.sent_messages: list[str] = []
        """All raw JSON strings sent via ``send()``, in order."""

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        return self._is_connected

    async def connect(self) -> None:
        """Simulate connecting (sets ``is_connected = True``)."""
        self._is_connected = True
        self._closed = False
        self._error = None
        # Reset the queue for fresh connections
        self._queue = asyncio.Queue()

    async def send(self, message: str) -> None:
        """Record a sent message.

        Args:
            message: JSON string to send.

        Raises:
            ConnectionError: If the transport is not connected.
        """
        if not self._is_connected:
            raise DroidConnectionError("Transport not connected")
        self.sent_messages.append(message)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding injected messages.

        Blocks on the internal queue until a message is available.
        Terminates when a sentinel is received (from ``close()``
        or ``inject_error()``). If an error was injected, raises it.

        Yields:
            Parsed JSON-RPC message dicts.
        """
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    async def close(self) -> None:
        """Simulate closing (sets ``is_connected = False``).

        Idempotent — safe to call multiple times.
        """
        self._is_connected = False
        self._closed = True
        # Unblock any waiting read_messages
        self._queue.put_nowait(_SENTINEL)

    # ----------------------------------------------------------
    # Test helper methods (not part of DroidClientTransport)
    # ----------------------------------------------------------

    def inject_message(self, message: dict[str, Any]) -> None:
        """Inject a JSON-RPC message as if received from the process.

        Puts the dict directly into the queue for ``read_messages()``
        to yield.

        Args:
            message: A JSON-RPC message dict.
        """
        self._queue.put_nowait(message)

    def inject_error(self, error: Exception) -> None:
        """Inject a transport error.

        Causes the ``read_messages()`` iterator to raise the error,
        simulating a transport-level failure (e.g., subprocess crash).

        Args:
            error: The exception to deliver.
        """
        self._error = error
        self._queue.put_nowait(_SENTINEL)

    def get_last_sent_parsed(self) -> dict[str, Any]:
        """Parse and return the last sent message as a dict.

        Returns:
            The parsed JSON dict of the most recent ``send()`` call.

        Raises:
            AssertionError: If no messages have been sent.
        """
        assert len(self.sent_messages) > 0, "No messages sent"
        return json.loads(self.sent_messages[-1])  # type: ignore[no-any-return]

    def get_sent_parsed(self, index: int) -> dict[str, Any]:
        """Parse and return the sent message at the given index.

        Args:
            index: Index into ``sent_messages``.

        Returns:
            The parsed JSON dict.
        """
        return json.loads(self.sent_messages[index])  # type: ignore[no-any-return]

    async def inject_message_async(self, message: dict[str, Any]) -> None:
        """Inject a message after yielding to the event loop.

        Useful when a request task needs to run before the response
        is injected.

        Args:
            message: A JSON-RPC message dict.
        """
        await asyncio.sleep(0)
        self.inject_message(message)


def make_success_response(
    request_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-RPC success response dict.

    Args:
        request_id: The ``id`` from the original request.
        result: The ``result`` payload.

    Returns:
        A complete JSON-RPC success response dict.
    """
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
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response dict.

    Args:
        request_id: The ``id`` from the original request.
        code: JSON-RPC error code.
        message: Error message.
        data: Optional error data.

    Returns:
        A complete JSON-RPC error response dict.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "response",
        "id": request_id,
        "error": error,
    }


def make_notification(
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-RPC notification dict.

    Args:
        method: Notification method name.
        params: Notification parameters.

    Returns:
        A complete JSON-RPC notification dict.
    """
    return {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "notification",
        "method": method,
        "params": params,
    }


__all__ = [
    "InMemoryTransport",
    "make_error_response",
    "make_notification",
    "make_success_response",
]
