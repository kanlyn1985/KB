from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "reader": frozenset({"health:read", "query:run", "documents:read"}),
    "contributor": frozenset({"health:read", "query:run", "documents:read", "feedback:write"}),
    "indexer": frozenset({"health:read", "query:run", "documents:read", "feedback:write", "documents:index"}),
    "admin": frozenset({"*"}),
}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def permissions(self) -> frozenset[str]:
        values: set[str] = set()
        for role in self.roles:
            values.update(ROLE_PERMISSIONS.get(role, frozenset()))
        return frozenset(values)

    def allows(self, permission: str) -> bool:
        permissions = self.permissions()
        return "*" in permissions or permission in permissions

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class APIKeyRecord:
    key_digest: str
    principal: Principal
    enabled: bool = True


class AuthenticationError(PermissionError):
    pass


class AuthorizationError(PermissionError):
    pass


class APIKeyAuthenticator:
    """Constant-time API-key authentication with environment-backed secrets.

    Raw keys are hashed at construction time and are never returned by the
    public API. `AGENT_KB_API_KEYS` accepts a JSON object whose keys are API
    tokens and whose values contain `principal_id`, `tenant_id`, and `roles`.
    """

    def __init__(self, records: Iterable[APIKeyRecord]) -> None:
        self._records = tuple(records)

    @classmethod
    def from_mapping(cls, mapping: dict[str, dict[str, Any]]) -> APIKeyAuthenticator:
        records: list[APIKeyRecord] = []
        for raw_key, payload in mapping.items():
            key = str(raw_key or "")
            if len(key) < 16:
                raise ValueError("API keys must contain at least 16 characters")
            roles = tuple(str(role) for role in payload.get("roles") or ["reader"])
            unknown = [role for role in roles if role not in ROLE_PERMISSIONS]
            if unknown:
                raise ValueError(f"unsupported roles: {unknown}")
            principal = Principal(
                principal_id=str(payload.get("principal_id") or _key_identifier(key)),
                tenant_id=normalize_tenant_id(str(payload.get("tenant_id") or "default")),
                roles=roles,
                metadata=dict(payload.get("metadata") or {}),
            )
            records.append(
                APIKeyRecord(
                    key_digest=_digest_key(key),
                    principal=principal,
                    enabled=bool(payload.get("enabled", True)),
                )
            )
        return cls(records)

    @classmethod
    def from_environment(cls, variable: str = "AGENT_KB_API_KEYS") -> APIKeyAuthenticator:
        raw = os.environ.get(variable, "").strip()
        if not raw:
            raise ValueError(f"{variable} is not configured")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"{variable} must be a JSON object")
        return cls.from_mapping({str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)})

    def authenticate(self, raw_key: str) -> Principal:
        candidate = _digest_key(str(raw_key or ""))
        for record in self._records:
            if record.enabled and hmac.compare_digest(candidate, record.key_digest):
                return record.principal
        raise AuthenticationError("invalid API key")


def require_permission(principal: Principal, permission: str) -> None:
    if not principal.allows(permission):
        raise AuthorizationError(f"permission denied: {permission}")


class TenantDatabaseRouter:
    """Physical tenant isolation through one SQLite database per tenant."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, tenant_id: str) -> Path:
        normalized = normalize_tenant_id(tenant_id)
        path = (self.root_dir / f"{normalized}.sqlite3").resolve()
        root = self.root_dir.resolve()
        if root not in path.parents:
            raise ValueError("tenant database path escapes configured root")
        return path

    def list_tenants(self) -> list[str]:
        return sorted(path.stem for path in self.root_dir.glob("*.sqlite3") if path.is_file())


def normalize_tenant_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-").lower()
    if not normalized or len(normalized) > 64:
        raise ValueError("invalid tenant id")
    return normalized


def bearer_token(header_value: str | None) -> str:
    value = str(header_value or "").strip()
    if not value.lower().startswith("bearer "):
        raise AuthenticationError("Bearer authorization is required")
    token = value[7:].strip()
    if not token:
        raise AuthenticationError("Bearer token is empty")
    return token


def _digest_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _key_identifier(raw_key: str) -> str:
    return f"key_{_digest_key(raw_key)[:12]}"
