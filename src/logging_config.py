"""
Logging configuration for The Orchestrator.
Provides structured logging with appropriate levels and formatting.
"""

import logging
import logging.config
from pathlib import Path
from typing import Optional


DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - "
    "[%(filename)s:%(lineno)d] - %(message)s"
)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    detailed: bool = False,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output
        detailed: Whether to use detailed format with filename/lineno
    """
    log_format = DETAILED_LOG_FORMAT if detailed else DEFAULT_LOG_FORMAT

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": log_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            # Orchestrator modules
            "orchestrator": {
                "level": level,
                "handlers": ["console"],
                "propagate": False,
            },
            # Reduce noise from external libraries
            "httpx": {
                "level": "WARNING",
            },
            "httpcore": {
                "level": "WARNING",
            },
            "ollama": {
                "level": "WARNING",
            },
        },
    }

    # Add file handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "formatter": "default",
            "filename": str(log_file),
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
        }
        config["root"]["handlers"].append("file")
        config["loggers"]["orchestrator"]["handlers"].append("file")

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
