from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from pydantic import BaseModel

from droid_sdk import (
    AssistantMessage,
    Autonomy,
    ErrorEvent,
    HookExecution,
    InteractionHandlers,
    JsonSchema,
    McpAuthCompleted,
    McpAuthRequired,
    McpStatusChanged,
    Mode,
    PermissionRequest,
    PermissionResolved,
    QuestionRequest,
    ReasoningEffort,
    RunFailure,
    RunInterrupted,
    RunStream,
    RunSuccess,
    RunTimeoutError,
    SessionSettingsUpdate,
    SessionTitleUpdated,
    SessionWorkingDirectoryChanged,
    SettingsUpdated,
    StreamIncompleteError,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    TokenUsageUpdate,
    ToolCall,
    ToolCallDelta,
    ToolConfirmationOutcome,
    ToolProgress,
    ToolResult,
    UserMessage,
    WorkingStateChanged,
)
from droid_sdk._high_level.interaction_adapter import InteractionDispatcher
from droid_sdk._high_level.output import prepare_output_adapter
from droid_sdk._high_level.streaming import _javascript_number_string
from droid_sdk.errors import DroidProtocolError
from droid_sdk.low_level import DroidClient

USAGE = {
    "inputTokens": 1,
    "outputTokens": 2,
    "cacheCreationTokens": 3,
    "cacheReadTokens": 4,
    "thinkingTokens": 5,
    "factoryCredits": 0.25,
}


def _message(
    role: str = "assistant",
    *,
    content: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{role}-message",
        "role": role,
        "content": content or [{"type": "text", "id": "text-1", "text": "done"}],
        "parentId": "parent",
        "createdAt": 1_700_000_000,
        "updatedAt": 1_700_000_001,
    }


def _complete(
    reason: str = "completed",
    turn_id: str | None = "turn",
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "agent_turn_completed",
        "reason": reason,
        "tokenUsage": USAGE,
        "durationMs": 125,
    }
    if turn_id is not None:
        value["turnId"] = turn_id
    return value


async def _collect(stream: RunStream[Any]) -> list[object]:
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_deadline_checked_before_each_queued_event_and_terminal() -> None:
    current = 100.0
    releases: list[bool] = []
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        timeout=10,
        monotonic=lambda: current,
        finish=releases.append,
    )
    await stream.__aenter__()
    stream.feed_notification({"type": "create_message", "message": _message("user")})
    stream.feed_notification(_complete())
    iterator = stream.__aiter__()

    current = 109.999
    assert isinstance(await anext(iterator), UserMessage)

    current = 110.0
    with pytest.raises(RunTimeoutError):
        await anext(iterator)

    assert releases == [True]
    assert stream.completed is False
    with pytest.raises(StreamIncompleteError):
        _ = stream.result


@pytest.mark.asyncio
async def test_queued_terminal_after_deadline_cannot_become_success() -> None:
    current = 5.0
    releases: list[bool] = []
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        timeout=1,
        monotonic=lambda: current,
        finish=releases.append,
    )
    await stream.__aenter__()
    stream.feed_notification(_complete())
    current = 6.001

    with pytest.raises(RunTimeoutError):
        await anext(stream.__aiter__())

    assert releases == [True]
    assert stream.completed is False


@pytest.mark.asyncio
async def test_terminal_arriving_after_deadline_is_never_recorded_as_success() -> None:
    current = 1.0
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        timeout=2,
        monotonic=lambda: current,
    )
    await stream.__aenter__()
    current = 3.0
    stream.feed_notification(_complete())

    assert stream.completed is False
    with pytest.raises(RunTimeoutError):
        await anext(stream.__aiter__())


