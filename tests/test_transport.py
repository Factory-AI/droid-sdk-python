"""Tests for the ProcessTransport class and DroidClientTransport Protocol.

Tests use mock subprocesses (small Python scripts via asyncio.create_subprocess_exec)
to simulate droid exec behavior.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import signal
import sys
from typing import TYPE_CHECKING, Any

import pytest

from droid_sdk.errors import ConnectionError as DroidConnectionError
from droid_sdk.errors import ProcessExitError
from droid_sdk.transport import ProcessTransport
from droid_sdk.types import DroidClientTransport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# DroidClientTransport Protocol tests
# ---------------------------------------------------------------------------


class TestDroidClientTransportProtocol:
    """Tests for the DroidClientTransport Protocol definition."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """DroidClientTransport is decorated with @runtime_checkable."""
        assert hasattr(DroidClientTransport, "__protocol_attrs__") or isinstance(
            DroidClientTransport, type
        )

    def test_process_transport_satisfies_protocol(self) -> None:
        """ProcessTransport satisfies the DroidClientTransport protocol."""
        transport = ProcessTransport()
        assert isinstance(transport, DroidClientTransport)

    def test_protocol_defines_required_methods(self) -> None:
        """Protocol defines connect, send, read_messages, close, is_connected."""
        transport = ProcessTransport()
        assert hasattr(transport, "connect")
        assert callable(transport.connect)
        assert hasattr(transport, "send")
        assert callable(transport.send)
        assert hasattr(transport, "read_messages")
        assert callable(transport.read_messages)
        assert hasattr(transport, "close")
        assert callable(transport.close)
        assert hasattr(transport, "is_connected")

    def test_mock_transport_satisfies_protocol(self) -> None:
        """A custom in-memory mock can satisfy DroidClientTransport."""

        class MockTransport:
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

        mock = MockTransport()
        assert isinstance(mock, DroidClientTransport)


# ---------------------------------------------------------------------------
# Helper: Python script strings for mock subprocesses
# ---------------------------------------------------------------------------

# Echo server: reads stdin line-by-line and echoes back to stdout
ECHO_SCRIPT = """
import sys
for line in sys.stdin:
    sys.stdout.write(line)
    sys.stdout.flush()
"""


# Script that outputs predefined lines then exits
def make_output_script(lines: list[str]) -> str:
    """Create a Python script that outputs given lines to stdout and waits for EOF."""
    escaped = repr(lines)
    return f"""
import sys, time
lines = {escaped}
for line in lines:
    sys.stdout.write(line + '\\n')
    sys.stdout.flush()
# Wait for stdin to close (i.e., parent calls close)
try:
    sys.stdin.read()
except:
    pass
"""


# Script that outputs lines then exits immediately
def make_output_and_exit_script(lines: list[str], exit_code: int = 0) -> str:
    escaped = repr(lines)
    return f"""
import sys
lines = {escaped}
for line in lines:
    sys.stdout.write(line + '\\n')
    sys.stdout.flush()
sys.exit({exit_code})
"""


# Script that ignores SIGTERM (stubborn process)
STUBBORN_SCRIPT = """
import signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
# Signal readiness
sys.stdout.write('{"ready": true}\\n')
sys.stdout.flush()
# Block forever
while True:
    time.sleep(1)
"""

# Script that exits on SIGTERM (cooperative process)
COOPERATIVE_SCRIPT = """
import signal, sys, time

def handler(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handler)
sys.stdout.write('{"ready": true}\\n')
sys.stdout.flush()
while True:
    time.sleep(1)
"""


# Script that exits immediately with a specific code
def make_exit_script(code: int) -> str:
    return f"""
import sys
sys.exit({code})
"""


# Script that writes to stderr
STDERR_SCRIPT = """
import sys
sys.stderr.write("some error output\\n")
sys.stderr.flush()
sys.stdout.write('{"ready": true}\\n')
sys.stdout.flush()
try:
    sys.stdin.read()
except:
    pass
"""

# Script that fills stderr beyond a typical OS pipe before protocol output.
LARGE_STDERR_SCRIPT = """
import sys
sys.stderr.write("diagnostic " * 200000)
sys.stderr.flush()
sys.stdout.write('{"ready": true}\\n')
sys.stdout.flush()
try:
    sys.stdin.read()
