"""LLM client implementations for various providers.

This module contains concrete implementations of LLM clients,
handling HTTP communication with provider APIs.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..domain.llm import ILLMClient, LLMClientError, LLMResponse, Message, Provider
from ..config import AppEndpoints


class LLMClient(ILLMClient):
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: Provider = Provider.CLAUDE,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        """Initialize LLM client.

        Args:
            provider: LLM provider type
            api_base: API base URL (default: load from env)
            api_key: API key (default: load from env)
            timeout: Request timeout in seconds
            max_retries: Max retry attempts on failure
        """
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max_retries

        # Load from environment if not provided
        endpoints = AppEndpoints.from_env()
        if provider == Provider.CLAUDE:
            self.api_base = (api_base or endpoints.anthropic_base_url).rstrip("/")
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self._default_model = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        elif provider == Provider.OPENAI:
            self.api_base = (api_base or endpoints.openai_api_base).rstrip("/")
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            self._default_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        elif provider == Provider.MINIMAX:
            self.api_base = (api_base or endpoints.minimax_api_host).rstrip("/")
            self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
            self._default_model = os.environ.get("MINIMAX_MODEL", "abab6.5s-chat")
        elif provider == Provider.ASTRON:
            self.api_base = (api_base or endpoints.astron_api_base).rstrip("/")
            self.api_key = api_key or os.environ.get("ASTRON_API_KEY", "")
            self._default_model = os.environ.get("ASTRON_MODEL", "astron-vlm")
        else:
            raise LLMClientError(f"Unknown provider: {provider}")

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
        model = model or self._default_model

        for attempt in range(self.max_retries + 1):
            try:
                if self.provider == Provider.CLAUDE:
                    return self._claude_chat(
                        messages, model, system_prompt, temperature, max_tokens, **kwargs
                    )
                elif self.provider in {Provider.OPENAI, Provider.ASTRON}:
                    return self._openai_chat(
                        messages, model, system_prompt, temperature, max_tokens, **kwargs
                    )
                elif self.provider == Provider.MINIMAX:
                    return self._minimax_vlm(
                        messages, model, temperature, max_tokens, **kwargs
                    )
            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries:
                    raise LLMClientError(f"HTTP {e.response.status_code}: {e}")
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == self.max_retries:
                    raise LLMClientError(f"Network error: {e}")
            except Exception as e:
                if attempt == self.max_retries:
                    raise LLMClientError(f"LLM error: {e}")

        raise LLMClientError("Max retries exceeded")

    def _claude_chat(
        self,
        messages: list[Message],
        model: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> LLMResponse:
        """Call Claude Messages API."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Convert messages to Claude format
        content = []
        for msg in messages:
            content.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": content,
            **kwargs,
        }
        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=self.timeout) as client:
            response = httpx.post(
                f"{self.api_base}/v1/messages",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        content_blocks = data.get("content", [])
        if isinstance(content_blocks, list):
            content_text = "\n".join(
                block.get("text", "") for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            content_text = str(content_blocks)

        return LLMResponse(
            content=content_text,
            model=data.get("model"),
            usage=data.get("usage"),
            raw=data,
        )

    def _openai_chat(
        self,
        messages: list[Message],
        model: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> LLMResponse:
        """Call OpenAI-compatible Chat Completions API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

        # Convert messages to OpenAI format
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        for msg in messages:
            msgs.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = httpx.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        return LLMResponse(
            content=content,
            model=data.get("model"),
            usage=data.get("usage"),
            raw=data,
        )

    def _minimax_vlm(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> LLMResponse:
        """Call MiniMax VLM API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

        # Extract prompt and image_url from messages
        prompt = ""
        image_url = ""
        for msg in messages:
            if msg.role == "user":
                content = msg.content
                if isinstance(content, str):
                    prompt = content
                elif isinstance(content, dict):
                    prompt = content.get("text", "")
                    image_url = content.get("image_url", "")

        payload = {"prompt": prompt, "image_url": image_url, **kwargs}

        with httpx.Client(timeout=self.timeout) as client:
            response = httpx.post(
                f"{self.api_base}/v1/coding_plan/vlm",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code")
        if status_code and status_code != 0:
            raise LLMClientError(f"MiniMax error {status_code}: {base_resp.get('status_msg', '')}")

        content = data.get("reply", "")

        return LLMResponse(
            content=content,
            model=model,
            raw=data,
        )


# Convenience functions for common providers


def create_claude_client(
    api_base: str | None = None,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> LLMClient:
    """Create Claude LLM client."""
    return LLMClient(
        provider=Provider.CLAUDE,
        api_base=api_base,
        api_key=api_key,
        timeout=timeout,
    )


def create_openai_client(
    api_base: str | None = None,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> LLMClient:
    """Create OpenAI-compatible LLM client."""
    return LLMClient(
        provider=Provider.OPENAI,
        api_base=api_base,
        api_key=api_key,
        timeout=timeout,
    )


def create_minimax_client(
    api_host: str | None = None,
    api_key: str | None = None,
    timeout: float = 180.0,
) -> LLMClient:
    """Create MiniMax VLM client."""
    return LLMClient(
        provider=Provider.MINIMAX,
        api_base=api_host,
        api_key=api_key,
        timeout=timeout,
    )