@pytest.mark.asyncio
async def test_stream_all_documented_partial_events_in_delivery_order() -> None:
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        include_partial_messages=True,
    )
    notifications: list[dict[str, Any]] = [
        {
            "type": "assistant_text_delta",
            "messageId": "assistant-message",
            "blockIndex": 0,
            "textDelta": "fallback",
        },
        {
            "type": "assistant_text_complete",
            "messageId": "assistant-message",
            "blockIndex": 0,
        },
        {
            "type": "thinking_text_delta",
            "messageId": "assistant-message",
            "blockIndex": 1,
            "textDelta": "thought",
        },
        {
            "type": "thinking_text_complete",
            "messageId": "assistant-message",
            "blockIndex": 1,
            "durationMs": 50,
        },
        {
            "type": "tool_call",
            "toolUse": {
                "type": "tool_use",
                "id": "tool-1",
                "name": "Read",
                "input": {"path": "/repo/a.py"},
            },
        },
        {
            "type": "tool_progress_update",
            "toolUseId": "tool-1",
            "toolName": "Read",
            "update": {
                "type": "status",
                "status": "running",
                "timestamp": 1_700_000_002,
                "parameters": {"path": "/repo/a.py"},
                "terminalId": "terminal",
                "fullOutput": "output",
                "subagentSessionId": "child",
            },
        },
        {
            "type": "session_token_usage_changed",
            "sessionId": "session",
            "tokenUsage": USAGE,
        },
        {"type": "droid_working_state_changed", "newState": "idle"},
        {
            "type": "permission_resolved",
            "requestId": "permission",
            "toolUseIds": ["tool-1"],
            "selectedOption": "proceed_always_file",
        },
        {
            "type": "settings_updated",
            "settings": {
                "modelId": "model",
                "reasoningEffort": "high",
                "interactionMode": "auto",
                "autonomyLevel": "low",
            },
        },
        {"type": "session_title_updated", "title": "New title"},
        {"type": "session_working_directory_changed", "cwd": "/repo"},
        {
            "type": "mcp_status_changed",
            "servers": [
                {
                    "name": "local",
                    "status": "connected",
                    "source": "project",
                    "isManaged": False,
                    "serverType": "stdio",
                }
            ],
            "summary": {
                "total": 1,
                "connected": 1,
                "connecting": 0,
                "failed": 0,
            },
        },
        {
            "type": "mcp_auth_required",
            "serverName": "remote",
            "authUrl": "https://example.test/auth",
            "message": "Authenticate",
            "state": "state",
        },
        {
            "type": "mcp_auth_completed",
            "serverName": "remote",
            "outcome": "success",
            "message": "Done",
        },
        {"type": "unknown_future_notification", "private": "ignored"},
        _complete(),
    ]
    for notification in notifications:
        stream.feed_notification(notification)

    events = await _collect(stream)
    assert [type(event) for event in events] == [
        TextDelta,
        TextComplete,
        ThinkingDelta,
        ThinkingComplete,
        ToolCallDelta,
        ToolProgress,
        TokenUsageUpdate,
        WorkingStateChanged,
        PermissionResolved,
        SettingsUpdated,
        SessionTitleUpdated,
        SessionWorkingDirectoryChanged,
        McpStatusChanged,
        McpAuthRequired,
        McpAuthCompleted,
        RunSuccess,
    ]
    assert cast("TextDelta", events[0]).message_id == "assistant-message"
    assert cast("ThinkingComplete", events[3]).duration == timedelta(milliseconds=50)
    assert cast("ToolProgress", events[5]).update.terminal_id == "terminal"
    assert cast("PermissionResolved", events[8]).selected_option is (
        ToolConfirmationOutcome.PROCEED_ALWAYS_EXACT_PATH
    )
    assert stream.result.text == "fallback"


@pytest.mark.asyncio
async def test_protocol_epoch_milliseconds_are_aware_datetimes() -> None:
    timestamp_ms = 1_700_000_000_123
    expected = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        include_partial_messages=True,
    )
    message = _message()
    message["createdAt"] = timestamp_ms
    message["updatedAt"] = timestamp_ms + 1
    stream.feed_notification({"type": "create_message", "message": message})
    stream.feed_notification(
        {
            "type": "tool_progress_update",
            "toolUseId": "tool",
            "toolName": "Read",
            "update": {
                "type": "status",
                "text": "working",
                "timestamp": timestamp_ms,
            },
        }
    )
    stream.feed_notification(_complete())

    events = await _collect(stream)
    assistant = cast("AssistantMessage", events[0])
    progress = cast("ToolProgress", events[1])
    assert assistant.created_at == expected
    assert assistant.updated_at == datetime.fromtimestamp(
        (timestamp_ms + 1) / 1000,
        tz=timezone.utc,
    )
    assert progress.update.timestamp == expected


