"""Exception hierarchy for the Factory Droid SDK.

The v5 public exceptions all derive from :class:`DroidError`.  Legacy names
remain as aliases while the low-level client transitions to the v5 surface.
"""

from __future__ import annotations

from typing import Any


class DroidError(Exception):
    """Base class for every SDK-defined exception."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class RunTimeoutError(DroidError):
    """Raised when an operation exceeds its deadline."""

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
        return ", ".join(parts)


class StreamIncompleteError(DroidError):
    """Raised when a stream result is read before the stream completes."""


class InvalidAttachmentError(DroidError):
    """Raised when a local image or document attachment is invalid."""


class SessionError(DroidError):
    """Compatibility base for session-specific failures."""


class SessionNotOpenError(SessionError):
    """Raised when an operation requires an opened session."""


class SessionBusyError(SessionError):
    """Raised when a session already has an active turn."""


class SessionClosedError(SessionError):
    """Raised when an operation is attempted on a closed session."""


class SessionReplacedError(SessionError):
    """Raised when a successor session has retired this session handle."""

    def __init__(self, session_id: str, replacement_session_id: str) -> None:
        self.session_id = session_id
        self.replacement_session_id = replacement_session_id
        super().__init__(
            f"Session handle {session_id} was replaced by {replacement_session_id}. "
            "Use the returned session handle, or resume the original session "
            "explicitly."
        )


class SessionReplacementError(SessionError):
    """Raised when attaching a replacement session or restoring its source fails."""

    def __init__(
        self,
        session_id: str,
        replacement_session_id: str,
        *,
        rollback_error: BaseException | None = None,
    ) -> None:
        self.session_id = session_id
        self.replacement_session_id = replacement_session_id
        self.rollback_error = rollback_error
        self.rollback_failed = rollback_error is not None
        message = (
            f"Created replacement session {replacement_session_id}, but could not "
            f"attach it or restore session {session_id}."
            if self.rollback_failed
            else f"Created replacement session {replacement_session_id}, but could "
            "not attach it. The original session handle is still usable."
        )
        super().__init__(message)


class SessionNotFoundError(SessionError):
    """Raised when a saved session cannot be found."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class InvalidWorkingDirectoryError(SessionError):
    """Raised when a requested working directory is unavailable."""

    def __init__(self, cwd: str, message: str | None = None) -> None:
        self.cwd = cwd
        super().__init__(message or f"Invalid working directory: {cwd}")


class DroidConnectionError(DroidError):
    """Raised when connecting to or writing to Droid fails."""

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
        return ", ".join(parts)


class DroidProcessError(DroidError):
    """Raised when the Droid process exits unexpectedly."""

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
        return ", ".join(parts)


class DroidProtocolError(DroidError):
    """Raised for JSON-RPC negotiation, validation, or server errors."""

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
        return ", ".join(parts)


# Temporary low-level compatibility aliases.  They intentionally point at the
# v5 classes so catch behavior is identical under old and new imports.
DroidClientError = DroidError
ConnectionError = DroidConnectionError
TimeoutError = RunTimeoutError
ProcessExitError = DroidProcessError
ProtocolError = DroidProtocolError


__all__ = [
    "DroidConnectionError",
    "DroidError",
    "DroidProcessError",
    "DroidProtocolError",
    "InvalidAttachmentError",
    "InvalidWorkingDirectoryError",
    "RunTimeoutError",
    "SessionBusyError",
    "SessionClosedError",
    "SessionError",
    "SessionNotFoundError",
    "SessionNotOpenError",
    "SessionReplacedError",
    "SessionReplacementError",
    "StreamIncompleteError",
]
