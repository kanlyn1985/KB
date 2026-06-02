"""LLM domain models and interfaces.

This module contains pure domain concepts for LLM interactions,
with zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Provider(Enum):
    """LLM provider types."""
    CLAUDE = "claude"
    OPENAI = "openai"
    MINIMAX = "minimax"
    ASTRON = "astron"


@dataclass
class Message:
    """Chat message."""
    role: str
    content: str


@dataclass
class LLMResponse:
    """LLM response wrapper."""
    content: str
    model: str | None = None
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None


class LLMClientError(Exception):
    """LLM client error."""
    pass


class ILLMClient(Protocol):
    """LLM client interface.

    This protocol defines the contract for LLM clients.
    Implementations should handle provider-specific communication.
    """

    def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """Send chat completion request.

        Args:
            messages: List of chat messages
            model: Model name (default: provider default)
            system_prompt: System prompt (Claude only)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional provider-specific params

        Returns:
            LLMResponse with content and metadata
        """
        ...