@pytest.mark.asyncio
async def test_tool_progress_preserves_explicit_empty_text() -> None:
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        include_partial_messages=True,
    )
    stream.feed_notification(
        {
            "type": "tool_progress_update",
            "toolUseId": "tool",
            "toolName": "Read",
            "update": {
                "type": "status",
                "text": "",
                "status": "running",
                "details": "fallback",
            },
        }
    )
    stream.feed_notification(_complete())

    progress = cast("ToolProgress", (await _collect(stream))[0])
    assert progress.content == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (-0.0, "0"),
        (1, "1"),
        (-42, "-42"),
        (1.5, "1.5"),
        (1e-7, "1e-7"),
        (-2.5e-7, "-2.5e-7"),
        (1e-6, "0.000001"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1.2345678901234567, "1.2345678901234567"),
        (9_007_199_254_740_993, "9007199254740992"),
    ],
)
def test_javascript_number_stringification(
    value: int | float,
    expected: str,
) -> None:
    assert _javascript_number_string(value) == expected


@pytest.mark.asyncio
async def test_numeric_tool_result_uses_javascript_stringification() -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "tool_result",
            "messageId": "message",
            "toolUseId": "tool",
            "content": 1e-7,
        }
    )
    stream.feed_notification(_complete())

    result = cast("ToolResult", (await _collect(stream))[0])
    assert result.content == "1e-7"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire_settings", "expected"),
    [
        ({}, SessionSettingsUpdate()),
        ({"modelId": "model"}, SessionSettingsUpdate(model="model")),
        (
            {"reasoningEffort": "high"},
            SessionSettingsUpdate(reasoning_effort=ReasoningEffort.HIGH),
        ),
        (
            {
                "interactionMode": "spec",
                "autonomyLevel": "low",
                "enabledToolIds": [],
                "tags": [],
                "compactionThresholdCheckEnabled": False,
            },
            SessionSettingsUpdate(
                mode=Mode.SPEC,
                autonomy=Autonomy.LOW,
                enabled_tools=frozenset(),
                tags=(),
                compaction_threshold_check_enabled=False,
            ),
        ),
        (
            {
                "specModeModelId": "spec-model",
                "specModeReasoningEffort": "medium",
                "additionalToolIds": ["one"],
                "disabledToolIds": ["two"],
                "restrictToolIds": ["three"],
            },
            SessionSettingsUpdate(
                spec_model="spec-model",
                spec_reasoning_effort=ReasoningEffort.MEDIUM,
                additional_tools={"one"},
                disabled_tools={"two"},
                restrict_tools={"three"},
            ),
        ),
        (
            {"autonomyMode": "auto-medium"},
            SessionSettingsUpdate(
                mode=Mode.AUTO,
                autonomy=Autonomy.MEDIUM,
            ),
        ),
    ],
)
async def test_partial_settings_updates_are_always_emitted(
    wire_settings: dict[str, object],
    expected: SessionSettingsUpdate,
) -> None:
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        include_partial_messages=True,
    )
    stream.feed_notification({"type": "settings_updated", "settings": wire_settings})
    stream.feed_notification(_complete())

    event = cast("SettingsUpdated", (await _collect(stream))[0])
    assert event.settings == expected


@pytest.mark.asyncio
async def test_complete_messages_blocks_tools_hooks_errors_and_default_filter() -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant-message",
            "blockIndex": 0,
            "textDelta": "not persisted",
        }
    )
    stream.feed_notification(
        {
            "type": "create_message",
            "message": _message(
                content=[
                    {"type": "text", "id": "text", "text": "one"},
                    {
                        "type": "thinking",
                        "id": "thinking",
                        "thinking": "private",
                        "signature": "signature",
                        "durationMs": 5,
                    },
                    {
                        "type": "redacted_thinking",
                        "id": "redacted",
                        "data": "opaque",
                    },
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Read",
                        "input": {"path": "/repo/a.py"},
                    },
                    {
                        "type": "tool_result",
                        "id": "result",
                        "toolUseId": "tool-0",
                        "content": [{"type": "text", "text": "nested"}],
                        "isError": False,
                    },
                    {
                        "type": "document",
                        "id": "document",
                        "source": {
                            "type": "text",
                            "mediaType": "text/plain",
                            "data": "source",
                            "name": "a.py",
                        },
                    },
                    {"type": "text", "id": "text-2", "text": "two"},
                ]
            ),
        }
    )
    stream.feed_notification(
        {
            "type": "tool_result",
            "messageId": "tool-message",
            "toolUseId": "tool-1",
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
        }
    )
    stream.feed_notification(
        {
            "type": "hook_execution_started",
            "hookId": "hook",
            "hookEventName": "PreToolUse",
            "hookCommands": [{"command": "check", "timeout": 2}],
        }
    )
    stream.feed_notification(
        {
            "type": "hook_execution_completed",
            "hookId": "hook",
            "hookStatus": "completed",
            "hookResults": [
                {
                    "command": "check",
                    "timeout": 2,
                    "exitCode": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "suppressOutput": True,
                }
            ],
        }
    )
    stream.feed_notification(
        {
            "type": "error",
            "message": "recoverable",
            "errorType": "Error",
            "timestamp": "2025-01-01T00:00:00Z",
        }
    )
    stream.feed_notification(_complete())

    events = await _collect(stream)
    assert [type(event) for event in events] == [
        ToolCall,
        AssistantMessage,
        ToolResult,
        HookExecution,
        HookExecution,
        ErrorEvent,
        RunSuccess,
    ]
    tool_result = cast("ToolResult", events[2])
    assert tool_result.tool_name == "Read"
    assistant = cast("AssistantMessage", events[1])
    assert assistant.text == "onetwo"
    assert assistant.created_at.tzinfo is not None
    assert cast("HookExecution", events[3]).timeout == timedelta(seconds=2)
    assert cast("HookExecution", events[4]).suppress_output is True
    assert cast("ErrorEvent", events[5]).timestamp == datetime(
        2025,
        1,
        1,
        tzinfo=timezone.utc,
    )
    assert stream.result.messages == tuple(events[:-1])
    assert stream.result.text == "onetwo"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "error"])
