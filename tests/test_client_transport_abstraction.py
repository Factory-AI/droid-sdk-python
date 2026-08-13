"""Tests proving DroidClient works with any DroidClientTransport implementation.

Covers VAL-CLIENT-015:
- DroidClient accepts any object implementing DroidClientTransport Protocol
- Full lifecycle flow (connect→init→message→notification→close) succeeds
- transport.send receives valid JSON strings
- DroidClientTransport is importable from droid_sdk
- A custom transport class passes mypy structural typing checks

Uses the reusable InMemoryTransport from tests/helpers.py.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from droid_sdk.client import DroidClient
from droid_sdk.errors import DroidClientError
from droid_sdk.schemas.enums import (
    DroidClientMethod,
    DroidServerMethod,
    SessionNotificationType,
)
from droid_sdk.types import DroidClientTransport
from tests.helpers import (
    InMemoryTransport,
    make_notification,
    make_success_response,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Minimal valid result payloads for test flows
INIT_SESSION_RESULT: dict[str, Any] = {
    "sessionId": "sess-transport-test",
    "session": {"messages": []},
    "settings": {
        "modelId": "claude-sonnet-4",
        "reasoningEffort": "medium",
    },
}

ADD_MESSAGE_RESULT: dict[str, Any] = {}


# ============================================================
# Protocol conformance tests
# ============================================================


class TestInMemoryTransportConformance:
    """Verify InMemoryTransport satisfies DroidClientTransport Protocol."""

    def test_is_runtime_checkable_instance(self) -> None:
        """InMemoryTransport passes runtime_checkable isinstance check."""
        transport = InMemoryTransport()
        assert isinstance(transport, DroidClientTransport)

    def test_has_is_connected_property(self) -> None:
        """InMemoryTransport exposes is_connected as a property."""
        transport = InMemoryTransport()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_has_send_method(self) -> None:
        """InMemoryTransport has an async send method."""
        transport = InMemoryTransport()
        await transport.connect()
        await transport.send('{"test": true}')
        assert len(transport.sent_messages) == 1

    def test_has_read_messages_method(self) -> None:
        """InMemoryTransport has read_messages for async iteration."""
        transport = InMemoryTransport()
        assert hasattr(transport, "read_messages")
        assert callable(transport.read_messages)

    @pytest.mark.asyncio
    async def test_read_messages_yields_injected(self) -> None:
        """InMemoryTransport read_messages yields injected messages."""
        transport = InMemoryTransport()
        await transport.connect()
        transport.inject_message({"hello": "world"})
        # Close to terminate the iterator after the message
        await transport.close()

        received: list[dict[str, Any]] = []
        async for msg in transport.read_messages():
            received.append(msg)
        assert len(received) == 1
        assert received[0] == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_has_close_method(self) -> None:
        """InMemoryTransport has an async close method."""
        transport = InMemoryTransport()
        await transport.connect()
        assert transport.is_connected is True
        await transport.close()
        assert transport.is_connected is False


class TestDroidClientTransportExport:
    """Verify DroidClientTransport is importable from the public API."""

    def test_importable_from_types_module(self) -> None:
        """DroidClientTransport can be imported from droid_sdk.types."""
        from droid_sdk.types import DroidClientTransport as Transport

        assert Transport is not None

    def test_importable_from_low_level(self) -> None:
        """DroidClientTransport can be imported from droid_sdk.low_level."""
        from droid_sdk.low_level import DroidClientTransport as Transport

        assert Transport is not None

    def test_is_protocol_class(self) -> None:
        """DroidClientTransport is a typing.Protocol subclass."""
        # runtime_checkable protocols have _is_protocol set
        assert getattr(DroidClientTransport, "_is_protocol", False) is True

    def test_custom_class_passes_isinstance(self) -> None:
        """A custom class implementing the protocol passes isinstance."""

        class MyCustomTransport:
            """Minimal custom transport for type-checking verification."""

            @property
            def is_connected(self) -> bool:
                return False

            async def connect(self) -> None:
                pass

            async def send(self, message: str) -> None:
                pass

            async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
                return
                yield  # make it an async generator

            async def close(self) -> None:
                pass

        custom = MyCustomTransport()
        assert isinstance(custom, DroidClientTransport)


# ============================================================
# Full lifecycle flow tests
# ============================================================


class TestFullLifecycleWithInMemoryTransport:
    """Test complete connect→init→message→notification→close flow."""

    @pytest.mark.asyncio
    async def test_connect_init_message_notification_close(self) -> None:
        """Full lifecycle: connect, init session, send message,
        receive notification, close — all with InMemoryTransport."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)

        # Step 1: Connect
        await client.connect()
        assert client.is_connected is True
        assert client.session_id is None

        # Step 2: Initialize session (background task + inject response)
        notifications_received: list[dict[str, Any]] = []
        client.on_notification(
            lambda n: notifications_received.append(n),
        )

        init_task = asyncio.create_task(
            client.initialize_session(
                machine_id="test-machine",
                cwd="/tmp/test",
            )
        )
        await asyncio.sleep(0.01)

        # Verify the init request was sent as valid JSON
        assert len(transport.sent_messages) == 1
        init_request = json.loads(transport.sent_messages[0])
        assert init_request["method"] == DroidServerMethod.INITIALIZE_SESSION.value
        assert init_request["type"] == "request"
        assert "id" in init_request

        # Inject success response
        transport.inject_message(
            make_success_response(init_request["id"], INIT_SESSION_RESULT)
        )
        result = await init_task

        assert result.session_id == "sess-transport-test"
        assert client.session_id == "sess-transport-test"

        # Step 3: Send a user message
        msg_task = asyncio.create_task(
            client.add_user_message(text="Hello from transport test!")
        )
        await asyncio.sleep(0.01)

        assert len(transport.sent_messages) == 2
        msg_request = json.loads(transport.sent_messages[1])
        assert msg_request["method"] == DroidServerMethod.ADD_USER_MESSAGE.value
        assert msg_request["params"]["text"] == "Hello from transport test!"

        transport.inject_message(
            make_success_response(msg_request["id"], ADD_MESSAGE_RESULT)
        )
        await msg_task

        # Step 4: Receive a notification
        transport.inject_message(
            make_notification(
                method=DroidClientMethod.SESSION_NOTIFICATION.value,
                params={
                    "notification": {
                        "type": SessionNotificationType.ASSISTANT_TEXT_DELTA.value,
                        "delta": "Hello! How can I help?",
                    }
                },
            )
        )
        await asyncio.sleep(0.02)

        assert len(notifications_received) == 1
        notif = notifications_received[0]
        assert notif["method"] == DroidClientMethod.SESSION_NOTIFICATION.value
        inner = notif["params"]["notification"]
        assert inner["type"] == SessionNotificationType.ASSISTANT_TEXT_DELTA.value
        assert inner["delta"] == "Hello! How can I help?"

        # Step 5: Close
        await client.close()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_init_then_close_with_context_manager(self) -> None:
        """Full flow using async context manager."""
        transport = InMemoryTransport()

        async with DroidClient(transport=transport) as client:
            assert client.is_connected is True

            # Init session
            init_task = asyncio.create_task(
                client.initialize_session(
                    machine_id="ctx-machine",
                    cwd="/tmp/ctx",
                )
            )
            await asyncio.sleep(0.01)
            sent = json.loads(transport.sent_messages[-1])
            transport.inject_message(
                make_success_response(sent["id"], INIT_SESSION_RESULT)
            )
            await init_task

            assert client.session_id == "sess-transport-test"

        # After exiting the context, transport should be closed
        assert transport.is_connected is False


