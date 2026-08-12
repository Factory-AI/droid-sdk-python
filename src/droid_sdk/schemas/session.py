"""Session metadata and token usage schemas shared across protocol directions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LastCallTokenUsage",
    "SessionTag",
    "TokenUsage",
]


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
