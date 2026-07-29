"""HTTP service surface for kb-ontology."""

from kb_ontology.service.app import OntologyService, ServiceHealth
from kb_ontology.service.http_api import (
    OPENAPI_SPEC,
    SecureServiceContext,
    build_secure_context_from_environment,
    create_http_server,
    create_secure_http_server,
)

__all__ = [
    "OPENAPI_SPEC",
    "OntologyService",
    "SecureServiceContext",
    "ServiceHealth",
    "build_secure_context_from_environment",
    "create_http_server",
    "create_secure_http_server",
]
