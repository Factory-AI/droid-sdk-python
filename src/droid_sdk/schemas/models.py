"""Canonical model-discovery schemas shared by SDK protocol surfaces."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from droid_sdk.schemas.enums import ModelProvider, ReasoningEffort  # noqa: TC001

__all__ = [
    "ListModelsOptions",
    "ListModelsResult",
    "ModelInfo",
    "ModelMetadata",
]


class ModelMetadata(BaseModel):
    """Metadata shared by enabled and disabled model-catalog entries."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    display_name: str = Field(alias="displayName")
    short_display_name: str = Field(alias="shortDisplayName")
    model_provider: ModelProvider = Field(alias="modelProvider")
    supported_reasoning_efforts: list[ReasoningEffort] = Field(
        alias="supportedReasoningEfforts"
    )
    default_reasoning_effort: ReasoningEffort = Field(alias="defaultReasoningEffort")
    is_custom: bool = Field(default=False, alias="isCustom")
    no_image_support: bool | None = Field(default=None, alias="noImageSupport")
    supports_image_generation: bool | None = Field(
        default=None, alias="supportsImageGeneration"
    )
    tier: str | None = None
    token_multiplier: float | None = Field(default=None, alias="tokenMultiplier")
    promo_label: str | None = Field(default=None, alias="promoLabel")
    kind: str | None = None
    variant_badge: str | None = Field(default=None, alias="variantBadge")


class ModelInfo(ModelMetadata):
    """Public model-catalog entry with a validated disabled state."""

    disabled: bool = False
    disabled_reason: str | None = Field(default=None, alias="disabledReason")

    @model_validator(mode="after")
    def validate_disabled_reason(self) -> Self:
        if self.disabled and self.disabled_reason is None:
            raise ValueError("disabled models must include disabledReason")
        if not self.disabled and self.disabled_reason is not None:
            raise ValueError("enabled models must not include disabledReason")
        return self


class ListModelsOptions(BaseModel):
    """Options for sessionless model discovery."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    include_disabled: bool | None = Field(default=None, alias="includeDisabled")


class ListModelsResult(BaseModel):
    """Result returned by sessionless model discovery."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    models: list[ModelInfo]
