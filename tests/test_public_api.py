"""Exact v5 root and low-level namespace checks."""

from __future__ import annotations

import inspect

import droid_sdk
from droid_sdk import (
    Document,
    Image,
    McpServerStatus,
    ModelInfo,
    ModelProvider,
    Session,
    ToolConfirmationOutcome,
    ToolConfirmationType,
    list_models,
    list_sessions,
    run,
)
from droid_sdk.low_level import DroidClient, DroidClientTransport, ProcessTransport


def test_v5_entry_points_are_exported() -> None:
    assert droid_sdk.Session is Session
    assert droid_sdk.run is run
    assert droid_sdk.list_models is list_models
    assert droid_sdk.list_sessions is list_sessions
    assert {"Session", "run", "list_models", "list_sessions"} <= set(droid_sdk.__all__)


def test_root_exports_are_unique_and_present() -> None:
    assert len(droid_sdk.__all__) == len(set(droid_sdk.__all__))
    assert all(hasattr(droid_sdk, name) for name in droid_sdk.__all__)


def test_root_export_snapshot_is_exact() -> None:
    expected = {
        "MAX_ATTACHMENT_BYTES",
        "MAX_PDF_ATTACHMENT_BYTES",
        "ApplyPatchAction",
        "ApplyPatchFile",
        "AskUserAction",
        "AskUserParseError",
        "AssistantMessage",
        "Autonomy",
        "Base64ImageSource",
        "CompactOutcome",
        "ContentBlock",
        "ContextAccuracy",
        "ContextUsage",
        "ConversationMessage",
        "CreateFile",
        "Document",
        "DocumentBlock",
        "DocumentSource",
        "DroidConnectionError",
        "DroidError",
        "DroidProcessError",
        "DroidProtocolError",
        "DroidShieldViolationAction",
        "DroidTool",
        "EditAction",
        "ErrorEvent",
        "ErrorType",
        "ExecuteAction",
        "ExitSpecModeAction",
        "FrozenJsonObject",
        "FrozenJsonValue",
        "HookExecution",
        "HttpHeader",
        "HttpMcpServerConfig",
        "Image",
        "ImageBlock",
        "ImageMediaType",
        "InteractionHandlers",
        "InvalidAttachmentError",
        "InvalidWorkingDirectoryError",
        "JsonObject",
        "JsonSchema",
        "JsonValue",
        "ListToolsOptions",
        "McpAuthCompleted",
        "McpAuthOutcome",
        "McpAuthRequired",
        "McpConfigError",
        "McpMutationResult",
        "McpOAuthOptions",
        "McpServerConfig",
        "McpServerStatus",
        "McpServerStatusInfo",
        "McpServerType",
        "McpServersResult",
        "McpStatusChanged",
        "McpStatusSummary",
        "McpToolAction",
        "McpToolInfo",
        "McpToolInputSchema",
        "Message",
        "Mode",
        "ModelInfo",
        "ModelProvider",
        "OAuthTokenEndpointAuthMethod",
        "PdfDocumentSource",
        "PermissionAction",
        "PermissionHandler",
        "PermissionOption",
        "PermissionRequest",
        "PermissionResolved",
        "PermissionResponse",
        "Plan",
        "Question",
        "QuestionAnswer",
        "QuestionHandler",
        "QuestionRequest",
        "QuestionResponse",
        "ReasoningEffort",
        "RedactedThinkingBlock",
        "RewindEvictedFile",
        "RewindFileCreation",
        "RewindFileSnapshot",
        "RewindInfo",
        "RewindOutcome",
        "RunFailure",
        "RunInterrupted",
        "RunResult",
        "RunStream",
        "RunSuccess",
        "RunTimeoutError",
        "Runtime",
        "SandboxOperation",
        "SandboxSettings",
        "SandboxViolationAction",
        "SandboxViolationReason",
        "SandboxViolationType",
        "SavedSession",
        "SdkMcpServer",
        "SessionBusyError",
        "SessionClosedError",
        "SessionConfig",
        "SessionNotFoundError",
        "SessionNotOpenError",
        "Session",
        "SessionPlatform",
        "SessionReplacedError",
        "SessionReplacementError",
        "SessionSettings",
        "SessionSettingsUpdate",
        "SessionSource",
        "SessionTag",
        "SessionTitleUpdated",
        "SessionWorkingDirectoryChanged",
        "SettingsUpdated",
        "SkillInfo",
        "SkillMutationResult",
        "SkillResource",
        "SkillsResult",
        "SseMcpServerConfig",
        "StdioMcpServerConfig",
        "StreamEvent",
        "StreamIncompleteError",
        "StreamMessage",
        "StructuredOutputError",
        "SystemPromptConfig",
        "SystemPromptPreset",
        "TextBlock",
        "TextComplete",
        "TextDelta",
        "TextDocumentSource",
        "ThinkingBlock",
        "ThinkingComplete",
        "ThinkingDelta",
        "TokenUsageUpdate",
        "ToolCall",
        "ToolCallDelta",
        "ToolCategory",
        "ToolConfirmationOutcome",
        "ToolConfirmationType",
        "ToolInfo",
        "ToolProgress",
        "ToolProgressUpdate",
        "ToolResponse",
        "ToolResult",
        "ToolResultBlock",
        "ToolUseBlock",
        "Transport",
        "UpdateSettingsResult",
        "Usage",
        "UserMessage",
        "WorkingState",
        "WorkingStateChanged",
        "list_models",
        "list_sessions",
        "run",
        "__version__",
    }
    assert set(droid_sdk.__all__) == expected
    assert not hasattr(droid_sdk, "SessionError")


