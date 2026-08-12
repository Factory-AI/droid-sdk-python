"""Adapters between canonical server requests and public interaction values."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, cast

from droid_sdk._high_level.enums import (
    ErrorType,
    SandboxOperation,
    SandboxViolationReason,
    SandboxViolationType,
    ToolConfirmationOutcome,
)
from droid_sdk._high_level.interactions import (
    ApplyPatchAction,
    ApplyPatchFile,
    AskUserAction,
    AskUserParseError,
    CreateFile,
    DroidShieldViolationAction,
    EditAction,
    ExecuteAction,
    ExitSpecModeAction,
    InteractionHandlers,
    McpToolAction,
    PermissionAction,
    PermissionOption,
    PermissionRequest,
    PermissionResponse,
    Question,
    QuestionRequest,
    QuestionResponse,
    SandboxViolationAction,
)
from droid_sdk._high_level.messages import ErrorEvent, ToolUseBlock
from droid_sdk.schemas.cli import (
    ApplyPatchToolConfirmationDetails,
    AskUserConfirmationDetails,
    AskUserRequestParams,
    CreateToolConfirmationDetails,
    DroidShieldViolationConfirmationDetails,
    EditToolConfirmationDetails,
    ExecuteToolConfirmationDetails,
    ExitSpecModeConfirmationDetails,
    McpToolConfirmationDetails,
    RequestPermissionRequestParams,
    SandboxViolationConfirmationDetails,
)

ErrorSink = Callable[[ErrorEvent], None]


def _permission_response(value: object) -> PermissionResponse:
    if not isinstance(value, PermissionResponse):
        raise TypeError("invalid permission response")
    return value


def _question_response(value: object) -> QuestionResponse:
    if not isinstance(value, QuestionResponse):
        raise TypeError("invalid question response")
    return value


def _tool_use(value: Any) -> ToolUseBlock:
    return ToolUseBlock(
        id=value.id,
        name=value.name,
        input=value.input,
        thought_signature=value.thought_signature,
    )


def _permission_action(value: Any) -> PermissionAction:
    tool_use = _tool_use(value.tool_use)
    details = value.details.root
    if isinstance(details, EditToolConfirmationDetails):
        return EditAction(
            tool_use=tool_use,
            file_path=details.file_path,
            file_name=details.file_name,
            old_content=details.old_content,
            new_content=details.new_content,
        )
    if isinstance(details, ExecuteToolConfirmationDetails):
        return ExecuteAction(
            tool_use=tool_use,
            full_command=details.full_command,
            command=details.command,
            extracted_commands=details.extracted_commands,
            impact_level=details.impact_level,
            risk_level_reason=details.risk_level_reason,
        )
    if isinstance(details, CreateToolConfirmationDetails):
        return CreateFile(
            tool_use=tool_use,
            file_path=details.file_path,
            file_name=details.file_name,
            content=details.content,
        )
    if isinstance(details, AskUserConfirmationDetails):
        parsed = details.parsed
        return AskUserAction(
            tool_use=tool_use,
            questionnaire=details.questionnaire,
            questions=(
                ()
                if parsed is None
                else tuple(
                    Question(
                        index=question.index,
                        topic=question.topic,
                        question=question.question,
                        options=question.options,
                        multi_select=question.multi_select,
                    )
                    for question in parsed.questions
                )
            ),
            parse_error=(
                None
                if details.parse_error is None
                else AskUserParseError(
                    message=details.parse_error.message,
                    line=details.parse_error.line,
                )
            ),
        )
    if isinstance(details, ExitSpecModeConfirmationDetails):
        return ExitSpecModeAction(
            tool_use=tool_use,
            plan=details.plan,
            title=details.title,
        )
    if isinstance(details, ApplyPatchToolConfirmationDetails):
        files = None
        if details.files is not None:
            files = tuple(
                ApplyPatchFile(
                    file_path=str(file["filePath"]),
                    file_name=str(file["fileName"]),
                    operation=file["operation"],
                    move_to=cast("str | None", file.get("moveTo")),
                    old_content=cast("str | None", file.get("oldContent")),
                    new_content=cast("str | None", file.get("newContent")),
                )
                for file in details.files
            )
        return ApplyPatchAction(
            tool_use=tool_use,
            file_path=details.file_path,
            file_name=details.file_name,
            patch_content=details.patch_content,
            old_content=details.old_content,
            new_content=details.new_content,
            files=files,
        )
    if isinstance(details, McpToolConfirmationDetails):
        return McpToolAction(
            tool_use=tool_use,
            tool_name=details.tool_name,
            impact_level=details.impact_level,
            server_name=details.server_name,
            actual_tool_name=details.actual_tool_name,
        )
    if isinstance(details, SandboxViolationConfirmationDetails):
        return SandboxViolationAction(
            tool_use=tool_use,
            violating_tool_name=details.violating_tool_name,
            target=details.target,
            operation=SandboxOperation(details.operation_type.value),
            violation_type=SandboxViolationType(details.violation_type.value),
            reason=details.reason,
            is_org_deny=details.is_org_deny,
            violation_reason=(
                None
                if details.violation_reason is None
                else SandboxViolationReason(details.violation_reason.value)
            ),
        )
    if isinstance(details, DroidShieldViolationConfirmationDetails):
        return DroidShieldViolationAction(
            tool_use=tool_use,
            command=details.command,
            reason=details.reason,
        )
    raise ValueError("unsupported permission action")


def permission_request_from_wire(
    params: RequestPermissionRequestParams | Mapping[str, object],
) -> PermissionRequest:
    parsed = RequestPermissionRequestParams.model_validate(params)
    return PermissionRequest(
        actions=tuple(_permission_action(item) for item in parsed.tool_uses),
        options=tuple(
            PermissionOption(
                label=option.label,
                value=ToolConfirmationOutcome(option.value.value),
            )
            for option in parsed.options
        ),
        associated_session_ids=parsed.associated_session_ids or (),
    )


def question_request_from_wire(
    params: AskUserRequestParams | Mapping[str, object],
) -> QuestionRequest:
    parsed = AskUserRequestParams.model_validate(params)
    return QuestionRequest(
        tool_call_id=parsed.tool_call_id,
        questions=tuple(
            Question(
                index=question.index,
                topic=question.topic,
                question=question.question,
                options=question.options,
                multi_select=question.multi_select,
            )
            for question in parsed.questions
        ),
    )


class InteractionDispatcher:
    """Invoke public handlers and always return a safe wire response."""

    def __init__(
        self,
        handlers: InteractionHandlers | None = None,
        *,
        error_sink: ErrorSink | None = None,
    ) -> None:
        self.handlers = handlers or InteractionHandlers()
        self.error_sink = error_sink

    def _report(self, interaction: str) -> None:
        if self.error_sink is not None:
            with contextlib.suppress(Exception):
                self.error_sink(
                    ErrorEvent(
                        message=f"{interaction} interaction handler failed",
                        error_type=ErrorType.DROID_CLIENT_ERROR,
                        timestamp=datetime.now(timezone.utc),
                    )
                )

    async def handle_permission(self, raw: Mapping[str, object]) -> dict[str, object]:
        fallback: dict[str, object] = {"selectedOption": "cancel"}
        try:
            request = permission_request_from_wire(raw)
            handler = self.handlers.on_permission
            if handler is None:
                raise ValueError("missing permission handler")
            value = handler(request)
            if inspect.isawaitable(value):
                value = await value
            value = _permission_response(value)
            offered = {option.value for option in request.options}
            if value.selected_option not in offered:
                raise ValueError("permission option was not offered")
            if (
                value.selected_option is ToolConfirmationOutcome.PROCEED_EDIT
                and value.edited_spec_content is None
            ):
                raise ValueError("edited spec content is required")
            result: dict[str, object] = {"selectedOption": value.selected_option.value}
            if value.comment is not None:
                result["comment"] = value.comment
            if value.edited_spec_content is not None:
                result["editedSpecContent"] = value.edited_spec_content
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            self._report("Permission")
            return fallback

    async def handle_question(self, raw: Mapping[str, object]) -> dict[str, object]:
        fallback: dict[str, object] = {"cancelled": True, "answers": []}
        try:
            request = question_request_from_wire(raw)
            handler = self.handlers.on_question
            if handler is None:
                raise ValueError("missing question handler")
            value = handler(request)
            if inspect.isawaitable(value):
                value = await value
            value = _question_response(value)
            expected = {
                (question.index, question.question) for question in request.questions
            }
            if value.cancelled and value.answers:
                raise ValueError("cancelled response cannot contain answers")
            if any(
                (answer.index, answer.question) not in expected
                for answer in value.answers
            ):
                raise ValueError("question answer does not match request")
            if len({answer.index for answer in value.answers}) != len(value.answers):
                raise ValueError("duplicate question answer")
            return {
                "cancelled": value.cancelled,
                "answers": [
                    {
                        "index": answer.index,
                        "question": answer.question,
                        "answer": answer.answer,
                    }
                    for answer in value.answers
                ],
            }
        except asyncio.CancelledError:
            raise
        except Exception:
            self._report("Question")
            return fallback


__all__ = [
    "InteractionDispatcher",
    "permission_request_from_wire",
    "question_request_from_wire",
]
