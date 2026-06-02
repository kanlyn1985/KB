"""Tests for LLM domain models.

These tests verify pure domain logic with no external dependencies.
"""

from __future__ import annotations

import pytest

from enterprise_agent_kb.domain.llm import (
    LLMClientError,
    LLMResponse,
    Message,
    Provider,
)


class TestProvider:
    """Test Provider enum."""

    def test_has_all_expected_providers(self) -> None:
        """Provider enum should include all expected provider types."""
        expected_providers = {"claude", "openai", "minimax", "astron"}
        actual_providers = {p.value for p in Provider}
        assert actual_providers == expected_providers

    def test_provider_values_are_strings(self) -> None:
        """All provider values should be lowercase strings."""
        for provider in Provider:
            assert isinstance(provider.value, str)
            assert provider.value.islower()


class TestMessage:
    """Test Message dataclass."""

    def test_create_message_with_role_and_content(self) -> None:
        """Message should store role and content."""
        message = Message(role="user", content="test query")
        assert message.role == "user"
        assert message.content == "test query"

    def test_message_accepts_empty_content(self) -> None:
        """Message should accept empty string content."""
        message = Message(role="system", content="")
        assert message.content == ""

    def test_message_preserves_special_characters(self) -> None:
        """Message should preserve special characters in content."""
        content = "测试查询 with 特殊字符: @#$%"
        message = Message(role="user", content=content)
        assert message.content == content


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_create_response_with_content_only(self) -> None:
        """LLMResponse should be creatable with just content."""
        response = LLMResponse(content="test response")
        assert response.content == "test response"
        assert response.model is None
        assert response.usage is None
        assert response.raw is None

    def test_create_response_with_all_fields(self) -> None:
        """LLMResponse should store all fields."""
        response = LLMResponse(
            content="test response",
            model="claude-3-5-sonnet-20241022",
            usage={"input_tokens": 10, "output_tokens": 20},
            raw={"id": "msg_123"},
        )
        assert response.content == "test response"
        assert response.model == "claude-3-5-sonnet-20241022"
        assert response.usage == {"input_tokens": 10, "output_tokens": 20}
        assert response.raw == {"id": "msg_123"}

    def test_response_usage_can_be_empty_dict(self) -> None:
        """LLMResponse should accept empty dict for usage."""
        response = LLMResponse(content="test", usage={})
        assert response.usage == {}

    def test_response_raw_can_be_empty_dict(self) -> None:
        """LLMResponse should accept empty dict for raw."""
        response = LLMResponse(content="test", raw={})
        assert response.raw == {}


class TestLLMClientError:
    """Test LLMClientError exception."""

    def test_error_is_exception_subclass(self) -> None:
        """LLMClientError should inherit from Exception."""
        assert issubclass(LLMClientError, Exception)

    def test_can_raise_and_catch_error(self) -> None:
        """LLMClientError should be raisable and catchable."""
        with pytest.raises(LLMClientError) as exc_info:
            raise LLMClientError("test error")
        assert str(exc_info.value) == "test error"

    def test_error_accepts_any_message(self) -> None:
        """LLMClientError should accept any string message."""
        error = LLMClientError("HTTP 500: Internal Server Error")
        assert "HTTP 500" in str(error)


class TestDomainModelsIntegration:
    """Test interactions between domain models."""

    def test_message_list_can_be_created(self) -> None:
        """Should be able to create list of Messages."""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello!"),
            Message(role="assistant", content="Hi there!"),
        ]
        assert len(messages) == 3
        assert messages[0].role == "system"
        assert messages[2].content == "Hi there!"

    def test_response_content_can_be_long(self) -> None:
        """LLMResponse should handle long content."""
        long_content = "test response" * 1000
        response = LLMResponse(content=long_content)
        assert len(response.content) == len(long_content)

    def test_response_with_unicode_content(self) -> None:
        """LLMResponse should handle Unicode content."""
        unicode_content = "测试响应 with 中文 and 特殊字符: 🚀 🌟"
        response = LLMResponse(content=unicode_content)
        assert "测试响应" in response.content
        assert "🚀" in response.content
