"""Immutable complete messages, partial events, and terminal results."""

# ruff: noqa: TC001, TC002, TC003

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Generic, Literal, TypeAlias, TypeVar

from pydantic import ValidationError

from droid_sdk._high_level._immutable import (
    FrozenJsonObject,
    FrozenJsonValue,
    JsonValue,
    freeze_json,
    freeze_json_object,
)
from droid_sdk._high_level.attachments import (
    Base64ImageSource,
    DocumentSource,
)
from droid_sdk._high_level.config import SessionSettingsUpdate
from droid_sdk._high_level.enums import (
    ContextAccuracy,
    ErrorType,
    McpAuthOutcome,
    ToolConfirmationOutcome,
    WorkingState,
)
from droid_sdk._high_level.extensions import McpServerStatusInfo, McpStatusSummary

T = TypeVar("T")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TextBlock:
    id: str | None = field(default=None, kw_only=True)
    text: str


@dataclass(frozen=True, slots=True)
class ThinkingBlock:
    id: str | None = field(default=None, kw_only=True)
    thinking: str
    signature: str
    signature_provider: str | None = None
    duration: timedelta | None = None


@dataclass(frozen=True, slots=True)
class RedactedThinkingBlock:
    id: str | None = field(default=None, kw_only=True)
    data: str


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    id: str
    name: str
    input: Mapping[str, object]
    thought_signature: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input", freeze_json_object(self.input, where="tool input")
        )


@dataclass(frozen=True, slots=True, init=False)
class ToolResultBlock:
    id: str | None = field(default=None, kw_only=True)
    tool_use_id: str
    content: str | Sequence[ToolResultStoredContent] | None = None
    is_error: bool | None = None

    def __init__(
        self,
        tool_use_id: str,
        content: str | Sequence[ToolResultContent] | None = None,
        is_error: bool | None = None,
        *,
        id: str | None = None,
    ) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "tool_use_id", tool_use_id)
        object.__setattr__(self, "is_error", is_error)
        if content is None or isinstance(content, str):
            object.__setattr__(self, "content", content)
            return
        object.__setattr__(
            self,
            "content",
            tuple(
                item
                if isinstance(item, (TextBlock, ImageBlock, DocumentBlock))
                else freeze_json(item, where="tool result block")
                for item in content
            ),
        )


@dataclass(frozen=True, slots=True)
class ImageBlock:
    id: str | None = field(default=None, kw_only=True)
    source: Base64ImageSource
    generated: bool | None = None


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    id: str | None = field(default=None, kw_only=True)
    source: DocumentSource


ContentBlock: TypeAlias = (
    TextBlock
    | ThinkingBlock
    | RedactedThinkingBlock
    | ToolUseBlock
    | ToolResultBlock
    | ImageBlock
    | DocumentBlock
)
ToolResultContentBlock: TypeAlias = TextBlock | ImageBlock | DocumentBlock
ToolResultContent: TypeAlias = ToolResultContentBlock | JsonValue
ToolResultStoredContent: TypeAlias = ToolResultContentBlock | FrozenJsonValue


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    id: str
    content: tuple[ContentBlock, ...]
    text: str
    parent_id: str | None = field(default=None, kw_only=True)
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", tuple(self.content))
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class UserMessage(ConversationMessage):
    pass


@dataclass(frozen=True, slots=True)
class AssistantMessage(ConversationMessage):
    pass


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    tool_use_id: str
    input: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input", freeze_json_object(self.input, where="tool input")
        )


@dataclass(frozen=True, slots=True, init=False)
class ToolResult:
    tool_use_id: str
    tool_name: str
    content: str | Sequence[FrozenJsonValue]
    is_error: bool

    def __init__(
        self,
        tool_use_id: str,
        tool_name: str,
        content: str | Sequence[JsonValue],
        is_error: bool,
    ) -> None:
        object.__setattr__(self, "tool_use_id", tool_use_id)
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "is_error", is_error)
        object.__setattr__(
            self,
            "content",
            content
            if isinstance(content, str)
            else tuple(freeze_json(item, where="tool result") for item in content),
        )