# ============================================================
# Sent messages validation
# ============================================================


class TestSentMessagesAreValidJson:
    """Verify that transport.send receives valid JSON strings."""

    @pytest.mark.asyncio
    async def test_all_sent_messages_are_valid_json(self) -> None:
        """Every message passed to transport.send is valid JSON."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        # Init
        init_task = asyncio.create_task(
            client.initialize_session(
                machine_id="m1",
                cwd="/tmp",
                session_id="explicit-sid",
            )
        )
        await asyncio.sleep(0.01)
        init_req = json.loads(transport.sent_messages[0])
        transport.inject_message(
            make_success_response(init_req["id"], INIT_SESSION_RESULT)
        )
        await init_task

        # Add message
        msg_task = asyncio.create_task(client.add_user_message(text="Test message"))
        await asyncio.sleep(0.01)
        msg_req = json.loads(transport.sent_messages[1])
        transport.inject_message(
            make_success_response(msg_req["id"], ADD_MESSAGE_RESULT)
        )
        await msg_task

        # Verify all sent messages parse as valid JSON
        for i, raw in enumerate(transport.sent_messages):
            parsed = json.loads(raw)
            assert isinstance(parsed, dict), f"Message {i} is not a dict"
            assert "jsonrpc" in parsed, f"Message {i} missing 'jsonrpc'"
            assert parsed["jsonrpc"] == "2.0", f"Message {i} jsonrpc != '2.0'"
            assert "id" in parsed, f"Message {i} missing 'id'"
            assert "method" in parsed, f"Message {i} missing 'method'"
            assert "type" in parsed, f"Message {i} missing 'type'"
            assert parsed["type"] == "request", f"Message {i} type != 'request'"

        await client.close()

    @pytest.mark.asyncio
    async def test_sent_messages_are_strings(self) -> None:
        """transport.send receives str, not bytes or dict."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        init_task = asyncio.create_task(
            client.initialize_session(machine_id="m1", cwd="/tmp")
        )
        await asyncio.sleep(0.01)

        for msg in transport.sent_messages:
            assert isinstance(msg, str), f"Expected str, got {type(msg)}"

        # Clean up
        init_req = json.loads(transport.sent_messages[0])
        transport.inject_message(
            make_success_response(init_req["id"], INIT_SESSION_RESULT)
        )
        await init_task
        await client.close()

    @pytest.mark.asyncio
    async def test_sent_json_has_envelope_fields(self) -> None:
        """Each sent JSON includes required envelope fields."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        init_task = asyncio.create_task(
            client.initialize_session(machine_id="m1", cwd="/tmp")
        )
        await asyncio.sleep(0.01)

        parsed = json.loads(transport.sent_messages[0])
        # Check envelope fields
        assert parsed["jsonrpc"] == "2.0"
        assert "factoryApiVersion" in parsed
        assert "factoryProtocolVersion" in parsed
        assert parsed["factoryProtocolVersion"] == "1.1.0"

        # Respond and close
        transport.inject_message(
            make_success_response(parsed["id"], INIT_SESSION_RESULT)
        )
        await init_task
        await client.close()

    @pytest.mark.asyncio
    async def test_sent_json_has_unique_ids(self) -> None:
        """Each sent request has a unique ID."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        # Init
        init_task = asyncio.create_task(
            client.initialize_session(machine_id="m1", cwd="/tmp")
        )
        await asyncio.sleep(0.01)
        init_req = json.loads(transport.sent_messages[0])
        transport.inject_message(
            make_success_response(init_req["id"], INIT_SESSION_RESULT)
        )
        await init_task

        # Multiple messages
        tasks = []
        for i in range(3):
            task = asyncio.create_task(client.add_user_message(text=f"msg {i}"))
            tasks.append(task)
        await asyncio.sleep(0.01)

        # Respond to each
        for i in range(1, 4):  # messages 1, 2, 3
            req = json.loads(transport.sent_messages[i])
            transport.inject_message(
                make_success_response(req["id"], ADD_MESSAGE_RESULT)
            )
        await asyncio.gather(*tasks)

        # Collect all IDs
        ids = [json.loads(m)["id"] for m in transport.sent_messages]
        assert len(ids) == len(set(ids)), "Request IDs are not unique"

        await client.close()


