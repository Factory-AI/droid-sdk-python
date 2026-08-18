"""Canonical conversions between wire schemas and public high-level models.

Every wire<->public conversion shared by more than one high-level module
lives here so each concept is converted in exactly one place.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from droid_sdk._high_level.attachments import (
    Document,
    PdfDocumentSource,
    TextDocumentSource,
)
from droid_sdk._high_level.config import (
    DroidSystemPrompt,
    SandboxSettings,
    SessionSettings,
    SessionSettingsUpdate,
    SessionSource,
    SessionTag,
    SystemPromptConfig,
)
from droid_sdk._high_level.enums import (
    Autonomy,
    McpServerStatus,
    McpServerType,
    Mode,
    ReasoningEffort,
    ToolCategory,
)
from droid_sdk._high_level.extensions import (
    HttpMcpServerConfig,
    McpConfigError,
    McpServerConfig,
    McpServerStatusInfo,
    McpStatusSummary,
    SdkMcpServer,
    StdioMcpServerConfig,
)
from droid_sdk._high_level.messages import McpStatusChanged, Usage
from droid_sdk.errors import DroidProtocolError
from droid_sdk.schemas.cli import (
    McpStatusChangedNotification,
    SessionNotification,
    SessionNotificationUnion,
    SettingsUpdatedPayload,
)
from droid_sdk.schemas.client import HttpHeader as WireHttpHeader
from droid_sdk.schemas.client import (
    HttpMcpConfig,
    SseMcpConfig,
    StdioMcpConfig,
)
from droid_sdk.schemas.client import McpOAuthOptions as WireMcpOAuthOptions
from droid_sdk.schemas.client import SessionSettings as WireSessionSettings
from droid_sdk.schemas.enums import ReasoningEffort as WireReasoningEffort
from droid_sdk.schemas.enums import SessionNotificationType
from droid_sdk.schemas.session import SystemPromptConfig as WireSystemPromptConfig
from droid_sdk.schemas.session import SystemPromptPreset as WireSystemPromptPreset

if TYPE_CHECKING:
    from droid_sdk.schemas.mcp import McpServerStatusInfo as WireMcpServerStatusInfo
    from droid_sdk.schemas.mcp import McpStatusSummary as WireMcpStatusSummary
    from droid_sdk.schemas.session import TokenUsage as WireTokenUsage

_NOTIFICATION_ADAPTER: TypeAdapter[SessionNotificationUnion] = TypeAdapter(
    SessionNotificationUnion
)
_KNOWN_NOTIFICATION_TYPES = frozenset(item.value for item in SessionNotificationType)


# ----------------------------------------------------------
# Outgoing: public values -> wire payloads
# ----------------------------------------------------------


def wire_reasoning(value: ReasoningEffort | None) -> WireReasoningEffort | None:
    return None if value is None else WireReasoningEffort(value.value)


def wire_source(value: SessionSource | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        key: item.value if isinstance(item, Enum) else item
        for key, item in (
            (field, getattr(value, field)) for field in value.__dataclass_fields__
        )
        if item is not None
    }


def wire_tags(values: Sequence[SessionTag]) -> list[dict[str, Any]]:
    return [
        {
            "name": value.name,
            **({} if value.metadata is None else {"metadata": dict(value.metadata)}),
        }
        for value in values
    ]


def wire_system_prompt(
    value: SystemPromptConfig | None,
) -> WireSystemPromptConfig | None:
    if value is None or isinstance(value, str):
        return value
    return WireSystemPromptPreset(
        type="preset",
        preset="droid",
        append=value.append,
    )


def system_prompt_from_wire(
    value: WireSystemPromptConfig | None,
) -> SystemPromptConfig | None:
    if value is None or isinstance(value, str):
        return value
    return DroidSystemPrompt(append=value.append)


def mcp_config_to_wire(value: McpServerConfig) -> dict[str, Any]:
    if isinstance(value, SdkMcpServer):
        raise TypeError("SDK MCP servers must be started before serialization")
    try:
        if isinstance(value, StdioMcpServerConfig):
            model: BaseModel = StdioMcpConfig(
                name=value.name,
                command=value.command,
                args=list(value.args),
                env=dict(value.env),
            )
        else:
            oauth: WireMcpOAuthOptions | Literal[False] | None
            if value.oauth is None or value.oauth is False:
                oauth = value.oauth
            else:
                oauth = WireMcpOAuthOptions.model_validate(
                    {
                        field: (item.value if isinstance(item, Enum) else item)
                        for field, item in (
                            (field, getattr(value.oauth, field))
                            for field in value.oauth.__dataclass_fields__
                        )
                        if item is not None
                    }
                )
            headers = [
                WireHttpHeader(name=header.name, value=header.value)
                for header in value.headers
            ]
            if isinstance(value, HttpMcpServerConfig):
                model = HttpMcpConfig(
                    type="http",
                    name=value.name,
                    url=value.url,
                    headers=headers,
                    oauth=oauth,
                )
            else:
                model = SseMcpConfig(
                    type="sse",
                    name=value.name,
                    url=value.url,
                    headers=headers,
                    oauth=oauth,
                )
    except (ValidationError, ValueError):
        raise ValueError("Invalid MCP server configuration") from None
    return model.model_dump(by_alias=True, exclude_none=True)


def document_to_wire(document: Document) -> dict[str, Any]:
    source = document.source
    if isinstance(source, TextDocumentSource):
        return {
            "type": "text",
            "mediaType": "text/plain",
            "data": source.data,
            "name": source.name,
            "mime": source.mime,
        }
    assert isinstance(source, PdfDocumentSource)
    return {
        "type": "base64",
        "mediaType": "application/pdf",
        "data": source.data,
        "parsedData": source.parsed_data,
        "name": source.name,
        "path": source.path,
    }


def list_or_none(value: object) -> list[str] | None:
    if value is None:
        return None
    return sorted(cast("Sequence[str]", value))


def header_mapping(values: list[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        header = cast("Mapping[str, object]", value)
        name = header.get("name")
        content = header.get("value")
        if isinstance(name, str) and isinstance(content, str):
            result[name] = content
    return result


# ----------------------------------------------------------
# Incoming: wire payloads -> public values
# ----------------------------------------------------------


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


def inner_notification(raw: object) -> SessionNotificationUnion | None:
    """Validate a raw notification into the typed inner payload.

    Returns ``None`` for unrelated payloads and raises
    :class:`DroidProtocolError` when a known notification type fails
    validation.
    """
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


def raw_inner_notification(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract the inner notification dict without validating its payload."""
    params = cast("object", raw.get("params"))
    if not isinstance(params, Mapping):
        return None
    inner = cast("Mapping[str, object]", params).get("notification")
    return cast("dict[str, Any]", inner) if isinstance(inner, dict) else None