@dataclass(frozen=True, slots=True)
class HookExecution:
    hook_id: str
    event_name: str | None = None
    matcher: str | None = None
    tool_call_id: str | None = None
    command: str | None = None
    timeout: timedelta | None = None
    status: Literal["started", "completed", "error"] = "started"
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    suppress_output: bool | None = None


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str
    error_type: ErrorType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")


Message: TypeAlias = (
    UserMessage | AssistantMessage | ToolCall | ToolResult | HookExecution | ErrorEvent
)


@dataclass(frozen=True, slots=True)
class TextDelta:
    message_id: str
    block_index: int
    text: str


@dataclass(frozen=True, slots=True)
class TextComplete:
    message_id: str
    block_index: int


@dataclass(frozen=True, slots=True)
class ThinkingDelta:
    message_id: str
    block_index: int
    text: str


@dataclass(frozen=True, slots=True)
class ThinkingComplete:
    message_id: str
    block_index: int
    duration: timedelta | None = None


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    tool_use: ToolUseBlock


@dataclass(frozen=True, slots=True)
class ToolProgressUpdate:
    type: Literal["tool_call", "tool_result", "error", "status", "message"]
    tool_name: str | None = None
    status: str | None = None
    details: str | None = None
    text: str | None = None
    error: str | None = None
    timestamp: datetime | None = None
    parameters: Mapping[str, object] | None = None
    value_snippet: str | None = None
    terminal_id: str | None = None
    full_output: str | None = None
    subagent_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.timestamp is not None:
            _aware(self.timestamp, "timestamp")
        if self.parameters is not None:
            object.__setattr__(
                self,
                "parameters",
                freeze_json_object(self.parameters, where="tool progress parameters"),
            )


@dataclass(frozen=True, slots=True)
class ToolProgress:
    tool_use_id: str
    tool_name: str
    content: str
    update: ToolProgressUpdate


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    thinking_tokens: int
    factory_credits: float | None = None


@dataclass(frozen=True, slots=True)
class TokenUsageUpdate(Usage):
    pass


