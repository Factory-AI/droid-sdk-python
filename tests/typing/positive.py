# ruff: noqa: TC001

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel
from typing_extensions import assert_type

from droid_sdk import (
    ApplyPatchAction,
    ApplyPatchFile,
    AssistantMessage,
    CompactOutcome,
    DocumentBlock,
    FrozenJsonObject,
    FrozenJsonValue,
    ImageBlock,
    JsonObject,
    JsonSchema,
    McpServerStatusInfo,
    McpStatusChanged,
    PermissionAction,
    PermissionHandler,
    PermissionRequest,
    PermissionResponse,
    QuestionHandler,
    QuestionRequest,
    QuestionResponse,
    ReasoningEffort,
    RewindOutcome,
    RunFailure,
    RunInterrupted,
    RunResult,
    RunStream,
    RunSuccess,
    Session,
    SessionSettings,
    SessionSettingsUpdate,
    StreamEvent,
    StreamMessage,
    TextBlock,
    TextDelta,
    ToolCategory,
    ToolInfo,
    ToolResultBlock,
    ToolUseBlock,
    run,
)
from droid_sdk._high_level.output import OutputAdapter, prepare_output_adapter
from droid_sdk.observability import (
    LogEvent,
    Logger,
    MetricEvent,
    MetricSink,
    TraceContext,
    TraceContextProvider,
)


class Review(BaseModel):
    summary: str


assert_type(prepare_output_adapter(), OutputAdapter[None])
assert_type(prepare_output_adapter(Review), OutputAdapter[Review])

raw_adapter = prepare_output_adapter(JsonSchema({"type": "object"}))
assert_type(raw_adapter, OutputAdapter[JsonObject])

schema_input: JsonObject = {
    "type": "object",
    "required": ["summary"],
}
frozen_schema = JsonSchema(schema_input).schema
assert_type(frozen_schema, FrozenJsonObject)
assert_type(frozen_schema["type"], FrozenJsonValue)
assert_type(frozen_schema.get("required"), FrozenJsonValue | None)

settings = SessionSettings(
    model="claude-sonnet",
    reasoning_effort=ReasoningEffort.HIGH,
)
assert_type(settings.model, str)
assert_type(settings.reasoning_effort, ReasoningEffort)

settings_update = SessionSettingsUpdate(model="claude-sonnet")
assert_type(settings_update.model, str | None)
assert_type(settings_update.reasoning_effort, ReasoningEffort | None)

tool = ToolInfo(
    id="Read",
    display_name="Read",
    description="Read a file",
    category=ToolCategory.READ,
    default_allowed=True,
    allowed=True,
)
assert_type(tool.category, ToolCategory)

block = ToolResultBlock(
    tool_use_id="tool-1",
    content=[TextBlock(text="done")],
)
if block.content is not None and not isinstance(block.content, str):
    assert_type(
        block.content[0],
        TextBlock | ImageBlock | DocumentBlock | FrozenJsonValue,
    )

json_block = ToolResultBlock(
    tool_use_id="tool-2",
    content=[{"nested": ["value"]}],
)
if json_block.content is not None and not isinstance(json_block.content, str):
    assert_type(
        json_block.content[0],
        TextBlock | ImageBlock | DocumentBlock | FrozenJsonValue,
    )

tool_use = ToolUseBlock(id="tool-1", name="ApplyPatch", input={})
action: PermissionAction = ApplyPatchAction(
    tool_use=tool_use,
    file_path="/repo/a.py",
    file_name="a.py",
    patch_content="patch",
    files=[
        ApplyPatchFile(
            file_path="/repo/a.py",
            file_name="a.py",
            operation="update",
        )
    ],
)


def handle_action(value: PermissionAction) -> None:
    if isinstance(value, ApplyPatchAction):
        assert_type(value.files, Sequence[ApplyPatchFile] | None)


handle_action(action)


