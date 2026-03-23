"""Error class hierarchy for the Factory Droid SDK.

All SDK errors inherit from DroidClientError, which inherits from Exception.
Error classes are namespaced under droid_sdk.errors and do NOT shadow
Python builtins.
"""

from __future__ import annotations

from typing import Any


class DroidClientError(Exception):
    """Base exception for all Factory Droid SDK errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class ConnectionError(DroidClientError):
    """Raised when a connection to the droid process fails.

    Attributes:
        cwd: The working directory used when spawning the process, if available.
        exec_path: The executable path used when spawning the process, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        cwd: str | None = None,
        exec_path: str | None = None,
    ) -> None:
        self.cwd = cwd
        self.exec_path = exec_path
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.cwd is not None:
            parts.append(f"cwd={self.cwd!r}")
        if self.exec_path is not None:
            parts.append(f"exec_path={self.exec_path!r}")
        return ", ".join(parts) if len(parts) > 1 else parts[0]


class TimeoutError(DroidClientError):
    """Raised when a request to the droid process times out.

    Attributes:
        request_id: The ID of the timed-out request, if available.
        method: The RPC method that timed out, if available.
        timeout_duration: The timeout duration in seconds, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        method: str | None = None,
        timeout_duration: float | None = None,
    ) -> None:
        self.request_id = request_id
        self.method = method
        self.timeout_duration = timeout_duration
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.request_id is not None:
            parts.append(f"request_id={self.request_id!r}")
        if self.method is not None:
            parts.append(f"method={self.method!r}")
        if self.timeout_duration is not None:
            parts.append(f"timeout_duration={self.timeout_duration}")
        return ", ".join(parts) if len(parts) > 1 else parts[0]


class ProtocolError(DroidClientError):
    """Raised when a JSON-RPC protocol error occurs.

    Attributes:
        code: The JSON-RPC error code, if available.
        data: Additional error data from the JSON-RPC response, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        data: Any | None = None,
    ) -> None:
        self.code = code
        self.data = data
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.code is not None:
            parts.append(f"code={self.code}")
        if self.data is not None:
            parts.append(f"data={self.data!r}")
        return ", ".join(parts) if len(parts) > 1 else parts[0]


class SessionError(DroidClientError):
    """Raised for session-related errors."""


class SessionNotFoundError(SessionError):
    """Raised when a session cannot be found.

    Constructs a default message of 'Session not found: {session_id}'
    when given a session_id.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class ProcessExitError(DroidClientError):
    """Raised when the droid subprocess exits unexpectedly.

    Attributes:
        exit_code: The exit code of the process, if it exited normally.
        signal: The signal number that terminated the process, if it was killed.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        signal: int | None = None,
    ) -> None:
        self.exit_code = exit_code
        self.signal = signal
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.exit_code is not None:
            parts.append(f"exit_code={self.exit_code}")
        if self.signal is not None:
            parts.append(f"signal={self.signal}")
        return ", ".join(parts) if len(parts) > 1 else parts[0]


__all__ = [
    "ConnectionError",
    "DroidClientError",
    "ProcessExitError",
    "ProtocolError",
    "SessionError",
    "SessionNotFoundError",
    "TimeoutError",
]
