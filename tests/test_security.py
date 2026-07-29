"""Unit tests for auth, secrets, audit, and rate limiter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kb_ontology.runtime.rate_limit import TokenBucketRateLimiter
from kb_ontology.security import (
    APIKeyAuthenticator,
    AuthenticationError,
    AuthorizationError,
    AuditLog,
    EnvironmentSecretProvider,
    JSONFileSecretProvider,
    Principal,
    ROLE_PERMISSIONS,
    RotatingAPIKeyAuthenticator,
    TenantDatabaseRouter,
    bearer_token,
    normalize_tenant_id,
    require_permission,
)


def test_api_key_roundtrip_and_hmac() -> None:
    raw = "development-test-key-0001"
    auth = APIKeyAuthenticator.from_mapping(
        {
            raw: {
                "principal_id": "alice",
                "tenant_id": "acme",
                "roles": ["reader"],
            }
        }
    )
    principal = auth.authenticate(raw)
    assert principal.principal_id == "alice"
    assert principal.tenant_id == "acme"
    assert principal.allows("query:run")
    assert not principal.allows("extract:run")
    with pytest.raises(AuthenticationError):
        auth.authenticate("wrong-key-xxxxxxxxxxxx")


def test_admin_wildcard_and_require_permission() -> None:
    p = Principal("admin1", "default", ("admin",))
    require_permission(p, "extract:run")
    reader = Principal("r1", "default", ("reader",))
    with pytest.raises(AuthorizationError):
        require_permission(reader, "extract:run")


def test_short_key_rejected() -> None:
    with pytest.raises(ValueError, match="16"):
        APIKeyAuthenticator.from_mapping({"short": {"roles": ["reader"]}})


def test_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "development-test-key-0002": {
            "principal_id": "bob",
            "tenant_id": "t1",
            "roles": ["contributor"],
        }
    }
    monkeypatch.setenv("KB_ONTOLOGY_API_KEYS", json.dumps(payload))
    auth = APIKeyAuthenticator.from_environment()
    p = auth.authenticate("development-test-key-0002")
    assert p.allows("extract:run")


def test_bearer_and_tenant_normalize() -> None:
    assert bearer_token("Bearer abc") == "abc"
    with pytest.raises(AuthenticationError):
        bearer_token("Token x")
    assert normalize_tenant_id("Acme Corp!") == "acme-corp"
    with pytest.raises(ValueError):
        normalize_tenant_id("")


def test_tenant_router(tmp_path: Path) -> None:
    router = TenantDatabaseRouter(tmp_path)
    path = router.path_for("default")
    assert path.parent == tmp_path.resolve()
    assert path.name == "default.sqlite3"
    path.write_text("")  # touch
    assert router.list_tenants() == ["default"]


def test_audit_log(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "audit.db")
    log = AuditLog(conn)
    event = log.record(
        tenant_id="default",
        principal_id="alice",
        action="query:run",
        resource_type="query",
        metadata={"intent": "definition"},
    )
    assert event.event_id.startswith("audit_")
    listed = log.list(tenant_id="default")
    assert len(listed) == 1
    assert listed[0].metadata["intent"] == "definition"


def test_secret_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO_BAR", "secret-value")
    env = EnvironmentSecretProvider(prefix="FOO_")
    assert env.get_secret("BAR") == "secret-value"

    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"KB_ONTOLOGY_API_KEYS": {"k": {"roles": ["admin"]}}}), encoding="utf-8")
    # file stores nested object → serialized JSON string
    file_provider = JSONFileSecretProvider(path)
    raw = file_provider.get_secret("KB_ONTOLOGY_API_KEYS")
    assert "admin" in raw

    rotating = RotatingAPIKeyAuthenticator(
        EnvironmentSecretProvider(),
        secret_name="MISSING_KEY",
        refresh_interval_seconds=1.0,
    )
    monkeypatch.setenv(
        "MISSING_KEY",
        json.dumps(
            {
                "development-rotate-key-0001": {
                    "principal_id": "rot",
                    "tenant_id": "default",
                    "roles": ["admin"],
                }
            }
        ),
    )
    rotating = RotatingAPIKeyAuthenticator(
        EnvironmentSecretProvider(),
        secret_name="MISSING_KEY",
        refresh_interval_seconds=60.0,
    )
    p = rotating.authenticate("development-rotate-key-0001")
    assert p.principal_id == "rot"


def test_rate_limiter() -> None:
    limiter = TokenBucketRateLimiter(capacity=2, refill_per_second=0.001)
    assert limiter.consume("u1").allowed is True
    assert limiter.consume("u1").allowed is True
    denied = limiter.consume("u1")
    assert denied.allowed is False
    assert denied.retry_after_seconds > 0


def test_role_permissions_cover_ontology_ops() -> None:
    assert "query:run" in ROLE_PERMISSIONS["reader"]
    assert "extract:run" in ROLE_PERMISSIONS["contributor"]
    assert "*" in ROLE_PERMISSIONS["admin"]
