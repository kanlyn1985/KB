"""LLM chat client — Anthropic Messages and OpenAI Chat Completions.

Zero-dependency HTTP client for chat endpoints. Two wire formats:

- ``anthropic`` — POST ``{endpoint}/v1/messages`` (x-api-key)
- ``openai``    — POST ``{endpoint}/chat/completions`` (Bearer)

Krill (``https://api.cdn-krill-ai.com/v1`` + ``grok-4.5``) uses the OpenAI
format. Some gateways block the default ``Python-urllib/*`` User-Agent, so
requests always send an explicit client UA.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib import error, request

ApiFormat = Literal["anthropic", "openai"]


class LLMClientError(RuntimeError):
    """Raised when an LLM chat request fails."""


@dataclass(frozen=True)
class LLMChatResponse:
    """A completed chat response from the LLM."""

    content: str
    model: str
    usage_json: dict[str, Any]
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "usage": dict(self.usage_json),
        }


@dataclass(frozen=True)
class LLMChatClient:
    """Chat client for Anthropic- or OpenAI-compatible gateways.

    Secrets are read from environment variables and never appear in repr.
    """

    endpoint: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    api_format: ApiFormat = "anthropic"
    provider_id: str = "llm-chat-v1"
    user_agent: str = "kb-ontology/0.1"

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("LLM endpoint must use http or https")
        if not self.model.strip():
            raise ValueError("LLM model name is required")
        if self.api_format not in ("anthropic", "openai"):
            raise ValueError(
                f"api_format must be 'anthropic' or 'openai', got {self.api_format!r}"
            )

    # ── construction ──────────────────────────────────────────────────

    @classmethod
    def from_environment(
        cls,
        *,
        endpoint_var: str = "AGENT_KB_LLM_ENDPOINT",
        model_var: str = "AGENT_KB_LLM_MODEL",
        api_key_var: str = "AGENT_KB_LLM_API_KEY",
        timeout_var: str = "AGENT_KB_LLM_TIMEOUT",
        format_var: str = "AGENT_KB_LLM_API_FORMAT",
        load_dotenv: bool = True,
    ) -> LLMChatClient | None:
        """Build a client from environment variables.

        Resolution order for each field is documented inline. Returns None
        if no API key is configured.

        When ``load_dotenv`` is true, a project-local ``.env`` (cwd, then
        package parents) is loaded into ``os.environ`` if the key is not
        already set — never overwrites an explicit shell export.
        """
        if load_dotenv:
            _load_dotenv_if_present()

        endpoint = os.environ.get(endpoint_var, "").strip()
        if not endpoint:
            endpoint = os.environ.get("OPENAI_BASE_URL", "").strip()
        if not endpoint:
            endpoint = os.environ.get("ANTHROPIC_BASE_URL", "").strip()

        model = os.environ.get(model_var, "").strip()
        if not model:
            model = os.environ.get("OPENAI_MODEL", "").strip()
        if not model:
            model = os.environ.get("ANTHROPIC_MODEL", "").strip()
        if not model:
            model = os.environ.get("TEXT_LLM_MODEL", "").strip()
        if not model:
            model = os.environ.get("CLAUDE_MODEL", "").strip()
        if not model:
            model = "claude-3-5-sonnet-20241022"

        api_key = os.environ.get(api_key_var, "")
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None

        api_format = _resolve_api_format(
            explicit=os.environ.get(format_var, "").strip(),
            endpoint=endpoint,
        )

        try:
            timeout = float(os.environ.get(timeout_var, "120") or 120)
        except (ValueError, TypeError):
            timeout = 120.0

        provider_id = (
            "openai-compatible-chat-v1"
            if api_format == "openai"
            else "anthropic-compatible-chat-v1"
        )

        return cls(
            endpoint=endpoint.rstrip("/"),
            model=model,
            api_key=api_key,
            timeout_seconds=timeout,
            api_format=api_format,
            provider_id=provider_id,
        )

    # ── chat ──────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        *,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMChatResponse:
        """Send a chat completion request.

        Raises:
            LLMClientError: On HTTP errors, timeouts, or malformed responses.
        """
        if self.api_format == "openai":
            return self._chat_openai(
                user_message,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        return self._chat_anthropic(
            user_message,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _chat_anthropic(
        self,
        user_message: str,
        *,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMChatResponse:
        url = f"{self.endpoint}/v1/messages"
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max(1, int(max_tokens)),
            "temperature": max(0.0, min(float(temperature), 1.0)),
            "messages": [{"role": "user", "content": user_message}],
        }
        if system_prompt.strip():
            body["system"] = system_prompt.strip()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        data = self._post_json(url, headers, body)
        return self._parse_anthropic_response(data)

    def _chat_openai(
        self,
        user_message: str,
        *,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMChatResponse:
        # endpoint is expected to already include the /v1 prefix for OpenAI
        # gateways (e.g. https://api.cdn-krill-ai.com/v1).
        url = f"{self.endpoint.rstrip('/')}/chat/completions"
        messages: list[dict[str, str]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_message})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max(1, int(max_tokens)),
            "temperature": max(0.0, min(float(temperature), 2.0)),
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {self.api_key}",
        }
        data = self._post_json(url, headers, body)
        return self._parse_openai_response(data)

    def _post_json(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        raw = json.dumps(body).encode("utf-8")
        outbound = request.Request(url, data=raw, headers=headers, method="POST")
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                detail = str(exc)
            raise LLMClientError(
                f"LLM chat request failed: HTTPError {exc.code}: {detail}"
            ) from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise LLMClientError(
                f"LLM chat request failed: {type(exc).__name__}"
            ) from exc

        if not isinstance(data, dict):
            raise LLMClientError("LLM response must be a JSON object")
        return data

    def _parse_anthropic_response(self, data: dict[str, Any]) -> LLMChatResponse:
        content_blocks = data.get("content", [])
        if not isinstance(content_blocks, list):
            raise LLMClientError("LLM response content must be an array")

        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(str(text))

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        model_used = str(data.get("model", self.model))
        return LLMChatResponse(
            content="\n".join(text_parts),
            model=model_used,
            usage_json=dict(usage),
            raw_response=data,
        )

    def _parse_openai_response(self, data: dict[str, Any]) -> LLMChatResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMClientError("OpenAI response must include a non-empty choices array")

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            # Some gateways return a list of content parts.
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        parts.append(str(part.get("text", "")))
                content = "\n".join(p for p in parts if p)
            else:
                content = str(content)

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        model_used = str(data.get("model", self.model))
        return LLMChatResponse(
            content=content,
            model=model_used,
            usage_json=dict(usage),
            raw_response=data,
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(endpoint={self.endpoint!r}, "
            f"model={self.model!r}, api_format={self.api_format!r}, api_key=***)"
        )


# ── helpers ───────────────────────────────────────────────────────────


def _resolve_api_format(*, explicit: str, endpoint: str) -> ApiFormat:
    """Pick wire format from explicit env or endpoint heuristics."""
    value = explicit.lower()
    if value in ("openai", "openai-chat", "chat-completions"):
        return "openai"
    if value in ("anthropic", "claude", "messages"):
        return "anthropic"

    ep = endpoint.lower()
    # Known OpenAI-style gateways (base already ends with /v1).
    openai_markers = (
        "cdn-krill-ai.com",
        "api.openai.com",
        "openai.azure.com",
        "/v1",
    )
    # Anthropic-style markers win when both could match.
    anthropic_markers = (
        "anthropic.com",
        "/anthropic",
        "xf-yun.com/anthropic",
        "bigmodel.cn/api/anthropic",
        "api.z.ai/api/anthropic",
    )
    if any(m in ep for m in anthropic_markers):
        return "anthropic"
    if any(m in ep for m in openai_markers):
        # bare ".../v1" is ambiguous; only treat as openai when not anthropic path
        if ep.rstrip("/").endswith("/v1") or "cdn-krill-ai.com" in ep or "api.openai.com" in ep:
            return "openai"
    # Default keeps prior behaviour for local Anthropic-compatible proxies.
    return "anthropic"


def _load_dotenv_if_present() -> None:
    """Load KEY=VAL from the nearest .env into os.environ (no overwrite)."""
    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.append(cwd / ".env")
    # Walk up from this file: .../src/kb_ontology/llm/llm_client.py → project root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / ".env")
        if parent.name == "kb-ontology" or (parent / "pyproject.toml").exists():
            break

    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if not key:
                continue
            # Never clobber an explicit shell export.
            if key in os.environ and os.environ[key] != "":
                continue
            os.environ[key] = value
        # Only load the first .env found (nearest wins).
        break