def handle_result(result: RunResult[Review]) -> None:
    assert_type(result.output, Review | None)
    if isinstance(result, RunSuccess):
        assert_type(result.subtype, Literal["success"])
        assert_type(result.success, Literal[True])
        assert_type(result.interrupted, Literal[False])
    elif isinstance(result, RunInterrupted):
        assert_type(result.subtype, Literal["interrupted"])
        assert_type(result.success, Literal[False])
        assert_type(result.interrupted, Literal[True])
    elif isinstance(result, RunFailure):
        assert_type(
            result.subtype,
            Literal["error_during_execution", "error_structured_output"],
        )
        assert_type(result.success, Literal[False])
        assert_type(result.interrupted, Literal[False])


def handle_success(result: RunSuccess[Review]) -> None:
    assert_type(result.output, Review | None)


def handle_interrupted(result: RunInterrupted[Review]) -> None:
    assert_type(result.output, Review | None)


def handle_failure(result: RunFailure[Review]) -> None:
    assert_type(result.output, Review | None)


def handle_stream_event(event: StreamEvent[Review]) -> None:
    if isinstance(event, RunResult):
        assert_type(
            event,
            RunSuccess[Review] | RunInterrupted[Review] | RunFailure[Review],
        )
        assert_type(event.output, Review | None)
        if isinstance(event, RunSuccess):
            assert_type(event, RunSuccess[Review])
            assert_type(event.output, Review | None)


def handle_stream_message(message: StreamMessage[Review]) -> None:
    if isinstance(message, AssistantMessage):
        assert_type(message, AssistantMessage)
    elif isinstance(message, RunResult):
        assert_type(
            message,
            RunSuccess[Review] | RunInterrupted[Review] | RunFailure[Review],
        )


def handle_partial_event(event: StreamEvent[Review]) -> None:
    if isinstance(event, TextDelta):
        assert_type(event, TextDelta)
        assert_type(event.block_index, int)


def approve(request: PermissionRequest) -> PermissionResponse:
    return request.respond(request.options[0].value)


async def answer(request: QuestionRequest) -> QuestionResponse:
    return request.cancel()


permission_handler: PermissionHandler = approve
question_handler: QuestionHandler = answer


def handle_mcp(event: McpStatusChanged) -> None:
    assert_type(event.servers[0], McpServerStatusInfo)


class Sink:
    def log(self, event: LogEvent) -> None:
        pass

    def record(self, event: MetricEvent) -> None:
        pass

    def inject(self, carrier: TraceContext) -> None:
        pass


logger: Logger = Sink()
metrics: MetricSink = Sink()
tracing: TraceContextProvider = Sink()


async def public_generic_calls(session: Session) -> None:
    assert_type(await run("hello"), RunResult[None])
    assert_type(await run("hello", output=Review), RunResult[Review])
    assert_type(
        await run("hello", output=JsonSchema({"type": "object"})),
        RunResult[JsonObject],
    )

    assert_type(
        session.stream("hello"),
        RunStream[None, StreamMessage[None]],
    )
    assert_type(
        session.stream("hello", output=Review),
        RunStream[Review, StreamMessage[Review]],
    )
    assert_type(
        session.stream("hello", output=JsonSchema({"type": "object"})),
        RunStream[JsonObject, StreamMessage[JsonObject]],
    )
    assert_type(
        session.stream("hello", include_partial_messages=True),
        RunStream[None, StreamEvent[None]],
    )
    assert_type(
        session.stream(
            "hello",
            output=Review,
            include_partial_messages=True,
        ),
        RunStream[Review, StreamEvent[Review]],
    )
    assert_type(
        session.stream(
            "hello",
            output=JsonSchema({"type": "object"}),
            include_partial_messages=True,
        ),
        RunStream[JsonObject, StreamEvent[JsonObject]],
    )


async def lifecycle_outcomes(
    compact: CompactOutcome,
    rewind: RewindOutcome,
) -> None:
    assert_type(compact.session, Session)
    assert_type(rewind.session, Session)
    async with compact.session as successor:
        assert_type(successor, Session)
