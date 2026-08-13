from __future__ import annotations

import base64
import dataclasses
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pytest
from pydantic import BaseModel, RootModel, ValidationError
from typing_extensions import Self

import droid_sdk._high_level.attachments as attachment_module
from droid_sdk import (
    MAX_ATTACHMENT_BYTES,
    ApplyPatchAction,
    ApplyPatchFile,
    AskUserAction,
    AskUserParseError,
    Autonomy,
    Base64ImageSource,
    ContextAccuracy,
    CreateFile,
    Document,
    DocumentBlock,
    DroidShieldViolationAction,
    EditAction,
    ErrorEvent,
    ErrorType,
    ExecuteAction,
    ExitSpecModeAction,
    HttpHeader,
    Image,
    ImageBlock,
    InvalidAttachmentError,
    JsonSchema,
    ListToolsOptions,
    McpConfigError,
    McpOAuthOptions,
    McpServerStatus,
    McpServerStatusInfo,
    McpServerType,
    McpStatusChanged,
    McpStatusSummary,
    McpToolAction,
    Mode,
    PdfDocumentSource,
    PermissionRequest,
    ReasoningEffort,
    RunFailure,
    RunInterrupted,
    RunResult,
    RunSuccess,
    Runtime,
    SandboxOperation,
    SandboxViolationAction,
    SandboxViolationType,
    SessionConfig,
    SessionSettings,
    SessionTag,
    StdioMcpServerConfig,
    StructuredOutputError,
    TextBlock,
    TextDocumentSource,
    ToolCategory,
    ToolConfirmationOutcome,
    ToolConfirmationType,
    ToolInfo,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
)
from droid_sdk._high_level.output import prepare_output_adapter
from droid_sdk.observability import (
    LogEvent,
    MetricEvent,
    Observability,
    ObservabilityAdapter,
    TraceContext,
    emit_log,
    inject_trace_context,
    record_metric,
    serialize_error,
)
from droid_sdk.protocol import ProtocolTiming

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNg"
    "YAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
GIF = b"GIF89a" + (b"\0" * 20)
JPEG = b"\xff\xd8\xff\xe0" + (b"\0" * 20)
WEBP = b"RIFF\x04\x00\x00\x00WEBP"


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (PNG, "image/png"),
        (GIF, "image/gif"),
        (JPEG, "image/jpeg"),
        (WEBP, "image/webp"),
    ],
)
def test_image_bytes_and_content_detection(data: bytes, media_type: str) -> None:
    image = Image.from_bytes(data, media_type=media_type)  # type: ignore[arg-type]
    assert image.source.media_type == media_type
    assert base64.b64decode(image.source.data) == data


def test_image_path_ignores_misleading_extension(tmp_path: Path) -> None:
    path = tmp_path / "not-a-jpeg.jpg"
    path.write_bytes(PNG)
    assert Image.from_path(path).source.media_type == "image/png"


@pytest.mark.parametrize(
    "factory",
    [
        lambda path: Image.from_path(path),
        lambda path: Document.from_path(path),
    ],
)
def test_attachment_rejects_missing_and_directory(
    tmp_path: Path, factory: object
) -> None:
    call = factory  # keep parametrization readable
    with pytest.raises(InvalidAttachmentError):
        call(tmp_path / "missing")  # type: ignore[operator]
    with pytest.raises(InvalidAttachmentError):
        call(tmp_path)  # type: ignore[operator]


def test_attachment_errors_do_not_include_bytes() -> None:
    secret = b"private-file-content"
    with pytest.raises(InvalidAttachmentError) as raised:
        Image.from_bytes(secret, media_type="image/png")
    assert secret.decode() not in str(raised.value)


def test_attachment_size_boundary_and_oversize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(attachment_module, "MAX_ATTACHMENT_BYTES", len(PNG))

    boundary = tmp_path / "boundary.png"
    boundary.write_bytes(PNG)
    assert Image.from_path(boundary).source.media_type == "image/png"

    oversized = tmp_path / "oversized.png"
    oversized.write_bytes(PNG + b"private-file-content")
    with pytest.raises(InvalidAttachmentError) as raised:
        Image.from_path(oversized)
    assert "exceeds" in str(raised.value)
    assert "private-file-content" not in str(raised.value)
    with pytest.raises(InvalidAttachmentError, match="exceeds"):
        Image.from_bytes(PNG + b"x", media_type="image/png")
    assert Document.from_text("x" * len(PNG)).source.data == "x" * len(PNG)
    with pytest.raises(InvalidAttachmentError, match="exceeds"):
        Document.from_text("x" * (len(PNG) + 1))


