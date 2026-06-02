"""Common exceptions for enterprise agent knowledge base.

This module provides a unified exception hierarchy for better error handling and debugging.
"""

from __future__ import annotations


class KB1Error(Exception):
    """Base exception for all KB1 errors."""
    pass


class DatabaseError(KB1Error):
    """Database operation errors."""
    pass


class RepositoryError(KB1Error):
    """Repository operation errors."""
    pass


class LLMError(KB1Error):
    """LLM client communication errors."""
    pass


class ValidationError(KB1Error):
    """Data validation errors."""
    pass


class ConfigurationError(KB1Error):
    """Configuration errors."""
    pass


class DocumentProcessingError(KB1Error):
    """Document parsing and processing errors."""
    pass


class QueryError(KB1Error):
    """Query parsing and execution errors."""
    pass


class RetrievalError(KB1Error):
    """Information retrieval errors."""
    pass


class EvaluationError(KB1Error):
    """Test evaluation errors."""
    pass


class NetworkError(KB1Error):
    """Network communication errors."""
    pass


class TimeoutError(KB1Error):
    """Operation timeout errors."""
    pass
