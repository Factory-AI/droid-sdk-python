from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from droid_sdk import ErrorEvent, ErrorType, RunStream, RunSuccess

if TYPE_CHECKING:
    from collections.abc import Mapping


# --- Notification fixture helpers ---
def _complete() -> dict[str, object]:
    return {
        "type": "agent_turn_completed",
        "reason": "completed",
        "turnId": "turn",
        "durationMs": 1,
        "tokenUsage": {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "thinkingTokens": 0,
        },
    }


# --- End notification fixture helpers ---


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["LLMInvalidRequestError", "LLMServiceError"])
async def test_high_level_stream_preserves_error_discriminator(name: str) -> None:
    """Applications must classify equal-message errors without parsing prose."""
    detail: dict[str, object] = {
        "name": name,
        "message": "Provider request failed",
        "cause": {"status": 404, "attempts": [1, 2]},
    }
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "error",
            "message": "Provider request failed",
            "errorType": "Error",
            "timestamp": "2026-08-02T11:00:13.647Z",
            "error": detail,
        }
    )
    stream.feed_notification(_complete())

    events = [event async for event in stream]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.error_type is ErrorType.ERROR
    assert error.message == "Provider request failed"
    assert error.error_name == name
    assert error.error_detail is not None
    assert error.error_detail["name"] == name
    cause = cast("Mapping[str, object]", error.error_detail["cause"])
    assert cause["status"] == 404
    assert cause["attempts"] == (1, 2)
    assert error.timestamp.isoformat() == "2026-08-02T11:00:13.647000+00:00"
    assert isinstance(events[-1], RunSuccess)
    assert stream.result.messages == (error,)
    with pytest.raises(TypeError):
        cast("dict[str, object]", cause)["status"] = 500


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"error": None}])
async def test_high_level_error_without_detail_remains_supported(
    extra: dict[str, object],
) -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "error",
            "message": "recoverable",
            "errorType": "Error",
            "timestamp": "2025-01-01T00:00:00Z",
            **extra,
        }
    )
    stream.feed_notification(_complete())

    events = [event async for event in stream]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.error_name is None
    assert error.error_detail is None


def test_error_detail_is_detached_from_mutable_constructor_input() -> None:
    detail: dict[str, object] = {"cause": {"attempts": [1, 2]}}
    error = ErrorEvent(
        message="failed",
        error_type=ErrorType.ERROR,
        error_detail=detail,
    )
    cast("dict[str, object]", detail["cause"])["attempts"] = [3]

    assert error.error_detail is not None
    cause = cast("Mapping[str, object]", error.error_detail["cause"])
    assert cause["attempts"] == (1, 2)