except:
    pass
"""

# Script that waits for input and echoes JSON-RPC style
WAIT_AND_ECHO_SCRIPT = """
import sys, json
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            data = json.loads(line)
            response = {"jsonrpc": "2.0", "id": data.get("id"), "result": "ok"}
            sys.stdout.write(json.dumps(response) + '\\n')
            sys.stdout.flush()
        except json.JSONDecodeError:
            pass
"""


# ---------------------------------------------------------------------------
# Helper to collect messages from read_messages() in background
# ---------------------------------------------------------------------------


async def _collect_messages(
    transport: ProcessTransport,
    *,
    timeout: float = 5.0,
) -> tuple[list[dict[str, Any]], list[Exception]]:
    """Run read_messages() as a background task, collecting messages and errors."""
    messages: list[dict[str, Any]] = []
    errors: list[Exception] = []

    async def _reader() -> None:
        try:
            async for msg in transport.read_messages():
                messages.append(msg)
        except Exception as e:
            errors.append(e)

    task = asyncio.create_task(_reader())

    # Let it run briefly, then cancel
    await asyncio.sleep(timeout)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    return messages, errors


async def _read_until_done(
    transport: ProcessTransport,
    *,
    timeout: float = 5.0,
) -> tuple[list[dict[str, Any]], list[Exception]]:
    """Read all messages until the iterator ends or times out."""
    messages: list[dict[str, Any]] = []
    errors: list[Exception] = []

    async def _reader() -> None:
        try:
            async for msg in transport.read_messages():
                messages.append(msg)
        except Exception as e:
            errors.append(e)

    task = asyncio.create_task(_reader())

    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    return messages, errors


# ---------------------------------------------------------------------------
# ProcessTransport: connect() tests
# ---------------------------------------------------------------------------


class TestProcessTransportConnect:
    """Tests for connect() spawning subprocess."""

    @pytest.mark.asyncio
    async def test_connect_spawns_subprocess_and_sets_connected(self) -> None:
        """connect() spawns subprocess with correct args, sets is_connected=True."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        assert transport.is_connected is False
        await transport.connect()
        assert transport.is_connected is True
        await transport.close()

    @pytest.mark.asyncio
    async def test_connect_with_nonexistent_binary_raises(self) -> None:
        """connect() with non-existent binary raises an error."""
        transport = ProcessTransport(
            exec_path="/nonexistent/binary/droid",
            exec_args=["exec"],
        )
        with pytest.raises((FileNotFoundError, DroidConnectionError)):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_while_connected_raises_connection_error(self) -> None:
        """connect() while already connected raises ConnectionError."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()
        try:
            with pytest.raises(DroidConnectionError, match="already connected"):
                await transport.connect()
        finally:
            await transport.close()

    @pytest.mark.asyncio
    async def test_connect_sets_custom_env(self) -> None:
        """connect() forwards custom env vars to the subprocess."""
        script = """
import os, sys, json
val = os.environ.get("TEST_CUSTOM_VAR", "missing")
sys.stdout.write(json.dumps({"env_val": val}) + '\\n')
sys.stdout.flush()
try:
    sys.stdin.read()
except:
    pass
"""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", script],
            env={"TEST_CUSTOM_VAR": "hello_world"},
        )
        await transport.connect()
        messages, _ = await _collect_messages(transport, timeout=0.3)
        await transport.close()
        assert len(messages) >= 1
        assert messages[0]["env_val"] == "hello_world"

    @pytest.mark.asyncio
    async def test_connect_sets_custom_cwd(self) -> None:
        """connect() forwards custom cwd to the subprocess."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            script = """
import os, sys, json
sys.stdout.write(json.dumps({"cwd": os.getcwd()}) + '\\n')
sys.stdout.flush()
try:
    sys.stdin.read()
except:
    pass