@pytest.mark.parametrize("hook_results", [None, []])
async def test_hook_completion_without_results_emits_no_phantom_event(
    status: str,
    hook_results: object,
) -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "hook_execution_started",
            "hookId": "hook",
            "hookEventName": "PreToolUse",
            "hookMatcher": "Read",
            "hookToolCallId": "tool",
            "hookCommands": [{"command": "check"}],
        }
    )
    stream.feed_notification(
        {
            "type": "hook_execution_completed",
            "hookId": "hook",
            "hookEventName": "PreToolUse",
            "hookMatcher": "Read",
            "hookToolCallId": "tool",
            "hookStatus": status,
            "hookResults": hook_results,
        }
    )
    stream.feed_notification(_complete())

    events = await _collect(stream)
    hooks = [event for event in events if isinstance(event, HookExecution)]
    assert [hook.status for hook in hooks] == ["started"]


@pytest.mark.asyncio
async def test_user_message_and_foreign_idle_and_missing_turn_ids() -> None:
    stream = RunStream[None](
        expected_turn_id="turn",
        session_id="session",
        include_partial_messages=True,
    )
    stream.feed_notification({"type": "create_message", "message": _message("user")})
    stream.feed_notification(
        {"type": "droid_working_state_changed", "newState": "idle"}
    )
    stream.feed_notification(_complete(turn_id="foreign"))
    with pytest.raises(StreamIncompleteError):
        _ = stream.result
    stream.feed_notification(_complete())
    events = await _collect(stream)
    assert isinstance(events[0], UserMessage)
    assert isinstance(events[1], WorkingStateChanged)
    assert isinstance(events[-1], RunSuccess)

    malformed = RunStream[None](expected_turn_id="turn", session_id="session")
    malformed.feed_notification(_complete(turn_id=None))
    with pytest.raises(DroidProtocolError, match="expected turn ID"):
        await _collect(malformed)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "notification",
    [
        {"type": "agent_turn_completed", "reason": "completed", "turnId": "turn"},
        {
            "type": "assistant_text_delta",
            "messageId": "message",
            "blockIndex": 0,
        },
        {
            "type": "tool_progress_update",
            "toolUseId": "tool",
            "toolName": "Read",
            "update": {"status": "running"},
        },
        {"type": "create_message"},
    ],
)
async def test_malformed_known_notifications_terminate_stream(
    notification: dict[str, object],
) -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(notification)

    with pytest.raises(DroidProtocolError, match=r"Invalid .* notification payload"):
        await _collect(stream)


@pytest.mark.asyncio
async def test_malformed_known_wrapped_notification_terminates_stream() -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "jsonrpc": "2.0",
            "method": "droid.session_notification",
            "params": {
                "notification": {
                    "type": "assistant_text_complete",
                    "messageId": "message",
                }
            },
        }
    )

    with pytest.raises(DroidProtocolError, match="assistant_text_complete"):
        await _collect(stream)


