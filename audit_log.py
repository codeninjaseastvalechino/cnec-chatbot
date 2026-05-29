"""
Simple JSON-based audit logging for the chatbot.

Logs all interactions (user messages, assistant responses, errors) to a JSON file
for internal auditing purposes.
"""

import json
import os
from datetime import datetime
from pathlib import Path


class AuditLogger:
    """Simple file-based audit logger."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"

    def log_event(self, event_type: str, data: dict) -> None:
        """
        Log an event to the audit log.

        Args:
            event_type: Type of event (e.g., "user_message", "assistant_response", "error")
            data: Event data as a dictionary
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            **data
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_log(self, limit: int = 100) -> list:
        """
        Read the last N entries from the audit log.

        Args:
            limit: Maximum number of entries to return (most recent first)

        Returns:
            List of audit log entries (dicts)
        """
        if not self.log_file.exists():
            return []

        with open(self.log_file, "r") as f:
            lines = f.readlines()

        entries = []
        for line in reversed(lines[-limit:]):
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass

        return list(reversed(entries))
