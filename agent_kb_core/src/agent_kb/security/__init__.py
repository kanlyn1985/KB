"""Authentication, authorization, tenant isolation, and audit contracts."""

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

__all__ = [
    "APIKeyAuthenticator",
    "APIKeyRecord",
    "AuditEvent",
    "AuditLog",
    "AuthenticationError",
    "AuthorizationError",
    "Principal",
    "ROLE_PERMISSIONS",
    "TenantDatabaseRouter",
    "bearer_token",
    "normalize_tenant_id",
    "require_permission",
]
