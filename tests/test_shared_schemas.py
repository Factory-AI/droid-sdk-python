"""Tests for JSON-RPC 2.0 base Pydantic models (shared schemas)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from droid_sdk.schemas.constants import (
    JSONRPC_VERSION,
    LEGACY_FACTORY_API_VERSION,
)
from droid_sdk.schemas.enums import JsonRpcErrorCode
from droid_sdk.schemas.shared import (
    BaseNotification,
    BaseRequest,
    BaseResponseFailure,
    BaseResponseSuccess,
    JsonRpcEnvelope,
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponseFailure,
    JsonRpcResponseSuccess,
    TraceContextMeta,
)

# --- TraceContextMeta Tests ---


class TestTraceContextMeta:
    """Tests for TraceContextMeta model."""

    def test_construction_with_all_fields(self) -> None:
        """Construct with both traceparent and tracestate."""
        meta = TraceContextMeta(
            traceparent="00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01",
            tracestate="congo=t61rcWkgMzE",
        )
        assert (
            meta.traceparent
            == "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"
        )
        assert meta.tracestate == "congo=t61rcWkgMzE"

    def test_optional_fields_default_to_none(self) -> None:
        """Both fields are optional and default to None."""
        meta = TraceContextMeta()
        assert meta.traceparent is None
        assert meta.tracestate is None

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        meta = TraceContextMeta(
            traceparent="00-abc123-def456-01",
            tracestate="vendor=value",
        )
        json_str = meta.model_dump_json(by_alias=True)
        restored = TraceContextMeta.model_validate_json(json_str)
        assert restored == meta

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            TraceContextMeta(
                traceparent="abc",
                extra_field="not_allowed",  # type: ignore[call-arg]
            )


# --- JsonRpcEnvelope Tests ---


class TestJsonRpcEnvelope:
    """Tests for JsonRpcEnvelope model."""

    def test_construction_minimal(self) -> None:
        """Construct with required fields only."""
        envelope = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
        )
        assert envelope.jsonrpc == JSONRPC_VERSION
        assert envelope.factory_api_version == LEGACY_FACTORY_API_VERSION
        assert envelope.factory_protocol_version is None
        assert envelope.meta is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields including optional."""
        meta = TraceContextMeta(traceparent="00-abc-def-01")
        envelope = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            meta=meta,
        )
        assert envelope.factory_protocol_version == "1.1.0"
        assert envelope.meta == meta

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        envelope = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            meta=TraceContextMeta(traceparent="abc"),
        )
        data = envelope.model_dump(by_alias=True)
        assert "factoryApiVersion" in data
        assert "factoryProtocolVersion" in data
        assert "_meta" in data
        # Ensure snake_case keys are NOT in the output
        assert "factory_api_version" not in data
        assert "factory_protocol_version" not in data

    def test_deserialization_from_camel_case(self) -> None:
        """Deserialization accepts camelCase keys."""
        raw = {
            "jsonrpc": "2.0",
            "factoryApiVersion": "1.0.0",
            "factoryProtocolVersion": "1.1.0",
            "_meta": {"traceparent": "00-abc-def-01"},
        }
        envelope = JsonRpcEnvelope.model_validate(raw)
        assert envelope.factory_api_version == "1.0.0"
        assert envelope.factory_protocol_version == "1.1.0"
        assert envelope.meta is not None
        assert envelope.meta.traceparent == "00-abc-def-01"

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves all fields via by_alias=True."""
        envelope = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            meta=TraceContextMeta(traceparent="abc"),
        )
        json_str = envelope.model_dump_json(by_alias=True)
        restored = JsonRpcEnvelope.model_validate_json(json_str)
        assert restored == envelope

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            JsonRpcEnvelope(
                jsonrpc=JSONRPC_VERSION,
                factory_api_version=LEGACY_FACTORY_API_VERSION,
                unknown="bad",  # type: ignore[call-arg]
            )


# --- JsonRpcError Tests ---


class TestJsonRpcError:
    """Tests for JsonRpcError model."""

    def test_construction(self) -> None:
        """Construct with code and message."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.PARSE_ERROR,
            message="Parse error",
        )
        assert error.code == JsonRpcErrorCode.PARSE_ERROR
        assert error.message == "Parse error"
        assert error.data is None

    def test_construction_with_data(self) -> None:
        """Construct with optional data field."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.INTERNAL_ERROR,
            message="Internal error",
            data={"details": "something went wrong"},
        )
        assert error.data == {"details": "something went wrong"}

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.ENTITY_NOT_FOUND,
            message="Not found",
            data="extra info",
        )
        json_str = error.model_dump_json(by_alias=True)
        restored = JsonRpcError.model_validate_json(json_str)
        assert restored == error

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.PARSE_ERROR,
            message="error",
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert error.message == "error"


# --- BaseRequest Tests ---


class TestBaseRequest:
    """Tests for BaseRequest model."""

    def test_construction(self) -> None:
        """Construct with all required fields."""
        req = BaseRequest(
            type="request",
            id="req-123",
            method="some.method",
        )
        assert req.type == "request"
        assert req.id == "req-123"
        assert req.method == "some.method"
        assert req.params is None

    def test_with_params(self) -> None:
        """Construct with optional params."""
        req = BaseRequest(
            type="request",
            id="req-456",
            method="some.method",
            params={"key": "value"},
        )
        assert req.params == {"key": "value"}

    def test_literal_type_enforcement(self) -> None:
        """Type field must be 'request'."""
        with pytest.raises(ValidationError):
            BaseRequest(
                type="notification",  # type: ignore[arg-type]
                id="req-789",
                method="some.method",
            )

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        req = BaseRequest(
            type="request",
            id="req-abc",
            method="test.method",
            params={"a": 1},
        )
        json_str = req.model_dump_json(by_alias=True)
        restored = BaseRequest.model_validate_json(json_str)
        assert restored == req

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            BaseRequest(
                type="request",
                id="req-x",
                method="m",
                extra="bad",  # type: ignore[call-arg]
            )


# --- BaseResponseSuccess Tests ---


class TestBaseResponseSuccess:
    """Tests for BaseResponseSuccess model."""

    def test_construction(self) -> None:
        """Construct with required fields."""
        resp = BaseResponseSuccess(
            type="response",
            id="resp-123",
            result={"data": "value"},
        )
        assert resp.type == "response"
        assert resp.id == "resp-123"
        assert resp.result == {"data": "value"}

    def test_literal_type_enforcement(self) -> None:
        """Type field must be 'response'."""
        with pytest.raises(ValidationError):
            BaseResponseSuccess(
                type="request",  # type: ignore[arg-type]
                id="resp-456",
                result={},
            )

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        resp = BaseResponseSuccess(
            type="response",
            id="resp-abc",
            result={"key": "val"},
        )
        json_str = resp.model_dump_json(by_alias=True)
        restored = BaseResponseSuccess.model_validate_json(json_str)
        assert restored == resp

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        resp = BaseResponseSuccess(
            type="response",
            id="resp-x",
            result={},
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert resp.id == "resp-x"


# --- BaseResponseFailure Tests ---


class TestBaseResponseFailure:
    """Tests for BaseResponseFailure model."""

    def test_construction(self) -> None:
        """Construct with required fields."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.INTERNAL_ERROR,
            message="error",
        )
        resp = BaseResponseFailure(
            type="response",
            id="resp-err-1",
            error=error,
        )
        assert resp.type == "response"
        assert resp.id == "resp-err-1"
        assert resp.error == error

    def test_optional_id(self) -> None:
        """ID is optional (nullable) for error responses."""
        resp = BaseResponseFailure(
            type="response",
            error=JsonRpcError(
                code=JsonRpcErrorCode.PARSE_ERROR,
                message="parse error",
            ),
        )
        assert resp.id is None

    def test_literal_type_enforcement(self) -> None:
        """Type field must be 'response'."""
        with pytest.raises(ValidationError):
            BaseResponseFailure(
                type="notification",  # type: ignore[arg-type]
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message="error",
                ),
            )

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        resp = BaseResponseFailure(
            type="response",
            id="resp-fail",
            error=JsonRpcError(
                code=JsonRpcErrorCode.METHOD_NOT_FOUND,
                message="not found",
                data={"method": "unknown"},
            ),
        )
        json_str = resp.model_dump_json(by_alias=True)
        restored = BaseResponseFailure.model_validate_json(json_str)
        assert restored == resp

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        resp = BaseResponseFailure(
            type="response",
            error=JsonRpcError(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message="error",
            ),
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert resp.error.message == "error"


# --- BaseNotification Tests ---


class TestBaseNotification:
    """Tests for BaseNotification model."""

    def test_construction(self) -> None:
        """Construct with required fields."""
        notif = BaseNotification(
            type="notification",
            method="droid.session_notification",
        )
        assert notif.type == "notification"
        assert notif.method == "droid.session_notification"
        assert notif.params is None

    def test_with_params(self) -> None:
        """Construct with optional params."""
        notif = BaseNotification(
            type="notification",
            method="droid.session_notification",
            params={"notification": {"type": "error"}},
        )
        assert notif.params == {"notification": {"type": "error"}}

    def test_literal_type_enforcement(self) -> None:
        """Type field must be 'notification'."""
        with pytest.raises(ValidationError):
            BaseNotification(
                type="request",  # type: ignore[arg-type]
                method="some.method",
            )

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        notif = BaseNotification(
            type="notification",
            method="test.notify",
            params={"key": "val"},
        )
        json_str = notif.model_dump_json(by_alias=True)
        restored = BaseNotification.model_validate_json(json_str)
        assert restored == notif

    def test_extra_field_allowed(self) -> None:
        """Notification models tolerate extra fields for protocol evolution."""
        notif = BaseNotification(
            type="notification",
            method="m",
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert notif.method == "m"


# --- JsonRpcRequest (Combined) Tests ---


class TestJsonRpcRequest:
    """Tests for JsonRpcRequest (JsonRpcEnvelope + BaseRequest)."""

    def test_construction(self) -> None:
        """Construct with all envelope + request fields."""
        req = JsonRpcRequest(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            type="request",
            id="req-full-1",
            method="droid.initialize_session",
            params={"cwd": "/tmp"},
        )
        assert req.jsonrpc == JSONRPC_VERSION
        assert req.factory_api_version == LEGACY_FACTORY_API_VERSION
        assert req.type == "request"
        assert req.id == "req-full-1"
        assert req.method == "droid.initialize_session"
        assert req.params == {"cwd": "/tmp"}

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        req = JsonRpcRequest(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            type="request",
            id="req-cc",
            method="test.method",
        )
        data = req.model_dump(by_alias=True)
        assert "factoryApiVersion" in data
        assert "factoryProtocolVersion" in data

    def test_deserialization_from_camel_case(self) -> None:
        """Deserialization accepts camelCase JSON."""
        raw = {
            "jsonrpc": "2.0",
            "factoryApiVersion": "1.0.0",
            "factoryProtocolVersion": "1.1.0",
            "type": "request",
            "id": "req-deser",
            "method": "test.method",
            "params": {"key": "val"},
        }
        req = JsonRpcRequest.model_validate(raw)
        assert req.factory_api_version == "1.0.0"
        assert req.factory_protocol_version == "1.1.0"
        assert req.id == "req-deser"
        assert req.method == "test.method"
        assert req.params == {"key": "val"}

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves all fields."""
        req = JsonRpcRequest(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            meta=TraceContextMeta(traceparent="abc"),
            type="request",
            id="req-rt",
            method="droid.load_session",
            params={"sessionId": "sess-1"},
        )
        json_str = req.model_dump_json(by_alias=True)
        restored = JsonRpcRequest.model_validate_json(json_str)
        assert restored == req

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            JsonRpcRequest(
                jsonrpc=JSONRPC_VERSION,
                factory_api_version=LEGACY_FACTORY_API_VERSION,
                type="request",
                id="req-x",
                method="m",
                extra="bad",  # type: ignore[call-arg]
            )

    def test_literal_type_enforcement(self) -> None:
        """Type must be 'request'."""
        with pytest.raises(ValidationError):
            JsonRpcRequest(
                jsonrpc=JSONRPC_VERSION,
                factory_api_version=LEGACY_FACTORY_API_VERSION,
                type="response",  # type: ignore[arg-type]
                id="req-x",
                method="m",
            )


# --- JsonRpcResponseSuccess (Combined) Tests ---


class TestJsonRpcResponseSuccess:
    """Tests for JsonRpcResponseSuccess (JsonRpcEnvelope + BaseResponseSuccess)."""

    def test_construction(self) -> None:
        """Construct with all fields."""
        resp = JsonRpcResponseSuccess(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            id="resp-succ-1",
            result={"sessionId": "abc"},
        )
        assert resp.type == "response"
        assert resp.id == "resp-succ-1"
        assert resp.result == {"sessionId": "abc"}

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        resp = JsonRpcResponseSuccess(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            id="resp-cc",
            result={},
        )
        data = resp.model_dump(by_alias=True)
        assert "factoryApiVersion" in data

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        resp = JsonRpcResponseSuccess(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            type="response",
            id="resp-rt",
            result={"data": [1, 2, 3]},
        )
        json_str = resp.model_dump_json(by_alias=True)
        restored = JsonRpcResponseSuccess.model_validate_json(json_str)
        assert restored == resp

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        resp = JsonRpcResponseSuccess(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            id="resp-x",
            result={},
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert resp.id == "resp-x"


# --- JsonRpcResponseFailure (Combined) Tests ---


class TestJsonRpcResponseFailure:
    """Tests for JsonRpcResponseFailure (JsonRpcEnvelope + BaseResponseFailure)."""

    def test_construction(self) -> None:
        """Construct with all fields."""
        resp = JsonRpcResponseFailure(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            error=JsonRpcError(
                code=JsonRpcErrorCode.ENTITY_NOT_FOUND,
                message="Session not found",
            ),
        )
        assert resp.type == "response"
        assert resp.id is None
        assert resp.error.code == JsonRpcErrorCode.ENTITY_NOT_FOUND

    def test_with_id(self) -> None:
        """Construct with optional id."""
        resp = JsonRpcResponseFailure(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            id="resp-fail-id",
            error=JsonRpcError(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message="error",
            ),
        )
        assert resp.id == "resp-fail-id"

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        resp = JsonRpcResponseFailure(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            type="response",
            id="resp-fail-rt",
            error=JsonRpcError(
                code=JsonRpcErrorCode.PARSE_ERROR,
                message="parse error",
                data={"line": 42},
            ),
        )
        json_str = resp.model_dump_json(by_alias=True)
        restored = JsonRpcResponseFailure.model_validate_json(json_str)
        assert restored == resp

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        resp = JsonRpcResponseFailure(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="response",
            error=JsonRpcError(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message="error",
            ),
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert resp.error.message == "error"


# --- JsonRpcNotification (Combined) Tests ---


class TestJsonRpcNotification:
    """Tests for JsonRpcNotification (JsonRpcEnvelope + BaseNotification)."""

    def test_construction(self) -> None:
        """Construct with all fields."""
        notif = JsonRpcNotification(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="notification",
            method="droid.session_notification",
            params={"notification": {"type": "error", "message": "boom"}},
        )
        assert notif.type == "notification"
        assert notif.method == "droid.session_notification"
        assert notif.params is not None

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        notif = JsonRpcNotification(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="notification",
            method="test.notify",
        )
        data = notif.model_dump(by_alias=True)
        assert "factoryApiVersion" in data

    def test_json_roundtrip(self) -> None:
        """JSON roundtrip preserves data."""
        notif = JsonRpcNotification(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            meta=TraceContextMeta(traceparent="trace-123"),
            type="notification",
            method="droid.session_notification",
            params={"key": "val"},
        )
        json_str = notif.model_dump_json(by_alias=True)
        restored = JsonRpcNotification.model_validate_json(json_str)
        assert restored == notif

    def test_literal_type_enforcement(self) -> None:
        """Type must be 'notification'."""
        with pytest.raises(ValidationError):
            JsonRpcNotification(
                jsonrpc=JSONRPC_VERSION,
                factory_api_version=LEGACY_FACTORY_API_VERSION,
                type="request",  # type: ignore[arg-type]
                method="m",
            )

    def test_extra_field_allowed(self) -> None:
        """Notification models tolerate extra fields for protocol evolution."""
        notif = JsonRpcNotification(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            type="notification",
            method="m",
            extra="tolerated",  # type: ignore[call-arg]
        )
        assert notif.method == "m"


# --- Cross-Model Tests ---


class TestCrossModelBehavior:
    """Tests covering behavior across all shared models."""

    def test_all_models_camel_case_keys(self) -> None:
        """All combined models produce camelCase keys when serialized."""
        request = JsonRpcRequest(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
            factory_protocol_version="1.1.0",
            type="request",
            id="test-1",
            method="test.method",
        )
        data = json.loads(request.model_dump_json(by_alias=True))
        assert "factoryApiVersion" in data
        assert "factoryProtocolVersion" in data

    def test_deserialization_from_camel_case_json_string(self) -> None:
        """Deserialization from camelCase JSON string works for all combined models."""
        raw_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "factoryApiVersion": "1.0.0",
                "factoryProtocolVersion": "1.1.0",
                "_meta": {"traceparent": "trace-abc"},
                "type": "request",
                "id": "req-json",
                "method": "droid.initialize_session",
                "params": {"cwd": "/home"},
            }
        )
        req = JsonRpcRequest.model_validate_json(raw_json)
        assert req.factory_api_version == "1.0.0"
        assert req.factory_protocol_version == "1.1.0"
        assert req.meta is not None
        assert req.meta.traceparent == "trace-abc"
        assert req.id == "req-json"
        assert req.method == "droid.initialize_session"

    def test_optional_fields_default_none(self) -> None:
        """Optional fields across all models default to None."""
        # Envelope optional fields
        envelope = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
        )
        assert envelope.factory_protocol_version is None
        assert envelope.meta is None

        # BaseRequest params
        req = BaseRequest(type="request", id="r1", method="m")
        assert req.params is None

        # BaseNotification params
        notif = BaseNotification(type="notification", method="m")
        assert notif.params is None

        # BaseResponseFailure id
        resp = BaseResponseFailure(
            type="response",
            error=JsonRpcError(code=JsonRpcErrorCode.INTERNAL_ERROR, message="err"),
        )
        assert resp.id is None

        # JsonRpcError data
        err = JsonRpcError(code=JsonRpcErrorCode.PARSE_ERROR, message="parse")
        assert err.data is None

    def test_json_rpc_error_code_in_error(self) -> None:
        """JsonRpcErrorCode enum values are correctly used in JsonRpcError."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.ENTITY_NOT_FOUND,
            message="Entity not found",
        )
        data = error.model_dump(by_alias=True)
        assert data["code"] == -32004

    def test_json_rpc_error_serialization_with_enum(self) -> None:
        """JsonRpcError serializes code as integer."""
        error = JsonRpcError(
            code=JsonRpcErrorCode.PARSE_ERROR,
            message="parse",
        )
        json_str = error.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)
        assert parsed["code"] == -32700
        assert isinstance(parsed["code"], int)

    def test_populate_by_name(self) -> None:
        """Models accept both Python field names and camelCase aliases."""
        # Using Python field name
        envelope1 = JsonRpcEnvelope(
            jsonrpc=JSONRPC_VERSION,
            factory_api_version=LEGACY_FACTORY_API_VERSION,
        )
        # Using model_validate with alias
        envelope2 = JsonRpcEnvelope.model_validate(
            {
                "jsonrpc": JSONRPC_VERSION,
                "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            }
        )
        assert envelope1 == envelope2

    def test_full_response_failure_with_envelope(self) -> None:
        """Full JsonRpcResponseFailure serialization and deserialization."""
        raw = {
            "jsonrpc": "2.0",
            "factoryApiVersion": "1.0.0",
            "type": "response",
            "id": None,
            "error": {
                "code": -32700,
                "message": "Parse error",
                "data": {"line": 1, "col": 5},
            },
        }
        resp = JsonRpcResponseFailure.model_validate(raw)
        assert resp.id is None
        assert resp.error.code == JsonRpcErrorCode.PARSE_ERROR
        assert resp.error.message == "Parse error"
        assert resp.error.data == {"line": 1, "col": 5}
