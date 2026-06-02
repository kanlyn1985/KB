"""Tests for LLM client infrastructure implementations.

These tests verify LLM client initialization and configuration
without requiring real API calls.
"""

from __future__ import annotations

import pytest

from enterprise_agent_kb.domain.llm import Message, Provider
from enterprise_agent_kb.infrastructure.llm_client import LLMClient


class TestLLMClientInit:
    """Test LLMClient initialization."""

    def test_init_with_defaults(self) -> None:
        """LLMClient should initialize with default provider."""
        client = LLMClient()
        assert client.provider == Provider.CLAUDE

    def test_init_with_claude_provider(self) -> None:
        """LLMClient should initialize with Claude provider."""
        client = LLMClient(provider=Provider.CLAUDE)
        assert client.provider == Provider.CLAUDE
        assert client.api_base is not None

    def test_init_with_openai_provider(self) -> None:
        """LLMClient should initialize with OpenAI provider."""
        client = LLMClient(provider=Provider.OPENAI)
        assert client.provider == Provider.OPENAI

    def test_init_with_minimax_provider(self) -> None:
        """LLMClient should initialize with MiniMax provider."""
        client = LLMClient(provider=Provider.MINIMAX)
        assert client.provider == Provider.MINIMAX

    def test_init_with_astron_provider(self) -> None:
        """LLMClient should initialize with Astron provider."""
        client = LLMClient(provider=Provider.ASTRON)
        assert client.provider == Provider.ASTRON

    def test_init_with_custom_timeout(self) -> None:
        """LLMClient should accept custom timeout."""
        client = LLMClient(timeout=120.0)
        assert client.timeout == 120.0

    def test_init_with_custom_retries(self) -> None:
        """LLMClient should accept custom max retries."""
        client = LLMClient(max_retries=5)
        assert client.max_retries == 5

    def test_init_with_custom_api_base(self) -> None:
        """LLMClient should accept custom API base URL."""
        custom_base = "https://custom.api.com"
        client = LLMClient(provider=Provider.CLAUDE, api_base=custom_base)
        assert custom_base in client.api_base

    def test_init_with_custom_api_key(self) -> None:
        """LLMClient should accept custom API key."""
        custom_key = "test-api-key-12345"
        client = LLMClient(provider=Provider.CLAUDE, api_key=custom_key)
        assert client.api_key == custom_key


class TestLLMClientConfiguration:
    """Test LLMClient configuration for different providers."""

    def test_claude_default_model_from_env(self) -> None:
        """Claude client should load model from environment."""
        import os
        original = os.environ.get("CLAUDE_MODEL")
        os.environ["CLAUDE_MODEL"] = "test-claude-model"
        try:
            client = LLMClient(provider=Provider.CLAUDE)
            assert "test-claude-model" in client._default_model
        finally:
            if original:
                os.environ["CLAUDE_MODEL"] = original
            else:
                os.environ.pop("CLAUDE_MODEL", None)

    def test_openai_default_model_from_env(self) -> None:
        """OpenAI client should load model from environment."""
        import os
        original = os.environ.get("OPENAI_MODEL")
        os.environ["OPENAI_MODEL"] = "test-gpt-model"
        try:
            client = LLMClient(provider=Provider.OPENAI)
            assert "test-gpt-model" in client._default_model
        finally:
            if original:
                os.environ["OPENAI_MODEL"] = original
            else:
                os.environ.pop("OPENAI_MODEL", None)

    def test_claude_api_base_from_env(self) -> None:
        """Claude client should load API base from environment."""
        import os
        original = os.environ.get("ANTHROPIC_BASE_URL")
        os.environ["ANTHROPIC_BASE_URL"] = "https://test.api.com/anthropic"
        try:
            client = LLMClient(provider=Provider.CLAUDE)
            assert "test.api.com" in client.api_base
        finally:
            if original:
                os.environ["ANTHROPIC_BASE_URL"] = original
            else:
                os.environ.pop("ANTHROPIC_BASE_URL", None)


class TestLLMClientInterface:
    """Test LLMClient interface compliance."""

    def test_has_chat_method(self) -> None:
        """LLMClient should have chat method."""
        client = LLMClient(provider=Provider.CLAUDE, api_key="test")
        assert hasattr(client, "chat")
        assert callable(client.chat)

    def test_chat_method_signature(self) -> None:
        """chat method should accept expected parameters."""
        import inspect
        client = LLMClient(provider=Provider.CLAUDE, api_key="test")
        sig = inspect.signature(client.chat)
        params = list(sig.parameters.keys())
        assert "messages" in params
        assert "model" in params
        assert "system_prompt" in params
        assert "temperature" in params
        assert "max_tokens" in params


class TestProviderSelection:
    """Test provider selection logic."""

    def test_unknown_provider_raises_error(self) -> None:
        """Unknown provider should raise LLMClientError."""
        from enterprise_agent_kb.domain.llm import LLMClientError, Provider

        # Create a mock provider that doesn't exist
        class MockProvider:
            value = "mock_provider"

        with pytest.raises(LLMClientError):
            LLMClient(provider=MockProvider)


class TestConvenienceFunctions:
    """Test convenience factory functions."""

    def test_create_claude_client(self) -> None:
        """create_claude_client should return Claude client."""
        from enterprise_agent_kb.infrastructure.llm_client import create_claude_client

        client = create_claude_client(api_key="test")
        assert client.provider == Provider.CLAUDE

    def test_create_openai_client(self) -> None:
        """create_openai_client should return OpenAI client."""
        from enterprise_agent_kb.infrastructure.llm_client import create_openai_client

        client = create_openai_client(api_key="test")
        assert client.provider == Provider.OPENAI

    def test_create_minimax_client(self) -> None:
        """create_minimax_client should return MiniMax client."""
        from enterprise_agent_kb.infrastructure.llm_client import create_minimax_client

        client = create_minimax_client(api_key="test")
        assert client.provider == Provider.MINIMAX

    def test_create_claude_client_with_custom_params(self) -> None:
        """create_claude_client should pass custom parameters."""
        from enterprise_agent_kb.infrastructure.llm_client import create_claude_client

        client = create_claude_client(
            api_base="https://custom.example.com",
            api_key="custom-key",
            timeout=90.0,
        )
        assert "custom.example.com" in client.api_base
        assert client.api_key == "custom-key"
        assert client.timeout == 90.0


class TestLLMClientAttributes:
    """Test LLMClient attribute configuration."""

    def test_provider_attribute_stored(self) -> None:
        """Provider should be stored as instance attribute."""
        client = LLMClient(provider=Provider.OPENAI, api_key="test")
        assert client.provider == Provider.OPENAI

    def test_timeout_attribute_stored(self) -> None:
        """Timeout should be stored as instance attribute."""
        client = LLMClient(timeout=45.0)
        assert client.timeout == 45.0

    def test_retries_attribute_stored(self) -> None:
        """Max retries should be stored as instance attribute."""
        client = LLMClient(max_retries=3)
        assert client.max_retries == 3

    def test_api_key_attribute_stored(self) -> None:
        """API key should be stored when provided."""
        client = LLMClient(api_key="my-key-123")
        assert client.api_key == "my-key-123"
