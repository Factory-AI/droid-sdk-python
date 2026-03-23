"""JSON-RPC 2.0 base Pydantic models for the Factory Droid protocol.

Ported from TypeScript source:
- packages/common/src/shared/schemas.ts
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from droid_sdk.schemas.enums import JsonRpcErrorCode  # noqa: TC001

__all__ = [
    "BaseNotification",
    "BaseRequest",
    "BaseResponseFailure",
    "BaseResponseSuccess",
    "JsonRpcEnvelope",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponseFailure",
    "JsonRpcResponseSuccess",
    "TraceContextMeta",
]


class TraceContextMeta(BaseModel):
    """Trace context metadata for distributed tracing propagation.

    Follows W3C Trace Context standard for cross-service trace correlation.
    See: https://www.w3.org/TR/trace-context/
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    traceparent: str | None = None
    """W3C traceparent header value."""

    tracestate: str | None = None
    """W3C tracestate header value for vendor-specific trace data."""


class JsonRpcEnvelope(BaseModel):
    """JSON-RPC 2.0 envelope with Factory protocol extensions."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    jsonrpc: Literal["2.0"]
    """JSON-RPC protocol version, always '2.0'."""

    factory_api_version: Literal["1.0.0"] = Field(
        alias="factoryApiVersion",
    )
    """DEPRECATED - use factory_protocol_version for versioning instead."""

    factory_protocol_version: str | None = Field(
        default=None,
        alias="factoryProtocolVersion",
    )
    """Optional runtime compatibility signal."""

    meta: TraceContextMeta | None = Field(
        default=None,
        alias="_meta",
    )
    """Optional metadata for trace context propagation (MCP-style)."""


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    code: JsonRpcErrorCode
    """Error code."""

    message: str
    """Error message."""

    data: Any | None = None
    """Optional additional error data."""


class BaseRequest(BaseModel):
    """Base JSON-RPC request (without envelope)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["request"]
    """Message type discriminator."""

    id: str
    """Request identifier."""

    method: str
    """Method name."""

    params: dict[str, Any] | None = None
    """Optional method parameters."""


class BaseResponseSuccess(BaseModel):
    """Base JSON-RPC success response (without envelope)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["response"]
    """Message type discriminator."""

    id: str
    """Response identifier matching the request."""

    result: dict[str, Any]
    """Response result data."""


class BaseResponseFailure(BaseModel):
    """Base JSON-RPC failure response (without envelope)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["response"]
    """Message type discriminator."""

    id: str | None = None
    """Response identifier (nullable for parse errors)."""

    error: JsonRpcError
    """Error details."""


class BaseNotification(BaseModel):
    """Base JSON-RPC notification (without envelope)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["notification"]
    """Message type discriminator."""

    method: str
    """Notification method name."""

    params: dict[str, Any] | None = None
    """Optional notification parameters."""


# --- Combined models (Envelope + Base) ---


class JsonRpcRequest(JsonRpcEnvelope, BaseRequest):
    """Full JSON-RPC request with envelope fields."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class JsonRpcResponseSuccess(JsonRpcEnvelope, BaseResponseSuccess):
    """Full JSON-RPC success response with envelope fields."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class JsonRpcResponseFailure(JsonRpcEnvelope, BaseResponseFailure):
    """Full JSON-RPC failure response with envelope fields."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class JsonRpcNotification(JsonRpcEnvelope, BaseNotification):
    """Full JSON-RPC notification with envelope fields."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
