"""Unit tests for AppEndpoints default and override behavior."""
from __future__ import annotations

import os

import pytest

from enterprise_agent_kb.config import AppEndpoints


EXPECTED_DEFAULTS = {
    "minimax_api_host": "https://api.minimaxi.com",
    "minimax_anthropic_base": "https://api.minimaxi.com/anthropic",
    "anthropic_base_url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic",
    "openai_api_base": "https://api.openai.com/v1",
    "astron_api_base": "https://maas-coding-api.cn-huabei-1.xf-yun.com",
}


def test_app_endpoints_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIMAX_API_HOST", raising=False)
    monkeypatch.delenv("MINIMAX_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("ASTRON_API_BASE", raising=False)
    endpoints = AppEndpoints.from_env()
    for field_name, expected in EXPECTED_DEFAULTS.items():
        assert getattr(endpoints, field_name) == expected, field_name


def test_app_endpoints_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_HOST", "http://localhost:9000")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:9001")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:9002")
    monkeypatch.setenv("ASTRON_API_BASE", "http://localhost:9003")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "http://localhost:9004")
    endpoints = AppEndpoints.from_env()
    assert endpoints.minimax_api_host == "http://localhost:9000"
    assert endpoints.anthropic_base_url == "http://localhost:9001"
    assert endpoints.openai_api_base == "http://localhost:9002"
    assert endpoints.astron_api_base == "http://localhost:9003"
    assert endpoints.minimax_anthropic_base == "http://localhost:9004"


def test_app_endpoints_is_frozen() -> None:
    endpoints = AppEndpoints.from_env()
    with pytest.raises((AttributeError, Exception)):
        endpoints.minimax_api_host = "https://example.com"  # type: ignore[misc]
