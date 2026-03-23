"""Tests for message schemas (FactoryDroidMessage and content blocks)."""

from __future__ import annotations

import json

from droid_sdk.schemas.messages import (
    DocumentBlock,
    DocumentSourceType,
    FactoryDroidMessage,
    ImageBlock,
    MessageContentBlockType,
    MessageRole,
    MessageVisibility,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

# ============================================================
# Message enums
# ============================================================


class TestMessageEnums:
    """Tests for message-level enums."""

    def test_message_role_values(self) -> None:
        assert MessageRole.User.value == "user"
        assert MessageRole.Assistant.value == "assistant"
        assert MessageRole.Tool.value == "tool"
        assert MessageRole.System.value == "system"
        assert len(MessageRole) == 4

    def test_message_visibility_values(self) -> None:
        assert MessageVisibility.Both.value == "both"
        assert MessageVisibility.LLMOnly.value == "llm_only"
        assert MessageVisibility.UserOnly.value == "user_only"
        assert len(MessageVisibility) == 3

    def test_message_content_block_type_values(self) -> None:
        assert MessageContentBlockType.Text.value == "text"
        assert MessageContentBlockType.Image.value == "image"
        assert MessageContentBlockType.Thinking.value == "thinking"
        assert MessageContentBlockType.RedactedThinking.value == "redacted_thinking"
        assert MessageContentBlockType.ToolUse.value == "tool_use"
        assert MessageContentBlockType.ToolResult.value == "tool_result"
        assert MessageContentBlockType.Document.value == "document"
        assert len(MessageContentBlockType) == 7

    def test_document_source_type_values(self) -> None:
        assert DocumentSourceType.Base64.value == "base64"
        assert DocumentSourceType.Text.value == "text"
        assert len(DocumentSourceType) == 2

    def test_json_serialization_raw_strings(self) -> None:
        """String enums serialize as raw strings in JSON."""
        assert json.dumps(MessageRole.User) == '"user"'
        assert json.dumps(MessageVisibility.Both) == '"both"'
        assert json.dumps(MessageContentBlockType.Text) == '"text"'


# ============================================================
# Content block models
# ============================================================


class TestTextBlock:
    def test_construction(self) -> None:
        block = TextBlock(type=MessageContentBlockType.Text, text="Hello")
        assert block.type == MessageContentBlockType.Text
        assert block.text == "Hello"
        assert block.id is None

    def test_from_dict(self) -> None:
        block = TextBlock.model_validate({"type": "text", "text": "Hi"})
        assert block.text == "Hi"


class TestToolUseBlock:
    def test_construction(self) -> None:
        block = ToolUseBlock(
            type=MessageContentBlockType.ToolUse,
            id="tu-1",
            input={"command": "ls"},
            name="Execute",
        )
        assert block.id == "tu-1"
        assert block.name == "Execute"
        assert block.input == {"command": "ls"}

    def test_with_thought_signature(self) -> None:
        block = ToolUseBlock.model_validate(
            {
                "type": "tool_use",
                "id": "tu-1",
                "input": {},
                "name": "test",
                "thoughtSignature": "sig123",
            }
        )
        assert block.thought_signature == "sig123"


class TestToolResultBlock:
    def test_string_content(self) -> None:
        block = ToolResultBlock.model_validate(
            {
                "type": "tool_result",
                "toolUseId": "tu-1",
                "content": "some result text",
            }
        )
        assert block.tool_use_id == "tu-1"
        assert block.content == "some result text"

    def test_array_content(self) -> None:
        block = ToolResultBlock.model_validate(
            {
                "type": "tool_result",
                "toolUseId": "tu-1",
                "content": [{"type": "text", "text": "result"}],
            }
        )
        assert isinstance(block.content, list)


class TestThinkingBlock:
    def test_construction(self) -> None:
        block = ThinkingBlock.model_validate(
            {
                "type": "thinking",
                "signature": "abc",
                "thinking": "I think...",
            }
        )
        assert block.thinking == "I think..."
        assert block.signature == "abc"


class TestRedactedThinkingBlock:
    def test_construction(self) -> None:
        block = RedactedThinkingBlock.model_validate(
            {"type": "redacted_thinking", "data": "encrypted-data"}
        )
        assert block.data == "encrypted-data"


class TestDocumentBlock:
    def test_construction(self) -> None:
        block = DocumentBlock.model_validate(
            {
                "type": "document",
                "source": {
                    "type": "text",
                    "mediaType": "text/plain",
                    "data": "hello",
                },
            }
        )
        assert block.source["type"] == "text"


class TestImageBlock:
    def test_construction(self) -> None:
        block = ImageBlock.model_validate(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "data": "abc123",
                    "mediaType": "image/png",
                },
            }
        )
        assert block.source.media_type == "image/png"


# ============================================================
# FactoryDroidMessage
# ============================================================


class TestFactoryDroidMessage:
    """Tests for the FactoryDroidMessage model."""

    def test_minimal_construction(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-1",
                "role": "assistant",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            }
        )
        assert msg.id == "msg-1"
        assert msg.role == MessageRole.Assistant
        assert msg.content == []
        assert msg.created_at == 1700000000
        assert msg.updated_at == 1700000000

    def test_with_content_blocks(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-2",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {
                        "type": "tool_use",
                        "id": "tu-1",
                        "input": {"cmd": "ls"},
                        "name": "Execute",
                    },
                ],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            }
        )
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextBlock)
        assert isinstance(msg.content[1], ToolUseBlock)

    def test_with_all_optional_fields(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-3",
                "role": "user",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
                "parentId": "p-1",
                "visibility": "both",
                "openaiMessageId": "oai-1",
                "openaiPhase": "commentary",
                "openaiEncryptedContent": "enc",
                "openaiReasoningId": "r-1",
                "openaiReasoningSummary": "sum",
                "geminiThoughtSignature": "sig",
                "chatCompletionReasoningField": "reasoning",
                "chatCompletionReasoningContent": "content",
                "isUserVisible": True,
                "isError": False,
            }
        )
        assert msg.parent_id == "p-1"
        assert msg.visibility == MessageVisibility.Both
        assert msg.openai_message_id == "oai-1"
        assert msg.openai_phase == "commentary"
        assert msg.openai_encrypted_content == "enc"
        assert msg.openai_reasoning_id == "r-1"
        assert msg.openai_reasoning_summary == "sum"
        assert msg.gemini_thought_signature == "sig"
        assert msg.chat_completion_reasoning_field == "reasoning"
        assert msg.chat_completion_reasoning_content == "content"
        assert msg.is_user_visible is True
        assert msg.is_error is False

    def test_optional_fields_default_to_none(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-4",
                "role": "user",
                "content": [],
                "createdAt": 0,
                "updatedAt": 0,
            }
        )
        assert msg.parent_id is None
        assert msg.visibility is None
        assert msg.openai_message_id is None
        assert msg.is_error is None

    def test_camel_case_serialization(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-5",
                "role": "assistant",
                "content": [],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
                "parentId": "p-1",
            }
        )
        dumped = msg.model_dump(by_alias=True)
        assert "createdAt" in dumped
        assert "updatedAt" in dumped
        assert "parentId" in dumped

    def test_json_roundtrip(self) -> None:
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-6",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
                "createdAt": 1700000000,
                "updatedAt": 1700000000,
            }
        )
        roundtripped = FactoryDroidMessage.model_validate_json(
            msg.model_dump_json(by_alias=True)
        )
        assert roundtripped.id == msg.id
        assert roundtripped.role == msg.role
        assert len(roundtripped.content) == 1

    def test_extra_fields_allowed(self) -> None:
        """FactoryDroidMessage uses extra='allow' for forward compatibility."""
        msg = FactoryDroidMessage.model_validate(
            {
                "id": "msg-7",
                "role": "user",
                "content": [],
                "createdAt": 0,
                "updatedAt": 0,
                "someFutureField": "value",
            }
        )
        assert msg.id == "msg-7"

    def test_role_enum_values(self) -> None:
        """All 4 roles are accepted."""
        for role in ["user", "assistant", "tool", "system"]:
            msg = FactoryDroidMessage.model_validate(
                {
                    "id": "msg",
                    "role": role,
                    "content": [],
                    "createdAt": 0,
                    "updatedAt": 0,
                }
            )
            assert msg.role.value == role

    def test_serializes_to_none_in_json(self) -> None:
        """The message value 'none' for ReasoningEffort serializes correctly."""
        from droid_sdk.schemas.enums import ReasoningEffort

        assert ReasoningEffort.NONE.value == "none"
        assert json.dumps(ReasoningEffort.NONE) == '"none"'
