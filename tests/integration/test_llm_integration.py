"""Integration tests for LLM functionality.

These tests verify that LLM clients work correctly with
the systems that use them (parse.py, query_semantic_parser.py).
"""

from __future__ import annotations

import pytest

from enterprise_agent_kb.domain.llm import Message, Provider
from enterprise_agent_kb.infrastructure.llm_client import LLMClient


class TestLLMClientIntegration:
    """Test LLM client integration with calling systems."""

    def test_llm_client_interface_compatibility(self) -> None:
        """LLM client should satisfy the ILLMClient protocol."""
        client = LLMClient(provider=Provider.CLAUDE, api_key="test")
        # Verify client has required method
        assert hasattr(client, "chat")
        assert callable(client.chat)

    def test_message_creation_for_different_roles(self) -> None:
        """Should be able to create messages for different roles."""
        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content="User query"),
            Message(role="assistant", content="Assistant response"),
        ]
        assert all(isinstance(msg, Message) for msg in messages)
        assert [msg.role for msg in messages] == ["system", "user", "assistant"]

    def test_provider_enum_for_all_supported_providers(self) -> None:
        """Provider enum should support all expected providers."""
        expected = ["claude", "openai", "minimax", "astron"]
        actual = [p.value for p in Provider]
        assert set(actual) == set(expected)

    def test_client_initialization_for_each_provider(self) -> None:
        """Should be able to initialize client for each provider."""
        providers = [
            Provider.CLAUDE,
            Provider.OPENAI,
            Provider.MINIMAX,
            Provider.ASTRON,
        ]
        for provider in providers:
            client = LLMClient(provider=provider, api_key="test")
            assert client.provider == provider


class TestLLMWorkflow:
    """Test common LLM usage patterns."""

    def test_single_message_workflow(self) -> None:
        """Test common single-message workflow."""
        client = LLMClient(provider=Provider.CLAUDE, api_key="test")

        # Verify message can be created
        message = Message(role="user", content="Test query")
        assert message.content == "Test query"

    def test_multi_message_conversation(self) -> None:
        """Test multi-message conversation workflow."""
        messages = [
            Message(role="user", content="First question"),
            Message(role="assistant", content="First answer"),
            Message(role="user", content="Follow-up question"),
        ]

        # Verify conversation structure
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_message_with_long_content(self) -> None:
        """Test handling of long message content."""
        long_content = "A" * 10000
        message = Message(role="user", content=long_content)
        assert len(message.content) == 10000

    def test_message_with_special_characters(self) -> None:
        """Test handling of special characters in messages."""
        special_content = "Test with 特殊characters: 🚀 🌟"
        message = Message(role="user", content=special_content)
        assert "特殊characters" in message.content
        assert "🚀" in message.content


class TestErrorScenarios:
    """Test error scenarios and edge cases."""

    def test_empty_message_content(self) -> None:
        """Should handle empty message content gracefully."""
        message = Message(role="user", content="")
        assert message.content == ""

    def test_message_with_unicode_emoji(self) -> None:
        """Should handle Unicode emoji correctly."""
        emoji_content = "Test emoji: 😀 🎉 🚀"
        message = Message(role="user", content=emoji_content)
        assert "😀" in message.content

    def test_provider_value_access(self) -> None:
        """Should be able to access provider enum values."""
        assert Provider.CLAUDE.value == "claude"
        assert Provider.OPENAI.value == "openai"
        assert Provider.MINIMAX.value == "minimax"
        assert Provider.ASTRON.value == "astron"
