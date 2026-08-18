# ruff: noqa: TC001

from __future__ import annotations

from droid_sdk import (
    DroidSystemPrompt,
    FrozenJsonObject,
    FrozenJsonValue,
    PermissionHandler,
    PermissionRequest,
    QuestionHandler,
    QuestionRequest,
    RunResult,
    Session,
    SessionConfig,
    SessionSettings,
    ToolInfo,
    ToolResultBlock,
)
from droid_sdk._high_level.output import prepare_output_adapter
from droid_sdk.observability import Logger


class BadLogger:
    def log(self, event: str) -> None:
        pass


SessionSettings()
SessionSettings(model=None, reasoning_effort=None)
SessionConfig(system_prompt={"append": "prompt"})
DroidSystemPrompt(append=1)
ToolInfo(id="Read")
ToolResultBlock(tool_use_id="tool-1", content=[object()])
prepare_output_adapter(str)
logger: Logger = BadLogger()


def bad_permission_handler(request: PermissionRequest) -> str:
    return "proceed_once"


def bad_question_handler(request: QuestionRequest) -> dict[str, object]:
    return {"cancelled": True, "answers": []}


permission_handler: PermissionHandler = bad_permission_handler
question_handler: QuestionHandler = bad_question_handler


def consume_text(value: str) -> None:
    pass


def misuse_result_output(result: RunResult[int]) -> None:
    consume_text(result.output)


def mutate_frozen_json(
    value: FrozenJsonObject,
    sequence: tuple[FrozenJsonValue, ...],
) -> None:
    value["changed"] = True
    sequence[0] = "changed"


async def misuse_high_level_generics(session: Session) -> None:
    await session.stream("prompt", output=str)
    await session.remove_mcp_server("name", scope="project")