def usage_from_wire(value: WireTokenUsage) -> Usage:
    return Usage(
        input_tokens=value.input_tokens,
        output_tokens=value.output_tokens,
        cache_creation_tokens=value.cache_creation_tokens,
        cache_read_tokens=value.cache_read_tokens,
        thinking_tokens=value.thinking_tokens,
        factory_credits=value.factory_credits,
    )


def settings_update_from_wire(
    value: SettingsUpdatedPayload | WireSessionSettings,
) -> SessionSettingsUpdate:
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
            else frozenset(value.additional_tool_ids)
        ),
        enabled_tools=(
            None
            if value.enabled_tool_ids is None
            else frozenset(value.enabled_tool_ids)
        ),
        disabled_tools=(
            None
            if value.disabled_tool_ids is None
            else frozenset(value.disabled_tool_ids)
        ),
        restrict_tools=(
            None
            if value.restrict_tool_ids is None
            else frozenset(value.restrict_tool_ids)
        ),
        compaction_threshold_check_enabled=value.compaction_threshold_check_enabled,
    )


def full_settings_from_wire(value: WireSessionSettings) -> SessionSettings:
    update = settings_update_from_wire(value)
    sandbox = value.sandbox
    return SessionSettings(
        model=value.model_id,
        reasoning_effort=ReasoningEffort(value.reasoning_effort.value),
        mode=update.mode,
        autonomy=update.autonomy,
        spec_model=update.spec_model,
        spec_reasoning_effort=update.spec_reasoning_effort,
        tags=update.tags or (),
        system_prompt=system_prompt_from_wire(value.system_prompt),
        sandbox=(
            None
            if sandbox is None
            else SandboxSettings(
                enabled=sandbox.enabled,
                mode=None if sandbox.mode is None else sandbox.mode.value,
            )
        ),
        additional_tools=update.additional_tools,
        enabled_tools=update.enabled_tools,
        disabled_tools=update.disabled_tools,
        restrict_tools=update.restrict_tools,
    )