def test_attachment_rejects_sparse_oversize_without_reading(tmp_path: Path) -> None:
    sparse = tmp_path / "sparse.pdf"
    with sparse.open("wb") as file:
        file.truncate(MAX_ATTACHMENT_BYTES + 1)
    with pytest.raises(InvalidAttachmentError, match="exceeds"):
        Document.from_path(sparse)


def test_pdf_path_enforces_pdf_specific_size_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary_bytes = b"%PDF-" + b"x" * 11
    monkeypatch.setattr(
        attachment_module, "MAX_PDF_ATTACHMENT_BYTES", len(boundary_bytes)
    )
    boundary = tmp_path / "boundary.pdf"
    boundary.write_bytes(boundary_bytes)
    document = Document.from_path(boundary)
    assert isinstance(document.source, PdfDocumentSource)
    assert base64.b64decode(document.source.data) == boundary_bytes

    oversized_bytes = boundary_bytes + b"x"
    oversized = tmp_path / "oversized.pdf"
    oversized.write_bytes(oversized_bytes)
    with pytest.raises(InvalidAttachmentError) as from_path:
        Document.from_path(oversized)
    with pytest.raises(InvalidAttachmentError) as from_bytes:
        Document.from_bytes(oversized_bytes)
    assert str(from_path.value) == str(from_bytes.value)
    assert str(from_path.value) == (
        f"PDF attachment exceeds the {len(boundary_bytes)}-byte limit"
    )


