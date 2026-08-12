"""Protocol definitions and type aliases for the Factory Droid SDK.

Defines the ``DroidClientTransport`` Protocol that all transport
implementations must satisfy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator  # noqa: TC003
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DroidClientTransport(Protocol):
    """Protocol defining the transport layer interface.

    All transport implementations (e.g., ``ProcessTransport``) must
    implement this interface. Uses ``typing.Protocol`` for structural
    subtyping.

    The transport is responsible for:

    - Connecting to the underlying transport (e.g., spawning subprocess)
    - Sending serialized JSON-RPC messages to the droid process
    - Yielding parsed messages via the ``read_messages`` async generator
    - Managing the connection lifecycle (connect / close)
    """

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        ...

    async def connect(self) -> None:
        """Connect the transport (e.g., spawn subprocess).

        Raises:
            ConnectionError: If the transport is already connected.
        """
        ...

    async def send(self, message: str) -> None:
        """Send a serialized JSON-RPC message.

        Args:
            message: A JSON string to send to the droid process.

        Raises:
            ConnectionError: If the transport is not connected.
            ProcessExitError: If the underlying process has exited.
        """
        ...

    def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator yielding parsed JSON-RPC messages.

        Yields parsed ``dict`` objects from the transport. The iterator
        terminates naturally when the transport closes (e.g., process
        exits cleanly). On transport errors (e.g., abnormal process
        exit), raises the appropriate exception from the iterator.

        Yields:
            Parsed JSON-RPC message dicts.

        Raises:
            DroidProcessError: If the underlying process exits.
        """
        ...

    async def close(self) -> None:
        """Close the transport and release resources.

        Idempotent — safe to call multiple times.
        """
        ...


__all__ = [
    "DroidClientTransport",
]
