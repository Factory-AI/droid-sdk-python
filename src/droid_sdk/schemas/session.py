"""Session metadata and token usage schemas shared across protocol directions."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

__all__ = [
    "LastCallTokenUsage",
    "SessionTag",
    "SystemPromptConfig",
    "SystemPromptPreset",
    "TokenUsage",
]


SystemPromptContent: TypeAlias = Annotated[str, StringConstraints(pattern=r"\S")]


class SystemPromptPreset(BaseModel):
    """Droid's built-in behavioral prompt with appended instructions."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["preset"]
    preset: Literal["droid"]
    append: SystemPromptContent


SystemPromptConfig: TypeAlias = SystemPromptContent | SystemPromptPreset


class SessionTag(BaseModel):
    """Session tag metadata."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    metadata: dict[str, str] | None = None


class TokenUsage(BaseModel):
    """Complete cumulative token usage information."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    input_tokens: int = Field(alias="inputTokens")
    output_tokens: int = Field(alias="outputTokens")
    cache_creation_tokens: int = Field(alias="cacheCreationTokens")
    cache_read_tokens: int = Field(alias="cacheReadTokens")
    thinking_tokens: int = Field(alias="thinkingTokens")
    factory_credits: float | None = Field(default=None, alias="factoryCredits")


class LastCallTokenUsage(BaseModel):
    """Provider usage fields used by the context and compaction meter."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    input_tokens: int = Field(alias="inputTokens")
    cache_read_tokens: int = Field(alias="cacheReadTokens")
    output_tokens: int | None = Field(default=None, alias="outputTokens")
