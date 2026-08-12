"""Tests for the error class hierarchy in droid_sdk.errors."""

from __future__ import annotations

import pytest

from droid_sdk.errors import (
    ConnectionError,
    DroidClientError,
    ProcessExitError,
    ProtocolError,
    SessionError,
    SessionNotFoundError,
    TimeoutError,
)

# ---------------------------------------------------------------------------
# Inheritance hierarchy tests
# ---------------------------------------------------------------------------


class TestInheritanceHierarchy:
    """Verify issubclass relationships for the error hierarchy."""

    def test_droid_client_error_is_base_exception(self) -> None:
        assert issubclass(DroidClientError, Exception)

    def test_connection_error_inherits_droid_client_error(self) -> None:
        assert issubclass(ConnectionError, DroidClientError)

    def test_timeout_error_inherits_droid_client_error(self) -> None:
        assert issubclass(TimeoutError, DroidClientError)

    def test_protocol_error_inherits_droid_client_error(self) -> None:
        assert issubclass(ProtocolError, DroidClientError)

    def test_session_error_inherits_droid_client_error(self) -> None:
        assert issubclass(SessionError, DroidClientError)

    def test_session_not_found_error_inherits_session_error(self) -> None:
        assert issubclass(SessionNotFoundError, SessionError)

    def test_session_not_found_error_inherits_droid_client_error(self) -> None:
        assert issubclass(SessionNotFoundError, DroidClientError)

    def test_process_exit_error_inherits_droid_client_error(self) -> None:
        assert issubclass(ProcessExitError, DroidClientError)

    def test_all_errors_are_exceptions(self) -> None:
        """All SDK error classes should be catchable as Exception."""
        error_classes = [
            DroidClientError,
            ConnectionError,
            TimeoutError,
            ProtocolError,
            SessionError,
            SessionNotFoundError,
            ProcessExitError,
        ]
        for cls in error_classes:
            assert issubclass(cls, Exception), f"{cls.__name__} is not an Exception"


# ---------------------------------------------------------------------------
# Instance attribute tests
# ---------------------------------------------------------------------------


class TestDroidClientError:
    """Tests for the base DroidClientError class."""

    def test_message_attribute(self) -> None:
        err = DroidClientError("something went wrong")
        assert err.message == "something went wrong"

    def test_str_representation(self) -> None:
        err = DroidClientError("base error")
        assert str(err) == "base error"

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(DroidClientError, match="test error"):
            raise DroidClientError("test error")

    def test_args_tuple(self) -> None:
        err = DroidClientError("oops")
        assert err.args == ("oops",)


class TestConnectionError:
    """Tests for ConnectionError with cwd and exec_path attributes."""

    def test_attributes_default_to_none(self) -> None:
        err = ConnectionError("connection failed")
        assert err.cwd is None
        assert err.exec_path is None

    def test_cwd_attribute(self) -> None:
        err = ConnectionError("failed", cwd="/home/user/project")
        assert err.cwd == "/home/user/project"

    def test_exec_path_attribute(self) -> None:
        err = ConnectionError("failed", exec_path="/usr/local/bin/droid")
        assert err.exec_path == "/usr/local/bin/droid"

    def test_both_attributes(self) -> None:
        err = ConnectionError("failed", cwd="/home/user", exec_path="/usr/bin/droid")
        assert err.cwd == "/home/user"
        assert err.exec_path == "/usr/bin/droid"

    def test_message_attribute(self) -> None:
        err = ConnectionError("conn failed")
        assert err.message == "conn failed"

    def test_str_includes_metadata_cwd(self) -> None:
        err = ConnectionError("failed", cwd="/home/user")
        result = str(err)
        assert "failed" in result
        assert "cwd=" in result
        assert "/home/user" in result

    def test_str_includes_metadata_exec_path(self) -> None:
        err = ConnectionError("failed", exec_path="/usr/bin/droid")
        result = str(err)
        assert "failed" in result
        assert "exec_path=" in result
        assert "/usr/bin/droid" in result

    def test_str_includes_all_metadata(self) -> None:
        err = ConnectionError("failed", cwd="/home", exec_path="/usr/bin/droid")
        result = str(err)
        assert "failed" in result
        assert "cwd=" in result
        assert "exec_path=" in result

    def test_str_no_metadata(self) -> None:
        err = ConnectionError("simple failure")
        assert str(err) == "simple failure"

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise ConnectionError("oops")


