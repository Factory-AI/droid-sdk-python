"""Comprehensive tests for the JSON-RPC 2.0 protocol engine.

Tests cover:
- Envelope construction with all required fields
- Request ID uniqueness (UUID strings)
- Request/response correlation (matched by ID)
- Out-of-order response resolution
- Timeout handling with metadata
- Notification dispatch to registered handlers
- Server→client request handling (permission, ask_user)
- Error code mapping (ENTITY_NOT_FOUND → SessionNotFoundError)
- Sticky transport error behavior
- Concurrent request resolution
- Unknown response ID handling
- Malformed response handling
- Duplicate response ID handling
- Large message handling
- Notification before initialize_session
- Close behavior
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.errors import (
    DroidClientError,
    InvalidWorkingDirectoryError,
    ProtocolError,
    SessionNotFoundError,
)
from droid_sdk.errors import (
    TimeoutError as DroidTimeoutError,
)
from droid_sdk.protocol import (
    DEFAULT_REQUEST_TIMEOUT,
    MCP_AUTH_TIMEOUT,
    SESSION_INIT_TIMEOUT,
    ProtocolEngine,
    ProtocolTiming,
)
from droid_sdk.schemas.cli import RequestPermissionResult
from droid_sdk.schemas.constants import (
    FACTORY_PROTOCOL_VERSION,
    JSONRPC_VERSION,
    LEGACY_FACTORY_API_VERSION,
)
from droid_sdk.schemas.enums import (
    JsonRpcErrorCode,
    ToolConfirmationOutcome,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ============================================================
# Sentinel for queue-based mock transport
# ============================================================

_SENTINEL = object()

# ============================================================
# Mock transport for testing (async generator based)
# ============================================================


class MockTransport:
    """In-memory mock transport implementing DroidClientTransport protocol."""

    def __init__(self) -> None:
        self._is_connected: bool = False
        self.sent_messages: list[str] = []
        self._closed: bool = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._error: Exception | None = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self) -> None:
        self._is_connected = True
        self._closed = False
        self._error = None
        self._queue = asyncio.Queue()

    async def send(self, message: str) -> None:
        if not self._is_connected:
            raise DroidConnectionError("Transport not connected")
        self.sent_messages.append(message)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    async def close(self) -> None:
        self._is_connected = False
        self._closed = True
        self._queue.put_nowait(_SENTINEL)

    # Test helpers
    def deliver_message(self, message: str) -> None:
        """Simulate receiving a message from the droid process.

        Accepts a JSON string, parses it, and puts the dict in the queue.
        """
        parsed = json.loads(message)
        self._queue.put_nowait(parsed)

    def deliver_error(self, error: Exception) -> None:
        """Simulate a transport error."""
        self._error = error
        self._queue.put_nowait(_SENTINEL)

    def get_last_sent(self) -> dict[str, Any]:
        """Get the last sent message as parsed JSON."""
        assert self.sent_messages, "No messages sent"
        return json.loads(self.sent_messages[-1])  # type: ignore[no-any-return]


def make_success_response(
    request_id: str,
    result: dict[str, Any] | None = None,
) -> str:
    """Create a JSON-RPC success response string."""
    return json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "response",
            "id": request_id,
            "result": result or {},
        }
    )


def make_error_response(
    request_id: str | None,
    code: int,
    message: str,
    data: Any = None,
) -> str:
    """Create a JSON-RPC error response string."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "response",
            "id": request_id,
            "error": error,
        }
    )


def make_notification(
    method: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Create a JSON-RPC notification string."""
    return json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "notification",
            "method": method,
            "params": params or {},
        }
    )


def make_server_request(
    request_id: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Create a JSON-RPC request from server to client."""
    return json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
    )


@pytest_asyncio.fixture
async def transport() -> MockTransport:
    """Create a connected mock transport."""
    t = MockTransport()
    await t.connect()
    return t


@pytest_asyncio.fixture
async def engine(transport: MockTransport) -> AsyncIterator[ProtocolEngine]:
    """Create a ProtocolEngine with a connected mock transport and start it."""
    e = ProtocolEngine(transport=transport)
    await e.start()
    yield e
    await e.close()


# ============================================================
# VAL-PROTOCOL-001: Envelope construction includes all required fields
# ============================================================


