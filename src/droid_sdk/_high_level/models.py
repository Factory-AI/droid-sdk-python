"""Sessionless discovery of models selectable by Droid."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from droid_sdk._high_level.enums import ModelProvider, ReasoningEffort
from droid_sdk._high_level.runtime import Runtime
from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    DroidConnectionError,
    DroidError,
    InvalidWorkingDirectoryError,
)
from droid_sdk.observability import ObservabilityAdapter
from droid_sdk.transport import ProcessTransport

if TYPE_CHECKING:
    from collections.abc import Sequence

    from droid_sdk.schemas.models import ModelInfo as WireModelInfo


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Immutable metadata for a model selectable by Droid."""

    id: str
    display_name: str
    short_display_name: str
    model_provider: ModelProvider
    supported_reasoning_efforts: Sequence[ReasoningEffort]
    default_reasoning_effort: ReasoningEffort
    is_custom: bool = False
    disabled: bool = False
    disabled_reason: str | None = None
    no_image_support: bool | None = None
    supports_image_generation: bool | None = None
    tier: str | None = None
    token_multiplier: float | None = None
    promo_label: str | None = None
    kind: str | None = None
    variant_badge: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "supported_reasoning_efforts",
            tuple(self.supported_reasoning_efforts),
        )
        if self.disabled and self.disabled_reason is None:
            raise ValueError("disabled models must include disabled_reason")
        if not self.disabled and self.disabled_reason is not None:
            raise ValueError("enabled models must not include disabled_reason")


def _model_from_wire(value: WireModelInfo) -> ModelInfo:
    return ModelInfo(
        id=value.id,
        display_name=value.display_name,
        short_display_name=value.short_display_name,
        model_provider=ModelProvider(value.model_provider.value),
        supported_reasoning_efforts=tuple(
            ReasoningEffort(item.value) for item in value.supported_reasoning_efforts
        ),
        default_reasoning_effort=ReasoningEffort(value.default_reasoning_effort.value),
        is_custom=value.is_custom,
        disabled=value.disabled,
        disabled_reason=value.disabled_reason,
        no_image_support=value.no_image_support,
        supports_image_generation=value.supports_image_generation,
        tier=value.tier,
        token_multiplier=value.token_multiplier,
        promo_label=value.promo_label,
        kind=value.kind,
        variant_badge=value.variant_badge,
    )


def _working_directory(value: str | Path | None) -> Path:
    path = Path.cwd() if value is None else Path(value)
    try:
        if not path.is_dir():
            raise InvalidWorkingDirectoryError(str(path))
        return path.resolve()
    except OSError as exc:
        raise InvalidWorkingDirectoryError(str(path)) from exc


async def _close_quietly(client: DroidClient) -> None:
    task = asyncio.create_task(client.close())
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
    except Exception:
        pass


async def list_models(
    *,
    include_disabled: bool = False,
    cwd: str | Path | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> list[ModelInfo]:
    """List models currently selectable by a one-shot Droid process."""
    selected_cwd = _working_directory(cwd)
    runtime_config = runtime or Runtime()
    adapter = ObservabilityAdapter(runtime_config.observability)

    if runtime_config.transport is not None:
        if not runtime_config.transport.is_connected:
            raise DroidError("A supplied transport must already be connected")
        transport = runtime_config.transport
    else:
        key = api_key or os.environ.get("FACTORY_API_KEY")
        env = dict(runtime_config.env)
        if key:
            env["FACTORY_API_KEY"] = key
        executable = (
            "droid"
            if runtime_config.executable is None
            else str(runtime_config.executable)
        )
        transport = ProcessTransport(
            exec_path=executable,
            exec_args=[
                "exec",
                "--input-format",
                "stream-jsonrpc",
                "--output-format",
                "stream-jsonrpc",
                *runtime_config.args,
            ],
            cwd=str(selected_cwd),
            env=env,
        )

    client = DroidClient(
        transport=transport,
        trace_meta_injector=adapter.trace_meta_injector,
        timing_callback=adapter.timing_callback,
    )
    try:
        try:
            await client.connect()
        except FileNotFoundError as exc:
            raise DroidConnectionError(
                "Droid executable was not found",
                exec_path=(
                    None
                    if runtime_config.executable is None
                    else str(runtime_config.executable)
                ),
                cwd=str(selected_cwd),
            ) from exc
        result = await client.list_models(
            include_disabled=True if include_disabled else None
        )
        return [_model_from_wire(model) for model in result.models]
    finally:
        await _close_quietly(client)


__all__ = ["ModelInfo", "list_models"]
