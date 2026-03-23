"""Python asyncio SDK for Factory Droid.

Provides a high-level async client for communicating with a ``droid exec``
subprocess via JSON-RPC 2.0 over JSONL (newline-delimited JSON).
"""

from __future__ import annotations

import importlib.metadata

from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    ConnectionError,
    DroidClientError,
    ProcessExitError,
    ProtocolError,
    SessionError,
    SessionNotFoundError,
    TimeoutError,
)
from droid_sdk.query import DroidQueryOptions, query
from droid_sdk.schemas.enums import (
    DroidWorkingState,
    McpServerStatus,
    MissionState,
    SessionNotificationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
)
from droid_sdk.stream import (
    AssistantTextDelta,
    ErrorEvent,
    StreamMessage,
    ThinkingTextDelta,
    TokenUsageUpdate,
    ToolProgress,
    ToolResult,
    ToolUse,
    TurnComplete,
    WorkingStateChanged,
)
from droid_sdk.transport import ProcessTransport
from droid_sdk.types import DroidClientTransport

__version__: str = importlib.metadata.version("droid-sdk")

__all__: list[str] = [
    # Stream message types
    "AssistantTextDelta",
    "ConnectionError",
    # Client
    "DroidClient",
    # Errors
    "DroidClientError",
    "DroidClientTransport",
    # Query convenience API
    "DroidQueryOptions",
    "DroidWorkingState",
    "ErrorEvent",
    "McpServerStatus",
    "MissionState",
    "ProcessExitError",
    # Transport
    "ProcessTransport",
    "ProtocolError",
    "SessionError",
    "SessionNotFoundError",
    "SessionNotificationType",
    "StreamMessage",
    "ThinkingTextDelta",
    "TimeoutError",
    "TokenUsageUpdate",
    # Key enums
    "ToolConfirmationOutcome",
    "ToolConfirmationType",
    "ToolProgress",
    "ToolResult",
    "ToolUse",
    "TurnComplete",
    "WorkingStateChanged",
    # Version
    "__version__",
    # Query function
    "query",
]