@pytest.mark.asyncio
async def test_unknown_notification_type_remains_ignored() -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification({"type": "future_notification", "value": "ignored"})
    stream.feed_notification(_complete())

    events = await _collect(stream)
    assert events == [stream.result]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "result_type", "subtype"),
    [
        ("completed", RunSuccess, "success"),
        ("spec_handoff", RunSuccess, "success"),
        ("cancelled", RunInterrupted, "interrupted"),
        ("permission_rejected", RunInterrupted, "interrupted"),
        ("error", RunFailure, "error_during_execution"),
        ("structured_output_missing", RunFailure, "error_structured_output"),
        ("structured_output_invalid", RunFailure, "error_structured_output"),
        ("structured_output_schema_invalid", RunFailure, "error_structured_output"),
    ],
)
async def test_every_terminal_result_family(
    reason: str,
    result_type: type[object],
    subtype: str,
) -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    stream.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant-message",
            "blockIndex": 0,
            "textDelta": "partial",
        }
    )
    stream.feed_notification(_complete(reason))
    await _collect(stream)
    assert isinstance(stream.result, result_type)
    assert stream.result.subtype == subtype
    assert stream.result.text == "partial"
    assert stream.result.usage is not None
    assert stream.result.usage.factory_credits == 0.25
    assert stream.result.duration == timedelta(milliseconds=125)
    if isinstance(stream.result, RunFailure):
        assert stream.result.error is not None
        assert (stream.result.structured_output_error is not None) is (
            subtype == "error_structured_output"
        )


class Review(BaseModel):
    summary: str
    count: int


class NumericOutput(BaseModel):
    value: float


@pytest.mark.asyncio
async def test_structured_output_raw_adapted_fallback_and_validation_error() -> None:
    valid = RunStream[Review](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=prepare_output_adapter(Review),
    )
    valid.feed_notification(
        {
            "type": "structured_output",
            "messageId": "assistant",
            "structuredOutput": {"summary": "ok", "count": 2},
        }
    )
    valid.feed_notification(_complete())
    await _collect(valid)
    assert valid.result.output == Review(summary="ok", count=2)
    assert valid.result.structured_output == {"summary": "ok", "count": 2}

    invalid = RunStream[Review](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=prepare_output_adapter(Review),
    )
    invalid.feed_notification(
        {
            "type": "structured_output",
            "messageId": "assistant",
            "structuredOutput": {"summary": "partial", "count": "bad"},
        }
    )
    invalid.feed_notification(_complete())
    await _collect(invalid)
    assert isinstance(invalid.result, RunFailure)
    assert invalid.result.subtype == "error_structured_output"
    assert invalid.result.structured_output_error is not None
    assert invalid.result.structured_output_error.code == "local_validation_failed"
    assert invalid.result.output is None
    assert invalid.result.output_validation_error is not None
    assert invalid.result.structured_output == {
        "summary": "partial",
        "count": "bad",
    }

    raw = RunStream[Mapping[str, object]](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=cast(
            "Any",
            prepare_output_adapter(JsonSchema({"type": "object"})),
        ),
    )
    raw.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant",
            "blockIndex": 0,
            "textDelta": '{"summary":"fallback"}',
        }
    )
    raw.feed_notification(_complete())
    await _collect(raw)
    assert raw.result.output == {"summary": "fallback"}


@pytest.mark.asyncio
async def test_requested_output_that_never_arrives_is_a_failure() -> None:
    missing = RunStream[Mapping[str, object]](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=cast(
            "Any",
            prepare_output_adapter(JsonSchema({"type": "object"})),
        ),
    )
    missing.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant",
            "blockIndex": 0,
            "textDelta": "no structured output here",
        }
    )
    missing.feed_notification(_complete())
    await _collect(missing)
    assert isinstance(missing.result, RunFailure)
    assert missing.result.subtype == "error_structured_output"
    assert missing.result.structured_output_error is not None
    assert missing.result.structured_output_error.code == "local_output_missing"
    assert missing.result.output is None
    assert missing.result.output_validation_error is None
    assert missing.result.text == "no structured output here"

    # Sessions always pass an adapter object; with output=None it carries no
    # wire format and must not trigger the output guarantee.
    for adapter in (None, prepare_output_adapter()):
        plain = RunStream[None](
            expected_turn_id="turn",
            session_id="session",
            output_adapter=adapter,
        )
        plain.feed_notification(
            {
                "type": "assistant_text_delta",
                "messageId": "assistant",
                "blockIndex": 0,
                "textDelta": "no output requested",
            }
        )
        plain.feed_notification(_complete())
        await _collect(plain)
        assert isinstance(plain.result, RunSuccess)
        assert plain.result.output is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_json",
    [
        '{"summary":"invalid","count":NaN}',
        '{"summary":"invalid","count":Infinity}',
        '{"summary":"invalid","count":-Infinity}',
        '{"summary":"invalid","count":1e10000}',
        '{"summary":"invalid","count":-1e10000}',
        ('{"summary":"valid","count":1,"nested":{"items":[{"value":1e10000}]}}'),
        ('{"summary":"valid","count":1,"nested":{"items":[{"value":-1e10000}]}}'),
    ],
)
async def test_non_finite_structured_output_fallback_always_terminalizes(
    raw_json: str,
) -> None:
    stream = RunStream[Review](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=prepare_output_adapter(Review),
    )
    stream.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant",
            "blockIndex": 0,
            "textDelta": raw_json,
        }
    )
    stream.feed_notification(_complete())

    events = await _collect(stream)
    assert events[-1] is stream.result
    assert isinstance(stream.result, RunFailure)
    assert stream.result.subtype == "error_structured_output"
    assert stream.result.output is None
    assert stream.result.structured_output is None
    assert stream.result.output_validation_error is not None


@pytest.mark.asyncio
async def test_large_finite_structured_output_is_retained_and_adapted() -> None:
    stream = RunStream[NumericOutput](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=prepare_output_adapter(NumericOutput),
    )
    stream.feed_notification(
        {
            "type": "assistant_text_delta",
            "messageId": "assistant",
            "blockIndex": 0,
            "textDelta": '{"value":1e300}',
        }
    )
    stream.feed_notification(_complete())

    await _collect(stream)
    assert stream.result.output == NumericOutput(value=1e300)
    assert stream.result.structured_output == {"value": 1e300}
    assert stream.result.output_validation_error is None


@pytest.mark.asyncio
async def test_non_finite_structured_output_notification_is_not_retained() -> None:
    stream = RunStream[Review](
        expected_turn_id="turn",
        session_id="session",
        output_adapter=prepare_output_adapter(Review),
    )
    stream.feed_notification(
        {
            "type": "structured_output",
            "messageId": "assistant",
            "structuredOutput": {"summary": "invalid", "count": float("nan")},
        }
    )
    stream.feed_notification(_complete())

    await _collect(stream)
    assert stream.result.output is None
    assert stream.result.structured_output is None
    assert stream.result.output_validation_error is not None


@pytest.mark.asyncio
async def test_result_cache_error_propagation_and_single_consumer() -> None:
    stream = RunStream[None](expected_turn_id="turn", session_id="session")
    with pytest.raises(StreamIncompleteError):
        _ = stream.result
    stream.feed_notification(_complete())
    first = await _collect(stream)
    assert first[-1] is stream.result
    assert stream.result is stream.result
    with pytest.raises(RuntimeError, match="one consumer"):
        await _collect(stream)

    failed = RunStream[None](expected_turn_id="turn", session_id="session")
    failed.feed_error(DroidProtocolError("transport failed"))
    with pytest.raises(DroidProtocolError, match="transport failed"):
        await _collect(failed)


def _permission_params(
    *,
    detail: dict[str, Any] | None = None,
    option: str = "proceed_once",
) -> dict[str, object]:
    return {
        "toolUses": [
            {
                "toolUse": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Create",
                    "input": {"secret": "prompt payload"},
                },
                "confirmationType": (detail or {}).get("type", "create"),
                "details": detail
                or {
                    "type": "create",
                    "filePath": "/repo/a.py",
                    "fileName": "a.py",
                    "content": "credential payload",
                },
            }
        ],
        "options": [{"label": "Proceed", "value": option}],
        "associatedSessionIds": ["child"],
    }


