"""Unified logging configuration for KB1.

This module provides structured logging configuration
replacing print statements with proper logging.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(
    level: str | int = logging.INFO,
    log_file: str | Path | None = None,
    format_string: str | None = None,
) -> None:
    """Setup unified logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for file logging
        format_string: Custom format string
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logger
    logging.basicConfig(
        level=level,
        format=format_string,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Add file handler if log file specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(format_string))
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with consistent configuration.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    return logger


# Convenience loggers for different components
def get_query_logger() -> logging.Logger:
    """Get logger for query components."""
    return get_logger("enterprise_agent_kb.query")


def get_database_logger() -> logging.Logger:
    """Get logger for database components."""
    return get_logger("enterprise_agent_kb.database")


def get_llm_logger() -> logging.Logger:
    """Get logger for LLM components."""
    return get_logger("enterprise_agent_kb.llm")


def get_eval_logger() -> logging.Logger:
    """Get logger for evaluation components."""
    return get_logger("enterprise_agent_kb.eval")


def get_parse_logger() -> logging.Logger:
    """Get logger for document parsing components."""
    return get_logger("enterprise_agent_kb.parse")
