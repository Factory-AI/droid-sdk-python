"""Sessionless discovery of models selectable by Droid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from droid_sdk._high_level._client import (
    managed_droid_client,
    resolve_working_directory,
)
from droid_sdk._high_level.enums import ModelProvider, ReasoningEffort
from droid_sdk._high_level.runtime import Runtime
from droid_sdk.errors import DroidProtocolError
from droid_sdk.observability import ObservabilityAdapter
from droid_sdk.schemas.enums import JsonRpcErrorCode

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

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


def _model_from_wire(wire_model: WireModelInfo) -> ModelInfo:
    return ModelInfo(
        id=wire_model.id,
        display_name=wire_model.display_name,
        short_display_name=wire_model.short_display_name,
        model_provider=ModelProvider(wire_model.model_provider.value),
        supported_reasoning_efforts=tuple(
            ReasoningEffort(effort.value)
            for effort in wire_model.supported_reasoning_efforts
        ),
        default_reasoning_effort=ReasoningEffort(
            wire_model.default_reasoning_effort.value
        ),
        is_custom=wire_model.is_custom,
        disabled=wire_model.disabled,
        disabled_reason=wire_model.disabled_reason,
        no_image_support=wire_model.no_image_support,
        supports_image_generation=wire_model.supports_image_generation,
        tier=wire_model.tier,
        token_multiplier=wire_model.token_multiplier,
        promo_label=wire_model.promo_label,
        kind=wire_model.kind,
        variant_badge=wire_model.variant_badge,
    )


async def list_models(
    *,
    include_disabled: bool = False,
    cwd: str | Path | None = None,
    runtime: Runtime | None = None,
    api_key: str | None = None,
) -> list[ModelInfo]:
    """List models currently selectable by a one-shot Droid process."""
    runtime_config = runtime or Runtime()
    if runtime_config.uses_supplied_transport:
        if cwd is not None:
            raise ValueError("cwd cannot be used with a supplied transport")
        if api_key is not None:
            raise ValueError("api_key cannot be used with a supplied transport")
    observability_adapter = ObservabilityAdapter(runtime_config.observability)
    working_directory = resolve_working_directory(cwd)
    async with managed_droid_client(
        runtime_config,
        api_key=api_key,
        cwd=working_directory,
        observability=observability_adapter,
    ) as client:
        try:
            result = await client.list_models(
                include_disabled=True if include_disabled else None
            )
        except DroidProtocolError as exc:
            if exc.code != JsonRpcErrorCode.METHOD_NOT_FOUND.value:
                raise
            raise DroidProtocolError(
                "The installed Droid version does not support model discovery. "
                "Update Droid and try again.",
                code=exc.code,
                data=exc.data,
            ) from exc
        return [_model_from_wire(model) for model in result.models]


__all__ = ["ModelInfo", "list_models"]