def test_attachment_rejects_file_changed_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "changing.txt"
    path.write_text("safe", encoding="utf-8")
    original_open = Path.open

    class ChangingFile:
        def __init__(self, file_path: Path) -> None:
            self._path = file_path
            self._file = original_open(file_path, "rb")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            self._file.close()

        def fileno(self) -> int:
            return self._file.fileno()

        def read(self, size: int = -1) -> bytes:
            data = self._file.read(size)
            descriptor = os.open(self._path, os.O_WRONLY | os.O_APPEND)
            try:
                os.write(descriptor, b"x")
            finally:
                os.close(descriptor)
            return data

    def changing_open(
        file_path: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> ChangingFile:
        assert mode == "rb"
        return ChangingFile(file_path)

    monkeypatch.setattr(Path, "open", changing_open)
    with pytest.raises(InvalidAttachmentError, match="changed while"):
        Document.from_path(path)


def test_attachment_rejects_file_replaced_between_stat_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "replaced.txt"
    replacement = tmp_path / "replacement.txt"
    path.write_text("original", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    original_open = Path.open
    replaced = False

    def replacing_open(
        file_path: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        nonlocal replaced
        if file_path == path and not replaced:
            replaced = True
            os.replace(replacement, path)
        return original_open(file_path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replacing_open)
    with pytest.raises(InvalidAttachmentError, match="changed before"):
        Document.from_path(path)


def test_image_direct_source_validates_base64_and_signature() -> None:
    with pytest.raises(InvalidAttachmentError):
        Base64ImageSource(data="not base64", media_type="image/png")
    with pytest.raises(InvalidAttachmentError):
        Image.from_bytes(PNG, media_type="image/jpeg")


def test_document_text_pdf_and_encoding(tmp_path: Path) -> None:
    text_path = tmp_path / "hello.md"
    text_path.write_text("hello", encoding="utf-8")
    text = Document.from_path(text_path)
    assert text.source == TextDocumentSource(
        data="hello", name="hello.md", mime="text/plain"
    )

    pdf_path = tmp_path / "report.pdf"
    pdf_bytes = b"%PDF-1.7\n%%EOF\n"
    pdf_path.write_bytes(pdf_bytes)
    pdf = Document.from_path(pdf_path)
    assert isinstance(pdf.source, PdfDocumentSource)
    assert base64.b64decode(pdf.source.data) == pdf_bytes
    assert pdf.source.name == "report.pdf"
    assert pdf.source.path == str(pdf_path)

    bad_path = tmp_path / "binary.bin"
    bad_path.write_bytes(b"\xff\xfe")
    with pytest.raises(InvalidAttachmentError):
        Document.from_path(bad_path)
    with pytest.raises(InvalidAttachmentError):
        Document.from_bytes(b"not pdf")


def test_configuration_is_recursively_immutable() -> None:
    metadata = {"owner": "sdk"}
    tags = [SessionTag("test", metadata)]
    disabled = {"Execute"}
    config = SessionConfig(
        mode=Mode.SPEC,
        autonomy=Autonomy.LOW,
        spec_reasoning_effort=ReasoningEffort.HIGH,
        tags=tags,
        disabled_tools=disabled,
    )
    tags.clear()
    metadata["owner"] = "changed"
    disabled.add("Edit")
    assert config.tags[0].metadata == {"owner": "sdk"}
    assert config.disabled_tools == frozenset({"Execute"})
    assert isinstance(config.tags[0].metadata, MappingProxyType)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.mode = Mode.AUTO  # type: ignore[misc]


def test_tool_overrides_accept_any_iterable_and_reject_strings() -> None:
    config = SessionConfig(
        additional_tools=["CustomTool"],
        enabled_tools=("Read",),
        disabled_tools=iter(["Execute"]),
        restrict_tools={"Read", "Grep"},
    )
    assert config.additional_tools == frozenset({"CustomTool"})
    assert config.enabled_tools == frozenset({"Read"})
    assert config.disabled_tools == frozenset({"Execute"})
    assert config.restrict_tools == frozenset({"Read", "Grep"})

    options = ListToolsOptions(disabled_tools=["Execute"])
    assert options.disabled_tools == frozenset({"Execute"})

    with pytest.raises(TypeError, match="disabled_tools"):
        SessionConfig(disabled_tools="Execute")
    with pytest.raises(TypeError, match="restrict_tools"):
        ListToolsOptions(restrict_tools="Read")


def test_json_schema_is_recursive_and_rejects_non_json() -> None:
    schema = {"type": "object", "required": ["name"]}
    value = JsonSchema(schema)
    schema["type"] = "array"
    assert value.schema["type"] == "object"
    assert value.schema["required"] == ("name",)
    with pytest.raises(TypeError):
        value.schema["type"] = "array"  # type: ignore[index]
    required = value.schema["required"]
    assert isinstance(required, tuple)
    with pytest.raises(TypeError):
        required[0] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        JsonSchema({"bad": object()})


class Review(BaseModel):
    severity: Literal["low", "high"]
    count: int


class ReviewList(RootModel[list[Review]]):
    pass


def test_pydantic_output_adapter_schema_success_and_failure() -> None:
    adapter = prepare_output_adapter(Review)
    wire = adapter.output_format
    assert wire is not None
    assert wire.type == "json_schema"
    assert wire.schema_["type"] == "object"

    success = adapter.adapt({"severity": "high", "count": 2})
    assert success.output == Review(severity="high", count=2)
    assert success.structured_output == {"severity": "high", "count": 2}
    assert success.validation_error is None

    failure = adapter.adapt({"severity": "unknown", "count": 2})
    assert failure.output is None
    assert failure.structured_output == {"severity": "unknown", "count": 2}
    assert isinstance(failure.validation_error, ValidationError)

    missing = adapter.adapt(None)
    assert missing.output is None
    assert isinstance(missing.validation_error, ValidationError)


def test_json_schema_output_adapter_and_bad_output_argument() -> None:
    adapter = prepare_output_adapter(JsonSchema({"type": "object"}))
    adapted = adapter.adapt({"summary": "ok"})
    assert adapted.output == {"summary": "ok"}
    assert adapted.structured_output == {"summary": "ok"}
    assert adapted.output is not adapted.structured_output
    adapted.output["summary"] = "changed"
    assert adapted.structured_output == {"summary": "ok"}
    with pytest.raises(TypeError):
        adapter.adapt(["not", "an", "object"])
    with pytest.raises(TypeError):
        prepare_output_adapter(str)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array", "items": {"type": "string"}},
        {"type": "string"},
        {"properties": {"summary": {"type": "string"}}},
    ],
)
def test_output_adapter_rejects_non_object_json_schemas(
    schema: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match="top-level object"):
        prepare_output_adapter(JsonSchema(schema))


def test_output_adapter_rejects_pydantic_root_list_model() -> None:
    with pytest.raises(TypeError, match="top-level object"):
        prepare_output_adapter(ReviewList)


def test_no_output_adapter_returns_empty_adaptation() -> None:
    adapted = prepare_output_adapter().adapt({"ignored": True})
    assert adapted.output is None
    assert adapted.structured_output is None
    assert adapted.validation_error is None


def test_tool_result_block_content_matches_protocol_blocks() -> None:
    json_content = {"nested": ["value"]}
    blocks = [
        TextBlock(text="done"),
        ImageBlock(
            source=Base64ImageSource(
                data=base64.b64encode(PNG).decode(), media_type="image/png"
            )
        ),
        DocumentBlock(source=TextDocumentSource(data="details")),
        json_content,
        ["nested", {"ok": True}],
        3,
        False,
        None,
    ]
    result = ToolResultBlock(tool_use_id="tool-1", content=blocks)
    blocks.clear()
    json_content["nested"].append("changed")
    assert isinstance(result.content, tuple)
    assert [type(item) for item in result.content[:3]] == [
        TextBlock,
        ImageBlock,
        DocumentBlock,
    ]
    assert result.content[3:] == (
        {"nested": ("value",)},
        ("nested", {"ok": True}),
        3,
        False,
        None,
    )
    assert isinstance(result.content[3], MappingProxyType)

    text = ToolResultBlock(tool_use_id="tool-2", content="plain")
    assert text.content == "plain"

    with pytest.raises(TypeError):
        ToolResultBlock(tool_use_id="tool-3", content=[object()])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        ToolResultBlock(tool_use_id="tool-4", content=[float("nan")])


def test_stream_tool_result_json_content_is_recursively_immutable() -> None:
    content = [{"nested": ["value"]}]
    result = ToolResult(
        tool_use_id="tool-1",
        tool_name="Read",
        content=content,
        is_error=False,
    )
    content[0]["nested"].append("changed")
    assert result.content == ({"nested": ("value",)},)
    assert isinstance(result.content[0], MappingProxyType)


def test_mcp_status_changed_uses_concrete_status_models() -> None:
    servers = [
        McpServerStatusInfo(
            name="local",
            status=McpServerStatus.CONNECTED,
            source="project",
            is_managed=False,
            server_type=McpServerType.STDIO,
        )
    ]
    summary = McpStatusSummary(
        total=1,
        connected=1,
        connecting=0,
        failed=0,
        config_error=McpConfigError(path="/repo/.factory/mcp.json", message="bad"),
    )
    changed = McpStatusChanged(servers=servers, summary=summary)
    servers.clear()
    assert changed.servers[0].name == "local"
    assert changed.summary is summary
    with pytest.raises(dataclasses.FrozenInstanceError):
        changed.servers[0].name = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        changed.summary.config_error.message = "changed"  # type: ignore[union-attr,misc]


def test_permission_actions_preserve_details_defaults_and_plan() -> None:
    tool_use = ToolUseBlock(id="tool-1", name="ApplyPatch", input={})
    patch_file = ApplyPatchFile(
        file_path="/repo/a.py",
        file_name="a.py",
        operation="update",
        old_content="old",
        new_content="new",
    )
    patch = ApplyPatchAction(
        tool_use=tool_use,
        file_path="/repo/a.py",
        file_name="a.py",
        patch_content="*** Begin Patch",
        old_content="old",
        new_content="new",
        files=[patch_file],
    )
    assert patch.files == (patch_file,)

    ask = AskUserAction(
        tool_use=tool_use,
        questionnaire="invalid questionnaire",
        questions=[],
        parse_error=AskUserParseError(message="invalid JSON", line=3),
    )
    assert ask.parse_error == AskUserParseError(message="invalid JSON", line=3)

    mcp = McpToolAction(
        tool_use=tool_use,
        tool_name="search",
        impact_level="low",
    )
    assert mcp.server_name is None
    assert mcp.actual_tool_name is None

    sandbox = SandboxViolationAction(
        tool_use=tool_use,
        violating_tool_name="Execute",
        target="/outside",
        operation=SandboxOperation.WRITE,
        violation_type=SandboxViolationType.FILESYSTEM_WRITE,
        reason="outside sandbox",
        is_org_deny=False,
    )
    assert sandbox.violation_reason is None

    request = PermissionRequest(
        actions=[
            ExitSpecModeAction(
                tool_use=tool_use,
                plan="Implement the change.",
                title="Implementation",
            )
        ],
        options=[],
    )
    assert request.plan is not None
    assert request.plan.text == "Implement the change."
    assert request.plan.title == "Implementation"


def test_every_permission_action_variant_fields_and_defaults() -> None:
    tool_use = ToolUseBlock(id="tool-1", name="tool", input={})

    edit = EditAction(tool_use=tool_use, file_path="/repo/a.py", file_name="a.py")
    assert edit.old_content is None
    assert edit.new_content is None
    assert edit.confirmation_type is ToolConfirmationType.EDIT

    commands = ["git", "status"]
    execute = ExecuteAction(
        tool_use=tool_use,
        full_command="git status",
        command="git",
        extracted_commands=commands,
    )
    commands.clear()
    assert execute.extracted_commands == ("git", "status")
    assert execute.impact_level is None
    assert execute.risk_level_reason is None

    create = CreateFile(
        tool_use=tool_use,
        file_path="/repo/new.py",
        file_name="new.py",
        content="pass\n",
    )
    assert create.confirmation_type is ToolConfirmationType.CREATE

    ask = AskUserAction(tool_use=tool_use, questionnaire="questionnaire")
    assert ask.questions == ()
    assert ask.parse_error is None

    exit_spec = ExitSpecModeAction(tool_use=tool_use, plan="Implement")
    assert exit_spec.title is None

    patch = ApplyPatchAction(
        tool_use=tool_use,
        file_path="/repo/a.py",
        file_name="a.py",
        patch_content="patch",
    )
    assert patch.old_content is None
    assert patch.new_content is None
    assert patch.files is None

    mcp = McpToolAction(
        tool_use=tool_use,
        tool_name="search",
        impact_level="low",
    )
    assert mcp.server_name is None
    assert mcp.actual_tool_name is None

    sandbox = SandboxViolationAction(
        tool_use=tool_use,
        violating_tool_name="Execute",
        target="/outside",
        operation=SandboxOperation.WRITE,
        violation_type=SandboxViolationType.FILESYSTEM_WRITE,
        reason="outside sandbox",
        is_org_deny=False,
    )
    assert sandbox.violation_reason is None

    shield = DroidShieldViolationAction(
        tool_use=tool_use,
        command="unsafe",
        reason="blocked",
    )
    assert shield.confirmation_type is ToolConfirmationType.DROID_SHIELD_VIOLATION


def test_tool_info_is_complete_and_immutable() -> None:
    tool = ToolInfo(
        id="Read",
        display_name="Read",
        description="Read a file",
        category=ToolCategory.READ,
        default_allowed=True,
        allowed=False,
    )
    assert tool.category is ToolCategory.READ
    assert tool.default_allowed
    assert not tool.allowed
    with pytest.raises(dataclasses.FrozenInstanceError):
        tool.allowed = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        ToolInfo(id="Read")  # type: ignore[call-arg]


def test_session_settings_require_model_and_reasoning_effort() -> None:
    settings = SessionSettings(
        model="claude-sonnet",
        reasoning_effort=ReasoningEffort.HIGH,
        disabled_tools={"Execute"},
    )
    assert settings.model == "claude-sonnet"
    assert settings.reasoning_effort is ReasoningEffort.HIGH
    assert settings.disabled_tools == frozenset({"Execute"})
    with pytest.raises(TypeError):
        SessionSettings()  # type: ignore[call-arg]


def test_structured_output_error_details_are_immutable() -> None:
    details = {"issues": [{"path": ["summary"]}]}
    error = StructuredOutputError(
        code="invalid_output",
        message="Output did not match schema",
        details=details,
    )
    details["issues"][0]["path"].append("changed")
    assert error.details == {"issues": ({"path": ("summary",)},)}
    assert isinstance(error.details, MappingProxyType)
    with pytest.raises(TypeError):
        StructuredOutputError("invalid_output", "bad", details=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StructuredOutputError("invalid_output", "bad", details=float("inf"))


def _terminal_kwargs() -> dict[str, object]:
    return {
        "text": "done",
        "messages": [],
        "usage": None,
        "duration": timedelta(seconds=1),
        "turn_count": 1,
        "session_id": "session-1",
    }


def test_terminal_result_invariants() -> None:
    success = RunSuccess(**_terminal_kwargs())  # type: ignore[arg-type]
    interrupted = RunInterrupted(**_terminal_kwargs())  # type: ignore[arg-type]
    assert success.subtype == "success"
    assert success.success and not success.interrupted
    assert success.error is None
    assert success.structured_output_error is None
    assert interrupted.subtype == "interrupted"
    assert not interrupted.success and interrupted.interrupted

    terminal_error = ErrorEvent(message="failed", error_type=ErrorType.ERROR)
    failure = RunFailure(
        subtype="error_during_execution",
        error=terminal_error,
        **_terminal_kwargs(),  # type: ignore[arg-type]
    )
    assert failure.error is terminal_error
    assert not failure.success and not failure.interrupted

    with pytest.raises(TypeError):
        RunSuccess(  # type: ignore[call-arg]
            error=terminal_error,
            **_terminal_kwargs(),
        )
    with pytest.raises(TypeError):
        RunInterrupted(  # type: ignore[call-arg]
            structured_output_error=StructuredOutputError("invalid", "bad"),
            **_terminal_kwargs(),
        )
    with pytest.raises(ValueError):
        RunFailure(  # type: ignore[arg-type]
            subtype="success",
            **_terminal_kwargs(),
        )


def test_run_result_is_a_runtime_generic_base() -> None:
    results = (
        RunSuccess(**_terminal_kwargs()),  # type: ignore[arg-type]
        RunInterrupted(**_terminal_kwargs()),  # type: ignore[arg-type]
        RunFailure(
            subtype="error_during_execution",
            **_terminal_kwargs(),  # type: ignore[arg-type]
        ),
    )
    assert all(isinstance(result, RunResult) for result in results)
    assert not isinstance(TextBlock(text="not terminal"), RunResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        results[0].text = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        RunResult()


class CollectingSink:
    def __init__(self) -> None:
        self.logs: list[LogEvent] = []
        self.metrics: list[MetricEvent] = []

    def log(self, event: LogEvent) -> None:
        self.logs.append(event)

    def record(self, event: MetricEvent) -> None:
        self.metrics.append(event)

    def inject(self, carrier: TraceContext) -> None:
        carrier.traceparent = "trace"
        carrier.tracestate = "state"


class BrokenSink:
    def log(self, event: LogEvent) -> None:
        raise RuntimeError

    def record(self, event: MetricEvent) -> None:
        raise RuntimeError

    def inject(self, carrier: TraceContext) -> None:
        carrier.traceparent = "partial"
        raise RuntimeError


def test_observability_shape_isolation_and_protocol_adapter() -> None:
    sink = CollectingSink()
    observability = Observability(logger=sink, metrics=sink, tracing=sink)
    attributes = {"safe": 1, "nested": {"secret": "removed"}}
    event = LogEvent(
        level="info",
        name="droid.sdk.test",
        message="safe",
        attributes=attributes,
    )
    attributes["safe"] = 2
    assert event.attributes == {"safe": 1}
    assert emit_log(observability, event)
    assert record_metric(
        observability,
        MetricEvent(
            name="count", kind="counter", value=1, unit="1", attributes={"ok": True}
        ),
    )
    carrier = TraceContext()
    assert inject_trace_context(observability, carrier)
    assert carrier.traceparent == "trace"

    broken = Observability(
        logger=BrokenSink(), metrics=BrokenSink(), tracing=BrokenSink()
    )
    assert not emit_log(broken, event)
    assert not record_metric(
        broken, MetricEvent(name="count", kind="counter", value=1, unit="1")
    )
    broken_carrier = TraceContext()
    assert not inject_trace_context(broken, broken_carrier)
    assert broken_carrier.traceparent is None

    adapter = ObservabilityAdapter(observability)
    metadata: dict[str, str] = {"existing": "value"}
    adapter.trace_meta_injector(metadata)
    adapter.timing_callback(ProtocolTiming("method", 0.5, "success"))
    assert metadata == {
        "existing": "value",
        "traceparent": "trace",
        "tracestate": "state",
    }
    assert sink.metrics[-1].attributes == {
        "method": "method",
        "outcome": "success",
    }


def test_runtime_normalization_and_transport_precedence() -> None:
    class Transport:
        is_connected = True

        async def connect(self) -> None: ...

        async def send(self, message: str) -> None: ...

        def read_messages(self) -> object:
            raise NotImplementedError

        async def close(self) -> None: ...

    env = {"KEY": "value"}
    runtime = Runtime(
        executable="droid",
        args=["--flag"],
        env=env,
        transport=Transport(),  # type: ignore[arg-type]
    )
    env["KEY"] = "changed"
    assert runtime.executable == Path("droid")
    assert runtime.args == ("--flag",)
    assert runtime.env == {"KEY": "value"}
    assert runtime.uses_supplied_transport


def test_environment_secrets_are_redacted_from_diagnostics() -> None:
    api_key = "sentinel-api-key-do-not-log"
    token = "sentinel-token-do-not-log"
    header_secret = "sentinel-header-do-not-log"
    oauth_secret = "sentinel-oauth-do-not-log"
    runtime = Runtime(env={"FACTORY_API_KEY": api_key})
    server = StdioMcpServerConfig(
        name="local",
        command="server",
        env={"ACCESS_TOKEN": token},
    )
    header = HttpHeader(name="Authorization", value=header_secret)
    oauth = McpOAuthOptions(client_id="client", client_secret=oauth_secret)

    assert runtime.env["FACTORY_API_KEY"] == api_key
    assert server.env["ACCESS_TOKEN"] == token
    assert tuple(runtime.env) == ("FACTORY_API_KEY",)
    assert tuple(server.env) == ("ACCESS_TOKEN",)
    with pytest.raises(TypeError):
        runtime.env["FACTORY_API_KEY"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        server.env["ACCESS_TOKEN"] = "changed"  # type: ignore[index]

    diagnostic_values = (
        repr(runtime),
        str(runtime),
        repr(server),
        str(server),
        repr(RuntimeError(repr(runtime))),
        repr(RuntimeError(repr(server))),
        repr(serialize_error(RuntimeError(repr(runtime)))),
        repr(header),
        repr(oauth),
        repr(
            LogEvent(
                level="error",
                name="droid.sdk.test",
                message="configuration failed",
                attributes={"runtime": repr(runtime), "server": repr(server)},
            )
        ),
    )
    assert all(api_key not in value for value in diagnostic_values)
    assert all(token not in value for value in diagnostic_values)
    assert all(header_secret not in value for value in diagnostic_values)
    assert all(oauth_secret not in value for value in diagnostic_values)
    assert "<redacted>" in repr(runtime)
    assert "<redacted>" in repr(server)


def test_public_enum_values() -> None:
    assert Mode.AUTO.value == "auto"
    assert ContextAccuracy.ESTIMATED.value == "estimated"
    assert ToolConfirmationOutcome.PROCEED_ALWAYS_EXACT_PATH.value == (
        "proceed_always_file"
    )


@pytest.mark.skipif(
    os.environ.get("DROID_LIVE_TESTS") != "1",
    reason="set DROID_LIVE_TESTS=1 to run examples against droid exec",
)
@pytest.mark.parametrize(
    "example",
    [
        "attachments.py",
        "factory_router.py",
        "observability.py",
        "structured_output_model.py",
    ],
)
def test_live_examples_execute(example: str) -> None:
    root = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "examples" / example)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout
