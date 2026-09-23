"""Protocol version constants for the Factory Droid SDK."""

from __future__ import annotations

from typing import Final

__all__ = [
    "FACTORY_CLIENT_HEADER",
    "FACTORY_CLIENT_VERSION",
    "FACTORY_PROTOCOL_VERSION",
    "FACTORY_SDK_HEADER",
    "JSONRPC_VERSION",
    "LEGACY_FACTORY_API_VERSION",
]

JSONRPC_VERSION: Final[str] = "2.0"
"""JSON-RPC protocol version."""

LEGACY_FACTORY_API_VERSION: Final[str] = "1.0.0"
"""Legacy Factory API version for backward compatibility."""

FACTORY_PROTOCOL_VERSION: Final[str] = "1.221.0"
"""Current Factory protocol version."""

FACTORY_CLIENT_HEADER: Final[str] = "X-Factory-Client"
"""HTTP header identifying the Factory client type."""

FACTORY_SDK_HEADER: Final[str] = "X-Factory-Sdk"
"""HTTP header identifying the Factory SDK language and version."""

FACTORY_CLIENT_VERSION: Final[str] = "X-Client-Version"
"""HTTP header identifying the Factory client version."""