def test_enum_member_snapshots_are_exact() -> None:
    assert tuple(ToolConfirmationOutcome.__members__) == (
        "PROCEED_ONCE",
        "PROCEED_ALWAYS",
        "PROCEED_ALWAYS_EXACT_PATH",
        "PROCEED_AUTO_RUN",
        "PROCEED_AUTO_RUN_LOW",
        "PROCEED_AUTO_RUN_MEDIUM",
        "PROCEED_AUTO_RUN_HIGH",
        "PROCEED_NEW_SESSION",
        "PROCEED_NEW_SESSION_LOW",
        "PROCEED_NEW_SESSION_MEDIUM",
        "PROCEED_NEW_SESSION_HIGH",
        "PROCEED_EDIT",
        "PROCEED_ALWAYS_TOOLS",
        "PROCEED_ALWAYS_SERVER",
        "CANCEL",
    )
    assert tuple(ToolConfirmationType.__members__) == (
        "EDIT",
        "EXECUTE",
        "CREATE",
        "ASK_USER",
        "EXIT_SPEC_MODE",
        "APPLY_PATCH",
        "MCP_TOOL",
        "SANDBOX_VIOLATION",
        "DROID_SHIELD_VIOLATION",
    )
    assert tuple(McpServerStatus.__members__) == (
        "CONNECTING",
        "CONNECTED",
        "DISCONNECTED",
        "FAILED",
        "DISABLED",
    )
    assert tuple(ModelProvider.__members__) == (
        "ANTHROPIC",
        "OPENAI",
        "GENERIC_CHAT_COMPLETION_API",
        "FACTORY",
        "GOOGLE",
        "XAI",
        "VOYAGE",
    )


def test_exact_public_signatures_exclude_unsupported_extras() -> None:
    assert tuple(inspect.signature(list_models).parameters) == (
        "include_disabled",
        "cwd",
        "runtime",
        "api_key",
    )
    assert tuple(inspect.signature(list_sessions).parameters) == (
        "cwd",
        "all_workspaces",
        "limit",
    )
    assert not hasattr(Image, "from_file")
    assert not hasattr(Document, "from_file")
    assert "path" not in inspect.signature(Document.from_bytes).parameters
    for method in (
        Session.remove_mcp_server,
        Session.enable_mcp_server,
        Session.disable_mcp_server,
    ):
        assert "scope" not in inspect.signature(method).parameters


def test_legacy_low_level_names_are_absent_from_root() -> None:
    legacy = {
        "AssistantTextDelta",
        "DroidClient",
        "DroidClientTransport",
        "DroidQueryOptions",
        "DroidWorkingState",
        "MissionState",
        "ProcessTransport",
        "SessionNotificationType",
        "ThinkingTextDelta",
        "ToolUse",
        "TurnComplete",
        "query",
    }
    assert legacy.isdisjoint(droid_sdk.__all__)
    # Importing a submodule makes Python attach it to its parent package.
    assert all(not hasattr(droid_sdk, name) for name in legacy if name != "query")


def test_mission_and_daemon_surfaces_are_absent() -> None:
    assert not any("Mission" in name or "Daemon" in name for name in droid_sdk.__all__)


def test_low_level_escape_hatch() -> None:
    assert DroidClient is not None
    assert DroidClientTransport is not None
    assert ProcessTransport is not None


def test_model_info_is_public() -> None:
    assert droid_sdk.ModelInfo is ModelInfo
