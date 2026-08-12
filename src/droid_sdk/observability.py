"""Synchronous, best-effort observability contracts and helpers."""

# ruff: noqa: TC001, TC003

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from droid_sdk._high_level._immutable import Scalar, freeze_scalar_mapping
from droid_sdk.protocol import ProtocolTiming


@dataclass(frozen=True, slots=True)
class SerializedError:
    message: str
    name: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class LogEvent:
    level: Literal["debug", "info", "warn", "error"]
    name: str
    message: str
    attributes: Mapping[str, Scalar] | None = None
    error: SerializedError | None = None

    def __post_init__(self) -> None:
        if self.attributes is not None:
            object.__setattr__(
                self, "attributes", freeze_scalar_mapping(self.attributes)
            )


@runtime_checkable
class Logger(Protocol):
    def log(self, event: LogEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class MetricEvent:
    name: str
    kind: Literal["counter", "histogram"]
    value: int | float
    unit: Literal["1", "ms"]
    attributes: Mapping[str, Scalar] | None = None

    def __post_init__(self) -> None:
        if self.attributes is not None:
            object.__setattr__(
                self, "attributes", freeze_scalar_mapping(self.attributes)
            )


@runtime_checkable
class MetricSink(Protocol):
    def record(self, event: MetricEvent) -> None: ...


@dataclass(slots=True)
class TraceContext:
    traceparent: str | None = None
    tracestate: str | None = None


@runtime_checkable
class TraceContextProvider(Protocol):
    def inject(self, carrier: TraceContext) -> None: ...


@dataclass(frozen=True, slots=True)
class Observability:
    logger: Logger | None = None
    metrics: MetricSink | None = None
    tracing: TraceContextProvider | None = None


def serialize_error(error: object) -> SerializedError:
    if isinstance(error, BaseException):
        code_value = getattr(error, "code", None)
        code = code_value if isinstance(code_value, str) else None
        return SerializedError(
            name=type(error).__name__,
            message=str(error),
            code=code,
        )
    return SerializedError(message=str(error))


def emit_log(
    observability: Observability | None,
    event: LogEvent,
) -> bool:
    sink = observability.logger if observability is not None else None
    if sink is None:
        return False
    try:
        sink.log(event)
    except Exception:
        return False
    return True


def record_metric(
    observability: Observability | None,
    event: MetricEvent,
) -> bool:
    sink = observability.metrics if observability is not None else None
    if sink is None:
        return False
    try:
        sink.record(event)
    except Exception:
        return False
    return True


def inject_trace_context(
    observability: Observability | None,
    carrier: TraceContext,
) -> bool:
    sink = observability.tracing if observability is not None else None
    if sink is None:
        return False
    try:
        sink.inject(carrier)
    except Exception:
        # A throwing provider must not leave partial context behind.
        carrier.traceparent = None
        carrier.tracestate = None
        return False
    return True


class ObservabilityAdapter:
    """Content-free callbacks accepted by :class:`ProtocolEngine`."""

    __slots__ = ("_observability",)

    def __init__(self, observability: Observability | None) -> None:
        self._observability = observability

    def trace_meta_injector(self, metadata: dict[str, str]) -> None:
        carrier = TraceContext()
        if not inject_trace_context(self._observability, carrier):
            return
        if carrier.traceparent is not None:
            metadata["traceparent"] = carrier.traceparent
        if carrier.tracestate is not None:
            metadata["tracestate"] = carrier.tracestate

    def timing_callback(self, timing: ProtocolTiming) -> None:
        self.record_request_timing(
            method=timing.method,
            duration_seconds=timing.duration_seconds,
            outcome=timing.outcome,
        )
        self.log(
            level="info" if timing.outcome == "success" else "error",
            name="droid.sdk.request",
            message="Droid request completed",
            attributes={
                "method": timing.method,
                "status": timing.outcome,
                "duration_ms": timing.duration_seconds * 1000,
            },
        )

    def log(
        self,
        *,
        level: Literal["debug", "info", "warn", "error"],
        name: str,
        message: str,
        attributes: Mapping[str, Scalar] | None = None,
        error: BaseException | None = None,
    ) -> None:
        serialized = (
            None
            if error is None
            else SerializedError(
                name=type(error).__name__,
                message="Droid SDK operation failed",
            )
        )
        emit_log(
            self._observability,
            LogEvent(
                level=level,
                name=name,
                message=message,
                attributes=attributes,
                error=serialized,
            ),
        )

    def record_request_timing(
        self,
        *,
        method: str,
        duration_seconds: float,
        outcome: str,
    ) -> None:
        """Emit one content-free protocol duration through the metric sink."""
        record_metric(
            self._observability,
            MetricEvent(
                name="droid.sdk.request.duration",
                kind="histogram",
                value=duration_seconds * 1000,
                unit="ms",
                attributes={
                    "method": method,
                    "outcome": outcome,
                },
            ),
        )

    def record_run_terminal(self, *, status: str) -> None:
        """Count a content-free high-level run terminal outcome."""
        record_metric(
            self._observability,
            MetricEvent(
                name="droid.sdk.run.terminal",
                kind="counter",
                value=1,
                unit="1",
                attributes={"status": status},
            ),
        )
