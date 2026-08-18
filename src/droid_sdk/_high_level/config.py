"""Immutable session configuration and discovery snapshots."""

# ruff: noqa: TC001, TC003

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict, cast

from droid_sdk._high_level._immutable import (
    FrozenJsonObject,
    ensure_aware,
    freeze_json_object,
)
from droid_sdk._high_level.enums import (
    Autonomy,
    Mode,
    ReasoningEffort,
    SessionPlatform,
)

if TYPE_CHECKING:
    from droid_sdk._high_level.extensions import McpServerConfig

_TOOL_SET_FIELDS = (
    "additional_tools",
    "enabled_tools",
    "disabled_tools",
    "restrict_tools",
)


class SystemPromptPreset(TypedDict):
    """Droid's built-in behavioral prompt with appended instructions."""

    type: Literal["preset"]
    preset: Literal["droid"]
    append: str


SystemPromptConfig: TypeAlias = str | SystemPromptPreset


def _freeze_system_prompt(
    value: object,
) -> SystemPromptConfig | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("system_prompt content must not be empty")
        return value
    if not isinstance(value, Mapping):
        raise TypeError("system_prompt must be a string or Droid preset mapping")

    mapping = cast("Mapping[object, object]", value)
    required_keys = {"type", "preset", "append"}
    if set(mapping) != required_keys:
        raise ValueError(
            "system_prompt preset must contain exactly type, preset, and append"
        )
    if mapping.get("type") != "preset" or mapping.get("preset") != "droid":
        raise ValueError("system_prompt preset must be the Droid preset")
    append = mapping.get("append")
    if not isinstance(append, str):
        raise TypeError("system_prompt append content must be a string")
    if not append.strip():
        raise ValueError("system_prompt append content must not be empty")

    return cast(
        "SystemPromptConfig",
        MappingProxyType(
            {
                "type": "preset",
                "preset": "droid",
                "append": append,
            }
        ),
    )


def freeze_tool_ids(name: str, items: Iterable[str] | None) -> frozenset[str] | None:
    """Freeze a tool-ID iterable, rejecting a bare string.

    A string is iterable, so ``frozenset("Execute")`` would silently become a
    set of single characters.
    """
    if items is None:
        return None
    if isinstance(items, str):
        raise TypeError(f"{name} takes an iterable of tool IDs, not a string")
    return frozenset(items)


def _freeze_tool_sets(value: object) -> None:
    for name in _TOOL_SET_FIELDS:
        items = getattr(value, name)
        if items is not None:
            object.__setattr__(value, name, freeze_tool_ids(name, items))


@dataclass(frozen=True, slots=True)
class SessionTag:
    name: str
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.metadata is not None:
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SessionSource:
    """Authority source attribution.

    Fields not used by a platform remain ``None``. Validation of required
    platform-specific fields occurs when the value is adapted to the wire.
    """

    platform: SessionPlatform
    delegation_session_id: str | None = None
    team_id: str | None = None
    channel: str | None = None
    thread_ts: str | None = None
    user_id: str | None = None
    automation_id: str | None = None
    agent_session_id: str | None = None
    issue_id: str | None = None
    issue_url: str | None = None
    issue_identifier: str | None = None
    organization_id: str | None = None
    cloud_id: str | None = None
    issue_key: str | None = None
    site_id: str | None = None
    project_id: str | None = None
    comment_id: str | None = None
    task_id: str | None = None
    tenant_id: str | None = None
    conversation_id: str | None = None
    service_url: str | None = None
    conversation_type: str | None = None
    root_message_id: str | None = None
    channel_id: str | None = None
    aad_object_id: str | None = None
    report_id: str | None = None
    repo_url: str | None = None
    criterion_id: str | None = None
    computer_id: str | None = None


@dataclass(frozen=True, slots=True)
class SandboxSettings:
    enabled: bool
    mode: str | None = None


@dataclass(frozen=True, slots=True)
class SessionConfig:
    mode: Mode | None = None
    autonomy: Autonomy | None = None
    spec_model: str | None = None
    spec_reasoning_effort: ReasoningEffort | None = None
    mcp_servers: Sequence[McpServerConfig] = ()
    machine_id: str | None = None
    tags: Sequence[SessionTag] = ()
    session_source: SessionSource | None = None
    auto_reject_permission_requests: bool | None = None
    disable_builtin_skills: bool | None = None
    system_prompt: SystemPromptConfig | None = None
    additional_tools: Iterable[str] | None = None
    enabled_tools: Iterable[str] | None = None
    disabled_tools: Iterable[str] | None = None
    restrict_tools: Iterable[str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mcp_servers", tuple(self.mcp_servers))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(
            self,
            "system_prompt",
            _freeze_system_prompt(self.system_prompt),
        )
        _freeze_tool_sets(self)


@dataclass(frozen=True, slots=True)
class SessionSettings:
    model: str
    reasoning_effort: ReasoningEffort
    mode: Mode | None = None
    autonomy: Autonomy | None = None
    spec_model: str | None = None
    spec_reasoning_effort: ReasoningEffort | None = None
    tags: Sequence[SessionTag] = ()
    sandbox: SandboxSettings | None = None
    system_prompt: SystemPromptConfig | None = None
    additional_tools: frozenset[str] | None = None
    enabled_tools: frozenset[str] | None = None
    disabled_tools: frozenset[str] | None = None
    restrict_tools: frozenset[str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(
            self,
            "system_prompt",
            _freeze_system_prompt(self.system_prompt),
        )
        _freeze_tool_sets(self)


@dataclass(frozen=True, slots=True)
class SessionSettingsUpdate:
    """Partial settings carried by a settings-updated notification."""

    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    mode: Mode | None = None
    autonomy: Autonomy | None = None
    spec_model: str | None = None
    spec_reasoning_effort: ReasoningEffort | None = None
    tags: Sequence[SessionTag] | None = None
    additional_tools: frozenset[str] | None = None
    enabled_tools: frozenset[str] | None = None
    disabled_tools: frozenset[str] | None = None
    restrict_tools: frozenset[str] | None = None
    compaction_threshold_check_enabled: bool | None = None

    def __post_init__(self) -> None:
        if self.tags is not None:
            object.__setattr__(self, "tags", tuple(self.tags))
        _freeze_tool_sets(self)


@dataclass(frozen=True, slots=True)
class UpdateSettingsResult:
    pass


@dataclass(frozen=True, slots=True)
class SavedSession:
    id: str
    title: str
    owner: str
    message_count: int
    modified_at: datetime
    created_at: datetime
    cwd: Path | None = None
    is_favorite: bool = False

    def __post_init__(self) -> None:
        ensure_aware(self.modified_at, "modified_at")
        ensure_aware(self.created_at, "created_at")
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd))


@dataclass(frozen=True, slots=True, init=False)
class JsonSchema:
    schema: FrozenJsonObject

    def __init__(self, schema: Mapping[str, object]) -> None:
        object.__setattr__(
            self,
            "schema",
            freeze_json_object(schema, where="schema"),
        )
