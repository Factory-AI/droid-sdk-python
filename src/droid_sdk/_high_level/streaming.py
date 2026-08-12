"""High-level notification conversion and single-consumer stream primitives."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import math
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Generic, NoReturn, cast

from pydantic import BaseModel, TypeAdapter, ValidationError
from typing_extensions import TypeVar

from droid_sdk._high_level._immutable import FrozenJsonObject, freeze_json_object
from droid_sdk._high_level.attachments import (
    Base64ImageSource,
    PdfDocumentSource,
    TextDocumentSource,
)
from droid_sdk._high_level.config import (
    SessionSettingsUpdate,
    SessionTag,
)
from droid_sdk._high_level.enums import (
    Autonomy,
    ErrorType,
    McpAuthOutcome,
    McpServerStatus,
    McpServerType,
    Mode,
    ReasoningEffort,
    ToolConfirmationOutcome,
    WorkingState,
)
from droid_sdk._high_level.extensions import (
    McpConfigError,
    McpServerStatusInfo,
    McpStatusSummary,
)
from droid_sdk._high_level.messages import (
    AssistantMessage,
    ContentBlock,
    DocumentBlock,
    ErrorEvent,
    HookExecution,
    ImageBlock,
    McpAuthCompleted,
    McpAuthRequired,
    McpStatusChanged,
    Message,
    PermissionResolved,
    RedactedThinkingBlock,
    RunFailure,
    RunInterrupted,
    RunResult,
    RunSuccess,
    SessionTitleUpdated,
    SessionWorkingDirectoryChanged,
    SettingsUpdated,
    StreamEvent,
    StructuredOutputError,
    TextBlock,
    TextComplete,
    TextDelta,
    ThinkingBlock,
    ThinkingComplete,
    ThinkingDelta,
    TokenUsageUpdate,
    ToolCall,
    ToolCallDelta,
    ToolProgress,
    ToolProgressUpdate,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
    WorkingStateChanged,
)
from droid_sdk.errors import DroidProtocolError, StreamIncompleteError
from droid_sdk.schemas import messages as wire_messages
from droid_sdk.schemas.cli import (
    AgentTurnCompletedNotification,
    AssistantTextCompleteNotification,
    AssistantTextDeltaNotification,
    CreateMessageNotification,
    DroidWorkingStateChangedNotification,
    ErrorNotification,
    HookExecutionCompletedNotification,
    HookExecutionStartedNotification,
    McpAuthCompletedNotification,
    McpAuthRequiredNotification,
    McpStatusChangedNotification,
    PermissionResolvedNotification,
    SessionNotification,
    SessionNotificationUnion,
    SessionTitleUpdatedNotification,
    SessionTokenUsageChangedNotification,
    SessionWorkingDirectoryChangedNotification,
    SettingsUpdatedNotification,
    StructuredOutputNotification,
    ThinkingTextCompleteNotification,
    ThinkingTextDeltaNotification,
    ToolCallNotification,
    ToolProgressUpdateNotification,
    ToolResultNotification,
)
from droid_sdk.schemas.enums import AgentTurnCompletionReason, SessionNotificationType

if TYPE_CHECKING:
    from droid_sdk._high_level.output import OutputAdapter

T = TypeVar("T")
E = TypeVar("E", bound=object, default=object)
_NOTIFICATION_ADAPTER: TypeAdapter[SessionNotificationUnion] = TypeAdapter(
    SessionNotificationUnion
)
_RESULT_TYPES = (RunSuccess, RunInterrupted, RunFailure)
_KNOWN_NOTIFICATION_TYPES = frozenset(item.value for item in SessionNotificationType)


def _utc_from_timestamp(value: float) -> datetime:
    """Convert the protocol's epoch-millisecond timestamps to aware UTC."""
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("protocol timestamp must be timezone-aware")
    return parsed


def _duration(milliseconds: float | None) -> timedelta | None:
    return None if milliseconds is None else timedelta(milliseconds=milliseconds)


