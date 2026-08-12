# pyright: reportUnsupportedDunderAll=false

"""Low-level JSON-RPC and transport API.

This namespace exposes protocol building blocks without adding high-level
session ordering, ownership, or cleanup guarantees.
"""

from __future__ import annotations

from droid_sdk.client import DroidClient
from droid_sdk.protocol import (
    COMPACTION_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    MCP_AUTH_TIMEOUT,
    SESSION_INIT_TIMEOUT,
    ProtocolEngine,
    ProtocolTiming,
    ProtocolTimingCallback,
    TraceMetaInjector,
)
from droid_sdk.schemas import *  # noqa: F403
from droid_sdk.schemas import __all__ as _schema_exports
from droid_sdk.transport import ProcessTransport
from droid_sdk.types import DroidClientTransport

Transport = DroidClientTransport

__all__ = [
    "COMPACTION_TIMEOUT",
    "DEFAULT_REQUEST_TIMEOUT",
    "DroidClient",
    "DroidClientTransport",
    "MCP_AUTH_TIMEOUT",
    "ProcessTransport",
    "ProtocolEngine",
    "ProtocolTiming",
    "ProtocolTimingCallback",
    "SESSION_INIT_TIMEOUT",
    "TraceMetaInjector",
    "Transport",
    *_schema_exports,
]
