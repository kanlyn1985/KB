"""Authentication, authorization, and tenant-isolation contracts."""

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
    "AuthenticationError",
    "AuthorizationError",
    "Principal",
    "ROLE_PERMISSIONS",
    "TenantDatabaseRouter",
    "bearer_token",
    "normalize_tenant_id",
    "require_permission",
]
