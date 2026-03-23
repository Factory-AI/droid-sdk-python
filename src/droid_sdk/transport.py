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
import signal
from collections.abc import AsyncIterator  # noqa: TC003
from typing import Any

from droid_sdk.errors import ConnectionError as DroidConnectionError
from droid_sdk.errors import ProcessExitError

logger = logging.getLogger(__name__)

# Default grace period (seconds) before escalating SIGTERM → SIGKILL
_DEFAULT_GRACE_PERIOD = 5.0

# Buffer limit for asyncio subprocess stdout reader (10 MB).
# Must be large enough to handle multi-MB JSON-RPC messages.
_STDOUT_BUFFER_LIMIT = 10 * 1024 * 1024

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
        self._process_error = None
        self._is_closing = False

        env: dict[str, str] | None = None
        if self._env is not None:
            env = {**os.environ, **self._env}

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

    async def send(self, message: str) -> None:
        """Send a message to the subprocess stdin.

        Writes ``message + "\\n"`` to stdin. Concurrent sends are
        serialized via an ``asyncio.Lock`` to prevent interleaving.

        Args:
            message: A JSON string to send.

        Raises:
            ConnectionError: If the transport is not connected.
            ProcessExitError: If the subprocess has exited.
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

        When stdout reaches EOF (process exit), the iterator checks the
        exit code. Normal exit (code 0) terminates the iterator naturally.
        Abnormal exit raises ``ProcessExitError``.

        Yields:
            Parsed JSON-RPC message dicts.

        Raises:
            ProcessExitError: If the subprocess exited abnormally.
        """
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                line_bytes = await self._process.stdout.readline()
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
                    # Non-JSON output (e.g. debug logging) — skip
                    logger.debug("Non-JSON stdout output: %s", line[:200])
        except asyncio.CancelledError:
            raise

        # After stdout closes, check process exit status
        if self._is_closing:
            return

        if self._process is not None and self._process.returncode is None:
            # Process hasn't exited yet, wait briefly
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._process.wait(), timeout=2.0)

        if self._process is not None:
            return_code = self._process.returncode

            if return_code is not None:
                # Capture stderr
                stderr_text = ""
                if self._process.stderr is not None:
                    try:
                        stderr_data = await self._process.stderr.read()
                        stderr_text = stderr_data.decode(
                            "utf-8", errors="replace"
                        ).strip()
                    except Exception:
                        pass

                # Determine exit_code and signal
                exit_code: int | None = None
                sig: int | None = None
                if return_code < 0:
                    sig = -return_code
                else:
                    exit_code = return_code

                self._is_connected = False

                # Normal exit (code 0) — just terminate the iterator
                if exit_code == 0:
                    # Build error for sticky pattern (send after exit)
                    error = ProcessExitError(
                        "Droid process exited normally",
                        exit_code=0,
                    )
                    self._process_error = error
                    return

                # Abnormal exit — raise ProcessExitError
                if sig is not None:
                    message = f"Droid process was killed (signal {sig})"
                elif exit_code is not None:
                    message = (
                        f"Droid process exited unexpectedly (exit code {exit_code})"
                    )
                else:
                    message = "Droid process exited unexpectedly"

                if stderr_text:
                    message += f": {stderr_text[:500]}"

                error = ProcessExitError(
                    message,
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

        if process is not None and process.returncode is None:
            # Process is still running — terminate gracefully
            with contextlib.suppress(ProcessLookupError, OSError):
                process.send_signal(signal.SIGTERM)

            try:
                await asyncio.wait_for(process.wait(), timeout=self._grace_period)
            except asyncio.TimeoutError:
                # Escalate to SIGKILL
                with contextlib.suppress(ProcessLookupError, OSError):
                    process.kill()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=2.0)

        # Close stdin if still open
        if process is not None and process.stdin is not None:
            with contextlib.suppress(Exception):
                process.stdin.close()

        # Reset closing flag to allow reconnection
        self._is_closing = False


__all__ = [
    "ProcessTransport",
]
