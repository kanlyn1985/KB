"""Authentication, authorization, tenant isolation, audit, and secret contracts."""

from kb_ontology.security.audit import AuditEvent, AuditLog
from kb_ontology.security.auth import (
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
from kb_ontology.security.secrets import (
    CompositeSecretProvider,
    EnvironmentSecretProvider,
    HTTPSecretProvider,
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
    "HTTPSecretProvider",
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