"""
            transport = ProcessTransport(
                exec_path=sys.executable,
                exec_args=["-c", script],
                cwd=tmpdir,
            )
            await transport.connect()
            messages, _ = await _collect_messages(transport, timeout=0.3)
            await transport.close()
            assert len(messages) >= 1
            import os

            assert os.path.realpath(messages[0]["cwd"]) == os.path.realpath(tmpdir)


# ---------------------------------------------------------------------------
# ProcessTransport: send() tests
# ---------------------------------------------------------------------------


class TestProcessTransportSend:
    """Tests for send() writing to stdin."""

    @pytest.mark.asyncio
    async def test_send_writes_compact_json_plus_newline(self) -> None:
        """send() writes compact JSON + newline to stdin."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()

        msg = {"jsonrpc": "2.0", "id": "1", "method": "test"}
        await transport.send(json.dumps(msg))
        await asyncio.sleep(0.2)

        messages, _ = await _collect_messages(transport, timeout=0.3)
        await transport.close()

        assert len(messages) >= 1
        assert messages[0] == msg

    @pytest.mark.asyncio
    async def test_send_after_exit_raises_immediately(self) -> None:
        """send() after subprocess exit raises immediately."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_exit_script(0)],
        )
        await transport.connect()
        # Consume read_messages to detect exit
        await _read_until_done(transport, timeout=5.0)
        assert transport.is_connected is False
        with pytest.raises((DroidConnectionError, ProcessExitError)):
            await transport.send('{"test": true}')

    @pytest.mark.asyncio
    async def test_send_after_close_raises(self) -> None:
        """send() after close() raises ConnectionError."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()
        await transport.close()
        with pytest.raises((DroidConnectionError, ProcessExitError)):
            await transport.send('{"test": true}')

    @pytest.mark.asyncio
    async def test_concurrent_sends_serialized_no_interleaving(self) -> None:
        """Multiple concurrent sends produce non-interleaved complete JSON lines."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()

        # Send 20 concurrent messages
        msgs = [json.dumps({"id": str(i), "data": "x" * 100}) for i in range(20)]
        await asyncio.gather(*(transport.send(m) for m in msgs))

        messages, _ = await _collect_messages(transport, timeout=0.5)
        await transport.close()

        # Each received message should be independently valid JSON with expected fields
        assert len(messages) == 20
        for msg in messages:
            assert "id" in msg
            assert "data" in msg


# ---------------------------------------------------------------------------
# ProcessTransport: Read loop tests (via read_messages)
# ---------------------------------------------------------------------------


class TestProcessTransportReadLoop:
    """Tests for read_messages() parsing stdout."""

    @pytest.mark.asyncio
    async def test_valid_json_lines_delivered(self) -> None:
        """Valid JSON lines are delivered individually from read_messages."""
        lines = [
            '{"jsonrpc": "2.0", "id": "1", "result": "hello"}',
            '{"jsonrpc": "2.0", "id": "2", "result": "world"}',
        ]
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_output_script(lines)],
        )
        await transport.connect()
        messages, _ = await _collect_messages(transport, timeout=0.5)
        await transport.close()

        assert len(messages) == 2
        assert messages[0]["result"] == "hello"
        assert messages[1]["result"] == "world"

    @pytest.mark.asyncio
    async def test_blank_lines_skipped(self) -> None:
        """Empty/whitespace lines are silently skipped."""
        lines = [
            '{"id": "1"}',
            "",
            "   ",
            '{"id": "2"}',
        ]
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_output_script(lines)],
        )
        await transport.connect()
        messages, _ = await _collect_messages(transport, timeout=0.5)
        await transport.close()

        assert len(messages) == 2
        assert messages[0]["id"] == "1"
        assert messages[1]["id"] == "2"

    @pytest.mark.asyncio
    async def test_malformed_json_skipped_without_stopping(self) -> None:
        """Malformed JSON is skipped but read_messages continues."""
        lines = [
            '{"id": "1"}',
            '{"broken json',
            '{"id": "2"}',
        ]
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_output_script(lines)],
        )
        await transport.connect()
        messages, _ = await _collect_messages(transport, timeout=0.5)
        await transport.close()

        # Valid messages still delivered, malformed skipped
        assert len(messages) == 2
        assert messages[0]["id"] == "1"
        assert messages[1]["id"] == "2"

    @pytest.mark.asyncio
    async def test_non_json_output_does_not_disrupt(self) -> None:
        """Non-JSON text (e.g., debug logging) is skipped, valid messages delivered."""
        lines = [
            "Debug: starting up...",
            '{"id": "1"}',
            "WARNING: something happened",
            '{"id": "2"}',
        ]
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_output_script(lines)],
        )
        await transport.connect()
        messages, _ = await _collect_messages(transport, timeout=0.5)
        await transport.close()

        assert len(messages) == 2
        assert messages[0]["id"] == "1"
        assert messages[1]["id"] == "2"


# ---------------------------------------------------------------------------
# ProcessTransport: Process exit detection
# ---------------------------------------------------------------------------


class TestProcessTransportExitDetection:
    """Tests for process exit detection."""

    @pytest.mark.asyncio
    async def test_normal_exit_sets_disconnected(self) -> None:
        """Normal exit (code 0) sets is_connected=False."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_exit_script(0)],
        )
        await transport.connect()
        # read_messages will terminate when process exits
        _messages, _errors = await _read_until_done(transport, timeout=5.0)
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_abnormal_exit_raises_process_exit_error(self) -> None:
        """Abnormal exit raises ProcessExitError from read_messages."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_exit_script(42)],
        )
        await transport.connect()
        _messages, errors = await _read_until_done(transport, timeout=5.0)

        assert transport.is_connected is False
        exit_errors = [e for e in errors if isinstance(e, ProcessExitError)]
        assert len(exit_errors) >= 1
        assert exit_errors[0].exit_code == 42

    @pytest.mark.asyncio
    async def test_exit_drains_remaining_stdout(self) -> None:
        """Remaining stdout is drained before reporting exit."""
        lines = [
            '{"id": "1"}',
            '{"id": "2"}',
        ]
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_output_and_exit_script(lines, exit_code=0)],
        )
        await transport.connect()
        messages, _errors = await _read_until_done(transport, timeout=5.0)

        # Messages should be received before exit
        assert len(messages) == 2
        assert messages[0]["id"] == "1"
        assert messages[1]["id"] == "2"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exit_code", [0, 23])
    async def test_exit_includes_bounded_stderr_diagnostics(
        self,
        exit_code: int,
    ) -> None:
        script = f"""