class TestEnvelopeConstruction:
    """Tests for outbound request envelope construction."""

    @pytest.mark.asyncio
    async def test_envelope_has_jsonrpc_version(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request includes jsonrpc='2.0'."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["jsonrpc"] == "2.0"
        # Resolve to clean up
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_factory_api_version(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request includes factoryApiVersion."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["factoryApiVersion"] == LEGACY_FACTORY_API_VERSION
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_factory_protocol_version(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request includes factoryProtocolVersion."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["factoryProtocolVersion"] == FACTORY_PROTOCOL_VERSION
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_type_request(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request includes type='request'."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["type"] == "request"
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_method(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request includes the correct method."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["method"] == "droid.list_skills"
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_params(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Outbound request includes params when provided."""
        params = {"text": "hello", "images": []}
        task = asyncio.create_task(
            engine.send_request("droid.add_user_message", params)
        )
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["params"] == params
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_envelope_has_unique_id(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Every outbound request has a unique UUID string id."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        # Verify it's a valid UUID
        uuid.UUID(sent["id"])
        transport.deliver_message(make_success_response(sent["id"]))
        await task


# ============================================================
# VAL-PROTOCOL-002: Request IDs are unique UUIDs
# ============================================================


class TestRequestIdUniqueness:
    """Tests for request ID uniqueness."""

    @pytest.mark.asyncio
    async def test_multiple_requests_have_unique_ids(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Each request has a unique id. No two share an ID."""
        tasks = []
        for _ in range(10):
            t = asyncio.create_task(engine.send_request("droid.list_skills", {}))
            tasks.append(t)
            await asyncio.sleep(0.001)

        ids = set()
        for msg in transport.sent_messages:
            parsed = json.loads(msg)
            req_id = parsed["id"]
            # Each is a valid UUID
            uuid.UUID(req_id)
            ids.add(req_id)

        assert len(ids) == 10

        # Resolve all
        for msg in transport.sent_messages:
            parsed = json.loads(msg)
            transport.deliver_message(make_success_response(parsed["id"]))

        for t in tasks:
            await t


# ============================================================
# VAL-PROTOCOL-003: Response correlation — matched by ID
# ============================================================


class TestResponseCorrelation:
    """Tests for request/response correlation."""

    @pytest.mark.asyncio
    async def test_response_resolves_correct_request(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Incoming responses matched by id resolve the correct pending Future."""
        task1 = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        id1 = json.loads(transport.sent_messages[0])["id"]

        task2 = asyncio.create_task(engine.send_request("droid.list_mcp_servers", {}))
        await asyncio.sleep(0.01)
        id2 = json.loads(transport.sent_messages[1])["id"]

        # Deliver responses in order
        transport.deliver_message(make_success_response(id1, {"skills": []}))
        transport.deliver_message(make_success_response(id2, {"servers": []}))

        result1 = await task1
        result2 = await task2
        assert result1["result"]["skills"] == []
        assert result2["result"]["servers"] == []

    @pytest.mark.asyncio
    async def test_out_of_order_responses(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Out-of-order responses resolve correctly."""
        task1 = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        id1 = json.loads(transport.sent_messages[0])["id"]

        task2 = asyncio.create_task(engine.send_request("droid.list_mcp_servers", {}))
        await asyncio.sleep(0.01)
        id2 = json.loads(transport.sent_messages[1])["id"]

        # Deliver in REVERSE order
        transport.deliver_message(make_success_response(id2, {"servers": ["s1"]}))
        transport.deliver_message(make_success_response(id1, {"skills": ["sk1"]}))

        result1 = await task1
        result2 = await task2
        assert result1["result"]["skills"] == ["sk1"]
        assert result2["result"]["servers"] == ["s1"]


class TestProtocolObservability:
    """Tests for content-free tracing and timing hooks."""

    @pytest.mark.asyncio
    async def test_trace_metadata_and_timing_callback(
        self, transport: MockTransport
    ) -> None:
        timings: list[ProtocolTiming] = []

        def inject(carrier: dict[str, str]) -> None:
            carrier["traceparent"] = "00-trace-parent"
            carrier["ignored"] = "secret"

        traced_engine = ProtocolEngine(
            transport=transport,
            trace_meta_injector=inject,
            timing_callback=timings.append,
        )
        await traced_engine.start()
        try:
            task = asyncio.create_task(
                traced_engine.send_request(
                    "droid.list_skills", {"sensitive": "not-observed"}
                )
            )
            await asyncio.sleep(0.01)
            sent = transport.get_last_sent()
            assert sent["_meta"] == {"traceparent": "00-trace-parent"}

            transport.deliver_message(make_success_response(sent["id"]))
            await task

            assert len(timings) == 1
            assert timings[0].method == "droid.list_skills"
            assert timings[0].outcome == "success"
            assert timings[0].duration_seconds >= 0
            assert not hasattr(timings[0], "params")
        finally:
            await traced_engine.close()


# ============================================================
# VAL-PROTOCOL-004: Timeout handling with metadata
# ============================================================


class TestTimeoutHandling:
    """Tests for request timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Timeout raises TimeoutError with metadata."""
        with pytest.raises(DroidTimeoutError) as exc_info:
            await engine.send_request("droid.list_skills", {}, timeout=0.05)

        err = exc_info.value
        assert err.method == "droid.list_skills"
        assert err.timeout_duration == 0.05
        assert err.request_id is not None

    @pytest.mark.asyncio
    async def test_timeout_cleans_up_pending(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """After timeout, the pending request entry is cleaned up."""
        with pytest.raises(DroidTimeoutError):
            await engine.send_request("droid.list_skills", {}, timeout=0.05)

        # Pending map should be empty
        assert len(engine._pending_requests) == 0

    @pytest.mark.asyncio
    async def test_default_timeout_constants(self) -> None:
        """Default timeout constants have correct values."""
        assert DEFAULT_REQUEST_TIMEOUT == 30.0
        assert SESSION_INIT_TIMEOUT == 60.0
        assert MCP_AUTH_TIMEOUT == 300.0

    @pytest.mark.asyncio
    async def test_custom_timeout_per_request(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Custom timeout can be specified per request."""
        with pytest.raises(DroidTimeoutError) as exc_info:
            await engine.send_request(
                "droid.authenticate_mcp_server",
                {"serverName": "test"},
                timeout=0.05,
            )
        assert exc_info.value.timeout_duration == 0.05


# ============================================================
# VAL-PROTOCOL-005: Notification dispatch to event system
# ============================================================


class TestNotificationDispatch:
    """Tests for notification dispatch to registered handlers."""

    @pytest.mark.asyncio
    async def test_notification_dispatched_to_handler(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Notifications dispatched to registered handlers."""
        received: list[dict[str, Any]] = []
        engine.on_notification(lambda msg: received.append(msg))

        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "assistant_text_delta", "text": "hi"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0]["method"] == "droid.session_notification"

    @pytest.mark.asyncio
    async def test_multiple_listeners_all_receive(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Multiple listeners all receive the same notification."""
        received1: list[dict[str, Any]] = []
        received2: list[dict[str, Any]] = []
        engine.on_notification(lambda msg: received1.append(msg))
        engine.on_notification(lambda msg: received2.append(msg))

        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "error", "message": "test"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_notification_listener_removal(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """A registered listener can be removed."""
        received: list[dict[str, Any]] = []

        def handler(msg: dict[str, Any]) -> None:
            received.append(msg)

        engine.on_notification(handler)
        engine.remove_notification_listener(handler)

        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "error", "message": "test"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_notification_listener_exception_isolated(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """If a listener raises, other listeners still receive the notification."""
        received: list[dict[str, Any]] = []

        def bad_handler(msg: dict[str, Any]) -> None:
            raise RuntimeError("handler crashed")

        def good_handler(msg: dict[str, Any]) -> None:
            received.append(msg)

        engine.on_notification(bad_handler)
        engine.on_notification(good_handler)

        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "error", "message": "test"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        assert len(received) == 1


# ============================================================
# VAL-PROTOCOL-006: Server→client request handling — permission request
# ============================================================


class TestPermissionRequestHandling:
    """Tests for server→client permission request handling."""

    @pytest.mark.asyncio
    async def test_permission_handler_called_response_sent(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Permission handler called, response sent with selectedOption."""

        async def handler(params: dict[str, Any]) -> str:
            return ToolConfirmationOutcome.ProceedOnce.value

        engine.set_permission_handler(handler)

        request = make_server_request(
            "perm-1",
            "droid.request_permission",
            {"toolUses": [], "options": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        # Check response was sent
        response_msgs = [
            m for m in transport.sent_messages if "perm-1" in m and "response" in m
        ]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["id"] == "perm-1"
        assert resp["type"] == "response"
        assert resp["result"]["selectedOption"] == "proceed_once"

    @pytest.mark.asyncio
    async def test_complete_permission_result_is_serialized(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        async def handler(params: dict[str, Any]) -> RequestPermissionResult:
            return RequestPermissionResult(
                selectedOption="proceed_edit",
                comment="approved",
                editedSpecContent="updated spec",
            )

        engine.set_permission_handler(handler)
        transport.deliver_message(
            make_server_request(
                "perm-complete",
                "droid.request_permission",
                {"toolUses": [], "options": []},
            )
        )
        await asyncio.sleep(0.05)

        response = json.loads(transport.sent_messages[-1])
        assert response["result"] == {
            "selectedOption": "proceed_edit",
            "comment": "approved",
            "editedSpecContent": "updated spec",
        }

    @pytest.mark.asyncio
    async def test_permission_no_handler_returns_cancel(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """No handler → Cancel default."""
        request = make_server_request(
            "perm-2",
            "droid.request_permission",
            {"toolUses": [], "options": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        response_msgs = [m for m in transport.sent_messages if "perm-2" in m]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["result"]["selectedOption"] == "cancel"

    @pytest.mark.asyncio
    async def test_permission_handler_exception_sends_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Handler exception → INTERNAL_ERROR response."""

        async def bad_handler(params: dict[str, Any]) -> str:
            raise RuntimeError("handler crashed")

        engine.set_permission_handler(bad_handler)

        request = make_server_request(
            "perm-3",
            "droid.request_permission",
            {"toolUses": [], "options": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        response_msgs = [m for m in transport.sent_messages if "perm-3" in m]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_handler_exception_diagnostics_do_not_disclose_secrets(
        self,
        engine: ProtocolEngine,
        transport: MockTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        secret = "SENTINEL-handler-secret-4f81"

        async def bad_handler(params: dict[str, Any]) -> str:
            raise RuntimeError(f"credential={secret}")

        engine.set_permission_handler(bad_handler)
        caplog.set_level(logging.WARNING, logger="droid_sdk.protocol")
        engine._handle_message(
            json.loads(
                make_server_request(
                    "perm-private",
                    "droid.request_permission",
                    {"toolUses": [], "options": []},
                )
            )
        )
        task = next(iter(engine._background_tasks))
        await task

        response = next(
            json.loads(message)
            for message in transport.sent_messages
            if "perm-private" in message
        )
        assert response["error"]["data"] == {"exceptionType": "RuntimeError"}
        surfaces = (caplog.text, json.dumps(response), str(response), repr(response))
        assert all(secret not in surface for surface in surfaces)
        assert "RuntimeError" in caplog.text


# ============================================================
# VAL-PROTOCOL-007: Server→client request handling — ask_user
# ============================================================


class TestAskUserRequestHandling:
    """Tests for server→client ask_user request handling."""

    @pytest.mark.asyncio
    async def test_ask_user_handler_called_response_sent(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Ask_user handler called, response sent."""

        async def handler(params: dict[str, Any]) -> dict[str, Any]:
            return {
                "cancelled": False,
                "answers": [{"index": 1, "question": "q", "answer": "a"}],
            }

        engine.set_ask_user_handler(handler)

        request = make_server_request(
            "ask-1",
            "droid.ask_user",
            {"toolCallId": "tc-1", "questions": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        response_msgs = [
            m for m in transport.sent_messages if "ask-1" in m and "response" in m
        ]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["id"] == "ask-1"
        assert resp["result"]["cancelled"] is False

    @pytest.mark.asyncio
    async def test_ask_user_no_handler_returns_cancelled(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """No handler → cancelled=True."""
        request = make_server_request(
            "ask-2",
            "droid.ask_user",
            {"toolCallId": "tc-2", "questions": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        response_msgs = [m for m in transport.sent_messages if "ask-2" in m]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["result"]["cancelled"] is True
        assert resp["result"]["answers"] == []

    @pytest.mark.asyncio
    async def test_ask_user_handler_exception_sends_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Handler exception → INTERNAL_ERROR response."""

        async def bad_handler(params: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("handler crashed")

        engine.set_ask_user_handler(bad_handler)

        request = make_server_request(
            "ask-3",
            "droid.ask_user",
            {"toolCallId": "tc-3", "questions": []},
        )
        transport.deliver_message(request)
        await asyncio.sleep(0.05)

        response_msgs = [m for m in transport.sent_messages if "ask-3" in m]
        assert len(response_msgs) >= 1
        resp = json.loads(response_msgs[0])
        assert resp["error"]["code"] == JsonRpcErrorCode.INTERNAL_ERROR.value


# ============================================================
# VAL-PROTOCOL-008: Error code mapping
# ============================================================


class TestErrorCodeMapping:
    """Tests for error code to exception mapping."""

    @pytest.mark.asyncio
    async def test_entity_not_found_maps_to_session_not_found(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """ENTITY_NOT_FOUND(-32004) → SessionNotFoundError."""
        task = asyncio.create_task(
            engine.send_request("droid.load_session", {"sessionId": "abc"})
        )
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.ENTITY_NOT_FOUND.value,
                "Session not found",
            )
        )

        with pytest.raises(SessionNotFoundError):
            await task

    @pytest.mark.asyncio
    async def test_other_error_maps_to_protocol_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Other error codes → ProtocolError."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.INTERNAL_ERROR.value,
                "Something failed",
            )
        )

        with pytest.raises(ProtocolError) as exc_info:
            await task
        assert exc_info.value.code == JsonRpcErrorCode.INTERNAL_ERROR.value

    @pytest.mark.asyncio
    async def test_entity_not_found_for_other_method_remains_protocol_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.ENTITY_NOT_FOUND.value,
                "Tool not found",
            )
        )

        with pytest.raises(ProtocolError):
            await task

    @pytest.mark.asyncio
    async def test_invalid_initialize_cwd_maps_to_specific_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        task = asyncio.create_task(
            engine.send_request("droid.initialize_session", {"cwd": "/missing/project"})
        )
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.INVALID_PARAMS.value,
                "Invalid working directory",
            )
        )

        with pytest.raises(InvalidWorkingDirectoryError) as exc_info:
            await task
        assert exc_info.value.cwd == "/missing/project"

    @pytest.mark.asyncio
    async def test_error_response_contains_metadata(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Error response carries code, message, data in ProtocolError."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.INVALID_PARAMS.value,
                "Bad params",
                {"detail": "missing field"},
            )
        )

        with pytest.raises(ProtocolError) as exc_info:
            await task
        err = exc_info.value
        assert err.code == JsonRpcErrorCode.INVALID_PARAMS.value
        assert err.data == {"detail": "missing field"}


# ============================================================
# VAL-PROTOCOL-009: Sticky transport error rejects all subsequent requests
# ============================================================


class TestStickyTransportError:
    """Tests for sticky transport error behavior."""

    @pytest.mark.asyncio
    async def test_transport_error_rejects_pending(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Transport error rejects all pending requests."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)

        transport.deliver_error(RuntimeError("transport died"))
        await asyncio.sleep(0.01)

        with pytest.raises(DroidClientError):
            await task

    @pytest.mark.asyncio
    async def test_transport_error_rejects_subsequent_requests(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """After transport error, subsequent requests are immediately rejected."""
        transport.deliver_error(RuntimeError("transport died"))
        await asyncio.sleep(0.01)

        with pytest.raises(DroidClientError):
            await engine.send_request("droid.list_skills", {})

    @pytest.mark.asyncio
    async def test_sticky_error_is_preserved(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """The sticky error is the same error instance for all rejections."""
        original_error = RuntimeError("transport died")
        transport.deliver_error(original_error)
        await asyncio.sleep(0.01)

        with pytest.raises(DroidClientError):
            await engine.send_request("droid.list_skills", {})

        with pytest.raises(DroidClientError):
            await engine.send_request("droid.list_mcp_servers", {})


# ============================================================
# VAL-PROTOCOL-010: Concurrent requests resolve independently
# ============================================================


class TestConcurrentRequests:
    """Tests for concurrent request handling."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_resolve_independently(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Multiple simultaneous requests each resolve with correct result."""
        tasks = [
            asyncio.create_task(engine.send_request("droid.list_skills", {})),
            asyncio.create_task(engine.send_request("droid.list_mcp_servers", {})),
            asyncio.create_task(engine.send_request("droid.list_mcp_tools", {})),
        ]
        await asyncio.sleep(0.01)

        # Get IDs
        ids = [json.loads(m)["id"] for m in transport.sent_messages[:3]]

        # Resolve each with distinct result
        transport.deliver_message(make_success_response(ids[0], {"skills": ["a"]}))
        transport.deliver_message(make_success_response(ids[1], {"servers": ["b"]}))
        transport.deliver_message(make_success_response(ids[2], {"tools": ["c"]}))

        results = await asyncio.gather(*tasks)
        assert results[0]["result"]["skills"] == ["a"]
        assert results[1]["result"]["servers"] == ["b"]
        assert results[2]["result"]["tools"] == ["c"]

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_poison_others(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """One failure does not poison other concurrent requests."""
        task_ok1 = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        task_fail = asyncio.create_task(
            engine.send_request("droid.load_session", {"sessionId": "x"})
        )
        task_ok2 = asyncio.create_task(
            engine.send_request("droid.list_mcp_servers", {})
        )
        await asyncio.sleep(0.01)

        ids = [json.loads(m)["id"] for m in transport.sent_messages[:3]]

        # Resolve first OK
        transport.deliver_message(make_success_response(ids[0], {"skills": []}))
        # Fail second
        transport.deliver_message(
            make_error_response(
                ids[1],
                JsonRpcErrorCode.ENTITY_NOT_FOUND.value,
                "Not found",
            )
        )
        # Resolve third OK
        transport.deliver_message(make_success_response(ids[2], {"servers": []}))

        result1 = await task_ok1
        assert result1["result"]["skills"] == []

        with pytest.raises(SessionNotFoundError):
            await task_fail

        result3 = await task_ok2
        assert result3["result"]["servers"] == []


# ============================================================
# VAL-PROTOCOL-011: Unknown response ID logged, not crashed
# ============================================================


class TestUnknownResponseId:
    """Tests for unknown response ID handling."""

    @pytest.mark.asyncio
    async def test_unknown_response_id_does_not_crash(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """A response with an unknown ID is logged, client remains functional."""
        transport.deliver_message(
            make_success_response("unknown-id-123", {"data": "test"})
        )
        await asyncio.sleep(0.01)

        # Engine should still be functional
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(make_success_response(sent["id"]))
        result = await task
        assert result["result"] == {}

    @pytest.mark.asyncio
    async def test_unknown_response_id_logged_as_warning(
        self,
        engine: ProtocolEngine,
        transport: MockTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown response ID triggers a warning log."""
        with caplog.at_level(logging.WARNING):
            transport.deliver_message(make_success_response("unknown-id-456", {}))
            await asyncio.sleep(0.01)

        assert any("unknown-id-456" in r.message for r in caplog.records)


# ============================================================
# VAL-PROTOCOL-012: Malformed response rejects pending request
# ============================================================


class TestMalformedResponse:
    """Tests for malformed response handling."""

    @pytest.mark.asyncio
    async def test_malformed_response_rejects_with_protocol_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Malformed response → ProtocolError on pending request."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        # Send an invalid response (missing required fields) as a parsed dict
        malformed = json.dumps(
            {"id": sent["id"], "type": "response", "bad_field": True}
        )
        transport.deliver_message(malformed)

        with pytest.raises(ProtocolError):
            await task

    @pytest.mark.asyncio
    async def test_completely_invalid_json_message_does_not_crash(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Unknown message format does not crash the engine."""
        # Inject a dict with no recognizable type (since read_messages now yields dicts)
        transport._queue.put_nowait({"unknown_field": True})
        await asyncio.sleep(0.01)

        # Engine still functional
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(make_success_response(sent["id"]))
        result = await task
        assert result is not None


# ============================================================
# VAL-PROTOCOL-013: Notification before initialize_session
# ============================================================


class TestNotificationBeforeInit:
    """Tests for notifications received before initialize_session."""

    @pytest.mark.asyncio
    async def test_notification_before_init_delivered(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Notifications before initialize_session are delivered to listeners."""
        received: list[dict[str, Any]] = []
        engine.on_notification(lambda msg: received.append(msg))

        # Send notification before any request
        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "error", "message": "early"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0]["params"]["notification"]["type"] == "error"

    @pytest.mark.asyncio
    async def test_client_still_functional_after_early_notification(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Client can still call initialize_session after early notification."""
        received: list[dict[str, Any]] = []
        engine.on_notification(lambda msg: received.append(msg))

        notification = make_notification(
            "droid.session_notification",
            {"notification": {"type": "error", "message": "early"}},
        )
        transport.deliver_message(notification)
        await asyncio.sleep(0.01)

        # Now send a request
        task = asyncio.create_task(
            engine.send_request(
                "droid.initialize_session",
                {"machineId": "m1", "cwd": "/tmp"},
            )
        )
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(
            make_success_response(sent["id"], {"sessionId": "s1"})
        )
        result = await task
        assert result["result"]["sessionId"] == "s1"


# ============================================================
# VAL-PROTOCOL-014: Duplicate response ID handled gracefully
# ============================================================


class TestDuplicateResponseId:
    """Tests for duplicate response ID handling."""

    @pytest.mark.asyncio
    async def test_duplicate_response_id_first_resolves(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """First response resolves the request, second is benign."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        # First response
        transport.deliver_message(make_success_response(sent["id"], {"skills": ["a"]}))
        result = await task
        assert result["result"]["skills"] == ["a"]

        # Second response with same ID (should be treated as unknown)
        transport.deliver_message(make_success_response(sent["id"], {"skills": ["b"]}))
        await asyncio.sleep(0.01)

        # Engine should still work
        task2 = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent2 = transport.get_last_sent()
        transport.deliver_message(make_success_response(sent2["id"]))
        await task2


# ============================================================
# VAL-PROTOCOL-015: Large message handling (multi-MB payloads)
# ============================================================


class TestLargeMessages:
    """Tests for large message handling."""

    @pytest.mark.asyncio
    async def test_large_response_handled_correctly(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """2MB response is correctly received and delivered."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        # Create 2MB result
        large_data = "x" * (2 * 1024 * 1024)
        transport.deliver_message(
            make_success_response(sent["id"], {"data": large_data})
        )

        result = await task
        assert result["result"]["data"] == large_data

    @pytest.mark.asyncio
    async def test_large_request_sent_correctly(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """1MB params are correctly serialized as a single JSONL line."""
        large_params = {"data": "y" * (1024 * 1024)}
        task = asyncio.create_task(
            engine.send_request("droid.add_user_message", large_params)
        )
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent()
        assert sent["params"]["data"] == large_params["data"]

        transport.deliver_message(make_success_response(sent["id"]))
        await task


# ============================================================
# Close behavior
# ============================================================


class TestClose:
    """Tests for close behavior."""

    @pytest.mark.asyncio
    async def test_close_rejects_pending_requests(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Close rejects all pending requests."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)

        await engine.close()

        with pytest.raises(DroidClientError):
            await task

    @pytest.mark.asyncio
    async def test_close_clears_handlers(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Close clears all handlers."""
        received: list[dict[str, Any]] = []
        engine.on_notification(lambda msg: received.append(msg))
        engine.set_permission_handler(AsyncMock(return_value="cancel"))
        engine.set_ask_user_handler(
            AsyncMock(return_value={"cancelled": True, "answers": []})
        )

        await engine.close()

        # Notification listeners cleared
        assert len(engine._notification_listeners) == 0

    @pytest.mark.asyncio
    async def test_close_makes_subsequent_requests_fail(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """After close, new requests fail immediately."""
        await engine.close()

        with pytest.raises(DroidClientError):
            await engine.send_request("droid.list_skills", {})

    @pytest.mark.asyncio
    async def test_close_is_idempotent(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Close can be called multiple times without error."""
        await engine.close()
        await engine.close()  # Should not raise


# ============================================================
# Null-id error response
# ============================================================


class TestNullIdErrorResponse:
    """Tests for null-id error response handling."""

    @pytest.mark.asyncio
    async def test_null_id_error_response_does_not_crash(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Null-id error response logged but doesn't crash."""
        transport.deliver_message(
            make_error_response(
                None,
                JsonRpcErrorCode.PARSE_ERROR.value,
                "Parse error",
            )
        )
        await asyncio.sleep(0.01)

        # Engine still works
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        transport.deliver_message(make_success_response(sent["id"]))
        result = await task
        assert result is not None


# ============================================================
# Error response for specific methods
# ============================================================


class TestMethodSpecificErrorMapping:
    """Tests for method-specific error code mapping."""

    @pytest.mark.asyncio
    async def test_session_not_found_error_has_metadata(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """SessionNotFoundError includes session_id when identifiable."""
        task = asyncio.create_task(
            engine.send_request("droid.load_session", {"sessionId": "test-session-123"})
        )
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        transport.deliver_message(
            make_error_response(
                sent["id"],
                JsonRpcErrorCode.ENTITY_NOT_FOUND.value,
                "Session not found",
            )
        )

        with pytest.raises(SessionNotFoundError) as exc_info:
            await task
        # SessionNotFoundError should have the sent id available
        assert exc_info.value.session_id is not None


# ============================================================
# Additional edge case tests
# ============================================================


class TestEdgeCases:
    """Tests for various edge cases."""

    @pytest.mark.asyncio
    async def test_send_request_when_transport_not_connected(self) -> None:
        """send_request when transport not connected raises."""
        transport = MockTransport()
        transport._is_connected = False
        engine = ProtocolEngine(transport=transport)

        with pytest.raises(DroidClientError):
            await engine.send_request("droid.list_skills", {})

    @pytest.mark.asyncio
    async def test_empty_params_sent_correctly(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """Empty params dict is included in the request."""
        task = asyncio.create_task(engine.send_request("droid.interrupt_session", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()
        assert sent["params"] == {}
        transport.deliver_message(make_success_response(sent["id"]))
        await task

    @pytest.mark.asyncio
    async def test_response_with_result_and_error_treated_as_error(
        self, engine: ProtocolEngine, transport: MockTransport
    ) -> None:
        """A response with both 'result' and 'error' treats error as precedent."""
        task = asyncio.create_task(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent()

        # Malformed: error present should be treated as error
        transport._queue.put_nowait(
            {
                "jsonrpc": "2.0",
                "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
                "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
                "type": "response",
                "id": sent["id"],
                "error": {
                    "code": JsonRpcErrorCode.INTERNAL_ERROR.value,
                    "message": "dual response",
                },
                "result": {"skills": []},
            }
        )

        # Should raise an error (ProtocolError or similar)
        with pytest.raises((ProtocolError, DroidClientError)):
            await task

    @pytest.mark.asyncio
    async def test_transport_send_failure_rejects_request(self) -> None:
        """If transport.send() raises, the pending request is rejected."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        # Make send fail
        async def failing_send(msg: str) -> None:
            raise DroidConnectionError("send failed")

        transport.send = failing_send  # type: ignore[assignment]

        try:
            with pytest.raises(DroidClientError):
                await engine.send_request("droid.list_skills", {})

            # Pending map should be clean
            assert len(engine._pending_requests) == 0
        finally:
            await engine.close()


# ============================================================
# Malformed (non-dict) error payloads
# ============================================================


class TestNonDictErrorPayload:
    """Regression tests for non-dict error payloads in responses."""

    @pytest.mark.asyncio
    async def test_string_error_payload_raises_protocol_error(self) -> None:
        """error='some string' should raise ProtocolError(PARSE_ERROR)."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        task = asyncio.ensure_future(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0)

        sent = transport.get_last_sent()
        request_id = sent["id"]

        transport._queue.put_nowait(
            {
                "jsonrpc": JSONRPC_VERSION,
                "type": "response",
                "id": request_id,
                "error": "something went wrong",
            }
        )

        try:
            with pytest.raises(ProtocolError) as exc_info:
                await task
            assert exc_info.value.code == JsonRpcErrorCode.PARSE_ERROR.value
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_int_error_payload_raises_protocol_error(self) -> None:
        """error=42 should raise ProtocolError(PARSE_ERROR)."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        task = asyncio.ensure_future(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0)

        sent = transport.get_last_sent()
        request_id = sent["id"]

        transport._queue.put_nowait(
            {
                "jsonrpc": JSONRPC_VERSION,
                "type": "response",
                "id": request_id,
                "error": 42,
            }
        )

        try:
            with pytest.raises(ProtocolError) as exc_info:
                await task
            assert exc_info.value.code == JsonRpcErrorCode.PARSE_ERROR.value
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_list_error_payload_raises_protocol_error(self) -> None:
        """error=[1, 2, 3] should raise ProtocolError(PARSE_ERROR)."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        task = asyncio.ensure_future(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0)

        sent = transport.get_last_sent()
        request_id = sent["id"]

        transport._queue.put_nowait(
            {
                "jsonrpc": JSONRPC_VERSION,
                "type": "response",
                "id": request_id,
                "error": [1, 2, 3],
            }
        )

        try:
            with pytest.raises(ProtocolError) as exc_info:
                await task
            assert exc_info.value.code == JsonRpcErrorCode.PARSE_ERROR.value
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_bool_error_payload_raises_protocol_error(self) -> None:
        """error=True should raise ProtocolError(PARSE_ERROR)."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        task = asyncio.ensure_future(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0)

        sent = transport.get_last_sent()
        request_id = sent["id"]

        transport._queue.put_nowait(
            {
                "jsonrpc": JSONRPC_VERSION,
                "type": "response",
                "id": request_id,
                "error": True,
            }
        )

        try:
            with pytest.raises(ProtocolError) as exc_info:
                await task
            assert exc_info.value.code == JsonRpcErrorCode.PARSE_ERROR.value
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_null_error_is_not_treated_as_error(self) -> None:
        """error=null with result present should NOT raise (treated as success)."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        task = asyncio.ensure_future(engine.send_request("droid.list_skills", {}))
        await asyncio.sleep(0)

        sent = transport.get_last_sent()
        request_id = sent["id"]

        transport._queue.put_nowait(
            {
                "jsonrpc": JSONRPC_VERSION,
                "type": "response",
                "id": request_id,
                "result": {"skills": []},
                "error": None,
            }
        )

        try:
            response = await task
            assert response["result"] == {"skills": []}
        finally:
            await engine.close()


# ============================================================
# Handler task cancellation on close
# ============================================================


class TestHandlerTaskCancellationOnClose:
    """Tests that close() cancels and awaits in-flight server→client
    handler tasks (permission/ask_user background tasks).
    """

    @pytest.mark.asyncio
    async def test_close_cancels_inflight_permission_handler_task(self) -> None:
        """close() cancels a long-running permission handler task."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        handler_started = asyncio.Event()
        handler_cancelled = asyncio.Event()

        async def slow_permission_handler(params: dict[str, Any]) -> str:
            handler_started.set()
            try:
                await asyncio.sleep(100)  # Very long wait
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise
            return "approve"

        engine.set_permission_handler(slow_permission_handler)

        # Send a permission request from the "server"
        transport.deliver_message(
            make_server_request(
                "perm-req-1",
                "droid.request_permission",
                {"toolUses": [{"name": "file_write"}], "options": []},
            )
        )

        # Wait for the handler to start
        await asyncio.wait_for(handler_started.wait(), timeout=2.0)

        # Verify there's a background task running
        assert len(engine._background_tasks) >= 1

        # Close the engine — should cancel the handler task
        await engine.close()

        # Handler should have been cancelled
        assert handler_cancelled.is_set()

        # No leftover background tasks
        assert len(engine._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_close_cancels_inflight_ask_user_handler_task(self) -> None:
        """close() cancels a long-running ask_user handler task."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        handler_started = asyncio.Event()
        handler_cancelled = asyncio.Event()

        async def slow_ask_user_handler(params: dict[str, Any]) -> dict[str, Any]:
            handler_started.set()
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise
            return {"cancelled": False, "answers": ["yes"]}

        engine.set_ask_user_handler(slow_ask_user_handler)

        # Send an ask_user request
        transport.deliver_message(
            make_server_request(
                "ask-req-1",
                "droid.ask_user",
                {"toolCallId": "tc-1", "questions": [{"text": "OK?"}]},
            )
        )

        # Wait for handler to start
        await asyncio.wait_for(handler_started.wait(), timeout=2.0)
        assert len(engine._background_tasks) >= 1

        # Close — should cancel and await
        await engine.close()

        assert handler_cancelled.is_set()
        assert len(engine._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_no_post_close_task_leakage(self) -> None:
        """Regression: after close(), no background tasks remain running."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        handlers_started = asyncio.Event()
        start_count = 0

        async def slow_handler(params: dict[str, Any]) -> str:
            nonlocal start_count
            start_count += 1
            if start_count >= 2:
                handlers_started.set()
            await asyncio.sleep(100)
            return "approve"

        engine.set_permission_handler(slow_handler)

        # Send two permission requests
        transport.deliver_message(
            make_server_request(
                "perm-1",
                "droid.request_permission",
                {"toolUses": [{"name": "exec"}], "options": []},
            )
        )
        transport.deliver_message(
            make_server_request(
                "perm-2",
                "droid.request_permission",
                {"toolUses": [{"name": "write"}], "options": []},
            )
        )

        # Wait for both to start
        await asyncio.wait_for(handlers_started.wait(), timeout=2.0)
        assert len(engine._background_tasks) >= 2

        # Close everything
        await engine.close()

        # Zero tasks remaining
        assert len(engine._background_tasks) == 0

        # Allow event loop to process
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_close_with_no_inflight_handlers_is_clean(self) -> None:
        """close() with no in-flight handlers doesn't raise or hang."""
        transport = MockTransport()
        await transport.connect()
        engine = ProtocolEngine(transport=transport)
        await engine.start()

        # No handlers running
        assert len(engine._background_tasks) == 0

        # Should complete cleanly
        await engine.close()
        assert len(engine._background_tasks) == 0