# Fields where an explicitly transmitted null clears the current value; for
# every other field null means "unchanged".
_CLEARABLE_SETTINGS_FIELDS = (
    ("mode", "interaction_mode"),
    ("autonomy", "autonomy_level"),
    ("spec_model", "spec_mode_model_id"),
    ("spec_reasoning_effort", "spec_mode_reasoning_effort"),
)


def merged_settings(
    current: SessionSettings,
    payload: SettingsUpdatedPayload,
) -> SessionSettings:
    update = settings_update_from_wire(payload)
    changes: dict[str, Any] = {
        name: value
        for name, value in (
            ("model", update.model),
            ("reasoning_effort", update.reasoning_effort),
            ("mode", update.mode),
            ("autonomy", update.autonomy),
            ("spec_model", update.spec_model),
            ("spec_reasoning_effort", update.spec_reasoning_effort),
            ("tags", update.tags),
            ("additional_tools", update.additional_tools),
            ("enabled_tools", update.enabled_tools),
            ("disabled_tools", update.disabled_tools),
            ("restrict_tools", update.restrict_tools),
        )
        if value is not None
    }
    provided = payload.model_fields_set
    for public_name, wire_name in _CLEARABLE_SETTINGS_FIELDS:
        if public_name not in changes and wire_name in provided:
            changes[public_name] = None
    return dataclasses.replace(current, **changes)


def mcp_server_from_wire(value: WireMcpServerStatusInfo) -> McpServerStatusInfo:
    return McpServerStatusInfo(
        name=value.name,
        status=McpServerStatus(value.status.value),
        source=value.source.value,
        is_managed=value.is_managed,
        server_type=McpServerType(value.server_type.value),
        error=value.error,
        tool_count=value.tool_count,
        has_auth_tokens=value.has_auth_tokens,
        requires_auth=value.requires_auth,
        pending_auth_url=value.pending_auth_url,
        pending_auth_message=value.pending_auth_message,
        pending_auth_state=value.pending_auth_state,
    )


def mcp_summary_from_wire(value: WireMcpStatusSummary) -> McpStatusSummary:
    return McpStatusSummary(
        total=value.total,
        connected=value.connected,
        connecting=value.connecting,
        failed=value.failed,
        disabled=value.disabled,
        config_error=(
            None
            if value.config_error is None
            else McpConfigError(value.config_error.path, value.config_error.message)
        ),
    )


def mcp_status_from_wire(
    notification: McpStatusChangedNotification,
) -> McpStatusChanged:
    return McpStatusChanged(
        servers=tuple(mcp_server_from_wire(server) for server in notification.servers),
        summary=mcp_summary_from_wire(notification.summary),
    )


def tool_category(value: str | None) -> ToolCategory:
    try:
        return ToolCategory(value)
    except ValueError:
        return ToolCategory.OTHER


def load_cwd(result: object, fallback: Path) -> Path:
    """Read the loaded session's cwd out of the result's extra fields.

    The load result does not yet model cwd/worktree in its schema, so this
    probes ``model_extra`` and falls back to the caller-supplied path.
    """
    extra = cast("dict[str, object]", getattr(result, "model_extra", None) or {})
    cwd = extra.get("cwd")
    if isinstance(cwd, str):
        return Path(cwd)
    worktree = extra.get("worktree")
    if isinstance(worktree, Mapping):
        typed_worktree = cast("Mapping[str, object]", worktree)
        path = typed_worktree.get("path")
        if isinstance(path, str):
            return Path(path)
    return fallback
