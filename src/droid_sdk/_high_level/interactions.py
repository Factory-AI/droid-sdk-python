"""Immutable interaction request and response values."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from droid_sdk._high_level.enums import (
    SandboxOperation,
    SandboxViolationReason,
    SandboxViolationType,
    ToolConfirmationOutcome,
    ToolConfirmationType,
)
from droid_sdk._high_level.messages import ToolUseBlock  # noqa: TC001


@dataclass(frozen=True, slots=True)
class PermissionOption:
    label: str
    value: ToolConfirmationOutcome


@dataclass(frozen=True, slots=True)
class EditAction:
    tool_use: ToolUseBlock
    file_path: str
    file_name: str
    old_content: str | None = None
    new_content: str | None = None
    confirmation_type: Literal[ToolConfirmationType.EDIT] = field(
        default=ToolConfirmationType.EDIT, init=False
    )


@dataclass(frozen=True, slots=True)
class ExecuteAction:
    tool_use: ToolUseBlock
    full_command: str
    command: str
    extracted_commands: Sequence[str] | None = None
    impact_level: str | None = None
    risk_level_reason: str | None = None
    confirmation_type: Literal[ToolConfirmationType.EXECUTE] = field(
        default=ToolConfirmationType.EXECUTE, init=False
    )

    def __post_init__(self) -> None:
        if self.extracted_commands is not None:
            object.__setattr__(
                self, "extracted_commands", tuple(self.extracted_commands)
            )


@dataclass(frozen=True, slots=True)
class CreateFile:
    tool_use: ToolUseBlock
    file_path: str
    file_name: str
    content: str
    confirmation_type: Literal[ToolConfirmationType.CREATE] = field(
        default=ToolConfirmationType.CREATE, init=False
    )


@dataclass(frozen=True, slots=True)
class AskUserParseError:
    message: str
    line: int | None = None


@dataclass(frozen=True, slots=True)
class AskUserAction:
    tool_use: ToolUseBlock
    questionnaire: str
    questions: Sequence[Question] = ()
    parse_error: AskUserParseError | None = None
    confirmation_type: Literal[ToolConfirmationType.ASK_USER] = field(
        default=ToolConfirmationType.ASK_USER, init=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", tuple(self.questions))


@dataclass(frozen=True, slots=True)
class ExitSpecModeAction:
    tool_use: ToolUseBlock
    plan: str
    title: str | None = None
    confirmation_type: Literal[ToolConfirmationType.EXIT_SPEC_MODE] = field(
        default=ToolConfirmationType.EXIT_SPEC_MODE, init=False
    )


@dataclass(frozen=True, slots=True)
class ApplyPatchAction:
    tool_use: ToolUseBlock
    file_path: str
    file_name: str
    patch_content: str
    old_content: str | None = None
    new_content: str | None = None
    files: Sequence[ApplyPatchFile] | None = None
    confirmation_type: Literal[ToolConfirmationType.APPLY_PATCH] = field(
        default=ToolConfirmationType.APPLY_PATCH, init=False
    )

    def __post_init__(self) -> None:
        if self.files is not None:
            object.__setattr__(self, "files", tuple(self.files))


@dataclass(frozen=True, slots=True)
class ApplyPatchFile:
    file_path: str
    file_name: str
    operation: Literal["create", "update", "delete"]
    move_to: str | None = None
    old_content: str | None = None
    new_content: str | None = None


@dataclass(frozen=True, slots=True)
class McpToolAction:
    tool_use: ToolUseBlock
    tool_name: str
    impact_level: str
    server_name: str | None = None
    actual_tool_name: str | None = None
    confirmation_type: Literal[ToolConfirmationType.MCP_TOOL] = field(
        default=ToolConfirmationType.MCP_TOOL, init=False
    )


@dataclass(frozen=True, slots=True)
class SandboxViolationAction:
    tool_use: ToolUseBlock
    violating_tool_name: str
    target: str
    operation: SandboxOperation
    violation_type: SandboxViolationType
    reason: str
    is_org_deny: bool
    violation_reason: SandboxViolationReason | None = None
    confirmation_type: Literal[ToolConfirmationType.SANDBOX_VIOLATION] = field(
        default=ToolConfirmationType.SANDBOX_VIOLATION, init=False
    )


@dataclass(frozen=True, slots=True)
class Plan:
    text: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class DroidShieldViolationAction:
    tool_use: ToolUseBlock
    command: str
    reason: str
    confirmation_type: Literal[ToolConfirmationType.DROID_SHIELD_VIOLATION] = field(
        default=ToolConfirmationType.DROID_SHIELD_VIOLATION, init=False
    )


PermissionAction: TypeAlias = (
    EditAction
    | ExecuteAction
    | CreateFile
    | AskUserAction
    | ExitSpecModeAction
    | ApplyPatchAction
    | McpToolAction
    | SandboxViolationAction
    | DroidShieldViolationAction
)


@dataclass(frozen=True, slots=True)
class PermissionResponse:
    selected_option: ToolConfirmationOutcome
    comment: str | None = None
    edited_spec_content: str | None = None

    def __post_init__(self) -> None:
        if (
            self.selected_option is ToolConfirmationOutcome.PROCEED_EDIT
            and self.edited_spec_content is None
        ):
            raise ValueError("edited_spec_content is required for PROCEED_EDIT")


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    actions: Sequence[PermissionAction]
    options: Sequence[PermissionOption]
    associated_session_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(
            self, "associated_session_ids", tuple(self.associated_session_ids)
        )

    @property
    def plan(self) -> Plan | None:
        action = next(
            (item for item in self.actions if isinstance(item, ExitSpecModeAction)),
            None,
        )
        if action is None:
            return None
        return Plan(text=action.plan, title=action.title)

    def respond(
        self,
        selected_option: ToolConfirmationOutcome,
        *,
        comment: str | None = None,
        edited_spec_content: str | None = None,
    ) -> PermissionResponse:
        if selected_option not in {option.value for option in self.options}:
            raise ValueError("selected_option was not offered by Droid")
        return PermissionResponse(
            selected_option=selected_option,
            comment=comment,
            edited_spec_content=edited_spec_content,
        )


@dataclass(frozen=True, slots=True)
class QuestionAnswer:
    index: int
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class Question:
    index: int
    topic: str
    question: str
    options: Sequence[str] = ()
    multi_select: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))

    def answer(self, answer: str) -> QuestionAnswer:
        return QuestionAnswer(index=self.index, question=self.question, answer=answer)

    def answer_multiple(self, answers: Sequence[str]) -> QuestionAnswer:
        """Create the wire-compatible comma-separated multi-select answer."""
        return self.answer(", ".join(answers))


@dataclass(frozen=True, slots=True)
class QuestionResponse:
    cancelled: bool
    answers: Sequence[QuestionAnswer] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "answers", tuple(self.answers))


@dataclass(frozen=True, slots=True)
class QuestionRequest:
    tool_call_id: str
    questions: Sequence[Question]

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", tuple(self.questions))

    def submit(self, answers: Sequence[QuestionAnswer]) -> QuestionResponse:
        submitted = tuple(answers)
        expected = {(item.index, item.question) for item in self.questions}
        if any((item.index, item.question) not in expected for item in submitted):
            raise ValueError("answer does not match a requested question")
        if len({item.index for item in submitted}) != len(submitted):
            raise ValueError("a question may only be answered once")
        return QuestionResponse(cancelled=False, answers=submitted)

    def cancel(self) -> QuestionResponse:
        return QuestionResponse(cancelled=True)


PermissionHandler: TypeAlias = Callable[
    [PermissionRequest], PermissionResponse | Awaitable[PermissionResponse]
]
QuestionHandler: TypeAlias = Callable[
    [QuestionRequest], QuestionResponse | Awaitable[QuestionResponse]
]


@dataclass(frozen=True, slots=True)
class InteractionHandlers:
    on_permission: PermissionHandler | None = None
    on_question: QuestionHandler | None = None