class TestTimeoutError:
    """Tests for TimeoutError with request_id, method, timeout_duration."""

    def test_attributes_default_to_none(self) -> None:
        err = TimeoutError("timed out")
        assert err.request_id is None
        assert err.method is None
        assert err.timeout_duration is None

    def test_request_id_attribute(self) -> None:
        err = TimeoutError("timed out", request_id="req-123")
        assert err.request_id == "req-123"

    def test_method_attribute(self) -> None:
        err = TimeoutError("timed out", method="droid.initialize_session")
        assert err.method == "droid.initialize_session"

    def test_timeout_duration_attribute(self) -> None:
        err = TimeoutError("timed out", timeout_duration=30.0)
        assert err.timeout_duration == 30.0

    def test_all_attributes(self) -> None:
        err = TimeoutError(
            "timed out",
            request_id="req-456",
            method="droid.add_user_message",
            timeout_duration=60.0,
        )
        assert err.request_id == "req-456"
        assert err.method == "droid.add_user_message"
        assert err.timeout_duration == 60.0

    def test_message_attribute(self) -> None:
        err = TimeoutError("request timed out")
        assert err.message == "request timed out"

    def test_str_includes_metadata(self) -> None:
        err = TimeoutError(
            "timed out",
            request_id="req-789",
            method="droid.init",
            timeout_duration=30.0,
        )
        result = str(err)
        assert "timed out" in result
        assert "request_id=" in result
        assert "req-789" in result
        assert "method=" in result
        assert "droid.init" in result
        assert "timeout_duration=" in result
        assert "30.0" in result

    def test_str_no_metadata(self) -> None:
        err = TimeoutError("timed out")
        assert str(err) == "timed out"

    def test_str_partial_metadata(self) -> None:
        err = TimeoutError("timed out", method="droid.init")
        result = str(err)
        assert "timed out" in result
        assert "method=" in result
        assert "request_id" not in result

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise TimeoutError("oops")


class TestProtocolError:
    """Tests for ProtocolError with code and data attributes."""

    def test_attributes_default_to_none(self) -> None:
        err = ProtocolError("protocol error")
        assert err.code is None
        assert err.data is None

    def test_code_attribute(self) -> None:
        err = ProtocolError("parse error", code=-32700)
        assert err.code == -32700

    def test_data_attribute(self) -> None:
        err = ProtocolError("error", data={"detail": "bad json"})
        assert err.data == {"detail": "bad json"}

    def test_both_attributes(self) -> None:
        err = ProtocolError("error", code=-32600, data="invalid request")
        assert err.code == -32600
        assert err.data == "invalid request"

    def test_message_attribute(self) -> None:
        err = ProtocolError("proto error")
        assert err.message == "proto error"

    def test_str_includes_metadata(self) -> None:
        err = ProtocolError("error", code=-32700, data={"x": 1})
        result = str(err)
        assert "error" in result
        assert "code=-32700" in result
        assert "data=" in result

    def test_str_no_metadata(self) -> None:
        err = ProtocolError("simple")
        assert str(err) == "simple"

    def test_str_code_only(self) -> None:
        err = ProtocolError("err", code=-32600)
        result = str(err)
        assert "err" in result
        assert "code=-32600" in result
        assert "data=" not in result

    def test_data_accepts_any_type(self) -> None:
        """data can be any type: dict, list, str, int, None."""
        assert ProtocolError("e", data=[1, 2, 3]).data == [1, 2, 3]
        assert ProtocolError("e", data="text").data == "text"
        assert ProtocolError("e", data=42).data == 42

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise ProtocolError("oops")


class TestSessionError:
    """Tests for SessionError."""

    def test_message_attribute(self) -> None:
        err = SessionError("no session")
        assert err.message == "no session"

    def test_str_representation(self) -> None:
        err = SessionError("session error")
        assert str(err) == "session error"

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise SessionError("oops")


class TestSessionNotFoundError:
    """Tests for SessionNotFoundError."""

    def test_session_id_attribute(self) -> None:
        err = SessionNotFoundError("sess-abc-123")
        assert err.session_id == "sess-abc-123"

    def test_message_includes_session_id(self) -> None:
        err = SessionNotFoundError("sess-abc-123")
        assert err.message == "Session not found: sess-abc-123"

    def test_str_includes_session_id(self) -> None:
        err = SessionNotFoundError("sess-xyz")
        assert "Session not found: sess-xyz" in str(err)

    def test_catchable_as_session_error(self) -> None:
        with pytest.raises(SessionError):
            raise SessionNotFoundError("abc")

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise SessionNotFoundError("abc")