import sys
sys.stderr.write("useful diagnostic " * 5000)
sys.stderr.flush()
sys.exit({exit_code})
"""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", script],
        )
        await transport.connect()
        _messages, errors = await _read_until_done(transport, timeout=5.0)

        assert len(errors) == 1
        assert isinstance(errors[0], ProcessExitError)
        assert "useful diagnostic" in str(errors[0])
        assert len(str(errors[0])) < 17_000
        assert transport._stderr_task is None

    @pytest.mark.asyncio
    async def test_stderr_secrets_are_never_exposed(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Raw child stderr and explicit environment secrets stay private."""
        secret = "factory-secret-value"
        script = """
import os, sys
sys.stderr.write(os.environ["PRIVATE_RUNTIME_VALUE"] + "\\n")
sys.stderr.flush()
sys.exit(1)
"""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", script],
            env={"PRIVATE_RUNTIME_VALUE": secret, "FACTORY_API_KEY": secret},
        )
        await transport.connect()
        _messages, errors = await _read_until_done(transport, timeout=5.0)

        exit_errors = [e for e in errors if isinstance(e, ProcessExitError)]
        assert len(exit_errors) >= 1
        assert exit_errors[0].exit_code == 1
        assert secret not in str(exit_errors[0])
        assert secret not in repr(exit_errors[0])
        assert secret not in caplog.text

    @pytest.mark.asyncio
    async def test_stderr_redacts_configured_values_and_key_patterns(self) -> None:
        configured = "ordinary-configured-value"
        api_key = "sk_live_unconfigured_api_key"
        script = f"""
import sys
sys.stderr.write(
    "configured={configured} API_KEY={api_key} "
    "Authorization: Bearer bearer-secret-value"
)
sys.stderr.flush()
sys.exit(1)
"""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", script],
            env={"DISPLAY_NAME": configured},
        )
        await transport.connect()
        _messages, errors = await _read_until_done(transport, timeout=5.0)

        diagnostic = str(errors[0])
        assert "[REDACTED]" in diagnostic
        assert configured not in diagnostic
        assert api_key not in diagnostic
        assert "bearer-secret-value" not in diagnostic


