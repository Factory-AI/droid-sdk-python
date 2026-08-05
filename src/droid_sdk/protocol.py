"""JSON-RPC 2.0 protocol engine for the Factory Droid SDK.

Sits between the transport layer and the client API. Handles:

- Envelope construction for outbound requests
- Request/response correlation via asyncio Futures keyed by UUID
- Configurable per-request timeouts
- Notification dispatch to registered listeners
- Server→client request handling (permission, ask_user)
- Error code mapping (ENTITY_NOT_FOUND → SessionNotFoundError)
- Sticky transport error: once a transport error fires, all
  pending and subsequent requests are immediately rejected
- Edge cases: unknown response IDs, duplicate response IDs,
  malformed responses, null-id error responses
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Callable  # noqa: TC003
from typing import Any, Final

from droid_sdk.errors import (
    ConnectionError as DroidConnectionError,
)
from droid_sdk.errors import (
    DroidClientError,
    ProtocolError,
    SessionNotFoundError,
)
from droid_sdk.errors import (
    TimeoutError as DroidTimeoutError,
)
from droid_sdk.schemas.constants import (
    FACTORY_PROTOCOL_VERSION,
    JSONRPC_VERSION,
    LEGACY_FACTORY_API_VERSION,
)
from droid_sdk.schemas.enums import JsonRpcErrorCode
from droid_sdk.types import DroidClientTransport  # noqa: TC001

logger = logging.getLogger(__name__)

# Timeout constants (in seconds, matching TypeScript SDK)
DEFAULT_REQUEST_TIMEOUT: Final[float] = 30.0
"""Standard timeout for quick request/response operations (30 seconds)."""

SESSION_INIT_TIMEOUT: Final[float] = 60.0
"""Extended timeout for session initialization (60 seconds)."""

COMPACTION_TIMEOUT: Final[float] = 240.0
"""Extended timeout for session compaction (4 minutes)."""

MCP_AUTH_TIMEOUT: Final[float] = 300.0
"""Extended timeout for MCP OAuth authentication (5 minutes)."""


class _PendingRequest:
    """Internal state for a pending request awaiting a response."""

    __slots__ = ("future", "method", "request_id")

    def __init__(
        self,
        future: asyncio.Future[dict[str, Any]],
        method: str,
        request_id: str,
    ) -> None:
        self.future = future
        self.method = method
        self.request_id = request_id


class ProtocolEngine:
    """JSON-RPC 2.0 protocol engine.

    Manages request/response correlation, timeout handling, notification
    dispatch, server→client request handling, and error mapping.

    After construction, call :meth:`start` to begin consuming messages
    from the transport's ``read_messages()`` async iterator.

    Args:
        transport: A connected ``DroidClientTransport`` implementation.
        default_timeout: Default timeout in seconds for ``send_request``.
    """

    def __init__(
        self,
        *,
        transport: DroidClientTransport,
        default_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._transport = transport
        self._default_timeout = default_timeout

        # Pending requests keyed by UUID string
        self._pending_requests: dict[str, _PendingRequest] = {}

        # Background tasks for server→client request handling
        self._background_tasks: set[asyncio.Task[None]] = set()

        # Notification listeners
        self._notification_listeners: list[Callable[[dict[str, Any]], None]] = []

        # Server→client request handlers
        self._permission_handler: Callable[[dict[str, Any]], Any] | None = None
        self._ask_user_handler: Callable[[dict[str, Any]], Any] | None = None

        # Sticky transport error
        self._transport_error: Exception | None = None

        # Closed flag
        self._closed: bool = False

        # Reader task (started by start())
        self._reader_task: asyncio.Task[None] | None = None

    # ----------------------------------------------------------
    # Public API: Start reading from transport
    # ----------------------------------------------------------

    async def start(self) -> None:
        """Start consuming messages from the transport.

        Launches a background task that reads from the transport's
        ``read_messages()`` async iterator and dispatches each message
        to the appropriate handler.
        """
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Consume messages from the transport iterator."""
        try:
            async for message in self._transport.read_messages():
                self._handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._handle_transport_error(e)

    # ----------------------------------------------------------
    # Public API: Sending requests
    # ----------------------------------------------------------

    async def send_request(
        self,
        method: str,
        params: dict[str, Any],
        timeout: float | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response.

        Constructs the full envelope, registers a pending Future, sends
        via transport, and returns the parsed response dict.

        Args:
            method: The RPC method name (e.g. ``"droid.list_skills"``).
            params: Method parameters dict.
            timeout: Timeout in seconds. Defaults to ``default_timeout``.
            request_id: Optional custom request ID. If not provided, a
                UUID is generated automatically.

        Returns:
            The full JSON-RPC response dict (including ``result`` or ``error``).

        Raises:
            DroidTimeoutError: If no response arrives within the timeout.
            ProtocolError: If the response contains an error.
            SessionNotFoundError: If error code is ENTITY_NOT_FOUND.
            DroidConnectionError: If transport is not connected.
            DroidClientError: If the engine is closed or a sticky error exists.
        """
        # Check closed state
        if self._closed:
            raise DroidClientError("Protocol engine is closed")

        # Check sticky transport error
        if self._transport_error is not None:
            raise DroidClientError(f"Transport error: {self._transport_error}")

        effective_timeout = timeout if timeout is not None else self._default_timeout

        # Build envelope
        if request_id is None:
            request_id = str(uuid.uuid4())
        envelope: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create future
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        pending = _PendingRequest(
            future=future,
            method=method,
            request_id=request_id,
        )
        self._pending_requests[request_id] = pending

        # Send via transport
        try:
            await self._transport.send(json.dumps(envelope))
        except Exception as send_exc:
            # Clean up pending and re-raise
            self._pending_requests.pop(request_id, None)
            if isinstance(send_exc, DroidClientError):
                raise
            raise DroidConnectionError(
                f"Failed to send request: {send_exc}"
            ) from send_exc

        # Wait with timeout
        try:
            response = await asyncio.wait_for(future, timeout=effective_timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise DroidTimeoutError(
                f"Request {method} timed out after {effective_timeout}s",
                request_id=request_id,
                method=method,
                timeout_duration=effective_timeout,
            ) from None

        # Check for error response and map to exceptions
        if "error" in response and response["error"] is not None:
            error_obj = response["error"]

            # Guard against non-dict error payloads
            if not isinstance(error_obj, dict):
                obj_type = type(error_obj).__name__
                raise ProtocolError(
                    f"Malformed error response: expected dict, got {obj_type}",
                    code=JsonRpcErrorCode.PARSE_ERROR.value,
                )

            code = error_obj.get("code")
            message = error_obj.get("message", "Unknown error")
            data = error_obj.get("data")

            if code == JsonRpcErrorCode.ENTITY_NOT_FOUND.value:
                # Extract session_id from params if available
                session_id = params.get("sessionId", request_id)
                raise SessionNotFoundError(str(session_id))

            raise ProtocolError(
                message,
                code=code,
                data=data,
            )

        return response

    # ----------------------------------------------------------
    # Public API: Notification listeners
    # ----------------------------------------------------------

    def on_notification(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler for incoming notifications.

        Multiple handlers can be registered. Each receives the full
        parsed notification dict.

        Args:
            handler: Callback invoked with the notification dict.
        """
        self._notification_listeners.append(handler)

    def remove_notification_listener(
        self, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Remove a previously registered notification listener.

        Args:
            handler: The handler to remove.
        """
        with contextlib.suppress(ValueError):
            self._notification_listeners.remove(handler)

    # ----------------------------------------------------------
    # Public API: Server→client request handlers
    # ----------------------------------------------------------

    def set_permission_handler(self, handler: Callable[..., Any]) -> None:
        """Register a handler for server→client permission requests.

        The handler receives the request params dict and should return
        a ``ToolConfirmationOutcome`` string value (or any string).

        Replaces any previously registered handler.

        Args:
            handler: Async callable ``(params) -> str``.
        """
        self._permission_handler = handler

    def clear_permission_handler(self) -> None:
        """Remove the permission request handler (restores default Cancel)."""
        self._permission_handler = None

    def set_ask_user_handler(self, handler: Callable[..., Any]) -> None:
        """Register a handler for server→client ask_user requests.

        The handler receives the request params dict and should return
        a dict with ``cancelled`` and ``answers`` keys.

        Replaces any previously registered handler.

        Args:
            handler: Async callable ``(params) -> dict``.
        """
        self._ask_user_handler = handler

    def clear_ask_user_handler(self) -> None:
        """Remove the ask_user request handler (restores default cancelled=True)."""
        self._ask_user_handler = None

    # ----------------------------------------------------------
    # Public API: Close
    # ----------------------------------------------------------

    async def close(self) -> None:
        """Close the protocol engine.

        Cancels the reader task, rejects all pending requests, cancels
        and awaits in-flight server→client handler tasks (permission/
        ask_user background tasks), clears handlers and listeners.
        Idempotent.
        """
        self._closed = True

        # Cancel reader task
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task
            self._reader_task = None

        # Reject all pending
        error = DroidClientError("Protocol engine closed: pending requests cancelled")
        self._reject_all_pending(error)

        # Cancel all in-flight server→client request handler tasks
        tasks_to_cancel = set(self._background_tasks)
        for task in tasks_to_cancel:
            task.cancel()

        # Await all cancelled tasks to ensure clean shutdown (no leakage)
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        self._background_tasks.clear()

        # Clear handlers
        self._permission_handler = None
        self._ask_user_handler = None
        self._notification_listeners.clear()

    # ----------------------------------------------------------
    # Internal: Message handling
    # ----------------------------------------------------------

    def _handle_message(self, parsed: dict[str, Any]) -> None:
        """Handle an incoming parsed message from the transport.

        Dispatches to response handler, notification handler, or
        server→client request handler based on message type.
        """
        msg_type = parsed.get("type")

        if msg_type == "response":
            self._handle_response(parsed)
        elif msg_type == "notification":
            self._handle_notification(parsed)
        elif msg_type == "request":
            # Server→client request — handle asynchronously
            self._schedule_server_request(parsed)
        else:
            # Try to determine by content
            if "result" in parsed or "error" in parsed:
                self._handle_response(parsed)
            elif "method" in parsed and "id" not in parsed:
                self._handle_notification(parsed)
            elif "method" in parsed and "id" in parsed:
                self._schedule_server_request(parsed)
            else:
                logger.warning("Unknown message format: %s", str(parsed)[:200])

    def _schedule_server_request(self, parsed: dict[str, Any]) -> None:
        """Schedule a server→client request handler as a background task."""
        task = asyncio.ensure_future(self._handle_server_request(parsed))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _handle_response(self, response: dict[str, Any]) -> None:
        """Handle an incoming response message.

        Matches by ID to resolve the correct pending Future.
        """
        response_id = response.get("id")

        # Null-id error response — log but don't crash
        if response_id is None:
            if "error" in response:
                error_obj = response.get("error", {})
                logger.warning(
                    "Received error response with null id: code=%s message=%s",
                    error_obj.get("code"),
                    error_obj.get("message"),
                )
            else:
                logger.warning(
                    "Received response with null id: %s",
                    str(response)[:200],
                )
            return

        pending = self._pending_requests.pop(response_id, None)

        if pending is None:
            # Unknown response ID — already timed out or duplicate
            logger.warning(
                "Received response for unknown request ID: %s",
                response_id,
            )
            return

        # Validate the response has either result or error
        has_result = "result" in response
        has_error = "error" in response

        if not has_result and not has_error:
            # Malformed response — reject with ProtocolError
            if not pending.future.done():
                pending.future.set_exception(
                    ProtocolError(
                        "Malformed response: missing 'result' and 'error'",
                        code=JsonRpcErrorCode.PARSE_ERROR.value,
                    )
                )
            return

        # Resolve the future
        if not pending.future.done():
            pending.future.set_result(response)

    def _handle_notification(self, notification: dict[str, Any]) -> None:
        """Handle an incoming notification message.

        Dispatches to all registered notification listeners.
        """
        for listener in list(self._notification_listeners):
            try:
                listener(notification)
            except Exception:
                logger.warning(
                    "Notification listener raised an exception",
                    exc_info=True,
                )

    async def _handle_server_request(self, request: dict[str, Any]) -> None:
        """Handle an incoming server→client request.

        Dispatches to the appropriate handler based on the method field.
        """
        method = request.get("method", "")
        request_id = request.get("id", "")
        params = request.get("params", {})

        if method == "droid.request_permission":
            await self._handle_permission_request(request_id, params)
        elif method == "droid.ask_user":
            await self._handle_ask_user_request(request_id, params)
        else:
            logger.warning("Unknown server→client request method: %s", method)

    async def _handle_permission_request(
        self,
        request_id: str,
        params: dict[str, Any],
    ) -> None:
        """Handle droid.request_permission server→client request."""
        handler = self._permission_handler

        if handler is None:
            # Default: Cancel
            await self._send_response(
                request_id,
                result={"selectedOption": "cancel"},
            )
            return

        try:
            result = handler(params)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                selected_option = await result
            else:
                selected_option = result
            await self._send_response(
                request_id,
                result={"selectedOption": selected_option},
            )
        except Exception as exc:
            logger.warning("Permission handler raised: %s", exc, exc_info=True)
            await self._send_error_response(
                request_id,
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Failed to handle permission request",
                data=str(exc),
            )

    async def _handle_ask_user_request(
        self,
        request_id: str,
        params: dict[str, Any],
    ) -> None:
        """Handle droid.ask_user server→client request."""
        handler = self._ask_user_handler

        if handler is None:
            # Default: cancelled=True
            await self._send_response(
                request_id,
                result={"cancelled": True, "answers": []},
            )
            return

        try:
            result = handler(params)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                ask_result = await result
            else:
                ask_result = result
            await self._send_response(
                request_id,
                result=ask_result,
            )
        except Exception as exc:
            logger.warning("Ask-user handler raised: %s", exc, exc_info=True)
            await self._send_error_response(
                request_id,
                code=JsonRpcErrorCode.INTERNAL_ERROR.value,
                message="Failed to handle ask-user request",
                data=str(exc),
            )

    # ----------------------------------------------------------
    # Internal: Transport error handling
    # ----------------------------------------------------------

    def _handle_transport_error(self, error: Exception) -> None:
        """Handle a transport error.

        Sets the sticky transport error and rejects all pending requests.
        """
        self._transport_error = error
        self._reject_all_pending(DroidClientError(f"Transport error: {error}"))

    # ----------------------------------------------------------
    # Internal: Response helpers
    # ----------------------------------------------------------

    async def _send_response(
        self,
        request_id: str,
        result: dict[str, Any],
    ) -> None:
        """Send a JSON-RPC success response back to the server."""
        response: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "response",
            "id": request_id,
            "result": result,
        }
        try:
            await self._transport.send(json.dumps(response))
        except Exception:
            logger.warning(
                "Failed to send response for request %s",
                request_id,
                exc_info=True,
            )

    async def _send_error_response(
        self,
        request_id: str,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        """Send a JSON-RPC error response back to the server."""
        error_obj: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error_obj["data"] = data

        response: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "factoryApiVersion": LEGACY_FACTORY_API_VERSION,
            "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
            "type": "response",
            "id": request_id,
            "error": error_obj,
        }
        try:
            await self._transport.send(json.dumps(response))
        except Exception:
            logger.warning(
                "Failed to send error response for request %s",
                request_id,
                exc_info=True,
            )

    def _reject_all_pending(self, error: Exception) -> None:
        """Reject all pending requests with the given error."""
        pending = dict(self._pending_requests)
        self._pending_requests.clear()

        for req in pending.values():
            if not req.future.done():
                req.future.set_exception(error)


__all__ = [
    "COMPACTION_TIMEOUT",
    "DEFAULT_REQUEST_TIMEOUT",
    "MCP_AUTH_TIMEOUT",
    "SESSION_INIT_TIMEOUT",
    "ProtocolEngine",
]
