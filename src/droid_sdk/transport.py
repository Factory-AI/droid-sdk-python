# pyright: reportUnnecessaryComparison=false

"""ProcessTransport implementation for the Factory Droid SDK.

Spawns a ``droid exec`` subprocess with piped stdin/stdout/stderr and provides
JSONL (newline-delimited JSON) framing for JSON-RPC 2.0 communication.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import signal
from collections.abc import AsyncIterator  # noqa: TC003
from typing import Any

from droid_sdk._util import consume_task_result
from droid_sdk.errors import DroidConnectionError, DroidProcessError

logger = logging.getLogger(__name__)

# Default grace period (seconds) before escalating SIGTERM → SIGKILL
_DEFAULT_GRACE_PERIOD = 5.0

# Buffer limit for asyncio subprocess stdout reader (10 MB).
# Must be large enough to handle multi-MB JSON-RPC messages.
_STDOUT_BUFFER_LIMIT = 10 * 1024 * 1024

# Stderr is drained continuously to prevent a full child pipe from blocking the
# protocol. Only a small, redacted prefix is retained for exit diagnostics.
_STDERR_CAPTURE_LIMIT = 16 * 1024
_STDERR_REDACTION_LOOKAHEAD = 512
_SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)((?:api[_-]?key|authorization|credential|password|secret|token)"
    r"\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]*)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+\S+")
_KEY_LIKE_TOKEN = re.compile(r"(?i)\b(?:api|pk|sk)[_-][A-Za-z0-9_-]{8,}\b")

# Default arguments for droid exec subprocess
_DEFAULT_EXEC_ARGS = [
    "exec",
    "--input-format",
    "stream-jsonrpc",
    "--output-format",
    "stream-jsonrpc",
]


class ProcessTransport:
    """Transport that communicates via JSONL over stdin/stdout of a subprocess.

    Spawns ``droid exec --input-format stream-jsonrpc --output-format
    stream-jsonrpc`` as an asyncio subprocess. Handles:

    - JSONL framing (one JSON object per newline-terminated line)
    - Write serialization via ``asyncio.Lock`` to prevent interleaving
    - Process lifecycle (SIGTERM → grace period → SIGKILL)
    - Reconnection after close
    """

    def __init__(
        self,
        *,
        exec_path: str = "droid",
        exec_args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        grace_period: float = _DEFAULT_GRACE_PERIOD,
    ) -> None:
        """Initialize the ProcessTransport.

        Args:
            exec_path: Path to the executable. Defaults to ``"droid"``.
            exec_args: Arguments for the executable. Defaults to
                the standard stream-jsonrpc flags.
            cwd: Working directory for the subprocess.
            env: Additional environment variables for the subprocess.
            grace_period: Seconds to wait after SIGTERM before SIGKILL.
        """
        self._exec_path = exec_path
        self._exec_args = (
            exec_args if exec_args is not None else list(_DEFAULT_EXEC_ARGS)
        )
        self._cwd = cwd
        self._env = env
        self._grace_period = grace_period

        self._process: asyncio.subprocess.Process | None = None
        self._write_lock = asyncio.Lock()
        self._is_connected = False
        self._is_closing = False
        self._process_error: Exception | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_capture = ""
        self._stderr_redaction_values: tuple[str, ...] = ()

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        return self._is_connected

    @property
    def pid(self) -> int | None:
        """PID of the subprocess, or ``None`` if not connected."""
        if self._process is not None:
            return self._process.pid
        return None

    async def connect(self) -> None:
        """Spawn the subprocess.

        Raises:
            ConnectionError: If the transport is already connected.
            FileNotFoundError: If the executable path does not exist.
            ConnectionError: If the subprocess fails to start.
        """
        if self._is_connected:
            raise DroidConnectionError(
                "Transport already connected",
                exec_path=self._exec_path,
            )

        # Reset state for reconnection
        await self._finish_stderr_task(cancel=True)
        self._process_error = None
        self._is_closing = False
        self._stderr_capture = ""

        env: dict[str, str] | None = None
        if self._env is not None:
            env = {**os.environ, **self._env}
        self._stderr_redaction_values = self._collect_redaction_values(env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._exec_path,
                *self._exec_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_STDOUT_BUFFER_LIMIT,
                cwd=self._cwd,
                env=env,
            )
        except FileNotFoundError:
            raise
        except OSError as e:
            raise DroidConnectionError(
                f"Failed to start droid process: {e}",
                exec_path=self._exec_path,
                cwd=self._cwd,
            ) from e

        self._is_connected = True
        self._write_lock = asyncio.Lock()
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(self._process.stderr),
                name="droid-sdk-process-stderr",
            )

    async def send(self, message: str) -> None:
        """Send a message to the subprocess stdin.

        Writes ``message + "\\n"`` to stdin. Concurrent sends are
        serialized via an ``asyncio.Lock`` to prevent interleaving.

        Args:
            message: A JSON string to send.

        Raises:
            ConnectionError: If the transport is not connected.
            DroidProcessError: If the subprocess has exited.
        """
        if self._process_error is not None:
            raise self._process_error

        if (
            not self._is_connected
            or self._process is None
            or self._process.stdin is None
        ):
            raise DroidConnectionError(
                "Transport not connected",
                exec_path=self._exec_path,
            )

        async with self._write_lock:
            # Re-check after acquiring lock
            if self._process_error is not None:
                raise self._process_error

            if (
                not self._is_connected
                or self._process is None
                or self._process.stdin is None
            ):
                raise DroidConnectionError(
                    "Transport disconnected during write",
                    exec_path=self._exec_path,
                )

            data = (message + "\n").encode("utf-8")
            try:
                self._process.stdin.write(data)
                await self._process.stdin.drain()
            except (
                BrokenPipeError,
                ConnectionResetError,
                OSError,
            ) as e:
                raise DroidConnectionError(
                    f"Failed to write to process stdin: {e}",
                    exec_path=self._exec_path,
                ) from e

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding parsed JSON-RPC messages from stdout.

        Reads stdout line-by-line, parses JSON, and yields dicts.
        Non-JSON lines (e.g., debug output) are silently skipped.
        Malformed JSON lines are logged and skipped.

        When stdout reaches EOF (process exit), the iterator raises
        ``DroidProcessError`` for both normal and abnormal process exits.

        Yields:
            Parsed JSON-RPC message dicts.

        Raises:
            DroidProcessError: If the subprocess exited abnormally.
        """
        process = self._process
        if process is None or process.stdout is None:
            return

        try:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    # EOF — process closed stdout
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    # Skip blank lines
                    continue

                # Try to parse as JSON
                if line.startswith("{") or line.startswith("["):
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning("Malformed JSON on stdout: %s", e)
                else:
                    # Raw child output can contain environment secrets.
                    logger.debug("Skipped non-JSON child stdout")
        except asyncio.CancelledError:
            raise

        # After stdout closes, check process exit status
        if self._is_closing:
            return

        if process.returncode is None:
            # Process hasn't exited yet, wait briefly
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2.0)

        return_code = process.returncode

        if return_code is not None:
            await self._finish_stderr_task()

            # Determine exit_code and signal
            exit_code: int | None = None
            sig: int | None = None
            if return_code < 0:
                sig = -return_code
            else:
                exit_code = return_code

            self._is_connected = False

            # Even a normal exit is a broken transport while the protocol
            # engine is active. Raise so pending and future requests fail
            # immediately with the same sticky process error.
            if exit_code == 0:
                error = DroidProcessError(
                    self._with_stderr_diagnostic("Droid process exited normally"),
                    exit_code=0,
                )
                self._process_error = error
                raise error

            # Abnormal exit — raise DroidProcessError
            if sig is not None:
                message = f"Droid process was killed (signal {sig})"
            elif exit_code is not None:
                message = f"Droid process exited unexpectedly (exit code {exit_code})"
            else:
                message = "Droid process exited unexpectedly"

            error = DroidProcessError(
                self._with_stderr_diagnostic(message),
                exit_code=exit_code,
                signal=sig,
            )
            self._process_error = error
            raise error

    async def close(self) -> None:
        """Close the transport and terminate the subprocess.

        Sends SIGTERM, waits the grace period, then escalates to
        SIGKILL. Idempotent — safe to call multiple times.
        """
        if self._is_closing:
            return

        self._is_closing = True
        self._is_connected = False

        process = self._process
        self._process = None

        cancelled: asyncio.CancelledError | None = None
        try:
            if process is not None and process.returncode is None:
                # Process is still running — terminate gracefully
                with contextlib.suppress(ProcessLookupError, OSError):
                    process.send_signal(signal.SIGTERM)

                try:
                    await asyncio.wait_for(
                        process.wait(),
                        timeout=self._grace_period,
                    )
                except asyncio.TimeoutError:
                    # Escalate to SIGKILL
                    with contextlib.suppress(ProcessLookupError, OSError):
                        process.kill()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                except asyncio.CancelledError as exc:
                    cancelled = exc
                    with contextlib.suppress(ProcessLookupError, OSError):
                        process.kill()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(process.wait(), timeout=2.0)

            # Close stdin if still open
            if process is not None and process.stdin is not None:
                with contextlib.suppress(Exception):
                    process.stdin.close()
        finally:
            try:
                await self._finish_stderr_task(
                    cancel=process is not None and process.returncode is None
                )
            except asyncio.CancelledError as exc:
                cancelled = exc
            # Reset closing flag to allow reconnection
            self._is_closing = False
        if cancelled is not None:
            raise cancelled

    def _collect_redaction_values(
        self,
        child_env: dict[str, str] | None,
    ) -> tuple[str, ...]:
        values: set[str] = set(self._env.values()) if self._env is not None else set()
        if child_env is not None:
            values.update(
                value
                for key, value in child_env.items()
                if any(marker in key.upper() for marker in _SENSITIVE_ENV_MARKERS)
            )
        values.discard("")
        return tuple(sorted(values, key=len, reverse=True))

    async def _drain_stderr(
        self,
        stderr: asyncio.StreamReader,
    ) -> None:
        max_secret_length = max(
            (len(value) for value in self._stderr_redaction_values),
            default=0,
        )
        if max_secret_length > _STDERR_CAPTURE_LIMIT:
            capture_limit = 0
        else:
            capture_limit = _STDERR_CAPTURE_LIMIT + max(
                _STDERR_REDACTION_LOOKAHEAD, max_secret_length
            )
        captured = ""
        try:
            while True:
                chunk = await stderr.read(8192)
                if not chunk:
                    break
                if len(captured) < capture_limit:
                    captured += chunk.decode("utf-8", errors="replace")[
                        : capture_limit - len(captured)
                    ]
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Failed while draining child stderr", exc_info=True)
        finally:
            self._stderr_capture = self._redact_stderr(captured)[:_STDERR_CAPTURE_LIMIT]

    def _redact_stderr(self, text: str) -> str:
        for value in self._stderr_redaction_values:
            text = text.replace(value, "[REDACTED]")
        text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
        text = _SENSITIVE_ASSIGNMENT.sub(r"\1[REDACTED]", text)
        return _KEY_LIKE_TOKEN.sub("[REDACTED]", text)

    async def _finish_stderr_task(self, *, cancel: bool = False) -> None:
        task = self._stderr_task
        self._stderr_task = None
        if task is None:
            return
        if cancel and not task.done():
            task.cancel()
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                task.add_done_callback(consume_task_result)
                raise
            with contextlib.suppress(asyncio.CancelledError):
                task.result()
        except Exception:
            pass

    def _with_stderr_diagnostic(self, message: str) -> str:
        diagnostic = " ".join(self._stderr_capture.split())
        if not diagnostic:
            return message
        return f"{message}; stderr: {diagnostic}"


__all__ = [
    "ProcessTransport",
]
