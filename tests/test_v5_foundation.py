"""Focused contract tests for the SDK v5 low-level foundation."""

from __future__ import annotations

from pathlib import Path

from droid_sdk.errors import (
    DroidConnectionError,
    DroidError,
    DroidProcessError,
    DroidProtocolError,
    InvalidAttachmentError,
    InvalidWorkingDirectoryError,
    RunTimeoutError,
    SessionBusyError,
    SessionClosedError,
    SessionNotFoundError,
    SessionNotOpenError,
    SessionReplacedError,
    SessionReplacementError,
    StreamIncompleteError,
)
from droid_sdk.low_level import (
    AgentTurnCompletedNotification,
    AgentTurnCompletionReason,
    McpOAuthOptions,
    ProcessTransport,
    ProtocolEngine,
    SandboxMode,
    SessionNotification,
    SessionNotificationType,
    ToolExecutionLifecyclePhase,
    Transport,
)
from droid_sdk.schemas.client import TokenUsage


def test_v5_exception_hierarchy_and_metadata() -> None:
    exception_types = (
        RunTimeoutError,
        StreamIncompleteError,
        InvalidAttachmentError,
        SessionNotOpenError,
        SessionBusyError,
        SessionClosedError,
        SessionReplacedError,
        SessionReplacementError,
        SessionNotFoundError,
        InvalidWorkingDirectoryError,
        DroidConnectionError,
        DroidProcessError,
        DroidProtocolError,
    )
    assert all(issubclass(error_type, DroidError) for error_type in exception_types)

    timeout = RunTimeoutError(
        "timed out", request_id="req-1", method="droid.test", timeout_duration=1.5
    )
    assert (timeout.request_id, timeout.method, timeout.timeout_duration) == (
        "req-1",
        "droid.test",
        1.5,
    )
    assert DroidProcessError("exited", exit_code=9).exit_code == 9
    assert DroidProtocolError("bad", code=-32602, data={"field": "cwd"}).data == {
        "field": "cwd"
    }


def test_canonical_enum_values() -> None:
    assert SessionNotificationType.AGENT_TURN_COMPLETED.value == "agent_turn_completed"
    assert AgentTurnCompletionReason.StructuredOutputInvalid.value == (
        "structured_output_invalid"
    )
    assert ToolExecutionLifecyclePhase.SettledAfterExecution.value == (
        "settled_after_execution"
    )
    assert SandboxMode.WholeProcess.value == "whole-process"


def test_turn_completion_schema_and_aliases() -> None:
    payload = {
        "type": "agent_turn_completed",
        "reason": "completed",
        "turnId": "turn-1",
        "tokenUsage": {
            "inputTokens": 1,
            "outputTokens": 2,
            "cacheCreationTokens": 3,
            "cacheReadTokens": 4,
            "thinkingTokens": 5,
        },
        "durationMs": 12.5,
    }
    notification = SessionNotification.model_validate(
        {
            "jsonrpc": "2.0",
            "factoryApiVersion": "1.0.0",
            "factoryProtocolVersion": "1.1.0",
            "type": "notification",
            "method": "droid.session_notification",
            "params": {"notification": payload},
        }
    )
    completed = notification.params.notification
    assert isinstance(completed, AgentTurnCompletedNotification)
    assert completed.token_usage == TokenUsage.model_validate(payload["tokenUsage"])
    assert completed.model_dump(by_alias=True)["durationMs"] == 12.5


def test_mcp_oauth_aliases_and_low_level_exports() -> None:
    options = McpOAuthOptions.model_validate(
        {
            "clientId": "client",
            "callbackPort": 8123,
            "authorizationServerIssuer": "https://issuer.example",
        }
    )
    assert options.client_id == "client"
    assert options.model_dump(by_alias=True)["callbackPort"] == 8123
    assert ProcessTransport is not None
    assert ProtocolEngine is not None
    assert Transport is not None


def test_dependency_and_pyright_metadata() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert '"mcp>=1.27,<2"' in pyproject
    assert '"pyright"' in pyproject
    assert 'typeCheckingMode = "strict"' in pyproject
