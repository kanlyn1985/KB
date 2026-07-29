"""Unit tests for LLMChatClient (Anthropic + OpenAI wire formats)."""

from __future__ import annotations

import io
import json
from unittest import mock
from urllib import error

import pytest

from kb_ontology.llm.llm_client import (
    LLMChatClient,
    LLMClientError,
    _resolve_api_format,
)


def _anthropic_body(text: str, model: str = "test-model") -> bytes:
    return json.dumps(
        {
            "id": "msg_1",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    ).encode()


def _openai_body(text: str, model: str = "grok-4.5") -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl_1",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": text,
                        "reasoning_content": "thinking…",
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    ).encode()


def _patch_urlopen(payload: bytes, *, capture: list | None = None):
    def _open(req, timeout=None):  # noqa: ANN001
        if capture is not None:
            capture.append(req)
        return io.BytesIO(payload)

    return _open


class TestResolveApiFormat:
    def test_explicit_openai(self):
        assert _resolve_api_format(explicit="openai", endpoint="") == "openai"

    def test_explicit_anthropic(self):
        assert _resolve_api_format(explicit="anthropic", endpoint="") == "anthropic"

    def test_krill_endpoint_is_openai(self):
        assert (
            _resolve_api_format(
                explicit="",
                endpoint="https://api.cdn-krill-ai.com/v1",
            )
            == "openai"
        )

    def test_anthropic_path_wins(self):
        assert (
            _resolve_api_format(
                explicit="",
                endpoint="https://maas.example.com/anthropic",
            )
            == "anthropic"
        )


class TestAnthropicChat:
    def test_posts_to_v1_messages(self, monkeypatch):
        captured: list = []
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _patch_urlopen(_anthropic_body("hello"), capture=captured),
        )
        client = LLMChatClient(
            endpoint="https://proxy.example.com",
            model="claude-test",
            api_key="k",
            api_format="anthropic",
        )
        resp = client.chat("hi", system_prompt="sys")
        assert resp.content == "hello"
        assert resp.model == "test-model"
        assert len(captured) == 1
        req = captured[0]
        assert req.full_url.endswith("/v1/messages")
        assert req.get_header("X-api-key") == "k" or req.headers.get("x-api-key") == "k"
        body = json.loads(req.data.decode())
        assert body["messages"][0]["content"] == "hi"
        assert body["system"] == "sys"


class TestOpenAIChat:
    def test_posts_to_chat_completions(self, monkeypatch):
        captured: list = []
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _patch_urlopen(_openai_body("pong"), capture=captured),
        )
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="secret",
            api_format="openai",
        )
        resp = client.chat("ping", system_prompt="be brief")
        assert resp.content == "pong"
        assert resp.model == "grok-4.5"
        assert resp.usage_json["total_tokens"] == 15

        req = captured[0]
        assert req.full_url == "https://api.cdn-krill-ai.com/v1/chat/completions"
        assert "Bearer secret" in (
            req.get_header("Authorization") or req.headers.get("Authorization") or ""
        )
        assert req.get_header("User-agent") or req.headers.get("User-Agent")
        body = json.loads(req.data.decode())
        assert body["model"] == "grok-4.5"
        assert body["messages"][0] == {"role": "system", "content": "be brief"}
        assert body["messages"][1] == {"role": "user", "content": "ping"}

    def test_ignores_reasoning_content(self, monkeypatch):
        """Krill returns reasoning_content; we only surface message.content."""
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _patch_urlopen(_openai_body("final answer")),
        )
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="k",
            api_format="openai",
        )
        assert client.chat("q").content == "final answer"

    def test_http_error_surfaces_status(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise error.HTTPError(
                url="https://x/v1/chat/completions",
                code=403,
                msg="Forbidden",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b"blocked"),
            )

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="k",
            api_format="openai",
        )
        with pytest.raises(LLMClientError, match="HTTPError 403"):
            client.chat("q")


class TestFromEnvironment:
    def test_krill_env_resolves_openai(self, monkeypatch):
        monkeypatch.setenv("AGENT_KB_LLM_ENDPOINT", "https://api.cdn-krill-ai.com/v1")
        monkeypatch.setenv("AGENT_KB_LLM_MODEL", "grok-4.5")
        monkeypatch.setenv("AGENT_KB_LLM_API_KEY", "nb_test")
        monkeypatch.delenv("AGENT_KB_LLM_API_FORMAT", raising=False)
        client = LLMChatClient.from_environment(load_dotenv=False)
        assert client is not None
        assert client.api_format == "openai"
        assert client.model == "grok-4.5"
        assert client.endpoint == "https://api.cdn-krill-ai.com/v1"

    def test_explicit_format_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_KB_LLM_ENDPOINT", "https://api.cdn-krill-ai.com/v1")
        monkeypatch.setenv("AGENT_KB_LLM_MODEL", "grok-4.5")
        monkeypatch.setenv("AGENT_KB_LLM_API_KEY", "nb_test")
        monkeypatch.setenv("AGENT_KB_LLM_API_FORMAT", "anthropic")
        client = LLMChatClient.from_environment(load_dotenv=False)
        assert client is not None
        assert client.api_format == "anthropic"

    def test_missing_key_returns_none(self, monkeypatch):
        for var in (
            "AGENT_KB_LLM_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("AGENT_KB_LLM_ENDPOINT", "https://api.cdn-krill-ai.com/v1")
        assert LLMChatClient.from_environment(load_dotenv=False) is None

    def test_repr_hides_key(self):
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="super-secret",
            api_format="openai",
        )
        text = repr(client)
        assert "super-secret" not in text
        assert "api_key=***" in text
        assert "api_format='openai'" in text
