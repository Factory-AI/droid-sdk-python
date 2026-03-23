"""Message schemas for the Factory Droid protocol.

Ported from TypeScript source:
- packages/common/src/sessionV2/messages/schemas.ts
- packages/common/src/sessionV2/messages/enums.ts

The FactoryDroidMessage schema is used in CreateMessageNotification and
session data. Content blocks use ``extra="allow"`` for flexibility with
deeply nested/variant structures, while top-level fields are fully typed.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Base64ImageSource",
    "ContentBlock",
    "DocumentBlock",
    "DocumentSourceType",
    "FactoryDroidMessage",
    "ImageBlock",
    "MessageContentBlockType",
    "MessageRole",
    "MessageVisibility",
    "RedactedThinkingBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
]


# ============================================================
# Enums (from sessionV2/messages/enums.ts)
# ============================================================


class MessageRole(str, Enum):
    """Message role enum."""

    User = "user"
    Assistant = "assistant"
    Tool = "tool"
    System = "system"


class MessageVisibility(str, Enum):
    """Message visibility enum."""

    Both = "both"
    LLMOnly = "llm_only"
    UserOnly = "user_only"


class MessageContentBlockType(str, Enum):
    """Message content block type enum."""

    Text = "text"
    Image = "image"
    Thinking = "thinking"
    RedactedThinking = "redacted_thinking"
    ToolUse = "tool_use"
    ToolResult = "tool_result"
    Document = "document"


class DocumentSourceType(str, Enum):
    """Document source type enum."""

    Base64 = "base64"
    Text = "text"


# ============================================================
# Content block models
# ============================================================


class TextBlock(BaseModel):
    """Text content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.Text]
    """Content block type, always 'text'."""

    text: str
    """Text content."""

    id: str | None = None
    """Optional content block ID."""


class Base64ImageSource(BaseModel):
    """Base64-encoded image source."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["base64"]
    """Source type, always 'base64'."""

    data: str
    """Base64-encoded image data."""

    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = Field(
        alias="mediaType"
    )
    """Image media type."""


class ImageBlock(BaseModel):
    """Image content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.Image]
    """Content block type, always 'image'."""

    source: Base64ImageSource
    """Image source."""

    id: str | None = None
    """Optional content block ID."""


class ThinkingBlock(BaseModel):
    """Thinking content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.Thinking]
    """Content block type, always 'thinking'."""

    signature: str
    """Signature (required but can be empty string for Gemini)."""

    thinking: str
    """Thinking content."""

    id: str | None = None
    """Optional content block ID."""

    signature_provider: str | None = Field(default=None, alias="signatureProvider")
    """Optional model provider or 'unknown'."""


class RedactedThinkingBlock(BaseModel):
    """Redacted thinking content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.RedactedThinking]
    """Content block type, always 'redacted_thinking'."""

    data: str
    """Redacted thinking data."""

    id: str | None = None
    """Optional content block ID."""


class ToolUseBlock(BaseModel):
    """Tool use content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.ToolUse]
    """Content block type, always 'tool_use'."""

    id: str
    """Tool use identifier."""

    input: dict[str, object]
    """Tool input parameters."""

    name: str
    """Tool name."""

    thought_signature: str | None = Field(default=None, alias="thoughtSignature")
    """Optional Gemini thought signature."""


class ToolResultBlock(BaseModel):
    """Tool result content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.ToolResult]
    """Content block type, always 'tool_result'."""

    tool_use_id: str = Field(alias="toolUseId")
    """Tool use ID this result corresponds to."""

    content: str | list[object] | None = None
    """Tool result content (string or array of content blocks)."""

    is_error: bool | None = Field(default=None, alias="isError")
    """Whether this result represents an error."""

    id: str | None = None
    """Optional content block ID."""


class DocumentBlock(BaseModel):
    """Document content block."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal[MessageContentBlockType.Document]
    """Content block type, always 'document'."""

    source: dict[str, object]
    """Document source (Base64PDF or PlainText — uses dict for flexibility)."""

    id: str | None = None
    """Optional content block ID."""


ContentBlock = Annotated[
    TextBlock
    | ImageBlock
    | ThinkingBlock
    | RedactedThinkingBlock
    | ToolUseBlock
    | ToolResultBlock
    | DocumentBlock,
    Field(discriminator="type"),
]
"""Discriminated union over all 7 content block types."""


# ============================================================
# FactoryDroidMessage
# ============================================================


class FactoryDroidMessage(BaseModel):
    """Factory Droid message schema.

    Used in CreateMessageNotification and session data.
    Ported from FactoryDroidMessageSchema in TypeScript.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    """Message identifier."""

    role: MessageRole
    """Message role (user, assistant, tool, system)."""

    content: list[ContentBlock]
    """Array of content blocks."""

    created_at: float = Field(alias="createdAt")
    """Creation timestamp."""

    updated_at: float = Field(alias="updatedAt")
    """Last update timestamp."""

    parent_id: str | None = Field(default=None, alias="parentId")
    """Optional parent message ID."""

    visibility: MessageVisibility | None = None
    """Optional message visibility."""

    openai_message_id: str | None = Field(default=None, alias="openaiMessageId")
    """Optional OpenAI message ID."""

    openai_phase: str | None = Field(default=None, alias="openaiPhase")
    """Optional OpenAI phase (commentary or final_answer)."""

    openai_encrypted_content: str | None = Field(
        default=None, alias="openaiEncryptedContent"
    )
    """Optional OpenAI encrypted content."""

    openai_reasoning_id: str | None = Field(default=None, alias="openaiReasoningId")
    """Optional OpenAI reasoning ID."""

    openai_reasoning_summary: str | None = Field(
        default=None, alias="openaiReasoningSummary"
    )
    """Optional OpenAI reasoning summary."""

    gemini_thought_signature: str | None = Field(
        default=None, alias="geminiThoughtSignature"
    )
    """Optional Gemini thought signature."""

    chat_completion_reasoning_field: str | None = Field(
        default=None, alias="chatCompletionReasoningField"
    )
    """Optional chat completion reasoning field ('reasoning' or 'reasoning_content')."""

    chat_completion_reasoning_content: str | None = Field(
        default=None, alias="chatCompletionReasoningContent"
    )
    """Optional chat completion reasoning content."""

    is_user_visible: bool | None = Field(default=None, alias="isUserVisible")
    """Deprecated: use visibility instead."""

    is_error: bool | None = Field(default=None, alias="isError")
    """Whether this message represents an error."""