@dataclass(frozen=True, slots=True)
class ContextUsage:
    used: int
    remaining: int
    limit: int
    accuracy: ContextAccuracy
    updated_at: datetime

    def __post_init__(self) -> None:
        _aware(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class WorkingStateChanged:
    state: WorkingState


@dataclass(frozen=True, slots=True)
class PermissionResolved:
    request_id: str
    tool_use_ids: Sequence[str]
    selected_option: ToolConfirmationOutcome

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_use_ids", tuple(self.tool_use_ids))


@dataclass(frozen=True, slots=True)
class SettingsUpdated:
    settings: SessionSettingsUpdate


@dataclass(frozen=True, slots=True)
class SessionTitleUpdated:
    title: str


@dataclass(frozen=True, slots=True)
class SessionWorkingDirectoryChanged:
    cwd: str


@dataclass(frozen=True, slots=True)
class McpStatusChanged:
    servers: Sequence[McpServerStatusInfo]
    summary: McpStatusSummary

    def __post_init__(self) -> None:
        object.__setattr__(self, "servers", tuple(self.servers))


@dataclass(frozen=True, slots=True)
class McpAuthRequired:
    server_name: str
    auth_url: str
    message: str
    state: str


@dataclass(frozen=True, slots=True)
class McpAuthCompleted:
    server_name: str
    outcome: McpAuthOutcome
    message: str


@dataclass(frozen=True, slots=True, init=False)
class StructuredOutputError:
    code: str
    message: str
    details: FrozenJsonValue | None = None

    def __init__(
        self,
        code: str,
        message: str,
        details: JsonValue | None = None,
    ) -> None:
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(
            self,
            "details",
            None if details is None else freeze_json(details, where="details"),
        )


def _freeze_structured_output(
    value: Mapping[str, object] | None,
) -> FrozenJsonObject | None:
    if value is None:
        return None
    return freeze_json_object(value, where="structured_output")


@dataclass(frozen=True, slots=True)
class RunResult(Generic[T]):
    """Runtime base class shared by all terminal result dataclasses."""

    subtype: Literal[
        "success",
        "interrupted",
        "error_during_execution",
        "error_structured_output",
    ] = field(init=False)
    text: str = field(init=False)
    messages: tuple[Message, ...] = field(init=False)
    usage: Usage | None = field(init=False)
    duration: timedelta = field(init=False)
    turn_count: int = field(init=False)
    session_id: str = field(init=False)
    success: bool = field(init=False)
    interrupted: bool = field(init=False)
    output: T | None = field(init=False)
    structured_output: FrozenJsonObject | None = field(init=False)
    output_validation_error: ValidationError | None = field(init=False)
    structured_output_error: StructuredOutputError | None = field(init=False)
    error: ErrorEvent | None = field(init=False)

    def __post_init__(self) -> None:
        raise TypeError("RunResult is an abstract terminal result base")


@dataclass(frozen=True, slots=True)
class RunSuccess(RunResult[T]):
    text: str
    messages: tuple[Message, ...]
    usage: Usage | None
    duration: timedelta
    turn_count: int
    session_id: str
    output: T | None = None
    structured_output: FrozenJsonObject | None = None
    output_validation_error: ValidationError | None = None
    structured_output_error: None = field(default=None, init=False)
    error: None = field(default=None, init=False)
    subtype: Literal["success"] = field(default="success", init=False)
    success: Literal[True] = field(default=True, init=False)
    interrupted: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(
            self,
            "structured_output",
            _freeze_structured_output(self.structured_output),
        )


@dataclass(frozen=True, slots=True)
class RunInterrupted(RunResult[T]):
    text: str
    messages: tuple[Message, ...]
    usage: Usage | None
    duration: timedelta
    turn_count: int
    session_id: str
    output: T | None = None
    structured_output: FrozenJsonObject | None = None
    output_validation_error: ValidationError | None = None
    structured_output_error: None = field(default=None, init=False)
    error: None = field(default=None, init=False)
    subtype: Literal["interrupted"] = field(default="interrupted", init=False)
    success: Literal[False] = field(default=False, init=False)
    interrupted: Literal[True] = field(default=True, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(
            self,
            "structured_output",
            _freeze_structured_output(self.structured_output),
        )


@dataclass(frozen=True, slots=True)
class RunFailure(RunResult[T]):
    subtype: Literal["error_during_execution", "error_structured_output"]
    text: str
    messages: tuple[Message, ...]
    usage: Usage | None
    duration: timedelta
    turn_count: int
    session_id: str
    output: T | None = None
    structured_output: FrozenJsonObject | None = None
    output_validation_error: ValidationError | None = None
    structured_output_error: StructuredOutputError | None = None
    error: ErrorEvent | None = None
    success: Literal[False] = field(default=False, init=False)
    interrupted: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.subtype not in {
            "error_during_execution",
            "error_structured_output",
        }:
            raise ValueError(f"invalid failure subtype: {self.subtype!r}")
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(
            self,
            "structured_output",
            _freeze_structured_output(self.structured_output),
        )


StreamMessage: TypeAlias = Message | RunSuccess[T] | RunInterrupted[T] | RunFailure[T]
StreamEvent: TypeAlias = (
    StreamMessage[T]
    | TextDelta
    | TextComplete
    | ThinkingDelta
    | ThinkingComplete
    | ToolCallDelta
    | ToolProgress
    | TokenUsageUpdate
    | WorkingStateChanged
    | PermissionResolved
    | SettingsUpdated
    | SessionTitleUpdated
    | SessionWorkingDirectoryChanged
    | McpStatusChanged
    | McpAuthRequired
    | McpAuthCompleted
)