# ============================================================
# Notification delivery tests
# ============================================================


class TestNotificationDeliveryWithInMemoryTransport:
    """Test notification delivery through InMemoryTransport."""

    @pytest.mark.asyncio
    async def test_multiple_notification_types(self) -> None:
        """Multiple notification types are delivered correctly."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        received: list[dict[str, Any]] = []
        client.on_notification(lambda n: received.append(n))

        # Inject various notification types
        notification_types = [
            SessionNotificationType.ASSISTANT_TEXT_DELTA,
            SessionNotificationType.DROID_WORKING_STATE_CHANGED,
            SessionNotificationType.ERROR,
        ]

        for ntype in notification_types:
            transport.inject_message(
                make_notification(
                    method=DroidClientMethod.SESSION_NOTIFICATION.value,
                    params={
                        "notification": {
                            "type": ntype.value,
                        }
                    },
                )
            )
        await asyncio.sleep(0.02)

        assert len(received) == 3
        for i, ntype in enumerate(notification_types):
            inner = received[i]["params"]["notification"]
            assert inner["type"] == ntype.value

        await client.close()

    @pytest.mark.asyncio
    async def test_notification_with_type_filter(self) -> None:
        """Notification filtering by type works with InMemoryTransport."""
        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        filtered: list[dict[str, Any]] = []
        client.on_notification(
            lambda n: filtered.append(n),
            notification_type=SessionNotificationType.ERROR,
        )

        # Send one matching and one non-matching
        transport.inject_message(
            make_notification(
                method=DroidClientMethod.SESSION_NOTIFICATION.value,
                params={
                    "notification": {
                        "type": SessionNotificationType.ASSISTANT_TEXT_DELTA.value,
                    }
                },
            )
        )
        transport.inject_message(
            make_notification(
                method=DroidClientMethod.SESSION_NOTIFICATION.value,
                params={
                    "notification": {
                        "type": SessionNotificationType.ERROR.value,
                        "message": "Something went wrong",
                    }
                },
            )
        )
        await asyncio.sleep(0.02)

        assert len(filtered) == 1
        assert filtered[0]["params"]["notification"]["type"] == "error"

        await client.close()


# ============================================================
# Error simulation tests
# ============================================================


class TestErrorSimulationWithInMemoryTransport:
    """Test error injection through InMemoryTransport."""

    @pytest.mark.asyncio
    async def test_transport_error_causes_sticky_failure(self) -> None:
        """Injecting a transport error causes sticky failure state."""
        from droid_sdk.errors import ProcessExitError

        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()

        # Init session first
        init_task = asyncio.create_task(
            client.initialize_session(machine_id="m1", cwd="/tmp")
        )
        await asyncio.sleep(0.01)
        init_req = json.loads(transport.sent_messages[0])
        transport.inject_message(
            make_success_response(init_req["id"], INIT_SESSION_RESULT)
        )
        await init_task

        # Inject transport error
        transport.inject_error(ProcessExitError("Process crashed", exit_code=1))

        # After sticky error, further requests should fail
        # Give the protocol engine time to process the error
        await asyncio.sleep(0.01)

        # The next request should fail due to sticky error
        with pytest.raises(DroidClientError):
            msg_task = asyncio.create_task(client.add_user_message(text="should fail"))
            await msg_task

        await client.close()

    @pytest.mark.asyncio
    async def test_send_after_close_raises(self) -> None:
        """Calling methods after close raises ConnectionError."""
        from droid_sdk.errors import ConnectionError as DroidConnectionError

        transport = InMemoryTransport()
        client = DroidClient(transport=transport)
        await client.connect()
        await client.close()

        with pytest.raises(DroidConnectionError):
            await client.initialize_session(machine_id="m1", cwd="/tmp")


# ============================================================
# Mypy structural typing verification test
# ============================================================


class TestMypyStructuralTyping:
    """Tests that verify structural typing compatibility.

    These tests document that a custom class implementing the
    DroidClientTransport protocol methods works with DroidClient.
    The real mypy check happens when running ``mypy --strict`` on
    this file.
    """

    @pytest.mark.asyncio
    async def test_custom_transport_works_with_droid_client(self) -> None:
        """A completely custom transport class works with DroidClient."""

        _SENTINEL = object()

        class CustomTestTransport:
            """A custom transport with a different internal implementation."""

            def __init__(self) -> None:
                self._connected: bool = False
                self.log: list[str] = []
                self._queue: asyncio.Queue[Any] = asyncio.Queue()

            @property
            def is_connected(self) -> bool:
                return self._connected

            async def connect(self) -> None:
                self._connected = True
                self._queue = asyncio.Queue()

            async def send(self, message: str) -> None:
                self.log.append(f"SEND:{message}")

            async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
                while True:
                    item = await self._queue.get()
                    if item is _SENTINEL:
                        return
                    yield item

            async def close(self) -> None:
                self._connected = False
                self._queue.put_nowait(_SENTINEL)

            def deliver(self, data: dict[str, Any]) -> None:
                self._queue.put_nowait(data)

        # Use the custom transport with DroidClient
        transport = CustomTestTransport()

        # Type annotation proves mypy structural typing works:
        _typed_transport: DroidClientTransport = transport

        client = DroidClient(transport=transport)
        await client.connect()
        assert client.is_connected is True

        # Init session
        init_task = asyncio.create_task(
            client.initialize_session(machine_id="custom-m", cwd="/tmp/custom")
        )
        await asyncio.sleep(0.01)

        assert len(transport.log) == 1
        assert transport.log[0].startswith("SEND:")

        # Parse the sent message
        sent_json = json.loads(transport.log[0][5:])  # strip "SEND:"
        assert sent_json["method"] == DroidServerMethod.INITIALIZE_SESSION.value

        # Inject response
        transport.deliver(make_success_response(sent_json["id"], INIT_SESSION_RESULT))
        result = await init_task
        assert result.session_id == "sess-transport-test"

        await client.close()
        assert client.is_connected is False

    def test_type_annotation_assignment(self) -> None:
        """InMemoryTransport can be assigned to DroidClientTransport variable.

        This is a mypy check — running ``mypy --strict`` on this file
        verifies the assignment is type-safe.
        """
        transport: DroidClientTransport = InMemoryTransport()
        assert isinstance(transport, DroidClientTransport)
