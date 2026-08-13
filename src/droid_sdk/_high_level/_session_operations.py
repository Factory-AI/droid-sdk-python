"""Request/response session operations layered on the lifecycle core.

:class:`SessionOperationsMixin` holds every session method that is a plain
request/response call on the low-level client (settings, tools, skills, MCP
management, context, spec mode) plus the replacement-producing operations
(fork, compact, rewind). The lifecycle state machine that these methods rely
on lives in :mod:`droid_sdk._high_level.session`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from droid_sdk._high_level._convert import (
    header_mapping,
    list_or_none,
    mcp_config_to_wire,
    mcp_server_from_wire,
    mcp_summary_from_wire,
    tool_category,
    wire_reasoning,
    wire_tags,
)
from droid_sdk._high_level.config import (
    SessionSettings,
    UpdateSettingsResult,
    freeze_tool_ids,
)
from droid_sdk._high_level.enums import ContextAccuracy, Mode
from droid_sdk._high_level.extensions import (
    CompactOutcome,
    McpMutationResult,
    McpServersResult,
    McpToolInfo,
    McpToolInputSchema,
    RewindEvictedFile,
    RewindFileCreation,
    RewindFileSnapshot,
    RewindInfo,
    RewindOutcome,
    SkillInfo,
    SkillMutationResult,
    SkillResource,
    SkillsResult,
    ToolInfo,
)
from droid_sdk._high_level.messages import ContextUsage
from droid_sdk.schemas.enums import (
    AutonomyLevel as WireAutonomy,
)
from droid_sdk.schemas.enums import (
    DroidInteractionMode,
    SettingsLevel,
)
from droid_sdk.schemas.enums import (
    McpServerType as WireMcpServerType,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from droid_sdk._high_level.config import SessionTag
    from droid_sdk._high_level.enums import Autonomy, ReasoningEffort
    from droid_sdk._high_level.extensions import (
        HttpMcpServerConfig,
        SseMcpServerConfig,
        StdioMcpServerConfig,
    )
    from droid_sdk._high_level.session import Session
    from droid_sdk.client import DroidClient


class _Unset:
    pass


_UNSET = _Unset()


class SessionOperationsMixin:
    """Session operations that translate one call into one client request."""

    if TYPE_CHECKING:
        _settings: SessionSettings | None
        _load_options: dict[str, object]

        @property
        def settings(self) -> SessionSettings: ...

        def _ensure_active(self) -> None: ...

        def _require_client(self) -> DroidClient: ...

        async def _replacement_operation(
            self,
            operation: Callable[[], Any],
        ) -> tuple[Any, Session]: ...

    async def update_settings(
        self,
        *,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        mode: Mode | None = None,
        autonomy: Autonomy | None = None,
        spec_model: str | _Unset | None = _UNSET,
        spec_reasoning_effort: ReasoningEffort | _Unset | None = _UNSET,
        tags: Sequence[SessionTag] | None = None,
        compaction_token_limit: int | None = None,
        compaction_threshold_check_enabled: bool | None = None,
        additional_tools: Iterable[str] | None = None,
        enabled_tools: Iterable[str] | None = None,
        disabled_tools: Iterable[str] | None = None,
        restrict_tools: Iterable[str] | None = None,
    ) -> UpdateSettingsResult:
        self._ensure_active()
        additional_tools = freeze_tool_ids("additional_tools", additional_tools)
        enabled_tools = freeze_tool_ids("enabled_tools", enabled_tools)
        disabled_tools = freeze_tool_ids("disabled_tools", disabled_tools)
        restrict_tools = freeze_tool_ids("restrict_tools", restrict_tools)
        spec_model_value = None if isinstance(spec_model, _Unset) else spec_model
        spec_reasoning_value = (
            None if isinstance(spec_reasoning_effort, _Unset) else spec_reasoning_effort
        )
        explicit_null_fields: list[
            Literal["specModeModelId", "specModeReasoningEffort"]
        ] = []
        if spec_model is None:
            explicit_null_fields.append("specModeModelId")
        if spec_reasoning_effort is None:
            explicit_null_fields.append("specModeReasoningEffort")
        await self._require_client().update_session_settings(
            model_id=model,
            reasoning_effort=wire_reasoning(reasoning_effort),
            interaction_mode=(
                None if mode is None else DroidInteractionMode(mode.value)
            ),
            autonomy_level=(None if autonomy is None else WireAutonomy(autonomy.value)),
            spec_mode_model_id=spec_model_value,
            spec_mode_reasoning_effort=wire_reasoning(spec_reasoning_value),
            tags=cast("Any", None if tags is None else wire_tags(tags)),
            compaction_token_limit=compaction_token_limit,
            compaction_threshold_check_enabled=(compaction_threshold_check_enabled),
            additional_tool_ids=list_or_none(additional_tools),
            enabled_tool_ids=list_or_none(enabled_tools),
            disabled_tool_ids=list_or_none(disabled_tools),
            restrict_tool_ids=list_or_none(restrict_tools),
            explicit_null_fields=explicit_null_fields,
        )
        for key, value in (
            ("additional_tools", additional_tools),
            ("enabled_tools", enabled_tools),
            ("disabled_tools", disabled_tools),
            ("restrict_tools", restrict_tools),
        ):
            if value is not None:
                self._load_options[key] = value
        current = self.settings
        self._settings = SessionSettings(
            model=current.model if model is None else model,
            reasoning_effort=(
                current.reasoning_effort
                if reasoning_effort is None
                else reasoning_effort
            ),
            mode=current.mode if mode is None else mode,
            autonomy=current.autonomy if autonomy is None else autonomy,
            spec_model=(
                current.spec_model if isinstance(spec_model, _Unset) else spec_model
            ),
            spec_reasoning_effort=(
                current.spec_reasoning_effort
                if isinstance(spec_reasoning_effort, _Unset)
                else spec_reasoning_effort
            ),
            tags=current.tags if tags is None else tags,
            sandbox=current.sandbox,
            additional_tools=(
                current.additional_tools
                if additional_tools is None
                else additional_tools
            ),
            enabled_tools=(
                current.enabled_tools if enabled_tools is None else enabled_tools
            ),
            disabled_tools=(
                current.disabled_tools if disabled_tools is None else disabled_tools
            ),
            restrict_tools=(
                current.restrict_tools if restrict_tools is None else restrict_tools
            ),
        )
        return UpdateSettingsResult()

    async def rename(self, title: str) -> None:
        self._ensure_active()
        await self._require_client().rename_session(title=title)

    async def list_tools(
        self,
        *,
        model: str | None = None,
        mode: Mode | None = None,
        autonomy: Autonomy | None = None,
        spec_model: str | None = None,
        additional_tools: Iterable[str] | None = None,
        enabled_tools: Iterable[str] | None = None,
        disabled_tools: Iterable[str] | None = None,
        restrict_tools: Iterable[str] | None = None,
        skip_permissions_unsafe: bool | None = None,
    ) -> list[ToolInfo]:
        self._ensure_active()
        additional_tools = freeze_tool_ids("additional_tools", additional_tools)
        enabled_tools = freeze_tool_ids("enabled_tools", enabled_tools)
        disabled_tools = freeze_tool_ids("disabled_tools", disabled_tools)
        restrict_tools = freeze_tool_ids("restrict_tools", restrict_tools)
        result = await self._require_client().list_tools(
            model_id=model,
            interaction_mode=(
                None if mode is None else DroidInteractionMode(mode.value)
            ),
            autonomy_level=(None if autonomy is None else WireAutonomy(autonomy.value)),
            spec_mode_model_id=spec_model,
            additional_tool_ids=list_or_none(additional_tools),
            enabled_tool_ids=list_or_none(enabled_tools),
            disabled_tool_ids=list_or_none(disabled_tools),
            restrict_tool_ids=list_or_none(restrict_tools),
            skip_permissions_unsafe=skip_permissions_unsafe,
        )
        return [
            ToolInfo(
                id=item.llm_id or item.id,
                display_name=item.display_name or item.llm_id or item.id,
                description=item.description or "",
                category=tool_category(item.category),
                default_allowed=item.default_allowed,
                allowed=item.currently_allowed,
            )
            for item in result.tools
        ]

    async def list_skills(self) -> SkillsResult:
        self._ensure_active()
        result = await self._require_client().list_skills()
        return SkillsResult(
            skills=[
                SkillInfo(
                    name=item.name,
                    description=item.description,
                    location=cast("Any", item.location.value),
                    file_path=item.file_path,
                    enabled=item.enabled,
                    user_invocable=item.user_invocable,
                    version=item.version,
                    content=item.content,
                    resources=tuple(
                        SkillResource(
                            name=resource.name,
                            path=resource.path,
                            type=resource.type,
                        )
                        for resource in (item.resources or ())
                    ),
                    disabled_by=item.disabled_by,
                )
                for item in result.skills
            ],
            project_available=result.project_available,
        )

    async def enable_skill(
        self,
        name: str,
        *,
        scope: Literal["user", "project"] = "user",
    ) -> SkillMutationResult:
        return await self._set_skill(name, False, scope)

    async def disable_skill(
        self,
        name: str,
        *,
        scope: Literal["user", "project"] = "user",
    ) -> SkillMutationResult:
        return await self._set_skill(name, True, scope)

    async def _set_skill(
        self,
        name: str,
        disabled: bool,
        scope: Literal["user", "project"],
    ) -> SkillMutationResult:
        self._ensure_active()
        result = await self._require_client().set_skill_disabled(
            skill_name=name,
            disabled=disabled,
            settings_level=SettingsLevel(scope),
        )
        return SkillMutationResult(result.success)

    async def list_mcp_servers(self) -> McpServersResult:
        self._ensure_active()
        result = await self._require_client().list_mcp_servers()
        return McpServersResult(
            servers=tuple(mcp_server_from_wire(item) for item in result.servers),
            summary=mcp_summary_from_wire(result.summary),
        )

    async def list_mcp_tools(self) -> list[McpToolInfo]:
        self._ensure_active()
        result = await self._require_client().list_mcp_tools()
        return [
            McpToolInfo(
                server_name=item.server_name,
                name=item.name,
                description=item.description,
                is_enabled=item.is_enabled,
                is_read_only=item.is_read_only,
                input_schema=(
                    None
                    if item.input_schema is None
                    else McpToolInputSchema(
                        type=item.input_schema.type,
                        properties=item.input_schema.properties,
                        required=item.input_schema.required,
                    )
                ),
            )
            for item in result.tools
        ]

    async def add_mcp_server(
        self,
        config: StdioMcpServerConfig | HttpMcpServerConfig | SseMcpServerConfig,
    ) -> McpMutationResult:
        self._ensure_active()
        raw = mcp_config_to_wire(config)
        headers = cast("object", raw.get("headers"))
        result = await self._require_client().add_mcp_server(
            name=config.name,
            type=WireMcpServerType(raw.get("type", "stdio")),
            url=cast("str | None", raw.get("url")),
            headers=(
                None
                if not isinstance(headers, list)
                else header_mapping(cast("list[object]", headers))
            ),
            command=cast("str | None", raw.get("command")),
            args=cast("list[str] | None", raw.get("args")),
            env=cast("dict[str, str] | None", raw.get("env")),
            oauth=cast("Any", raw.get("oauth")),
        )
        return McpMutationResult(result.success)

    async def remove_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().remove_mcp_server(
            server_name=name,
            settings_level=SettingsLevel.User,
        )
        return McpMutationResult(result.success)

    async def enable_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        return await self._toggle_mcp_server(name, True)

    async def disable_mcp_server(
        self,
        name: str,
    ) -> McpMutationResult:
        return await self._toggle_mcp_server(name, False)

    async def _toggle_mcp_server(
        self,
        name: str,
        enabled: bool,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().toggle_mcp_server(
            server_name=name,
            enabled=enabled,
            settings_level=SettingsLevel.User,
        )
        return McpMutationResult(result.success)

    async def enable_mcp_tool(
        self, server_name: str, tool_name: str
    ) -> McpMutationResult:
        return await self._toggle_mcp_tool(server_name, tool_name, True)

    async def disable_mcp_tool(
        self, server_name: str, tool_name: str
    ) -> McpMutationResult:
        return await self._toggle_mcp_tool(server_name, tool_name, False)

    async def _toggle_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        enabled: bool,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().toggle_mcp_tool(
            server_name=server_name,
            tool_name=tool_name,
            enabled=enabled,
        )
        return McpMutationResult(result.success)

    async def authenticate_mcp_server(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().authenticate_mcp_server(server_name=name)
        return McpMutationResult(result.success)

    async def cancel_mcp_auth(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().cancel_mcp_auth(server_name=name)
        return McpMutationResult(result.success)

    async def clear_mcp_auth(self, name: str) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().clear_mcp_auth(server_name=name)
        return McpMutationResult(result.success)

    async def submit_mcp_auth_code(
        self, name: str, *, code: str, state: str
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().submit_mcp_auth_code(
            server_name=name, code=code, state=state
        )
        return McpMutationResult(result.success)

    async def submit_mcp_auth_error(
        self,
        name: str,
        *,
        error: str,
        state: str,
        error_description: str | None = None,
    ) -> McpMutationResult:
        self._ensure_active()
        result = await self._require_client().submit_mcp_auth_error(
            server_name=name,
            error=error,
            state=state,
            error_description=error_description,
        )
        return McpMutationResult(result.success)

    async def context(self) -> ContextUsage:
        self._ensure_active()
        result = await self._require_client().get_context_stats()
        timestamp = datetime.fromisoformat(result.updated_at.replace("Z", "+00:00"))
        return ContextUsage(
            used=result.used,
            remaining=result.remaining,
            limit=result.limit,
            accuracy=ContextAccuracy(result.accuracy.value),
            updated_at=timestamp,
        )

    async def enter_spec(
        self,
        *,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> UpdateSettingsResult:
        if model is None and reasoning_effort is None:
            return await self.update_settings(mode=Mode.SPEC)
        if model is None:
            return await self.update_settings(
                mode=Mode.SPEC,
                spec_reasoning_effort=reasoning_effort,
            )
        if reasoning_effort is None:
            return await self.update_settings(
                mode=Mode.SPEC,
                spec_model=model,
            )
        return await self.update_settings(
            mode=Mode.SPEC,
            spec_model=model,
            spec_reasoning_effort=reasoning_effort,
        )

    async def leave_spec(self) -> UpdateSettingsResult:
        return await self.update_settings(mode=Mode.AUTO)

    async def fork(
        self,
        *,
        title: str | None = None,
        tags: Sequence[SessionTag] | None = None,
    ) -> Session:
        _, successor = await self._replacement_operation(
            lambda: self._require_client().fork_session(
                title=title,
                tags=cast("Any", None if tags is None else wire_tags(tags)),
            )
        )
        return successor

    async def compact(
        self,
        *,
        instructions: str | None = None,
    ) -> CompactOutcome:
        result, successor = await self._replacement_operation(
            lambda: self._require_client().compact_session(
                custom_instructions=instructions
            )
        )
        return CompactOutcome(successor, result.removed_count)

    async def rewind_info(self, message_id: str) -> RewindInfo:
        self._ensure_active()
        result = await self._require_client().get_rewind_info(message_id=message_id)
        return RewindInfo(
            available_files=tuple(
                RewindFileSnapshot(item.file_path, item.content_hash, item.size)
                for item in result.available_files
            ),
            created_files=tuple(
                RewindFileCreation(item.file_path) for item in result.created_files
            ),
            evicted_files=tuple(
                RewindEvictedFile(item.file_path, item.reason)
                for item in result.evicted_files
            ),
        )

    async def rewind(
        self,
        message_id: str,
        *,
        restore: Sequence[RewindFileSnapshot] = (),
        delete: Sequence[RewindFileCreation] = (),
        title: str,
    ) -> RewindOutcome:
        result, successor = await self._replacement_operation(
            lambda: self._require_client().execute_rewind(
                message_id=message_id,
                files_to_restore=[
                    {
                        "filePath": item.file_path,
                        "contentHash": item.content_hash,
                        "size": item.size,
                    }
                    for item in restore
                ],
                files_to_delete=[{"filePath": item.file_path} for item in delete],
                fork_title=title,
            )
        )
        return RewindOutcome(
            successor,
            result.restored_count,
            result.deleted_count,
            result.failed_restore_count,
            result.failed_delete_count,
        )


__all__ = ["SessionOperationsMixin"]
