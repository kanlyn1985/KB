from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib import error, parse, request

from .auth import APIKeyAuthenticator, Principal


class SecretProvider(Protocol):
    def get_secret(self, name: str) -> str: ...


@dataclass(frozen=True)
class EnvironmentSecretProvider:
    prefix: str = ""

    def get_secret(self, name: str) -> str:
        key = f"{self.prefix}{name}"
        value = os.environ.get(key)
        if value is None:
            raise KeyError(key)
        return value


@dataclass(frozen=True)
class JSONFileSecretProvider:
    path: Path

    def get_secret(self, name: str) -> str:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or name not in payload:
            raise KeyError(name)
        value = payload[name]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class HTTPSecretProvider:
    """Generic secret-manager adapter using GET `/secrets/{name}`."""

    base_url: str
    bearer_token: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("secret manager URL must use http or https")

    def get_secret(self, name: str) -> str:
        headers = {"Accept": "application/json", **self.headers}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        outbound = request.Request(
            self.base_url.rstrip("/") + "/secrets/" + parse.quote(name, safe=""),
            headers=headers,
            method="GET",
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 404:
                raise KeyError(name) from exc
            raise RuntimeError(f"secret manager HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"secret manager request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict) or "value" not in payload:
            raise RuntimeError("secret manager response must contain value")
        value = payload["value"]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)

    def __repr__(self) -> str:
        return (
            "HTTPSecretProvider("
            f"base_url={self.base_url!r}, timeout_seconds={self.timeout_seconds})"
        )


class CompositeSecretProvider:
    def __init__(self, *providers: SecretProvider) -> None:
        self.providers = tuple(providers)

    def get_secret(self, name: str) -> str:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return provider.get_secret(name)
            except KeyError as exc:
                last_error = exc
        raise KeyError(name) from last_error


class RotatingAPIKeyAuthenticator:
    """Reload API-key mappings from a secret provider on a bounded cadence."""

    def __init__(
        self,
        provider: SecretProvider,
        *,
        secret_name: str = "AGENT_KB_API_KEYS",
        refresh_interval_seconds: float = 30.0,
    ) -> None:
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be positive")
        self.provider = provider
        self.secret_name = secret_name
        self.refresh_interval_seconds = float(refresh_interval_seconds)
        self._authenticator: APIKeyAuthenticator | None = None
        self._loaded_value: str | None = None
        self._next_refresh = 0.0
        self._lock = threading.Lock()

    def authenticate(self, raw_key: str) -> Principal:
        self.refresh()
        assert self._authenticator is not None
        return self._authenticator.authenticate(raw_key)

    def refresh(self, *, force: bool = False, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else float(now)
        if not force and timestamp < self._next_refresh and self._authenticator is not None:
            return False
        with self._lock:
            if not force and timestamp < self._next_refresh and self._authenticator is not None:
                return False
            raw = self.provider.get_secret(self.secret_name)
            changed = raw != self._loaded_value or self._authenticator is None
            if changed:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("API-key secret must be a JSON object")
                mapping = {
                    str(key): dict(value)
                    for key, value in payload.items()
                    if isinstance(value, dict)
                }
                self._authenticator = APIKeyAuthenticator.from_mapping(mapping)
                self._loaded_value = raw
            self._next_refresh = timestamp + self.refresh_interval_seconds
            return changed
