"""Authentication, authorization, tenant isolation, audit, and secret contracts."""

from .audit import AuditEvent, AuditLog
from .auth import (
    APIKeyAuthenticator,
    APIKeyRecord,
    AuthenticationError,
    AuthorizationError,
    Principal,
    ROLE_PERMISSIONS,
    TenantDatabaseRouter,
    bearer_token,
    normalize_tenant_id,
    require_permission,
)
from .secrets import (
    CompositeSecretProvider,
    EnvironmentSecretProvider,
    JSONFileSecretProvider,
    RotatingAPIKeyAuthenticator,
    SecretProvider,
)

__all__ = [
    "APIKeyAuthenticator",
    "APIKeyRecord",
    "AuditEvent",
    "AuditLog",
    "AuthenticationError",
    "AuthorizationError",
    "CompositeSecretProvider",
    "EnvironmentSecretProvider",
    "JSONFileSecretProvider",
    "Principal",
    "ROLE_PERMISSIONS",
    "RotatingAPIKeyAuthenticator",
    "SecretProvider",
    "TenantDatabaseRouter",
    "bearer_token",
    "normalize_tenant_id",
    "require_permission",
]
