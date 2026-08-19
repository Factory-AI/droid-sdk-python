"""Tests for client→server request/response schemas."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from droid_sdk.schemas.client import (
    AddMcpServerRequest,
    AddMcpServerRequestParams,
    AddMcpServerResult,
    AddUserMessageRequest,
    AddUserMessageRequestParams,
    AddUserMessageResult,
    AuthenticateMcpServerRequest,
    AuthenticateMcpServerResult,
    AvailableModelConfig,
    Base64ImageSource,
    CancelMcpAuthRequest,
    CancelMcpAuthResult,
    ClearMcpAuthRequest,
    ClearMcpAuthResult,
    ClientRequest,
    DocumentSource,
    ForkSessionRequestParams,
    GitRepoInfo,
    HttpHeader,
    HttpMcpConfig,
    InitializeSessionRequest,
    InitializeSessionRequestParams,
    InitializeSessionResult,
    InterruptSessionRequest,
    InterruptSessionResult,
    KillWorkerSessionRequest,
    KillWorkerSessionRequestParams,
    KillWorkerSessionResult,
    ListMcpRegistryRequest,
    ListMcpRegistryResult,
    ListMcpServersRequest,
    ListMcpServersResult,
    ListMcpToolsRequest,
    ListMcpToolsResult,
    ListSkillsRequest,
    ListSkillsResult,
    LoadSessionRequest,
    LoadSessionRequestParams,
    LoadSessionResult,
    MissionSnapshot,
    RemoveMcpServerRequest,
    RemoveMcpServerRequestParams,
    RemoveMcpServerResult,
    SessionSettings,
    SessionSource,
    SessionTag,
    SkillInfo,
    SkillResource,
    SseMcpConfig,
    StdioMcpConfig,
    SubmitBugReportRequest,
    SubmitBugReportRequestParams,
    SubmitBugReportResult,
    SubmitMcpAuthCodeRequest,
    SubmitMcpAuthCodeRequestParams,
    SubmitMcpAuthCodeResult,
    ToggleMcpServerRequest,
    ToggleMcpServerRequestParams,
    ToggleMcpServerResult,
    ToggleMcpToolRequest,
    ToggleMcpToolRequestParams,
    ToggleMcpToolResult,
    TokenUsage,
    UpdateSessionSettingsRequest,
    UpdateSessionSettingsRequestParams,
    UpdateSessionSettingsResult,
    WorkerStateInfo,
)
from droid_sdk.schemas.enums import (
    AutonomyLevel,
    AutonomyMode,
    DecompSessionType,
    DroidInteractionMode,
    JsonRpcErrorCode,
    McpServerType,
    MissionState,
    ModelProvider,
    ReasoningEffort,
    SettingsLevel,
    SkillLocation,
)
from droid_sdk.schemas.messages import Base64PDFSource, PlainTextSource
from droid_sdk.schemas.shared import (
    JsonRpcResponseFailure,
)

# ============================================================
# Helper: common envelope fields for building request JSON
# ============================================================

_BASE_ENVELOPE = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
    "type": "request",
    "id": "req-001",
}

_BASE_RESPONSE_SUCCESS_ENVELOPE = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
    "type": "response",
    "id": "req-001",
}

_FAILURE_RESPONSE = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
    "type": "response",
    "id": "req-001",
    "error": {
        "code": -32603,
        "message": "Internal error",
    },
}


# ============================================================
# Supporting types tests
# ============================================================


class TestBase64ImageSource:
    """Tests for Base64ImageSource."""

    def test_construction(self) -> None:
        img = Base64ImageSource(type="base64", data="abc123", media_type="image/png")
        assert img.type == "base64"
        assert img.data == "abc123"
        assert img.media_type == "image/png"

    def test_camel_case_serialization(self) -> None:
        img = Base64ImageSource(type="base64", data="abc", media_type="image/jpeg")
        d = img.model_dump(by_alias=True)
        assert "mediaType" in d
        assert d["mediaType"] == "image/jpeg"

    def test_camel_case_deserialization(self) -> None:
        img = Base64ImageSource.model_validate(
            {"type": "base64", "data": "x", "mediaType": "image/gif"}
        )
        assert img.media_type == "image/gif"

    def test_invalid_media_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Base64ImageSource(type="base64", data="x", media_type="video/mp4")  # type: ignore[arg-type]

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Base64ImageSource.model_validate(
                {"type": "base64", "data": "x", "mediaType": "image/png", "extra": "x"}
            )


class TestDocumentSource:
    """Tests for DocumentSource."""

    def test_pdf_source(self) -> None:
        doc = Base64PDFSource(
            type="base64", media_type="application/pdf", data="base64data"
        )
        assert doc.type == "base64"
        assert doc.media_type == "application/pdf"

    def test_text_source(self) -> None:
        doc = PlainTextSource(
            type="text", media_type="text/plain", data="hello", name="test.txt"
        )
        assert doc.name == "test.txt"

    def test_camel_case_roundtrip(self) -> None:
        doc = Base64PDFSource(type="base64", media_type="application/pdf", data="xyz")
        d = doc.model_dump(by_alias=True)
        assert "mediaType" in d
        doc2 = TypeAdapter(DocumentSource).validate_python(d)
        assert doc2.media_type == doc.media_type


class TestSessionTag:
    """Tests for SessionTag."""

    def test_construction(self) -> None:
        tag = SessionTag(name="mission:worker")
        assert tag.name == "mission:worker"
        assert tag.metadata is None

    def test_with_metadata(self) -> None:
        tag = SessionTag(name="test", metadata={"key": "val"})
        assert tag.metadata == {"key": "val"}


class TestSessionSource:
    """Tests for SessionSource."""

    def test_basic_source(self) -> None:
        src = SessionSource.model_validate(
            {"platform": "web", "delegationSessionId": "delegation-1"}
        )
        assert src.platform == "web"

    def test_extra_fields_allowed(self) -> None:
        """SessionSource allows platform-specific extra fields."""
        src = SessionSource.model_validate(
            {
                "platform": "slack",
                "delegationSessionId": "delegation-1",
                "teamId": "T123",
                "channel": "C456",
            }
        )
        assert src.platform == "slack"


class TestStdioMcpConfig:
    """Tests for StdioMcpConfig."""

    def test_construction(self) -> None:
        cfg = StdioMcpConfig(name="server1", command="npx", args=["-y", "pkg"])
        assert cfg.name == "server1"
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "pkg"]

    def test_defaults(self) -> None:
        cfg = StdioMcpConfig(name="s", command="cmd")
        assert cfg.args == []
        assert cfg.env == {}


class TestHttpMcpConfig:
    """Tests for HttpMcpConfig."""

    def test_construction(self) -> None:
        cfg = HttpMcpConfig(
            type="http",
            name="httpserver",
            url="https://example.com/mcp",
            headers=[HttpHeader(name="Authorization", value="Bearer token")],
        )
        assert cfg.type == "http"
        assert len(cfg.headers) == 1

    def test_defaults(self) -> None:
        cfg = HttpMcpConfig(type="http", name="s", url="https://x.com")
        assert cfg.headers == []


class TestSseMcpConfig:
    """Tests for SseMcpConfig."""

    def test_construction(self) -> None:
        cfg = SseMcpConfig(type="sse", name="sse-srv", url="https://x.com/sse")
        assert cfg.type == "sse"
        assert cfg.headers == []


class TestSessionSettings:
    """Tests for SessionSettings."""

    def test_minimal(self) -> None:
        s = SessionSettings(
            model_id="claude-sonnet-4",
            reasoning_effort=ReasoningEffort.Medium,
        )
        assert s.model_id == "claude-sonnet-4"
        assert s.autonomy_mode is None

    def test_camel_case(self) -> None:
        s = SessionSettings.model_validate(
            {"modelId": "gpt-4", "reasoningEffort": "high"}
        )
        assert s.model_id == "gpt-4"
        d = s.model_dump(by_alias=True)
        assert "modelId" in d
        assert "reasoningEffort" in d


class TestAvailableModelConfig:
    """Tests for AvailableModelConfig."""

    def test_full_construction(self) -> None:
        m = AvailableModelConfig(
            id="claude-sonnet-4",
            display_name="Claude Sonnet 4",
            short_display_name="Sonnet 4",
            model_provider=ModelProvider.ANTHROPIC,
            supported_reasoning_efforts=[ReasoningEffort.Medium, ReasoningEffort.High],
            default_reasoning_effort=ReasoningEffort.Medium,
            is_custom=False,
            supports_image_generation=True,
            tier="standard",
            token_multiplier=1.0,
            kind="chat",
        )
        assert m.id == "claude-sonnet-4"
        assert m.model_provider == ModelProvider.ANTHROPIC
        assert m.supports_image_generation is True
        assert m.kind == "chat"

    def test_camel_case_roundtrip(self) -> None:
        data = {
            "id": "m1",
            "displayName": "Model 1",
            "shortDisplayName": "M1",
            "modelProvider": "anthropic",
            "supportedReasoningEfforts": ["medium"],
            "defaultReasoningEffort": "medium",
        }
        m = AvailableModelConfig.model_validate(data)
        assert m.display_name == "Model 1"
        d = m.model_dump(by_alias=True)
        assert d["displayName"] == "Model 1"
        assert d["shortDisplayName"] == "M1"


class TestTokenUsage:
    """Tests for TokenUsage."""

    def test_construction(self) -> None:
        t = TokenUsage(
            input_tokens=100,
            output_tokens=200,
            cache_creation_tokens=10,
            cache_read_tokens=20,
            thinking_tokens=50,
        )
        assert t.input_tokens == 100

    def test_camel_case(self) -> None:
        t = TokenUsage.model_validate(
            {
                "inputTokens": 1,
                "outputTokens": 2,
                "cacheCreationTokens": 3,
                "cacheReadTokens": 4,
                "thinkingTokens": 5,
            }
        )
        d = t.model_dump(by_alias=True)
        assert d["inputTokens"] == 1
        assert d["thinkingTokens"] == 5


class TestGitRepoInfo:
    """Tests for GitRepoInfo."""

    def test_construction(self) -> None:
        g = GitRepoInfo.model_validate({"repoName": "my-repo", "owner": "me"})
        assert g.repo_name == "my-repo"
        assert g.owner == "me"

    def test_optional_owner(self) -> None:
        g = GitRepoInfo.model_validate({"repoName": "repo"})
        assert g.owner is None


class TestWorkerStateInfo:
    """Tests for WorkerStateInfo."""

    def test_construction(self) -> None:
        w = WorkerStateInfo.model_validate(
            {
                "startedAt": "2024-01-01T00:00:00Z",
                "completedAt": "2024-01-01T01:00:00Z",
                "exitCode": 0,
            }
        )
        assert w.started_at == "2024-01-01T00:00:00Z"
        assert w.exit_code == 0


class TestSkillInfo:
    """Tests for SkillInfo."""

    def test_construction(self) -> None:
        s = SkillInfo(
            name="test-skill",
            location=SkillLocation.Project,
            file_path="/path/to/skill",
        )
        assert s.name == "test-skill"
        assert s.description is None

    def test_with_resources(self) -> None:
        s = SkillInfo(
            name="s",
            location=SkillLocation.Personal,
            file_path="/p",
            resources=[
                SkillResource(name="README.md", path="/p/README.md", type="reference"),
            ],
        )
        assert len(s.resources) == 1  # type: ignore[arg-type]
        assert s.resources[0].type == "reference"  # type: ignore[index]


# ============================================================
# Request params tests
# ============================================================


class TestInitializeSessionRequestParams:
    """Tests for InitializeSessionRequestParams."""

    def test_minimal(self) -> None:
        p = InitializeSessionRequestParams(machine_id="m1", cwd="/home/user")
        assert p.machine_id == "m1"
        assert p.cwd == "/home/user"
        assert p.workspace_id is None
        assert p.mcp_servers is None
        assert p.autonomy_mode is None
        assert p.tags is None

    def test_all_optional_params(self) -> None:
        """VAL-SCHEMA-005: Construction with all optional fields succeeds."""
        p = InitializeSessionRequestParams(
            machine_id="m1",
            cwd="/home",
            workspace_id="ws-1",
            session_id="sess-1",
            mcp_servers=[
                StdioMcpConfig(name="s", command="cmd"),
                HttpMcpConfig(type="http", name="h", url="https://x.com"),
            ],
            autonomy_mode=AutonomyMode.AutoHigh,
            interaction_mode=DroidInteractionMode.Auto,
            autonomy_level=AutonomyLevel.High,
            model_id="claude-sonnet-4",
            reasoning_effort=ReasoningEffort.High,
            system_prompt={
                "type": "preset",
                "preset": "droid",
                "append": "Prefer focused answers.",
            },
            spec_mode_model_id="claude-opus-4",
            spec_mode_reasoning_effort=ReasoningEffort.Max,
            decomp_session_type=DecompSessionType.Orchestrator,
            decomp_mission_id="mission-1",
            skip_permissions_unsafe=True,
            enabled_tool_ids=["slackPostMessageTool"],
            session_location="linear://issue/123",
            session_source=SessionSource.model_validate(
                {"platform": "web", "delegationSessionId": "delegation-1"}
            ),
            tags=[SessionTag(name="mission:worker")],
            mcp_oauth_callback_uri="https://example.com/callback",
        )
        # Verify all optional fields are set
        assert p.workspace_id == "ws-1"
        assert p.session_id == "sess-1"
        assert p.mcp_servers is not None and len(p.mcp_servers) == 2
        assert p.autonomy_mode == AutonomyMode.AutoHigh
        assert p.interaction_mode == DroidInteractionMode.Auto
        assert p.autonomy_level == AutonomyLevel.High
        assert p.model_id == "claude-sonnet-4"
        assert p.reasoning_effort == ReasoningEffort.High
        assert p.system_prompt is not None
        assert p.spec_mode_model_id == "claude-opus-4"
        assert p.spec_mode_reasoning_effort == ReasoningEffort.Max
        assert p.decomp_session_type == DecompSessionType.Orchestrator
        assert p.decomp_mission_id == "mission-1"
        assert p.skip_permissions_unsafe is True
        assert p.enabled_tool_ids == ["slackPostMessageTool"]
        assert p.session_location == "linear://issue/123"
        assert p.session_source is not None
        assert p.tags is not None and len(p.tags) == 1
        assert p.mcp_oauth_callback_uri == "https://example.com/callback"

    def test_camel_case_serialization_includes_all_fields(self) -> None:
        """VAL-SCHEMA-005: JSON output includes every field."""
        p = InitializeSessionRequestParams(
            machine_id="m1",
            cwd="/home",
            workspace_id="ws-1",
            session_id="s-1",
            autonomy_mode=AutonomyMode.Normal,
            interaction_mode=DroidInteractionMode.Auto,
            autonomy_level=AutonomyLevel.Low,
            model_id="m",
            reasoning_effort=ReasoningEffort.Low,
            system_prompt="  Keep this exact.\n",
            spec_mode_model_id="sm",
            spec_mode_reasoning_effort=ReasoningEffort.Medium,
            decomp_session_type=DecompSessionType.Worker,
            decomp_mission_id="dm",
            skip_permissions_unsafe=False,
            enabled_tool_ids=["t1"],
            session_location="loc",
            session_source=SessionSource.model_validate(
                {"platform": "api", "delegationSessionId": "delegation-1"}
            ),
            tags=[SessionTag(name="tag1")],
            mcp_oauth_callback_uri="https://cb.com",
        )
        json_str = p.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)
        expected_keys = {
            "machineId",
            "cwd",
            "workspaceId",
            "sessionId",
            "autonomyMode",
            "interactionMode",
            "autonomyLevel",
            "modelId",
            "reasoningEffort",
            "systemPrompt",
            "specModeModelId",
            "specModeReasoningEffort",
            "decompSessionType",
            "decompMissionId",
            "skipPermissionsUnsafe",
            "enabledToolIds",
            "sessionLocation",
            "sessionSource",
            "tags",
            "mcpOAuthCallbackUri",
        }
        for key in expected_keys:
            assert key in parsed, f"Missing key: {key}"

    def test_camel_case_deserialization(self) -> None:
        """VAL-SCHEMA-012: Parse camelCase JSON succeeds."""
        p = InitializeSessionRequestParams.model_validate(
            {
                "machineId": "m1",
                "cwd": "/home",
                "modelId": "claude-sonnet-4",
                "reasoningEffort": "high",
            }
        )
        assert p.machine_id == "m1"
        assert p.model_id == "claude-sonnet-4"

    @pytest.mark.parametrize(
        ("system_prompt", "expected"),
        [
            ("  Replacement prompt.\n", "  Replacement prompt.\n"),
            (
                {
                    "type": "preset",
                    "preset": "droid",
                    "append": "  Appended prompt.\n",
                },
                {
                    "type": "preset",
                    "preset": "droid",
                    "append": "  Appended prompt.\n",
                },
            ),
        ],
    )
    def test_system_prompt_serializes_exactly(
        self,
        system_prompt: object,
        expected: object,
    ) -> None:
        params = InitializeSessionRequestParams.model_validate(
            {
                "machineId": "m1",
                "cwd": "/home",
                "systemPrompt": system_prompt,
            }
        )
        assert (
            params.model_dump(
                by_alias=True,
                exclude_none=True,
            )["systemPrompt"]
            == expected
        )

    @pytest.mark.parametrize(
        "system_prompt",
        [
            "",
            " \n\t ",
            {"type": "preset", "preset": "droid", "append": ""},
            {"type": "preset", "preset": "droid", "append": " \n\t "},
            {"type": "preset", "preset": "droid"},
            {"type": "preset", "preset": "unknown", "append": "prompt"},
            {
                "type": "preset",
                "preset": "droid",
                "append": "prompt",
                "extra": True,
            },
        ],
    )
    def test_system_prompt_rejects_invalid_values(
        self,
        system_prompt: object,
    ) -> None:
        with pytest.raises(ValidationError):
            InitializeSessionRequestParams.model_validate(
                {
                    "machineId": "m1",
                    "cwd": "/home",
                    "systemPrompt": system_prompt,
                }
            )

    @pytest.mark.parametrize(
        ("schema", "payload"),
        [
            (
                LoadSessionRequestParams,
                {"sessionId": "session", "systemPrompt": "Not loadable."},
            ),
            (
                ForkSessionRequestParams,
                {"systemPrompt": "Not forkable."},
            ),
            (
                UpdateSessionSettingsRequestParams,
                {"systemPrompt": "Not updatable."},
            ),
        ],
    )
    def test_system_prompt_is_creation_only(
        self,
        schema: type[object],
        payload: dict[str, object],
    ) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(schema).validate_python(payload)


class TestLoadSessionRequestParams:
    def test_construction(self) -> None:
        p = LoadSessionRequestParams(session_id="sess-123")
        assert p.session_id == "sess-123"
        assert p.mcp_servers is None


class TestAddUserMessageRequestParams:
    def test_with_images_and_files(self) -> None:
        p = AddUserMessageRequestParams(
            text="Hello",
            images=[
                Base64ImageSource(type="base64", data="abc", media_type="image/png"),
            ],
            files=[
                PlainTextSource(type="text", media_type="text/plain", data="content"),
            ],
        )
        assert p.text == "Hello"
        assert p.images is not None and len(p.images) == 1
        assert p.files is not None and len(p.files) == 1

    def test_optional_message_id(self) -> None:
        p = AddUserMessageRequestParams(text="Hi", message_id="msg-1")
        assert p.message_id == "msg-1"


class TestKillWorkerSessionRequestParams:
    def test_construction(self) -> None:
        p = KillWorkerSessionRequestParams(worker_session_id="ws-1")
        assert p.worker_session_id == "ws-1"


class TestUpdateSessionSettingsRequestParams:
    def test_partial_update(self) -> None:
        p = UpdateSessionSettingsRequestParams(model_id="claude-sonnet-4")
        assert p.model_id == "claude-sonnet-4"
        assert p.reasoning_effort is None
        assert p.autonomy_mode is None


class TestToggleMcpServerRequestParams:
    def test_construction(self) -> None:
        p = ToggleMcpServerRequestParams(
            server_name="my-server",
            enabled=True,
            settings_level=SettingsLevel.User,
        )
        assert p.server_name == "my-server"
        assert p.enabled is True
        assert p.settings_level == SettingsLevel.User


class TestSubmitMcpAuthCodeRequestParams:
    def test_construction(self) -> None:
        p = SubmitMcpAuthCodeRequestParams(
            server_name="s1", code="abc123", state="state-xyz"
        )
        assert p.server_name == "s1"
        assert p.code == "abc123"
        assert p.state == "state-xyz"


class TestAddMcpServerRequestParams:
    def test_stdio_config(self) -> None:
        p = AddMcpServerRequestParams(
            name="my-server",
            type=McpServerType.Stdio,
            command="npx",
            args=["-y", "pkg"],
            env={"KEY": "VAL"},
        )
        assert p.type == McpServerType.Stdio
        assert p.command == "npx"

    def test_http_config(self) -> None:
        p = AddMcpServerRequestParams(
            name="my-http",
            type=McpServerType.Http,
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer token"},
        )
        assert p.type == McpServerType.Http
        assert p.url == "https://example.com/mcp"


class TestRemoveMcpServerRequestParams:
    def test_construction(self) -> None:
        p = RemoveMcpServerRequestParams(
            server_name="s1",
            settings_level=SettingsLevel.User,
        )
        assert p.server_name == "s1"


class TestToggleMcpToolRequestParams:
    def test_construction(self) -> None:
        p = ToggleMcpToolRequestParams(
            server_name="s1", tool_name="tool1", enabled=False
        )
        assert p.tool_name == "tool1"
        assert p.enabled is False


class TestSubmitBugReportRequestParams:
    def test_construction(self) -> None:
        p = SubmitBugReportRequestParams(
            user_comment="Bug found", client_logs="[log data]"
        )
        assert p.user_comment == "Bug found"
        assert p.client_logs == "[log data]"


# ============================================================
# Request schema tests (method literal enforcement + roundtrip)
# ============================================================

# Map of all 19 request types with their method, params, and class
_ALL_REQUESTS: list[tuple[type[object], str, dict[str, object]]] = [
    (
        InitializeSessionRequest,
        "droid.initialize_session",
        {"machineId": "m1", "cwd": "/home"},
    ),
    (
        LoadSessionRequest,
        "droid.load_session",
        {"sessionId": "s-1"},
    ),
    (
        AddUserMessageRequest,
        "droid.add_user_message",
        {"text": "Hello"},
    ),
    (
        InterruptSessionRequest,
        "droid.interrupt_session",
        {},
    ),
    (
        KillWorkerSessionRequest,
        "droid.kill_worker_session",
        {"workerSessionId": "ws-1"},
    ),
    (
        UpdateSessionSettingsRequest,
        "droid.update_session_settings",
        {},
    ),
    (
        ToggleMcpServerRequest,
        "droid.toggle_mcp_server",
        {"serverName": "s1", "enabled": True, "settingsLevel": "user"},
    ),
    (
        AuthenticateMcpServerRequest,
        "droid.authenticate_mcp_server",
        {"serverName": "s1"},
    ),
    (
        CancelMcpAuthRequest,
        "droid.cancel_mcp_auth",
        {"serverName": "s1"},
    ),
    (
        ClearMcpAuthRequest,
        "droid.clear_mcp_auth",
        {"serverName": "s1"},
    ),
    (
        SubmitMcpAuthCodeRequest,
        "droid.submit_mcp_auth_code",
        {"serverName": "s1", "code": "abc", "state": "xyz"},
    ),
    (
        AddMcpServerRequest,
        "droid.add_mcp_server",
        {"name": "s1", "type": "stdio", "command": "npx"},
    ),
    (
        RemoveMcpServerRequest,
        "droid.remove_mcp_server",
        {"serverName": "s1", "settingsLevel": "user"},
    ),
    (
        ListMcpRegistryRequest,
        "droid.list_mcp_registry",
        {},
    ),
    (
        ListMcpToolsRequest,
        "droid.list_mcp_tools",
        {},
    ),
    (
        ListMcpServersRequest,
        "droid.list_mcp_servers",
        {},
    ),
    (
        ToggleMcpToolRequest,
        "droid.toggle_mcp_tool",
        {"serverName": "s1", "toolName": "t1", "enabled": True},
    ),
    (
        ListSkillsRequest,
        "droid.list_skills",
        {},
    ),
    (
        SubmitBugReportRequest,
        "droid.submit_bug_report",
        {"userComment": "Bug!"},
    ),
]


class TestRequestMethodLiterals:
    """VAL-SCHEMA-004: Each request enforces its method as a literal string."""

    @pytest.mark.parametrize(
        "request_cls,method,params",
        _ALL_REQUESTS,
        ids=[r[1].split(".")[-1] for r in _ALL_REQUESTS],
    )
    def test_correct_method_accepted(
        self,
        request_cls: type[object],
        method: str,
        params: dict[str, object],
    ) -> None:
        """Constructing with the correct method literal succeeds."""
        data = {
            **_BASE_ENVELOPE,
            "method": method,
            "params": params,
        }
        req = request_cls.model_validate(data)  # type: ignore[attr-defined]
        assert req.method == method  # type: ignore[union-attr]

    @pytest.mark.parametrize(
        "request_cls,method,params",
        _ALL_REQUESTS,
        ids=[r[1].split(".")[-1] for r in _ALL_REQUESTS],
    )
    def test_wrong_method_raises_validation_error(
        self,
        request_cls: type[object],
        method: str,
        params: dict[str, object],
    ) -> None:
        """Wrong method literal raises ValidationError."""
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.wrong_method",
            "params": params,
        }
        with pytest.raises(ValidationError):
            request_cls.model_validate(data)  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "request_cls,method,params",
        _ALL_REQUESTS,
        ids=[r[1].split(".")[-1] for r in _ALL_REQUESTS],
    )
    def test_json_roundtrip(
        self,
        request_cls: type[object],
        method: str,
        params: dict[str, object],
    ) -> None:
        """model == Model.model_validate_json(model.model_dump_json()) holds."""
        data = {
            **_BASE_ENVELOPE,
            "method": method,
            "params": params,
        }
        req = request_cls.model_validate(data)  # type: ignore[attr-defined]
        json_str = req.model_dump_json(by_alias=True)  # type: ignore[union-attr]
        req2 = request_cls.model_validate_json(json_str)  # type: ignore[attr-defined]
        assert req == req2  # type: ignore[union-attr]


class TestRequestCount:
    """Verify we have exactly 19 request types."""

    def test_19_request_types(self) -> None:
        assert len(_ALL_REQUESTS) == 19


# ============================================================
# ClientRequest discriminated union tests
# ============================================================


class TestClientRequest:
    """VAL-SCHEMA-004: ClientRequest discriminated union dispatches all 19 types."""

    @pytest.mark.parametrize(
        "request_cls,method,params",
        _ALL_REQUESTS,
        ids=[r[1].split(".")[-1] for r in _ALL_REQUESTS],
    )
    def test_dispatch_all_19_types(
        self,
        request_cls: type[object],
        method: str,
        params: dict[str, object],
    ) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": method,
            "params": params,
        }
        client_req = ClientRequest.model_validate(data)
        assert isinstance(client_req.root, request_cls)

    def test_unknown_method_rejected(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.unknown_method",
            "params": {},
        }
        with pytest.raises(ValidationError):
            ClientRequest.model_validate(data)


# ============================================================
# Response schema tests (success + failure variants)
# ============================================================


class TestInitializeSessionResponse:
    """VAL-SCHEMA-006: Response union accepts success and failure."""

    def test_success_variant(self) -> None:
        data = {
            **_BASE_RESPONSE_SUCCESS_ENVELOPE,
            "result": {
                "sessionId": "s-1",
                "session": {"messages": []},
                "settings": {"modelId": "m1", "reasoningEffort": "medium"},
            },
        }
        # Parse as success type
        from droid_sdk.schemas.client import (
            _InitializeSessionResponseSuccess,
        )

        resp = _InitializeSessionResponseSuccess.model_validate(data)
        assert resp.result.session_id == "s-1"
        assert isinstance(resp.result, InitializeSessionResult)

    def test_failure_variant(self) -> None:
        resp = JsonRpcResponseFailure.model_validate(_FAILURE_RESPONSE)
        assert resp.error.code == JsonRpcErrorCode.INTERNAL_ERROR

    def test_success_with_all_fields(self) -> None:
        from droid_sdk.schemas.client import (
            _InitializeSessionResponseSuccess,
        )

        data = {
            **_BASE_RESPONSE_SUCCESS_ENVELOPE,
            "result": {
                "sessionId": "s-1",
                "session": {"messages": []},
                "settings": {"modelId": "m1", "reasoningEffort": "medium"},
                "gitRepo": {"repoName": "my-repo", "owner": "me"},
                "availableModels": [
                    {
                        "id": "claude-sonnet-4",
                        "displayName": "Claude Sonnet 4",
                        "shortDisplayName": "Sonnet 4",
                        "modelProvider": "anthropic",
                        "supportedReasoningEfforts": ["medium", "high"],
                        "defaultReasoningEffort": "medium",
                    }
                ],
            },
        }
        resp = _InitializeSessionResponseSuccess.model_validate(data)
        assert resp.result.git_repo is not None
        assert resp.result.git_repo.repo_name == "my-repo"
        assert resp.result.available_models is not None
        assert len(resp.result.available_models) == 1


class TestLoadSessionResponse:
    """Tests for LoadSessionResponse."""

    def test_success_minimal(self) -> None:
        from droid_sdk.schemas.client import _LoadSessionResponseSuccess

        data = {
            **_BASE_RESPONSE_SUCCESS_ENVELOPE,
            "result": {
                "session": {"messages": []},
                "settings": {"modelId": "m1", "reasoningEffort": "medium"},
            },
        }
        resp = _LoadSessionResponseSuccess.model_validate(data)
        assert isinstance(resp.result, LoadSessionResult)

    def test_success_with_optional_fields(self) -> None:
        from droid_sdk.schemas.client import _LoadSessionResponseSuccess

        data = {
            **_BASE_RESPONSE_SUCCESS_ENVELOPE,
            "result": {
                "session": {"messages": []},
                "settings": {"modelId": "m1", "reasoningEffort": "medium"},
                "isAgentLoopInProgress": True,
                "cwd": "/home/user",
                "callingSessionId": "cs-1",
                "callingToolUseId": "ct-1",
                "decompSessionType": "worker",
                "tokenUsage": {
                    "inputTokens": 100,
                    "outputTokens": 200,
                    "cacheCreationTokens": 10,
                    "cacheReadTokens": 20,
                    "thinkingTokens": 50,
                },
            },
        }
        resp = _LoadSessionResponseSuccess.model_validate(data)
        assert resp.result.is_agent_loop_in_progress is True
        assert resp.result.cwd == "/home/user"
        assert resp.result.calling_session_id == "cs-1"
        assert resp.result.decomp_session_type == DecompSessionType.Worker
        assert resp.result.token_usage is not None
        assert resp.result.token_usage.input_tokens == 100


class TestMissionSnapshot:
    """Tests for MissionSnapshot."""

    def test_construction(self) -> None:
        data = {
            "state": "running",
            "features": [],
            "progressLog": [],
            "workerSessionIds": ["ws-1"],
            "workerStates": {
                "ws-1": {
                    "startedAt": "2024-01-01T00:00:00Z",
                },
            },
        }
        snap = MissionSnapshot.model_validate(data)
        assert snap.state == MissionState.Running
        assert len(snap.worker_session_ids) == 1


# ============================================================
# Result types for empty/simple responses
# ============================================================


class TestSimpleResults:
    """Tests for simple result types."""

    def test_empty_results(self) -> None:
        """Empty result types accept no fields."""
        AddUserMessageResult()
        InterruptSessionResult()
        KillWorkerSessionResult()
        UpdateSessionSettingsResult()

    def test_success_boolean_results(self) -> None:
        """Results with success boolean."""
        assert ToggleMcpServerResult(success=True).success is True
        assert AuthenticateMcpServerResult(success=False).success is False
        assert CancelMcpAuthResult(success=True).success is True
        assert ClearMcpAuthResult(success=True).success is True
        assert SubmitMcpAuthCodeResult(success=True).success is True
        assert AddMcpServerResult(success=True).success is True
        assert RemoveMcpServerResult(success=True).success is True
        assert ToggleMcpToolResult(success=True).success is True

    def test_bug_report_result(self) -> None:
        r = SubmitBugReportResult.model_validate({"bugReportId": "br-123"})
        assert r.bug_report_id == "br-123"


class TestListResults:
    """Tests for list result types."""

    def test_list_mcp_registry_result(self) -> None:
        r = ListMcpRegistryResult(servers=[])
        assert r.servers == []

    def test_list_mcp_tools_result(self) -> None:
        r = ListMcpToolsResult(tools=[])
        assert r.tools == []

    def test_list_mcp_servers_result(self) -> None:
        from droid_sdk.schemas.mcp import McpStatusSummary

        r = ListMcpServersResult(
            servers=[],
            summary=McpStatusSummary(total=0, connected=0, connecting=0, failed=0),
        )
        assert r.servers == []
        assert r.summary.total == 0

    def test_list_skills_result(self) -> None:
        r = ListSkillsResult(
            skills=[
                SkillInfo(name="test", location=SkillLocation.Project, file_path="/p"),
            ]
        )
        assert len(r.skills) == 1


# ============================================================
# Cross-cutting behavior tests
# ============================================================


class TestCamelCaseAliases:
    """VAL-SCHEMA-011: All models use camelCase aliases for JSON serialization."""

    def test_initialize_session_request_camel_case(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.initialize_session",
            "params": {"machineId": "m1", "cwd": "/home"},
        }
        req = InitializeSessionRequest.model_validate(data)
        d = req.model_dump(by_alias=True)
        # Check top-level keys
        assert "factoryApiVersion" in d
        # Check params keys
        assert d["params"]["machineId"] == "m1"

    def test_kill_worker_session_camel_case(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.kill_worker_session",
            "params": {"workerSessionId": "ws-1"},
        }
        req = KillWorkerSessionRequest.model_validate(data)
        d = req.model_dump(by_alias=True)
        assert d["params"]["workerSessionId"] == "ws-1"


class TestCamelCaseDeserialization:
    """VAL-SCHEMA-012: All models accept camelCase keys during deserialization."""

    def test_worker_session_id_from_camel_case(self) -> None:
        p = KillWorkerSessionRequestParams.model_validate({"workerSessionId": "abc"})
        assert p.worker_session_id == "abc"

    def test_toggle_mcp_server_from_camel_case(self) -> None:
        p = ToggleMcpServerRequestParams.model_validate(
            {"serverName": "s1", "enabled": True, "settingsLevel": "user"}
        )
        assert p.server_name == "s1"


class TestOptionalDefaults:
    """VAL-SCHEMA-013: Optional fields default to None; list/dict fields to empty."""

    def test_optional_fields_default_none(self) -> None:
        p = InitializeSessionRequestParams(machine_id="m1", cwd="/")
        assert p.workspace_id is None
        assert p.mcp_servers is None
        assert p.model_id is None
        assert p.tags is None

    def test_list_defaults(self) -> None:
        """StdioMcpConfig list/dict fields default to empty."""
        cfg = StdioMcpConfig(name="s", command="cmd")
        assert cfg.args == []
        assert cfg.env == {}

    def test_http_header_defaults(self) -> None:
        cfg = HttpMcpConfig(type="http", name="s", url="https://x.com")
        assert cfg.headers == []


class TestExtraFieldsBehavior:
    """VAL-SCHEMA-014: Request reject extra; response models allow them."""

    def test_request_params_extra_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InitializeSessionRequestParams.model_validate(
                {"machineId": "m1", "cwd": "/", "extraField": "bad"}
            )

    def test_result_extra_allowed(self) -> None:
        """Response result models tolerate unknown fields for protocol evolution."""
        r = ToggleMcpServerResult.model_validate({"success": True, "extraField": "ok"})
        assert r.success is True

    def test_session_settings_extra_allowed(self) -> None:
        """Nested response types tolerate unknown fields for protocol evolution."""
        s = SessionSettings.model_validate(
            {"modelId": "m", "reasoningEffort": "medium", "extra": "ok"}
        )
        assert s.model_id == "m"


class TestEnumFieldValidation:
    """VAL-SCHEMA-015: Enum fields accept valid strings, reject invalid strings."""

    def test_valid_enum_parsing(self) -> None:
        p = UpdateSessionSettingsRequestParams.model_validate(
            {"reasoningEffort": "high"}
        )
        assert p.reasoning_effort == ReasoningEffort.High

    def test_invalid_enum_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UpdateSessionSettingsRequestParams.model_validate(
                {"reasoningEffort": "bogus"}
            )

    def test_valid_settings_level(self) -> None:
        p = ToggleMcpServerRequestParams.model_validate(
            {"serverName": "s1", "enabled": True, "settingsLevel": "user"}
        )
        assert p.settings_level == SettingsLevel.User

    def test_invalid_settings_level(self) -> None:
        """SettingsLevel is restricted to Literal['user'] for MCP mutations."""
        with pytest.raises(ValidationError):
            ToggleMcpServerRequestParams.model_validate(
                {"serverName": "s1", "enabled": True, "settingsLevel": "org"}
            )


# ============================================================
# Response success/failure union parsing
# ============================================================

# Map response success classes to their result data for parameterized testing
_RESPONSE_PAIRS: list[tuple[str, type[object], dict[str, object]]] = [
    (
        "initialize_session",
        InitializeSessionResult,
        {
            "sessionId": "s1",
            "session": {"messages": []},
            "settings": {"modelId": "m", "reasoningEffort": "medium"},
        },
    ),
    (
        "load_session",
        LoadSessionResult,
        {
            "session": {"messages": []},
            "settings": {"modelId": "m", "reasoningEffort": "medium"},
        },
    ),
    ("add_user_message", AddUserMessageResult, {}),
    ("interrupt_session", InterruptSessionResult, {}),
    ("kill_worker_session", KillWorkerSessionResult, {}),
    ("update_session_settings", UpdateSessionSettingsResult, {}),
    ("toggle_mcp_server", ToggleMcpServerResult, {"success": True}),
    ("authenticate_mcp_server", AuthenticateMcpServerResult, {"success": True}),
    ("cancel_mcp_auth", CancelMcpAuthResult, {"success": True}),
    ("clear_mcp_auth", ClearMcpAuthResult, {"success": True}),
    ("submit_mcp_auth_code", SubmitMcpAuthCodeResult, {"success": True}),
    ("add_mcp_server", AddMcpServerResult, {"success": True}),
    ("remove_mcp_server", RemoveMcpServerResult, {"success": True}),
    (
        "list_mcp_registry",
        ListMcpRegistryResult,
        {"servers": []},
    ),
    (
        "list_mcp_tools",
        ListMcpToolsResult,
        {"tools": []},
    ),
    (
        "list_mcp_servers",
        ListMcpServersResult,
        {
            "servers": [],
            "summary": {"total": 0, "connected": 0, "connecting": 0, "failed": 0},
        },
    ),
    ("toggle_mcp_tool", ToggleMcpToolResult, {"success": True}),
    (
        "list_skills",
        ListSkillsResult,
        {"skills": []},
    ),
    (
        "submit_bug_report",
        SubmitBugReportResult,
        {"bugReportId": "br-1"},
    ),
]


class TestResponseSuccessVariants:
    """VAL-SCHEMA-006: Each response type accepts valid success JSON."""

    @pytest.mark.parametrize(
        "name,result_cls,result_data",
        _RESPONSE_PAIRS,
        ids=[r[0] for r in _RESPONSE_PAIRS],
    )
    def test_result_parses(
        self,
        name: str,
        result_cls: type[object],
        result_data: dict[str, object],
    ) -> None:
        result = result_cls.model_validate(result_data)  # type: ignore[attr-defined]
        assert result is not None


class TestResponseFailureVariant:
    """VAL-SCHEMA-006: Each response type accepts valid failure JSON."""

    def test_failure_parses(self) -> None:
        resp = JsonRpcResponseFailure.model_validate(_FAILURE_RESPONSE)
        assert resp.error.code == JsonRpcErrorCode.INTERNAL_ERROR
        assert resp.error.message == "Internal error"

    def test_failure_with_different_codes(self) -> None:
        for code in [-32700, -32600, -32601, -32602, -32603, -32001, -32004, -32005]:
            data = {
                **_FAILURE_RESPONSE,
                "error": {"code": code, "message": "Error"},
            }
            resp = JsonRpcResponseFailure.model_validate(data)
            assert resp.error.code.value == code


# ============================================================
# Full roundtrip tests (request → JSON → request)
# ============================================================


class TestFullRoundtrip:
    """Full JSON roundtrip tests for complex requests."""

    def test_initialize_session_full_roundtrip(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.initialize_session",
            "params": {
                "machineId": "m1",
                "cwd": "/home",
                "modelId": "claude-sonnet-4",
                "reasoningEffort": "high",
                "mcpServers": [
                    {"name": "s1", "command": "npx", "args": ["-y", "pkg"]},
                    {"type": "http", "name": "h1", "url": "https://x.com"},
                ],
                "tags": [{"name": "test-tag"}],
            },
        }
        req = InitializeSessionRequest.model_validate(data)
        json_str = req.model_dump_json(by_alias=True)
        req2 = InitializeSessionRequest.model_validate_json(json_str)
        assert req2.params.machine_id == "m1"
        assert req2.params.model_id == "claude-sonnet-4"

    def test_add_mcp_server_roundtrip(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.add_mcp_server",
            "params": {
                "name": "test-server",
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server"],
                "env": {"API_KEY": "secret"},
            },
        }
        req = AddMcpServerRequest.model_validate(data)
        json_str = req.model_dump_json(by_alias=True)
        req2 = AddMcpServerRequest.model_validate_json(json_str)
        assert req2.params.name == "test-server"
        assert req2.params.command == "npx"

    def test_submit_bug_report_roundtrip(self) -> None:
        data = {
            **_BASE_ENVELOPE,
            "method": "droid.submit_bug_report",
            "params": {
                "userComment": "Found a bug",
                "clientLogs": "[log data]",
            },
        }
        req = SubmitBugReportRequest.model_validate(data)
        json_str = req.model_dump_json(by_alias=True)
        req2 = SubmitBugReportRequest.model_validate_json(json_str)
        assert req2.params.user_comment == "Found a bug"
        assert req2.params.client_logs == "[log data]"