def _image_source(source: wire_messages.Base64ImageSource) -> Base64ImageSource:
    return Base64ImageSource(data=source.data, media_type=source.media_type)


def _document_source(
    source: wire_messages.DocumentSource,
) -> TextDocumentSource | PdfDocumentSource:
    if isinstance(source, wire_messages.PlainTextSource):
        return TextDocumentSource(
            data=source.data,
            name=source.name,
            mime=source.mime,
        )
    return PdfDocumentSource(
        data=source.data,
        parsed_data=source.parsed_data,
        name=source.name,
        path=source.path,
    )


def _content_block(block: wire_messages.ContentBlock) -> ContentBlock:
    if isinstance(block, wire_messages.TextBlock):
        return TextBlock(id=block.id, text=block.text)
    if isinstance(block, wire_messages.ThinkingBlock):
        return ThinkingBlock(
            id=block.id,
            thinking=block.thinking,
            signature=block.signature,
            signature_provider=block.signature_provider,
            duration=_duration(block.duration_ms),
        )
    if isinstance(block, wire_messages.RedactedThinkingBlock):
        return RedactedThinkingBlock(id=block.id, data=block.data)
    if isinstance(block, wire_messages.ToolUseBlock):
        return ToolUseBlock(
            id=block.id,
            name=block.name,
            input=block.input,
            thought_signature=block.thought_signature,
        )
    if isinstance(block, wire_messages.ToolResultBlock):
        content: str | Sequence[object] | None
        if isinstance(block.content, list):
            content = [_content_block(item) for item in block.content]
        else:
            content = block.content
        return ToolResultBlock(
            id=block.id,
            tool_use_id=block.tool_use_id,
            content=cast("Any", content),
            is_error=block.is_error,
        )
    if isinstance(block, wire_messages.ImageBlock):
        return ImageBlock(
            id=block.id,
            source=_image_source(block.source),
            generated=block.generated,
        )
    return DocumentBlock(id=block.id, source=_document_source(block.source))


def _conversation_message(
    message: wire_messages.FactoryDroidMessage,
) -> UserMessage | AssistantMessage | None:
    content = tuple(_content_block(block) for block in message.content)
    text = "".join(block.text for block in content if isinstance(block, TextBlock))
    created_at = _utc_from_timestamp(message.created_at)
    updated_at = _utc_from_timestamp(message.updated_at)
    if message.role is wire_messages.MessageRole.User:
        return UserMessage(
            id=message.id,
            content=content,
            text=text,
            parent_id=message.parent_id,
            created_at=created_at,
            updated_at=updated_at,
        )
    if message.role is wire_messages.MessageRole.Assistant:
        return AssistantMessage(
            id=message.id,
            content=content,
            text=text,
            parent_id=message.parent_id,
            created_at=created_at,
            updated_at=updated_at,
        )
    return None


def _usage(value: Any) -> Usage:
    return Usage(
        input_tokens=value.input_tokens,
        output_tokens=value.output_tokens,
        cache_creation_tokens=value.cache_creation_tokens,
        cache_read_tokens=value.cache_read_tokens,
        thinking_tokens=value.thinking_tokens,
        factory_credits=value.factory_credits,
    )


def _tool_progress_update(value: Any) -> ToolProgressUpdate:
    timestamp = (
        None if value.timestamp is None else _utc_from_timestamp(value.timestamp)
    )
    return ToolProgressUpdate(
        type=value.type,
        tool_name=value.tool_name,
        status=value.status,
        details=value.details,
        text=value.text,
        error=value.error,
        timestamp=timestamp,
        parameters=value.parameters,
        value_snippet=value.value_snippet,
        terminal_id=value.terminal_id,
        full_output=value.full_output,
        subagent_session_id=value.subagent_session_id,
    )


def _tool_progress_content(update: ToolProgressUpdate) -> str:
    if update.text is not None:
        return update.text
    if update.status is not None:
        return update.status
    return update.details or ""


def _settings(value: Any) -> SessionSettingsUpdate:
    mode = None
    if value.interaction_mode is not None and value.interaction_mode.value in {
        "auto",
        "spec",
    }:
        mode = Mode(value.interaction_mode.value)
    elif value.autonomy_mode is not None:
        mode = Mode.SPEC if value.autonomy_mode.value == "spec" else Mode.AUTO
    autonomy = (
        None if value.autonomy_level is None else Autonomy(value.autonomy_level.value)
    )
    if autonomy is None and value.autonomy_mode is not None:
        autonomy = {
            "normal": Autonomy.OFF,
            "auto-low": Autonomy.LOW,
            "auto-medium": Autonomy.MEDIUM,
            "auto-high": Autonomy.HIGH,
        }.get(value.autonomy_mode.value)
    return SessionSettingsUpdate(
        model=value.model_id,
        reasoning_effort=(
            None
            if value.reasoning_effort is None
            else ReasoningEffort(value.reasoning_effort.value)
        ),
        mode=mode,
        autonomy=autonomy,
        spec_model=value.spec_mode_model_id,
        spec_reasoning_effort=(
            None
            if value.spec_mode_reasoning_effort is None
            else ReasoningEffort(value.spec_mode_reasoning_effort.value)
        ),
        tags=(
            None
            if value.tags is None
            else tuple(
                SessionTag(name=tag.name, metadata=tag.metadata) for tag in value.tags
            )
        ),
        additional_tools=(
            None
            if value.additional_tool_ids is None
            else set(value.additional_tool_ids)
        ),
        enabled_tools=(
            None if value.enabled_tool_ids is None else set(value.enabled_tool_ids)
        ),
        disabled_tools=(
            None if value.disabled_tool_ids is None else set(value.disabled_tool_ids)
        ),
        restrict_tools=(
            None if value.restrict_tool_ids is None else set(value.restrict_tool_ids)
        ),
        compaction_threshold_check_enabled=value.compaction_threshold_check_enabled,
    )


def _mcp_status(notification: McpStatusChangedNotification) -> McpStatusChanged:
    servers = tuple(
        McpServerStatusInfo(
            name=server.name,
            status=McpServerStatus(server.status.value),
            source=server.source.value,
            is_managed=server.is_managed,
            server_type=McpServerType(server.server_type.value),
            error=server.error,
            tool_count=server.tool_count,
            has_auth_tokens=server.has_auth_tokens,
            requires_auth=server.requires_auth,
            pending_auth_url=server.pending_auth_url,
            pending_auth_message=server.pending_auth_message,
            pending_auth_state=server.pending_auth_state,
        )
        for server in notification.servers
    )
    summary = notification.summary
    return McpStatusChanged(
        servers=servers,
        summary=McpStatusSummary(
            total=summary.total,
            connected=summary.connected,
            connecting=summary.connecting,
            failed=summary.failed,
            disabled=summary.disabled,
            config_error=(
                None
                if summary.config_error is None
                else McpConfigError(
                    path=summary.config_error.path,
                    message=summary.config_error.message,
                )
            ),
        ),
    )


def _json_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return value


def _json_values(values: list[Any]) -> list[object]:
    return [_json_value(value) for value in values]


def _javascript_number_string(value: int | float) -> str:
    """Return the ECMAScript ``Number::toString`` spelling for finite JSON numbers."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("tool result number must be finite")
    if number == 0:
        return "0"

    magnitude = abs(number)
    text = repr(number).lower()
    if "e" in text:
        coefficient, exponent_text = text.split("e", 1)
        exponent = int(exponent_text)
        coefficient = coefficient.rstrip("0").rstrip(".")
        if 1e-6 <= magnitude < 1e21:
            return format(Decimal(text), "f")
        sign = "+" if exponent >= 0 else ""
        return f"{coefficient}e{sign}{exponent}"
    if text.endswith(".0"):
        return text[:-2]
    return text


def _javascript_string(value: object) -> str:
    """Match JavaScript ``String(value)`` for non-array JSON tool results."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _javascript_number_string(value)
    if isinstance(value, Mapping):
        return "[object Object]"
    return str(value)


def _notification_type(raw: object) -> str | None:
    if not isinstance(raw, Mapping):
        return None
    payload = cast("Mapping[str, object]", raw)
    params = payload.get("params")
    if isinstance(params, Mapping):
        params_mapping = cast("Mapping[str, object]", params)
        notification = params_mapping.get("notification")
        if isinstance(notification, Mapping):
            payload = cast("Mapping[str, object]", notification)
    value = payload.get("type")
    return value if isinstance(value, str) else None


def _raise_for_invalid_known_notification(raw: object) -> None:
    notification_type = _notification_type(raw)
    if notification_type in _KNOWN_NOTIFICATION_TYPES:
        raise DroidProtocolError(
            f"Invalid {notification_type} notification payload"
        ) from None


def _inner_notification(raw: object) -> SessionNotificationUnion | None:
    raw_object: object = raw
    if isinstance(raw, SessionNotification):
        return raw.params.notification
    if isinstance(raw, Mapping):
        mapping = cast("Mapping[str, object]", raw)
        params = mapping.get("params")
        if isinstance(params, Mapping) and "notification" in params:
            try:
                return SessionNotification.model_validate(
                    raw_object
                ).params.notification
            except ValidationError:
                _raise_for_invalid_known_notification(raw_object)
                return None
    try:
        return _NOTIFICATION_ADAPTER.validate_python(raw_object)
    except ValidationError:
        _raise_for_invalid_known_notification(raw_object)
        return None


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON constant: {value}")


def _parse_structured_output(text: str) -> FrozenJsonObject | None:
    try:
        parsed = cast(
            "object",
            json.loads(text, parse_constant=_reject_json_constant),
        )
        if not isinstance(parsed, Mapping):
            return None
        return freeze_json_object(
            cast("Mapping[str, object]", parsed),
            where="structured output",
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


class StreamStateTracker(Generic[T]):
    """Convert canonical notifications and retain one turn's result state."""

    def __init__(
        self,
        *,
        expected_turn_id: str,
        session_id: str,
        output_adapter: OutputAdapter[T] | None = None,
        started_at: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.expected_turn_id = expected_turn_id
        self.session_id = session_id
        self.output_adapter = output_adapter
        self._monotonic = monotonic
        self._started_at = monotonic() if started_at is None else started_at
        self._now = now
        self._messages: list[Message] = []
        self._errors: list[ErrorEvent] = []
        self._tool_names: dict[str, str] = {}
        self._delta_text: list[str] = []
        self._final_assistant_text = ""
        self._structured_output: FrozenJsonObject | None = None
        self._last_usage: Usage | None = None
        self._completed = False

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def queue_error_event(self, event: ErrorEvent) -> ErrorEvent:
        self._errors.append(event)
        self._messages.append(event)
        return event

    def process(self, raw: object) -> tuple[StreamEvent[T], ...]:
        if self._completed:
            return ()
        notification = _inner_notification(raw)
        if notification is None:
            return ()

        if isinstance(notification, AgentTurnCompletedNotification):
            if notification.turn_id is None:
                raise DroidProtocolError(
                    "Agent turn completion did not include the expected turn ID"
                )
            if notification.turn_id != self.expected_turn_id:
                return ()
            result = self._complete(notification)
            self._completed = True
            return cast("tuple[StreamEvent[T], ...]", (result,))

        converted = self._convert(notification)
        for event in converted:
            self._track(event)
        return tuple(converted)

    def _track(self, event: StreamEvent[T]) -> None:
        if isinstance(event, ToolCall):
            self._tool_names[event.tool_use_id] = event.name
        elif isinstance(event, ToolCallDelta):
            self._tool_names[event.tool_use.id] = event.tool_use.name
        elif isinstance(event, TextDelta):
            self._delta_text.append(event.text)
        elif isinstance(event, AssistantMessage):
            self._final_assistant_text = event.text
        elif isinstance(event, TokenUsageUpdate):
            self._last_usage = Usage(
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cache_creation_tokens=event.cache_creation_tokens,
                cache_read_tokens=event.cache_read_tokens,
                thinking_tokens=event.thinking_tokens,
                factory_credits=event.factory_credits,
            )
        if isinstance(event, ErrorEvent):
            self._errors.append(event)
        if isinstance(
            event,
            (
                UserMessage,
                AssistantMessage,
                ToolCall,
                ToolResult,
                HookExecution,
                ErrorEvent,
            ),
        ):
            self._messages.append(event)

    def _convert(
        self,
        notification: SessionNotificationUnion,
    ) -> list[StreamEvent[T]]:
        if isinstance(notification, AssistantTextDeltaNotification):
            return [
                TextDelta(
                    message_id=notification.message_id,
                    block_index=notification.block_index,
                    text=notification.text_delta,
                )
            ]
        if isinstance(notification, AssistantTextCompleteNotification):
            return [
                TextComplete(
                    message_id=notification.message_id,
                    block_index=notification.block_index,
                )
            ]
        if isinstance(notification, ThinkingTextDeltaNotification):
            return [
                ThinkingDelta(
                    message_id=notification.message_id,
                    block_index=notification.block_index,
                    text=notification.text_delta,
                )
            ]
        if isinstance(notification, ThinkingTextCompleteNotification):
            return [
                ThinkingComplete(
                    message_id=notification.message_id,
                    block_index=notification.block_index,
                    duration=_duration(notification.duration_ms),
                )
            ]
        if isinstance(notification, ToolCallNotification):
            tool_use = notification.tool_use
            return [
                ToolCallDelta(
                    tool_use=ToolUseBlock(
                        id=tool_use.id,
                        name=tool_use.name,
                        input=tool_use.input,
                        thought_signature=tool_use.thought_signature,
                    )
                )
            ]
        if isinstance(notification, ToolResultNotification):
            raw_content = notification.content
            if raw_content is None:
                content: str | Sequence[Any] = ""
            elif isinstance(raw_content, str):
                content = raw_content
            elif isinstance(raw_content, list):
                items = cast("list[Any]", raw_content)  # type: ignore[redundant-cast]
                content = _json_values(items)
            else:
                content = _javascript_string(raw_content)
            return [
                ToolResult(
                    tool_use_id=notification.tool_use_id,
                    tool_name=self._tool_names.get(notification.tool_use_id, ""),
                    content=cast("Any", content),
                    is_error=bool(notification.is_error),
                )
            ]
        if isinstance(notification, ToolProgressUpdateNotification):
            update = _tool_progress_update(notification.update)
            return [
                ToolProgress(
                    tool_use_id=notification.tool_use_id,
                    tool_name=notification.tool_name,
                    content=_tool_progress_content(update),
                    update=update,
                )
            ]
        if isinstance(notification, DroidWorkingStateChangedNotification):
            return [
                WorkingStateChanged(state=WorkingState(notification.new_state.value))
            ]
        if isinstance(notification, SessionTokenUsageChangedNotification):
            usage = _usage(notification.token_usage)
            return [
                TokenUsageUpdate(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_tokens=usage.cache_creation_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    thinking_tokens=usage.thinking_tokens,
                    factory_credits=usage.factory_credits,
                )
            ]
        if isinstance(notification, CreateMessageNotification):
            result: list[StreamEvent[T]] = []
            for block in notification.message.content:
                if isinstance(block, wire_messages.ToolUseBlock):
                    result.append(
                        ToolCall(
                            name=block.name,
                            tool_use_id=block.id,
                            input=block.input,
                        )
                    )
            message = _conversation_message(notification.message)
            if message is not None:
                result.append(message)
            return result
        if isinstance(notification, ErrorNotification):
            return [
                ErrorEvent(
                    message=notification.message,
                    error_type=ErrorType(notification.error_type.value),
                    timestamp=_parse_timestamp(notification.timestamp),
                )
            ]
        if isinstance(notification, PermissionResolvedNotification):
            return [
                PermissionResolved(
                    request_id=notification.request_id,
                    tool_use_ids=notification.tool_use_ids,
                    selected_option=ToolConfirmationOutcome(
                        notification.selected_option.value
                    ),
                )
            ]
        if isinstance(notification, SettingsUpdatedNotification):
            return [SettingsUpdated(settings=_settings(notification.settings))]
        if isinstance(notification, SessionTitleUpdatedNotification):
            return [SessionTitleUpdated(title=notification.title)]
        if isinstance(notification, SessionWorkingDirectoryChangedNotification):
            return [SessionWorkingDirectoryChanged(cwd=notification.cwd)]
        if isinstance(notification, McpStatusChangedNotification):
            return [_mcp_status(notification)]
        if isinstance(notification, McpAuthRequiredNotification):
            return [
                McpAuthRequired(
                    server_name=notification.server_name,
                    auth_url=notification.auth_url,
                    message=notification.message,
                    state=notification.state,
                )
            ]
        if isinstance(notification, McpAuthCompletedNotification):
            return [
                McpAuthCompleted(
                    server_name=notification.server_name,
                    outcome=McpAuthOutcome(notification.outcome.value),
                    message=notification.message,
                )
            ]
        if isinstance(notification, HookExecutionStartedNotification):
            return [
                HookExecution(
                    hook_id=notification.hook_id,
                    event_name=notification.hook_event_name,
                    matcher=notification.hook_matcher,
                    tool_call_id=notification.hook_tool_call_id,
                    command=command.command,
                    timeout=(
                        None
                        if command.timeout is None
                        else timedelta(seconds=command.timeout)
                    ),
                    status="started",
                )
                for command in notification.hook_commands
            ]
        if isinstance(notification, HookExecutionCompletedNotification):
            if not notification.hook_results:
                return []
            return [
                HookExecution(
                    hook_id=notification.hook_id,
                    event_name=notification.hook_event_name,
                    matcher=notification.hook_matcher,
                    tool_call_id=notification.hook_tool_call_id,
                    command=result.command,
                    timeout=(
                        None
                        if result.timeout is None
                        else timedelta(seconds=result.timeout)
                    ),
                    status=notification.hook_status,
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    suppress_output=result.suppress_output,
                )
                for result in (notification.hook_results or ())
            ]
        if isinstance(notification, StructuredOutputNotification):
            try:
                self._structured_output = (
                    None
                    if notification.structured_output is None
                    else freeze_json_object(
                        notification.structured_output,
                        where="structured output",
                    )
                )
            except (TypeError, ValueError):
                self._structured_output = None
        return []

    def _complete(
        self,
        notification: AgentTurnCompletedNotification,
    ) -> RunResult[T]:
        text = self._final_assistant_text or "".join(self._delta_text)
        raw: FrozenJsonObject | None = self._structured_output
        if raw is None and self.output_adapter is not None:
            raw = _parse_structured_output(text)

        output: T | None = None
        validation_error: ValidationError | None = None
        if self.output_adapter is not None:
            try:
                adapted = self.output_adapter.adapt(raw)
            except (TypeError, ValueError):
                pass
            else:
                output = adapted.output
                validation_error = adapted.validation_error
                if adapted.structured_output is not None:
                    raw = adapted.structured_output

        usage = _usage(notification.token_usage) if notification.token_usage else None
        if usage is None:
            usage = self._last_usage
        elapsed = max(0.0, self._monotonic() - self._started_at)
        duration = (
            timedelta(seconds=elapsed)
            if notification.duration_ms is None
            else timedelta(milliseconds=notification.duration_ms)
        )
        reason = notification.reason
        if reason in {
            AgentTurnCompletionReason.Completed,
            AgentTurnCompletionReason.SpecHandoff,
        }:
            return RunSuccess(
                text=text,
                messages=tuple(self._messages),
                usage=usage,
                duration=duration,
                turn_count=1,
                session_id=self.session_id,
                output=output,
                structured_output=raw,
                output_validation_error=validation_error,
            )
        if reason in {
            AgentTurnCompletionReason.Cancelled,
            AgentTurnCompletionReason.PermissionRejected,
        }:
            return RunInterrupted(
                text=text,
                messages=tuple(self._messages),
                usage=usage,
                duration=duration,
                turn_count=1,
                session_id=self.session_id,
                output=output,
                structured_output=raw,
                output_validation_error=validation_error,
            )

        structured = reason in {
            AgentTurnCompletionReason.StructuredOutputMissing,
            AgentTurnCompletionReason.StructuredOutputInvalid,
            AgentTurnCompletionReason.StructuredOutputSchemaInvalid,
        }
        error = (
            self._errors[0]
            if self._errors
            else ErrorEvent(
                message=f"Agent turn ended: {reason.value}",
                error_type=ErrorType.ERROR,
                timestamp=self._now(),
            )
        )
        return RunFailure(
            subtype=(
                "error_structured_output" if structured else "error_during_execution"
            ),
            error=error,
            structured_output_error=(
                None
                if not structured
                else StructuredOutputError(
                    code=reason.value,
                    message=error.message,
                )
            ),
            text=text,
            messages=tuple(self._messages),
            usage=usage,
            duration=duration,
            turn_count=1,
            session_id=self.session_id,
            output=output,
            structured_output=raw,
            output_validation_error=validation_error,
        )


class RunStream(Generic[T, E], AsyncIterator[E]):
    """A queue-backed, deterministic single-consumer turn stream."""

    def __init__(
        self,
        *,
        expected_turn_id: str,
        session_id: str,
        include_partial_messages: bool = False,
        output_adapter: OutputAdapter[T] | None = None,
        started_at: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        start: Callable[[RunStream[T, E]], object] | None = None,
        finish: Callable[[bool], object] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._tracker = StreamStateTracker(
            expected_turn_id=expected_turn_id,
            session_id=session_id,
            output_adapter=output_adapter,
            started_at=started_at,
            monotonic=monotonic,
        )
        self._include_partial = include_partial_messages
        self._queue: deque[StreamEvent[T]] = deque()
        self._wakeup = asyncio.Event()
        self._result: RunResult[T] | None = None
        self._error: BaseException | None = None
        self._done = False
        self._iteration_claimed = False
        self._iterating = False
        self._start_callback = start
        self._finish_callback = finish
        self._monotonic = monotonic
        self._started = False
        self._released = False
        self._timeout = timeout
        self._deadline: float | None = None

    @property
    def result(self) -> RunResult[T]:
        if self._result is None:
            raise StreamIncompleteError("The stream has not completed")
        return self._result

    @property
    def completed(self) -> bool:
        return self._result is not None

    def feed_notification(self, notification: object) -> None:
        if self._done:
            return
        if self._deadline is not None and self._monotonic() >= self._deadline:
            self._wakeup.set()
            return
        try:
            events = self._tracker.process(notification)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.feed_error(exc)
            return
        for event in events:
            if isinstance(event, _RESULT_TYPES):
                self._result = cast("RunResult[T]", event)
                self._queue.append(event)
                self._done = True
            elif self._include_partial or isinstance(
                event,
                (
                    UserMessage,
                    AssistantMessage,
                    ToolCall,
                    ToolResult,
                    HookExecution,
                    ErrorEvent,
                ),
            ):
                self._queue.append(event)
        if events:
            self._wakeup.set()

    def queue_error_event(self, event: ErrorEvent) -> None:
        if self._done:
            return
        self._tracker.queue_error_event(event)
        self._queue.append(event)
        self._wakeup.set()

    def feed_error(self, error: BaseException) -> None:
        if isinstance(error, asyncio.CancelledError):
            raise error
        if self._done:
            return
        self._error = error
        self._done = True
        self._wakeup.set()

    async def __aenter__(self) -> RunStream[T, E]:
        await self._ensure_started()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self._release(interrupt=not self._done)

    def __aiter__(self) -> RunStream[T, E]:
        if self._iteration_claimed:
            raise RuntimeError("RunStream supports exactly one consumer")
        self._iteration_claimed = True
        self._iterating = True
        return self

    async def __anext__(self) -> E:
        if not self._iterating:
            raise RuntimeError("RunStream must be iterated with 'async for'")
        try:
            await self._ensure_started()
        except asyncio.CancelledError:
            self._iterating = False
            await asyncio.shield(self._release(interrupt=True))
            raise
        except BaseException:
            self._iterating = False
            await self._release(interrupt=False)
            raise
        while True:
            await self._raise_if_timed_out()
            if self._queue:
                event = self._queue.popleft()
                return cast("E", event)
            if self._done:
                self._iterating = False
                await self._release(interrupt=False)
                if self._error is not None:
                    raise self._error
                raise StopAsyncIteration
            self._wakeup.clear()
            if self._queue or self._done:
                continue
            try:
                if self._deadline is None:
                    await self._wakeup.wait()
                else:
                    remaining = self._deadline - self._monotonic()
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    await asyncio.wait_for(self._wakeup.wait(), remaining)
            except asyncio.TimeoutError:
                await self._raise_timeout()
            except asyncio.CancelledError:
                await asyncio.shield(self._release(interrupt=True))
                self._iterating = False
                raise

    async def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        if self._timeout is not None:
            if self._timeout <= 0:
                self._deadline = self._monotonic()
            else:
                self._deadline = self._monotonic() + self._timeout
        if self._start_callback is not None:
            result = self._start_callback(self)
            if hasattr(result, "__await__"):
                try:
                    await self._await_before_deadline(cast("Any", result))
                except asyncio.TimeoutError:
                    await self._raise_timeout()
                except asyncio.CancelledError:
                    await self._release(interrupt=True)
                    raise
                except BaseException:
                    await self._release(interrupt=False)
                    raise

    async def _await_before_deadline(self, awaitable: Awaitable[object]) -> None:
        if self._deadline is None:
            await awaitable
            return
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise asyncio.TimeoutError
        await asyncio.wait_for(awaitable, timeout=remaining)

    async def _raise_if_timed_out(self) -> None:
        if self._deadline is not None and self._monotonic() >= self._deadline:
            await self._raise_timeout()

    async def _raise_timeout(self) -> None:
        from droid_sdk.errors import RunTimeoutError

        self._queue.clear()
        self._result = None
        self._error = None
        self._done = True
        self._iterating = False
        await self._release(interrupt=True)
        raise RunTimeoutError(
            "The run exceeded its timeout",
            timeout_duration=self._timeout,
        ) from None

    async def _release(self, *, interrupt: bool) -> None:
        if self._released:
            return
        self._released = True
        if self._finish_callback is not None:
            task: asyncio.Future[object] | None = None
            try:
                result = self._finish_callback(interrupt)
                if hasattr(result, "__await__"):
                    finish_task = asyncio.ensure_future(cast("Any", result))
                    task = finish_task
                    await asyncio.wait_for(
                        asyncio.shield(finish_task),
                        timeout=0.1,
                    )
            except asyncio.TimeoutError:
                if task is not None:
                    task.add_done_callback(_consume_task_result)
            except asyncio.CancelledError:
                if task is not None:
                    task.add_done_callback(_consume_task_result)
                raise
            except Exception:
                # Cleanup and best-effort interruption never mask the primary
                # stream outcome.
                pass

    async def aclose(self) -> None:
        """Interrupt and detach this stream if it is unfinished."""
        await self._release(interrupt=not self._done)


def _consume_task_result(task: asyncio.Future[object]) -> None:
    with contextlib.suppress(BaseException):
        task.result()


__all__ = ["RunStream", "StreamStateTracker"]