def _question_params() -> dict[str, object]:
    return {
        "toolCallId": "tool-1",
        "questions": [
            {
                "index": 1,
                "topic": "Choice",
                "question": "Pick one",
                "options": ["a", "b"],
                "multiSelect": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_interaction_sync_async_helpers_wire_fields_and_outcomes() -> None:
    errors: list[ErrorEvent] = []

    def permission(request: PermissionRequest) -> object:
        assert request.associated_session_ids == ("child",)
        return request.respond(
            ToolConfirmationOutcome.PROCEED_ONCE,
            comment="approved",
        )

    async def question(request: QuestionRequest) -> object:
        question_value = request.questions[0]
        return request.submit([question_value.answer_multiple(["a", "b"])])

    dispatcher = InteractionDispatcher(
        cast(
            "Any",
            InteractionHandlers(
                on_permission=permission,
                on_question=question,
            ),
        ),
        error_sink=errors.append,
    )
    assert await dispatcher.handle_permission(_permission_params()) == {
        "selectedOption": "proceed_once",
        "comment": "approved",
    }
    assert await dispatcher.handle_question(_question_params()) == {
        "cancelled": False,
        "answers": [{"index": 1, "question": "Pick one", "answer": "a, b"}],
    }
    assert errors == []


@pytest.mark.parametrize(
    ("detail", "expected_type"),
    [
        (
            {
                "type": "edit",
                "filePath": "/repo/a.py",
                "fileName": "a.py",
                "oldContent": "old",
                "newContent": "new",
            },
            "EditAction",
        ),
        (
            {
                "type": "exec",
                "fullCommand": "git status",
                "command": "git",
                "extractedCommands": ["git", "status"],
                "impactLevel": "low",
                "riskLevelReason": "read-only",
            },
            "ExecuteAction",
        ),
        (
            {
                "type": "create",
                "filePath": "/repo/a.py",
                "fileName": "a.py",
                "content": "content",
            },
            "CreateFile",
        ),
        (
            {
                "type": "ask_user",
                "questionnaire": "questions",
                "parsed": {"questions": _question_params()["questions"]},
            },
            "AskUserAction",
        ),
        (
            {"type": "exit_spec_mode", "plan": "plan", "title": "title"},
            "ExitSpecModeAction",
        ),
        (
            {
                "type": "apply_patch",
                "filePath": "/repo/a.py",
                "fileName": "a.py",
                "patchContent": "patch",
                "files": [
                    {
                        "filePath": "/repo/a.py",
                        "fileName": "a.py",
                        "operation": "update",
                        "moveTo": "/repo/b.py",
                    }
                ],
            },
            "ApplyPatchAction",
        ),
        (
            {
                "type": "mcp_tool",
                "toolName": "search",
                "impactLevel": "medium",
                "serverName": "server",
                "actualToolName": "actual",
            },
            "McpToolAction",
        ),
        (
            {
                "type": "sandbox_violation",
                "violatingToolName": "Execute",
                "target": "/outside",
                "operationType": "write",
                "violationType": "filesystem-write",
                "reason": "outside sandbox",
                "violationReason": "not-allowed",
                "isOrgDeny": True,
            },
            "SandboxViolationAction",
        ),
        (
            {
                "type": "droid_shield_violation",
                "command": "unsafe",
                "reason": "blocked",
            },
            "DroidShieldViolationAction",
        ),
    ],
)
def test_every_permission_action_is_converted(
    detail: dict[str, Any],
    expected_type: str,
) -> None:
    captured: list[PermissionRequest] = []

    def handler(request: PermissionRequest) -> object:
        captured.append(request)
        return request.respond(ToolConfirmationOutcome.PROCEED_ONCE)

    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_permission=cast("Any", handler))
    )
    result = asyncio.run(
        dispatcher.handle_permission(_permission_params(detail=detail))
    )
    assert result == {"selectedOption": "proceed_once"}
    assert type(captured[0].actions[0]).__name__ == expected_type


@pytest.mark.asyncio
async def test_every_permission_outcome_and_edited_content_are_preserved() -> None:
    for outcome in ToolConfirmationOutcome:
        edited = (
            "edited plan" if outcome is ToolConfirmationOutcome.PROCEED_EDIT else None
        )

        def handler(
            request: PermissionRequest,
            selected: ToolConfirmationOutcome = outcome,
            content: str | None = edited,
        ) -> object:
            return request.respond(
                selected,
                comment="comment",
                edited_spec_content=content,
            )

        dispatcher = InteractionDispatcher(
            InteractionHandlers(on_permission=cast("Any", handler))
        )
        result = await dispatcher.handle_permission(
            _permission_params(option=outcome.value)
        )
        assert result["selectedOption"] == outcome.value
        assert result["comment"] == "comment"
        if edited is not None:
            assert result["editedSpecContent"] == edited


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [
        None,
        lambda request: object(),
        lambda request: request.respond(ToolConfirmationOutcome.CANCEL),
        lambda request: (_ for _ in ()).throw(
            RuntimeError("prompt payload credential payload /repo/a.py")
        ),
    ],
)
async def test_permission_failures_cancel_and_are_sanitized(handler: object) -> None:
    errors: list[ErrorEvent] = []
    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_permission=cast("Any", handler)),
        error_sink=errors.append,
    )
    result = await dispatcher.handle_permission(_permission_params())
    assert result == {"selectedOption": "cancel"}
    assert len(errors) == 1
    diagnostic = repr(errors[0])
    for secret in ("prompt payload", "credential payload", "/repo/a.py"):
        assert secret not in diagnostic