class TestProcessExitError:
    """Tests for ProcessExitError with exit_code and signal attributes."""

    def test_attributes_default_to_none(self) -> None:
        err = ProcessExitError("process exited")
        assert err.exit_code is None
        assert err.signal is None

    def test_exit_code_attribute(self) -> None:
        err = ProcessExitError("exited", exit_code=1)
        assert err.exit_code == 1

    def test_signal_attribute(self) -> None:
        err = ProcessExitError("killed", signal=9)
        assert err.signal == 9

    def test_both_attributes(self) -> None:
        err = ProcessExitError("exited", exit_code=137, signal=9)
        assert err.exit_code == 137
        assert err.signal == 9

    def test_message_attribute(self) -> None:
        err = ProcessExitError("proc exit")
        assert err.message == "proc exit"

    def test_str_includes_metadata_exit_code(self) -> None:
        err = ProcessExitError("exited", exit_code=1)
        result = str(err)
        assert "exited" in result
        assert "exit_code=1" in result

    def test_str_includes_metadata_signal(self) -> None:
        err = ProcessExitError("killed", signal=15)
        result = str(err)
        assert "killed" in result
        assert "signal=15" in result

    def test_str_includes_all_metadata(self) -> None:
        err = ProcessExitError("crashed", exit_code=137, signal=9)
        result = str(err)
        assert "crashed" in result
        assert "exit_code=137" in result
        assert "signal=9" in result

    def test_str_no_metadata(self) -> None:
        err = ProcessExitError("process gone")
        assert str(err) == "process gone"

    def test_catchable_as_droid_client_error(self) -> None:
        with pytest.raises(DroidClientError):
            raise ProcessExitError("oops")


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------


class TestErrorHierarchyCrossCutting:
    """Cross-cutting tests for the overall error hierarchy."""

    @pytest.mark.parametrize(
        "error_class",
        [
            ConnectionError,
            TimeoutError,
            ProtocolError,
            SessionError,
            SessionNotFoundError,
            ProcessExitError,
        ],
    )
    def test_all_subclasses_are_droid_client_errors(self, error_class: type) -> None:
        assert issubclass(error_class, DroidClientError)

    def test_catch_all_with_base_class(self) -> None:
        """All errors can be caught with a single except DroidClientError."""
        errors = [
            ConnectionError("c"),
            TimeoutError("t"),
            ProtocolError("p"),
            SessionError("s"),
            SessionNotFoundError("id"),
            ProcessExitError("x"),
        ]
        for err in errors:
            with pytest.raises(DroidClientError):
                raise err

    def test_session_not_found_caught_by_session_error(self) -> None:
        """SessionNotFoundError can be caught by SessionError handler."""
        with pytest.raises(SessionError):
            raise SessionNotFoundError("missing-session")

    def test_errors_do_not_shadow_builtins(self) -> None:
        """SDK errors are in their own namespace and don't shadow builtins."""
        import builtins

        # Our ConnectionError and TimeoutError are in droid_sdk.errors
        # and are NOT the same as the builtins
        assert ConnectionError is not builtins.ConnectionError  # type: ignore[attr-defined]
        assert TimeoutError is not builtins.TimeoutError  # type: ignore[attr-defined]

    def test_error_repr_includes_class_name(self) -> None:
        """repr() includes the class name for debugging."""
        err = DroidClientError("test")
        assert "DroidError" in repr(err)

    def test_str_of_each_error_with_metadata(self) -> None:
        """Verify str() of each error type includes its metadata."""
        conn = ConnectionError("conn failed", cwd="/tmp", exec_path="/usr/bin/droid")
        assert "cwd=" in str(conn)
        assert "exec_path=" in str(conn)

        timeout = TimeoutError(
            "timed out",
            request_id="r1",
            method="droid.init",
            timeout_duration=30.0,
        )
        assert "request_id=" in str(timeout)
        assert "method=" in str(timeout)
        assert "timeout_duration=" in str(timeout)

        proto = ProtocolError("proto err", code=-32700, data={"k": "v"})
        assert "code=" in str(proto)
        assert "data=" in str(proto)

        proc = ProcessExitError("exit", exit_code=1, signal=9)
        assert "exit_code=" in str(proc)
        assert "signal=" in str(proc)

        # SessionNotFoundError includes session_id in its message
        snf = SessionNotFoundError("sid-123")
        assert "sid-123" in str(snf)
