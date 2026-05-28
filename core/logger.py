"""
core/logger.py
==============
Shared structured JSON logger for all modules.

Usage:
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.error("Something failed: %s", error)

Output format (to logs/cnec_chatbot.log):
    {"timestamp": "2026-05-27T16:45:44.076568+00:00", "level": "INFO", "module": "sites.lineleader.auth", "message": "..."}
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "cnec_chatbot.log")


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": message,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that writes structured JSON to logs/cnec_chatbot.log
    and plain text to the console (INFO+ only).
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    # File handler — JSON, DEBUG+
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter())
    logger.addHandler(file_handler)

    # Console handler — plain text, INFO+
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger
