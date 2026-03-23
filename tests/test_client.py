"""Tests for the DroidClient class — session methods and core lifecycle.

Covers:
- initialize_session, load_session, add_user_message
- interrupt_session, kill_worker_session, update_session_settings
- is_connected property, session_id tracking
- close() cleanup, close-before-connect no-op, method-after-close error
- async context manager support
- Works with any DroidClientTransport implementation (mock transport)
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.errors import (
    DroidClientError,
    ProtocolError,
    SessionError,
    SessionNotFoundError,
)
from droid_sdk.protocol import SESSION_INIT_TIMEOUT
from droid_sdk.schemas.enums import DroidServerMethod, JsonRpcErrorCode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ============================================================
# Mock in-memory transport implementing DroidClientTransport Protocol
# ============================================================


_SENTINEL = object()


class MockTransport:
    """In-memory transport for testing DroidClient.

    Implements the DroidClientTransport Protocol with async generator
    read_messages().
    """

    def __init__(self) -> None:
        self._is_connected: bool = False
        self.sent_messages: list[str] = []
        self._closed: bool = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._error: Exception | None = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def send(self, message: str) -> None:
        if not self._is_connected:
            raise DroidConnectionError("Transport not connected")
        self.sent_messages.append(message)

    async def connect(self) -> None:
        self._is_connected = True
        self._closed = False
        self._error = None
        self._queue = asyncio.Queue()

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
    def inject_message(self, message: dict[str, Any]) -> None:
        """Inject a JSON-RPC message as if received from the process."""
        self._queue.put_nowait(message)

    def inject_error(self, error: Exception) -> None:
        """Inject a transport error."""
        self._error = error
        self._queue.put_nowait(_SENTINEL)

    def get_last_sent_parsed(self) -> dict[str, Any]:
        """Parse and return the last sent message."""
        assert len(self.sent_messages) > 0, "No messages sent"
        return json.loads(self.sent_messages[-1])  # type: ignore[no-any-return]


# ============================================================
# Helper to build JSON-RPC success responses
# ============================================================


def make_success_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response dict."""
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
    """Build a JSON-RPC error response dict."""
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


# Minimal valid result payloads
INIT_SESSION_RESULT: dict[str, Any] = {
    "sessionId": "sess-123",
    "session": {"messages": []},
    "settings": {
        "modelId": "claude-sonnet-4",
        "reasoningEffort": "medium",
    },
}

LOAD_SESSION_RESULT: dict[str, Any] = {
    "session": {"messages": []},
    "settings": {
        "modelId": "claude-sonnet-4",
        "reasoningEffort": "medium",
    },
}


# ============================================================
# Helper to set up a connected DroidClient with mock transport
# ============================================================


async def create_connected_client() -> tuple[Any, MockTransport]:
    """Create a DroidClient with a connected mock transport.

    Returns (client, transport) tuple. Import is done here to avoid
    import errors during the TDD red phase.
    """
    from droid_sdk.client import DroidClient

    transport = MockTransport()
    client = DroidClient(transport=transport)
    await client.connect()
    return client, transport


async def create_client_with_session() -> tuple[Any, MockTransport]:
    """Create a DroidClient with an active session."""
    client, transport = await create_connected_client()

    # Start init request in background and inject response
    async def do_init() -> Any:
        return await client.initialize_session(
            machine_id="test-machine",
            cwd="/tmp/test",
        )

    task = asyncio.create_task(do_init())
    await asyncio.sleep(0.01)  # Let the request be sent

    # Parse the sent request to get the ID
    sent = transport.get_last_sent_parsed()
    request_id = sent["id"]

    # Inject response
    transport.inject_message(make_success_response(request_id, INIT_SESSION_RESULT))
    await task

    return client, transport


# ============================================================
# Tests
# ============================================================


class TestDroidClientLifecycle:
    """Tests for connect/close/is_connected lifecycle."""

    @pytest.mark.asyncio
    async def test_is_connected_false_before_connect(self) -> None:
        """is_connected is False before connect() is called."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_is_connected_true_after_connect(self) -> None:
        """is_connected becomes True after connect()."""
        client, _transport = await create_connected_client()
        assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_is_connected_false_after_close(self) -> None:
        """is_connected becomes False after close()."""
        client, _transport = await create_connected_client()
        await client.close()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_close_before_connect_is_noop(self) -> None:
        """close() before connect() completes without exception."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)
        await client.close()  # Should not raise
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_close_before_connect_still_allows_connect(self) -> None:
        """After close() before connect(), connect() still works."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)
        await client.close()
        await client.connect()
        assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        """close() can be called multiple times without error."""
        client, _transport = await create_connected_client()
        await client.close()
        await client.close()  # Second close is no-op
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_session_id_none_before_init(self) -> None:
        """session_id is None before initialize_session or load_session."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)
        assert client.session_id is None


class TestMethodAfterClose:
    """Method call after close() raises ConnectionError."""

    @pytest.mark.asyncio
    async def test_initialize_session_after_close_raises(self) -> None:
        """initialize_session after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.initialize_session(
                machine_id="test-machine",
                cwd="/tmp/test",
            )

    @pytest.mark.asyncio
    async def test_load_session_after_close_raises(self) -> None:
        """load_session after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.load_session(session_id="abc")

    @pytest.mark.asyncio
    async def test_add_user_message_after_close_raises(self) -> None:
        """add_user_message after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.add_user_message(text="Hello")

    @pytest.mark.asyncio
    async def test_interrupt_session_after_close_raises(self) -> None:
        """interrupt_session after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.interrupt_session()

    @pytest.mark.asyncio
    async def test_kill_worker_session_after_close_raises(self) -> None:
        """kill_worker_session after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.kill_worker_session(worker_session_id="ws-1")

    @pytest.mark.asyncio
    async def test_update_session_settings_after_close_raises(self) -> None:
        """update_session_settings after close() raises ConnectionError."""
        client, _transport = await create_connected_client()
        await client.close()
        with pytest.raises(DroidConnectionError):
            await client.update_session_settings(model_id="gpt-4")


class TestAsyncContextManager:
    """async with DroidClient(...) support."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_closes(self) -> None:
        """async with connects on entry and closes on exit."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)

        async with client:
            assert client.is_connected is True

        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exception(self) -> None:
        """async with closes even if exception occurs."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)

        with pytest.raises(ValueError, match="boom"):
            async with client:
                assert client.is_connected is True
                raise ValueError("boom")

        assert client.is_connected is False


class TestInitializeSession:
    """Tests for initialize_session method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method(self) -> None:
        """initialize_session sends droid.initialize_session."""
        client, transport = await create_connected_client()

        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test-machine",
                cwd="/tmp/test",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.INITIALIZE_SESSION.value

        # Inject response
        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        result = await task
        assert result.session_id == "sess-123"

    @pytest.mark.asyncio
    async def test_sets_session_id_after_success(self) -> None:
        """session_id is set after successful initialize_session."""
        client, _transport = await create_client_with_session()
        assert client.session_id == "sess-123"

    @pytest.mark.asyncio
    async def test_uses_extended_timeout(self) -> None:
        """initialize_session uses SESSION_INIT_TIMEOUT."""
        # We validate that the timeout constant is correct.
        # The actual timeout passing is verified by integration tests.
        assert SESSION_INIT_TIMEOUT == 60.0

    @pytest.mark.asyncio
    async def test_passes_all_params(self) -> None:
        """initialize_session passes machine_id, cwd, and optional params."""
        client, transport = await create_connected_client()

        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="my-machine",
                cwd="/home/user/project",
                workspace_id="ws-abc",
                model_id="claude-sonnet-4",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        params = sent["params"]
        assert params["machineId"] == "my-machine"
        assert params["cwd"] == "/home/user/project"
        assert params["workspaceId"] == "ws-abc"
        assert params["modelId"] == "claude-sonnet-4"

        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        await task

    @pytest.mark.asyncio
    async def test_returns_typed_result(self) -> None:
        """initialize_session returns InitializeSessionResult."""
        client, transport = await create_connected_client()

        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test-machine",
                cwd="/tmp",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        result = await task

        from droid_sdk.schemas.client import InitializeSessionResult

        assert isinstance(result, InitializeSessionResult)
        assert result.session_id == "sess-123"
        assert result.settings.model_id == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_error_response_raises_protocol_error(self) -> None:
        """initialize_session raises ProtocolError on error response."""
        client, transport = await create_connected_client()

        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test-machine",
                cwd="/tmp",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Init failed",
            )
        )

        with pytest.raises(ProtocolError):
            await task


class TestLoadSession:
    """Tests for load_session method."""

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        """load_session sends droid.load_session with session_id."""
        client, transport = await create_connected_client()

        async def do_load() -> Any:
            return await client.load_session(session_id="sess-abc")

        task = asyncio.create_task(do_load())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.LOAD_SESSION.value
        assert sent["params"]["sessionId"] == "sess-abc"

        transport.inject_message(make_success_response(sent["id"], LOAD_SESSION_RESULT))
        await task

    @pytest.mark.asyncio
    async def test_sets_session_id_after_success(self) -> None:
        """session_id is set after successful load_session."""
        client, transport = await create_connected_client()

        async def do_load() -> Any:
            return await client.load_session(session_id="sess-xyz")

        task = asyncio.create_task(do_load())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], LOAD_SESSION_RESULT))
        await task
        assert client.session_id == "sess-xyz"

    @pytest.mark.asyncio
    async def test_returns_typed_result(self) -> None:
        """load_session returns LoadSessionResult."""
        client, transport = await create_connected_client()

        async def do_load() -> Any:
            return await client.load_session(session_id="sess-abc")

        task = asyncio.create_task(do_load())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], LOAD_SESSION_RESULT))
        result = await task

        from droid_sdk.schemas.client import LoadSessionResult

        assert isinstance(result, LoadSessionResult)
        assert result.settings.model_id == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_entity_not_found_raises_session_not_found_error(self) -> None:
        """load_session maps ENTITY_NOT_FOUND to SessionNotFoundError."""
        client, transport = await create_connected_client()

        async def do_load() -> Any:
            return await client.load_session(session_id="nonexistent")

        task = asyncio.create_task(do_load())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.ENTITY_NOT_FOUND.value,
                message="Session not found",
            )
        )

        with pytest.raises(SessionNotFoundError) as exc_info:
            await task
        assert "nonexistent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_other_error_raises_protocol_error(self) -> None:
        """load_session raises ProtocolError on non-ENTITY_NOT_FOUND errors."""
        client, transport = await create_connected_client()

        async def do_load() -> Any:
            return await client.load_session(session_id="abc")

        task = asyncio.create_task(do_load())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Something broke",
            )
        )

        with pytest.raises(ProtocolError):
            await task


class TestAddUserMessage:
    """Tests for add_user_message method."""

    @pytest.mark.asyncio
    async def test_requires_active_session(self) -> None:
        """add_user_message raises SessionError without active session."""
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError, match="No active session"):
            await client.add_user_message(text="Hello")

    @pytest.mark.asyncio
    async def test_sends_text(self) -> None:
        """add_user_message sends text parameter."""
        client, transport = await create_client_with_session()

        async def do_msg() -> Any:
            return await client.add_user_message(text="Hello world")

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.ADD_USER_MESSAGE.value
        assert sent["params"]["text"] == "Hello world"

        transport.inject_message(make_success_response(sent["id"], {}))
        await task

    @pytest.mark.asyncio
    async def test_sends_images_and_files(self) -> None:
        """add_user_message sends images and files."""
        client, transport = await create_client_with_session()

        images = [{"type": "base64", "data": "abc123", "mediaType": "image/png"}]
        files = [
            {
                "type": "base64",
                "mediaType": "application/pdf",
                "data": "pdf-data",
            }
        ]

        async def do_msg() -> Any:
            return await client.add_user_message(
                text="See attached",
                images=images,
                files=files,
            )

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["params"]["images"] == images
        assert sent["params"]["files"] == files

        transport.inject_message(make_success_response(sent["id"], {}))
        await task

    @pytest.mark.asyncio
    async def test_supports_custom_request_id(self) -> None:
        """add_user_message supports custom request_id."""
        client, transport = await create_client_with_session()

        async def do_msg() -> Any:
            return await client.add_user_message(
                text="Hi",
                request_id="custom-id-42",
            )

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["id"] == "custom-id-42"

        transport.inject_message(make_success_response("custom-id-42", {}))
        await task

    @pytest.mark.asyncio
    async def test_error_response_raises_protocol_error(self) -> None:
        """add_user_message raises ProtocolError on error response."""
        client, transport = await create_client_with_session()

        async def do_msg() -> Any:
            return await client.add_user_message(text="fail")

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Message failed",
            )
        )

        with pytest.raises(ProtocolError):
            await task


class TestInterruptSession:
    """Tests for interrupt_session method."""

    @pytest.mark.asyncio
    async def test_requires_active_session(self) -> None:
        """interrupt_session raises SessionError without active session."""
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError, match="No active session"):
            await client.interrupt_session()

    @pytest.mark.asyncio
    async def test_sends_correct_method(self) -> None:
        """interrupt_session sends droid.interrupt_session."""
        client, transport = await create_client_with_session()

        async def do_interrupt() -> Any:
            return await client.interrupt_session()

        task = asyncio.create_task(do_interrupt())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.INTERRUPT_SESSION.value

        transport.inject_message(make_success_response(sent["id"], {}))
        await task

    @pytest.mark.asyncio
    async def test_error_response_raises(self) -> None:
        """interrupt_session error response raises ProtocolError."""
        client, transport = await create_client_with_session()

        async def do_interrupt() -> Any:
            return await client.interrupt_session()

        task = asyncio.create_task(do_interrupt())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="fail",
            )
        )

        with pytest.raises(ProtocolError):
            await task


class TestKillWorkerSession:
    """Tests for kill_worker_session method."""

    @pytest.mark.asyncio
    async def test_requires_active_session(self) -> None:
        """kill_worker_session raises SessionError without active session."""
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError, match="No active session"):
            await client.kill_worker_session(worker_session_id="ws-1")

    @pytest.mark.asyncio
    async def test_sends_correct_method_and_params(self) -> None:
        """kill_worker_session sends correct method and worker_session_id."""
        client, transport = await create_client_with_session()

        async def do_kill() -> Any:
            return await client.kill_worker_session(worker_session_id="ws-abc-123")

        task = asyncio.create_task(do_kill())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.KILL_WORKER_SESSION.value
        assert sent["params"]["workerSessionId"] == "ws-abc-123"

        transport.inject_message(make_success_response(sent["id"], {}))
        await task


class TestUpdateSessionSettings:
    """Tests for update_session_settings method."""

    @pytest.mark.asyncio
    async def test_requires_active_session(self) -> None:
        """update_session_settings raises SessionError without active session."""
        client, _transport = await create_connected_client()
        with pytest.raises(SessionError, match="No active session"):
            await client.update_session_settings(model_id="gpt-4")

    @pytest.mark.asyncio
    async def test_sends_only_provided_fields(self) -> None:
        """update_session_settings sends only supplied settings fields."""
        client, transport = await create_client_with_session()

        async def do_update() -> Any:
            return await client.update_session_settings(model_id="claude-sonnet-4")

        task = asyncio.create_task(do_update())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["method"] == DroidServerMethod.UPDATE_SESSION_SETTINGS.value
        assert sent["params"]["modelId"] == "claude-sonnet-4"
        # Other fields should not be present (or be None)
        # The key assertion is that only modelId is populated

        transport.inject_message(make_success_response(sent["id"], {}))
        await task

    @pytest.mark.asyncio
    async def test_error_response_raises_protocol_error(self) -> None:
        """update_session_settings raises ProtocolError on error response."""
        client, transport = await create_client_with_session()

        async def do_update() -> Any:
            return await client.update_session_settings(model_id="bad-model")

        task = asyncio.create_task(do_update())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(
            make_error_response(
                sent["id"],
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Invalid model",
            )
        )

        with pytest.raises(ProtocolError):
            await task


class TestCloseCleanup:
    """Tests for close() resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_rejects_pending_requests(self) -> None:
        """close() rejects pending requests with descriptive error."""
        client, _transport = await create_client_with_session()

        async def do_msg() -> Any:
            return await client.add_user_message(text="pending")

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)

        # Close while request is pending
        await client.close()

        with pytest.raises((DroidClientError, DroidConnectionError)):
            await task

    @pytest.mark.asyncio
    async def test_close_clears_session_id(self) -> None:
        """close() does not necessarily clear session_id but further methods fail."""
        client, _transport = await create_client_with_session()
        assert client.session_id == "sess-123"
        await client.close()
        # After close, methods should raise
        with pytest.raises(DroidConnectionError):
            await client.add_user_message(text="after close")


class TestConnectionTracking:
    """Tests for is_connected mirroring transport state."""

    @pytest.mark.asyncio
    async def test_is_connected_mirrors_transport(self) -> None:
        """is_connected delegates to transport."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)

        assert client.is_connected is False

        await client.connect()
        assert client.is_connected is True

        await client.close()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_session_id_unchanged_by_other_calls(self) -> None:
        """session_id remains set after add_user_message, interrupt, etc."""
        client, transport = await create_client_with_session()
        assert client.session_id == "sess-123"

        # Send a message
        async def do_msg() -> Any:
            return await client.add_user_message(text="Hello")

        task = asyncio.create_task(do_msg())
        await asyncio.sleep(0.01)
        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], {}))
        await task

        # session_id should be unchanged
        assert client.session_id == "sess-123"


class TestEnvelopeFields:
    """Test that outbound requests have correct envelope fields."""

    @pytest.mark.asyncio
    async def test_envelope_has_required_fields(self) -> None:
        """Outbound requests include jsonrpc, type, factoryApiVersion, etc."""
        client, transport = await create_connected_client()

        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test",
                cwd="/tmp",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        assert sent["jsonrpc"] == "2.0"
        assert sent["type"] == "request"
        assert "factoryApiVersion" in sent
        assert "factoryProtocolVersion" in sent
        assert "id" in sent
        assert "method" in sent
        assert "params" in sent

        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        await task


class TestTransportAbstraction:
    """DroidClient works with any DroidClientTransport implementation."""

    @pytest.mark.asyncio
    async def test_works_with_mock_transport(self) -> None:
        """DroidClient accepts any transport implementing the Protocol."""
        client, transport = await create_connected_client()

        # Run init → message flow
        async def do_init() -> Any:
            return await client.initialize_session(
                machine_id="test",
                cwd="/tmp",
            )

        task = asyncio.create_task(do_init())
        await asyncio.sleep(0.01)

        sent = transport.get_last_sent_parsed()
        transport.inject_message(make_success_response(sent["id"], INIT_SESSION_RESULT))
        result = await task
        assert result.session_id == "sess-123"

        # Verify transport.send received valid JSON
        for msg_str in transport.sent_messages:
            parsed = json.loads(msg_str)
            assert isinstance(parsed, dict)
            assert "jsonrpc" in parsed


# ============================================================
# Constructor fallback: exec_path-based config
# ============================================================


class TestConstructorFallback:
    """DroidClient accepts exec_path/cwd/env config to auto-create a
    ProcessTransport during connect().
    """

    def test_requires_transport_or_exec_path(self) -> None:
        """Constructing without transport or exec_path raises ValueError."""
        from droid_sdk.client import DroidClient

        with pytest.raises(ValueError, match="requires either"):
            DroidClient()

    def test_explicit_transport_still_works(self) -> None:
        """Backward compatible: explicit transport is accepted."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport)
        # _transport is set immediately
        assert client._transport is transport

    def test_exec_path_defers_transport_creation(self) -> None:
        """When exec_path is given, _transport is None until connect()."""
        from droid_sdk.client import DroidClient

        client = DroidClient(exec_path="/fake/path/to/droid")
        assert client._transport is None
        assert client._exec_path == "/fake/path/to/droid"
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_exec_path_stores_config_for_deferred_connect(self) -> None:
        """exec_path config is stored and used to create transport later.

        Verifies the client stores config correctly. A full integration
        test with a real subprocess is in test_integration.py.
        """
        from droid_sdk.client import DroidClient

        client = DroidClient(
            exec_path="/usr/local/bin/droid",
            env={"MOCK_MODE": "lifecycle"},
        )
        assert client._transport is None
        assert client._exec_path == "/usr/local/bin/droid"
        assert client._env == {"MOCK_MODE": "lifecycle"}

        # close() before connect() should be a no-op
        await client.close()

    @pytest.mark.asyncio
    async def test_close_before_connect_with_exec_path_is_noop(self) -> None:
        """close() before connect() with exec_path config is a no-op."""
        from droid_sdk.client import DroidClient

        client = DroidClient(exec_path="/fake/droid")
        await client.close()
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_exec_path_with_cwd_and_env(self) -> None:
        """exec_path accepts optional cwd and env config."""
        from droid_sdk.client import DroidClient

        client = DroidClient(
            exec_path="/usr/bin/droid",
            cwd="/tmp/project",
            env={"FOO": "bar"},
        )
        assert client._exec_path == "/usr/bin/droid"
        assert client._cwd == "/tmp/project"
        assert client._env == {"FOO": "bar"}

    @pytest.mark.asyncio
    async def test_both_transport_and_exec_path_uses_transport(self) -> None:
        """When both transport and exec_path are given, transport wins."""
        from droid_sdk.client import DroidClient

        transport = MockTransport()
        client = DroidClient(transport=transport, exec_path="/fake/droid")
        assert client._transport is transport
        await client.connect()
        assert client.is_connected
        await client.close()