@pytest.mark.asyncio
async def test_interaction_cancellation_is_never_wrapped() -> None:
    async def cancelled(request: PermissionRequest) -> object:
        raise asyncio.CancelledError

    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_permission=cast("Any", cancelled))
    )
    with pytest.raises(asyncio.CancelledError):
        await dispatcher.handle_permission(_permission_params())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [
        None,
        lambda request: object(),
        lambda request: (_ for _ in ()).throw(RuntimeError("Pick one prompt payload")),
    ],
)
async def test_question_failures_cancel_and_are_sanitized(handler: object) -> None:
    errors: list[ErrorEvent] = []
    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_question=cast("Any", handler)),
        error_sink=errors.append,
    )
    assert await dispatcher.handle_question(_question_params()) == {
        "cancelled": True,
        "answers": [],
    }
    assert len(errors) == 1
    assert "Pick one" not in repr(errors[0])
    assert "prompt payload" not in repr(errors[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["sync", "async", "invalid"])
async def test_throwing_error_sink_cannot_block_permission_cancellation(
    failure_kind: str,
) -> None:
    def sync_failure(request: PermissionRequest) -> object:
        raise RuntimeError("permission failed")

    async def async_failure(request: PermissionRequest) -> object:
        raise RuntimeError("permission failed")

    def invalid_response(request: PermissionRequest) -> object:
        return object()

    handlers = {
        "sync": sync_failure,
        "async": async_failure,
        "invalid": invalid_response,
    }

    def throwing_sink(event: ErrorEvent) -> None:
        raise RuntimeError("sink failed")

    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_permission=cast("Any", handlers[failure_kind])),
        error_sink=throwing_sink,
    )
    assert await dispatcher.handle_permission(_permission_params()) == {
        "selectedOption": "cancel"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["sync", "async", "invalid"])
async def test_throwing_error_sink_cannot_block_question_cancellation(
    failure_kind: str,
) -> None:
    def sync_failure(request: QuestionRequest) -> object:
        raise RuntimeError("question failed")

    async def async_failure(request: QuestionRequest) -> object:
        raise RuntimeError("question failed")

    def invalid_response(request: QuestionRequest) -> object:
        return object()

    handlers = {
        "sync": sync_failure,
        "async": async_failure,
        "invalid": invalid_response,
    }

    def throwing_sink(event: ErrorEvent) -> None:
        raise RuntimeError("sink failed")

    dispatcher = InteractionDispatcher(
        InteractionHandlers(on_question=cast("Any", handlers[failure_kind])),
        error_sink=throwing_sink,
    )
    assert await dispatcher.handle_question(_question_params()) == {
        "cancelled": True,
        "answers": [],
    }


@pytest.mark.asyncio
async def test_dispatcher_registers_through_low_level_handler_slots() -> None:
    client = DroidClient(exec_path="/not-used")
    dispatcher = InteractionDispatcher(
        InteractionHandlers(
            on_permission=lambda request: request.respond(
                ToolConfirmationOutcome.PROCEED_ONCE
            ),
            on_question=lambda request: request.cancel(),
        )
    )
    client.set_permission_handler(dispatcher.handle_permission)
    client.set_ask_user_handler(dispatcher.handle_question)

    assert await client._dispatch_permission_request(_permission_params()) == {
        "selectedOption": "proceed_once"
    }
    assert await client._dispatch_ask_user_request(_question_params()) == {
        "cancelled": True,
        "answers": [],
    }

    client.clear_permission_handler()
    client.clear_ask_user_handler()
    assert client._dispatch_permission_request({}) == "cancel"
    assert client._dispatch_ask_user_request({}) == {
        "cancelled": True,
        "answers": [],
    }