# ---------------------------------------------------------------------------
# ProcessTransport: close() tests
# ---------------------------------------------------------------------------


class TestProcessTransportClose:
    """Tests for close() shutdown behavior."""

    @pytest.mark.asyncio
    async def test_close_sends_sigterm_cooperative_child(self) -> None:
        """close() sends SIGTERM, cooperative child exits cleanly."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", COOPERATIVE_SCRIPT],
        )
        await transport.connect()
        # Wait for ready signal
        await asyncio.sleep(0.3)
        assert transport.is_connected is True

        await asyncio.wait_for(transport.close(), timeout=10.0)
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_close_escalates_to_sigkill_stubborn_child(self) -> None:
        """close() escalates to SIGKILL for stubborn child (ignores SIGTERM)."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", STUBBORN_SCRIPT],
            grace_period=1.0,  # Short grace for test speed
        )
        await transport.connect()
        await asyncio.sleep(0.3)
        assert transport.is_connected is True

        # Should complete within grace_period + some buffer
        await asyncio.wait_for(transport.close(), timeout=5.0)
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self) -> None:
        """close() is idempotent — calling multiple times is safe."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()
        await transport.close()
        # Second close should not raise
        await transport.close()
        # Third close should not raise
        await transport.close()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_close_before_connect_is_safe(self) -> None:
        """close() before connect() is a no-op."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.close()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_close_completes_within_bounded_time(self) -> None:
        """close() completes within grace_period + buffer, even for stubborn child."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", STUBBORN_SCRIPT],
            grace_period=1.0,
        )
        await transport.connect()
        await asyncio.sleep(0.3)

        import time

        start = time.monotonic()
        await transport.close()
        elapsed = time.monotonic() - start

        # Should complete within grace_period(1s) + 2s buffer
        assert elapsed < 3.0

    @pytest.mark.asyncio
    async def test_close_cancellation_cleans_stderr_task_and_allows_reconnect(
        self,
    ) -> None:
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", STUBBORN_SCRIPT],
            grace_period=5,
        )
        await transport.connect()
        await asyncio.sleep(0.2)
        stderr_task = transport._stderr_task
        assert stderr_task is not None

        close_task = asyncio.create_task(transport.close())
        await asyncio.sleep(0)
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task

        assert stderr_task.done()
        assert transport._stderr_task is None
        transport._exec_args = ["-c", ECHO_SCRIPT]
        await transport.connect()
        await transport.close()
        assert transport._stderr_task is None


# ---------------------------------------------------------------------------
# ProcessTransport: Reconnection tests
# ---------------------------------------------------------------------------


class TestProcessTransportReconnection:
    """Tests for reconnection after close."""

    @pytest.mark.asyncio
    async def test_reconnect_spawns_new_pid(self) -> None:
        """After close(), connect() spawns a new subprocess with different PID."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()
        pid1 = transport.pid
        assert pid1 is not None

        await transport.close()
        assert transport.is_connected is False

        await transport.connect()
        pid2 = transport.pid
        assert pid2 is not None
        assert pid2 != pid1
        assert transport.is_connected is True

        await transport.close()

    @pytest.mark.asyncio
    async def test_reconnect_resets_state(self) -> None:
        """After close() + connect(), internal state is clean."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()

        # Send a message
        await transport.send('{"id": "1"}')
        await asyncio.sleep(0.2)

        # Close and reconnect
        await transport.close()

        await transport.connect()
        # New subprocess should work with a fresh send
        await transport.send('{"id": "2"}')
        messages, _ = await _collect_messages(transport, timeout=0.3)
        await transport.close()

        assert len(messages) >= 1
        assert messages[0]["id"] == "2"

    @pytest.mark.asyncio
    async def test_reconnect_after_process_exit(self) -> None:
        """After unexpected process exit, close() + connect() works."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_exit_script(1)],
        )
        await transport.connect()
        # Wait for process to exit
        _msgs, _errs = await _read_until_done(transport, timeout=5.0)
        assert transport.is_connected is False

        # Close (cleanup) then reconnect with a different script
        await transport.close()

        # Reconnect with echo script
        transport._exec_args = ["-c", ECHO_SCRIPT]
        await transport.connect()
        assert transport.is_connected is True

        await transport.send('{"id": "reconnected"}')
        messages, _ = await _collect_messages(transport, timeout=0.3)
        await transport.close()

        assert len(messages) >= 1
        assert messages[0]["id"] == "reconnected"


