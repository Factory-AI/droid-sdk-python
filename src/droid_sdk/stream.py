# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

"""Typed stream message dataclasses and notification-to-stream-message converter.

Provides simple ``@dataclass`` wrappers (NOT Pydantic models) that map
``SessionNotification`` payloads into developer-friendly typed objects.  The
:func:`_notification_to_stream_message` function converts a discriminated
notification payload into the corresponding dataclass instance.

Stream type mapping:

==================================  ==========================
SessionNotificationType             Stream Dataclass
==================================  ==========================
ASSISTANT_TEXT_DELTA                 AssistantTextDelta
THINKING_TEXT_DELTA                  ThinkingTextDelta
CREATE_MESSAGE (tool_use blocks)    ToolUse (list)
TOOL_RESULT                         ToolResult
TOOL_PROGRESS_UPDATE                ToolProgress
DROID_WORKING_STATE_CHANGED         WorkingStateChanged
SESSION_TOKEN_USAGE_CHANGED         TokenUsageUpdate
ERROR                               ErrorEvent
(sentinel)                          TurnComplete
==================================  ==========================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from droid_sdk.schemas.cli import (
    AssistantTextDeltaNotification,
    CreateMessageNotification,
    DroidWorkingStateChangedNotification,
    ErrorNotification,
    SessionNotificationUnion,
    SessionTokenUsageChangedNotification,
    ThinkingTextDeltaNotification,
    ToolProgressUpdateNotification,
    ToolResultNotification,
)
from droid_sdk.schemas.enums import DroidWorkingState  # noqa: TC001
from droid_sdk.schemas.messages import ToolUseBlock

__all__ = [
    "AssistantTextDelta",
    "ErrorEvent",
    "StreamMessage",
    "ThinkingTextDelta",
    "TokenUsageUpdate",
    "ToolProgress",
    "ToolResult",
    "ToolUse",
    "TurnComplete",
    "WorkingStateChanged",
    "_notification_to_stream_message",
]


# ---------------------------------------------------------------------------
# Stream message dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssistantTextDelta:
    """A delta of assistant-generated text (streaming token)."""

    text: str


@dataclass(frozen=True, slots=True)
class ThinkingTextDelta:
    """A delta of assistant thinking/reasoning text."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolUse:
    """A tool invocation issued by the assistant."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The result returned from a tool execution.

    ``tool_name`` is ``None`` when the name is unknown. The
    ``tool_result`` notification does not carry the tool name, so
    :meth:`~droid_sdk.client.DroidClient.receive_response` backfills it
    from the matching ``tool_use`` (correlated via ``tool_use_id``) when
    that call was seen earlier in the turn. It stays ``None`` when no
    match is available, which is distinct from a tool that reported an
    empty name. ``tool_use_id`` is optional for compatibility with
    callers that construct stream events directly.
    """

    tool_name: str | None
    content: str | list[Any]
    is_error: bool
    tool_use_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolProgress:
    """A streaming progress update from a tool execution.

    ``tool_use_id`` is optional for compatibility with callers that
    construct stream events directly.
    """

    tool_name: str
    content: str
    tool_use_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkingStateChanged:
    """The droid working state has changed."""

    state: DroidWorkingState


@dataclass(frozen=True, slots=True)
class TokenUsageUpdate:
    """Updated token usage counters for the session."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


@dataclass(frozen=True, slots=True)
class TurnComplete:
    """Sentinel yielded when the agent turn finishes (returns to Idle)."""

    token_usage: TokenUsageUpdate | None = field(default=None)


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """An error event from the droid process.

    ``error_type`` mirrors the top-level ``errorType`` field, which is
    frequently the unhelpful discriminator ``"Error"``. ``error_name``
    exposes the nested ``error.name`` the protocol carries (for example
    ``"LLMInvalidRequestError"``), giving callers a stable value to
    branch on. ``error_detail`` holds the full nested error payload when
    present.
    """

    message: str
    error_type: str
    error_name: str | None = field(default=None)
    error_detail: dict[str, Any] | None = field(default=None)


StreamMessage = (
    AssistantTextDelta
    | ThinkingTextDelta
    | ToolUse
    | ToolResult
    | ToolProgress
    | WorkingStateChanged
    | TokenUsageUpdate
    | TurnComplete
    | ErrorEvent
)
"""Union of all stream message types.

A discriminated union of all possible messages yielded by
:meth:`~droid_sdk.client.DroidClient.receive_response`.
"""


# ---------------------------------------------------------------------------
# Notification → StreamMessage converter
# ---------------------------------------------------------------------------


def _notification_to_stream_message(
    notification: SessionNotificationUnion,
) -> StreamMessage | list[ToolUse] | None:
    """Convert a session notification payload to the corresponding stream message.

    Args:
        notification: A discriminated notification payload from
            ``SessionNotification.params.notification``.

    Returns:
        A stream message dataclass, a list of :class:`ToolUse` for
        ``CREATE_MESSAGE`` notifications containing tool-use content blocks,
        or ``None`` for unmapped notification types.
    """
    if isinstance(notification, AssistantTextDeltaNotification):
        return AssistantTextDelta(text=notification.text_delta)

    if isinstance(notification, ThinkingTextDeltaNotification):
        return ThinkingTextDelta(text=notification.text_delta)

    if isinstance(notification, ToolResultNotification):
        # ToolResultNotification does not carry a tool_name field
        content: str | list[Any]
        if notification.content is None:
            content = ""
        elif isinstance(notification.content, str):
            content = notification.content
        elif isinstance(notification.content, list):
            content = list(notification.content)
        else:
            content = str(notification.content)
        # The tool_result notification carries no tool name; leave it None
        # so receive_response() can backfill it from the matching tool_use.
        return ToolResult(
            tool_name=None,
            tool_use_id=notification.tool_use_id,
            content=content,
            is_error=bool(notification.is_error),
        )

    if isinstance(notification, ToolProgressUpdateNotification):
        update = notification.update
        # Prefer .text, fall back to .status, then .details, then empty
        text = update.text or update.status or update.details or ""
        return ToolProgress(
            tool_name=notification.tool_name,
            tool_use_id=notification.tool_use_id,
            content=text,
        )

    if isinstance(notification, DroidWorkingStateChangedNotification):
        return WorkingStateChanged(state=notification.new_state)

    if isinstance(notification, SessionTokenUsageChangedNotification):
        tu = notification.token_usage
        return TokenUsageUpdate(
            input_tokens=tu.input_tokens,
            output_tokens=tu.output_tokens,
            cache_read_tokens=tu.cache_read_tokens,
            # The Pydantic TokenUsage model uses cache_creation_tokens;
            # map it to the stream dataclass field cache_write_tokens.
            cache_write_tokens=tu.cache_creation_tokens,
        )

    if isinstance(notification, ErrorNotification):
        error_name: str | None = None
        error_detail: dict[str, Any] | None = None
        if notification.error is not None:
            error_name = notification.error.name
            error_detail = notification.error.model_dump(by_alias=True)
        return ErrorEvent(
            message=notification.message,
            error_type=notification.error_type.value,
            error_name=error_name,
            error_detail=error_detail,
        )

    if isinstance(notification, CreateMessageNotification):
        tool_uses: list[ToolUse] = []
        for block in notification.message.content:
            if isinstance(block, ToolUseBlock):
                tool_uses.append(
                    ToolUse(
                        tool_name=block.name,
                        tool_input=dict(block.input),
                        tool_use_id=block.id,
                    )
                )
        if tool_uses:
            return tool_uses
        return None

    # Unmapped notification types
    return None