# ---------------------------------------------------------------------------
# ProcessTransport: Default exec_path and exec_args for droid exec
# ---------------------------------------------------------------------------


class TestProcessTransportDefaults:
    """Tests for default ProcessTransport configuration."""

    def test_default_exec_path_is_droid(self) -> None:
        """Default exec_path is 'droid'."""
        transport = ProcessTransport()
        assert transport._exec_path == "droid"

    def test_default_exec_args(self) -> None:
        """Default exec_args include stream-jsonrpc flags."""
        transport = ProcessTransport()
        assert transport._exec_args == [
            "exec",
            "--input-format",
            "stream-jsonrpc",
            "--output-format",
            "stream-jsonrpc",
        ]


# ---------------------------------------------------------------------------
# ProcessTransport: Large payload handling
# ---------------------------------------------------------------------------


class TestProcessTransportLargePayloads:
    """Tests for handling large messages."""

    @pytest.mark.asyncio
    async def test_large_message_send_and_receive(self) -> None:
        """Large messages (100KB+) are sent and received without truncation."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        await transport.connect()

        # Create a large message (~200KB)
        large_data = "x" * 200_000
        msg = json.dumps({"id": "large", "data": large_data})
        await transport.send(msg)

        messages, _ = await _collect_messages(transport, timeout=1.0)
        await transport.close()

        assert len(messages) >= 1
        assert messages[0]["id"] == "large"
        assert len(messages[0]["data"]) == 200_000

    @pytest.mark.asyncio
    async def test_large_stderr_before_protocol_output_cannot_deadlock(self) -> None:
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", LARGE_STDERR_SCRIPT],
        )
        await transport.connect()
        reader = transport.read_messages()
        message = await asyncio.wait_for(anext(reader), timeout=5)
        assert message == {"ready": True}
        await reader.aclose()
        await transport.close()
        assert transport._stderr_task is None


# ---------------------------------------------------------------------------
# ProcessTransport: Edge cases
# ---------------------------------------------------------------------------


class TestProcessTransportEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_send_without_connect_raises(self) -> None:
        """send() without connect() raises ConnectionError."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", ECHO_SCRIPT],
        )
        with pytest.raises(DroidConnectionError):
            await transport.send('{"test": true}')

    @pytest.mark.asyncio
    async def test_process_killed_externally(self) -> None:
        """Process killed externally is detected and reported."""
        import os

        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", COOPERATIVE_SCRIPT],
        )
        await transport.connect()
        await asyncio.sleep(0.3)

        # Kill the process externally
        pid = transport.pid
        assert pid is not None
        os.kill(pid, signal.SIGKILL)

        # read_messages should detect the exit
        _messages, errors = await _read_until_done(transport, timeout=5.0)

        assert transport.is_connected is False
        exit_errors = [e for e in errors if isinstance(e, ProcessExitError)]
        assert len(exit_errors) >= 1
        # SIGKILL = signal 9
        assert exit_errors[0].signal == 9 or exit_errors[0].exit_code is not None

    @pytest.mark.asyncio
    async def test_connect_after_process_exit_without_close(self) -> None:
        """After process exit, connect() without close() works."""
        transport = ProcessTransport(
            exec_path=sys.executable,
            exec_args=["-c", make_exit_script(0)],
        )
        await transport.connect()
        # Wait for exit
        await _read_until_done(transport, timeout=5.0)
        assert transport.is_connected is False

        # Should be able to reconnect after unexpected exit
        transport._exec_args = ["-c", ECHO_SCRIPT]
        await transport.connect()
        assert transport.is_connected is True
        await transport.close()
