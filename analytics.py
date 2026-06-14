"""
analytics.py
============
Query analytics logging — tracks every chat interaction with enough detail
to answer: "what are users asking most?" and "which tools get called most?"

Log file: logs/query_analytics.jsonl  (one JSON object per line)

Each entry captures:
  - timestamp       when the query arrived
  - query           what the user typed (or the quick-query label)
  - query_type      "natural_language" | "quick_query" (future shortcut path)
  - tools           list of {name, inputs, duration_s} — all tools called per query
  - total_duration_s  wall time from query received to response sent
  - response_chars  size of the final response text

Designed to be trivially queryable with jq or pandas:

  # Most common tools:
  jq -r '.tools[].name' logs/query_analytics.jsonl | sort | uniq -c | sort -rn

  # Slowest queries:
  jq -r '[.total_duration_s, .query] | @tsv' logs/query_analytics.jsonl | sort -rn | head -10

  # Quick-query vs natural language split:
  jq -r '.query_type' logs/query_analytics.jsonl | sort | uniq -c
"""

import json
from datetime import datetime, date as date_type
from pathlib import Path
from typing import Optional, List, Dict, Any


class QueryAnalytics:
    """
    Records one entry per user query to logs/query_analytics.jsonl.

    Usage (see chatbot.py for integration):

        analytics = QueryAnalytics()
        tracker = analytics.start_query("show me today's schedule", "natural_language")
        tracker.record_tool("get_full_schedule", {"date": "2026-06-03"}, duration_s=20.1)
        tracker.finish(response_chars=512)
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_file = Path(log_dir) / "query_analytics.jsonl"
        self.log_file.parent.mkdir(exist_ok=True)

    def start_query(self, query: str, query_type: str = "natural_language", user: str = "Unknown") -> "QueryTracker":
        """
        Begin tracking a new query. Returns a QueryTracker to record tools + finish.

        query_type:
          "natural_language" — user typed free text, routed through Claude
          "quick_query"      — user clicked a shortcut button, tool called directly (future)
        """
        return QueryTracker(query=query, query_type=query_type, log_file=self.log_file, user=user)

    def top_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most frequently seen query strings (case-insensitive)."""
        if not self.log_file.exists():
            return []
        counts: Dict[str, int] = {}
        with open(self.log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    q = entry.get("query", "").strip().lower()
                    counts[q] = counts.get(q, 0) + 1
                except Exception:
                    pass
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"query": q, "count": c} for q, c in sorted_items[:limit]]

    def top_intents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Group queries by normalized intent: tool name + date bucket.

        Buckets:
          today    — date matches today
          tomorrow — date is tomorrow
          past     — date is before today
          future   — date is 2+ days ahead
          -        — tool has no date input (e.g. reschedule_tour)
          none     — no tool called (pure conversation)

        Examples:
          "get_full_schedule / today"    count: 18
          "get_full_schedule / future"   count: 7
          "get_gbs_tours / today"        count: 5
          "reschedule_tour / -"          count: 2
          "none"                         count: 1
        """
        if not self.log_file.exists():
            return []

        counts: Dict[str, int] = {}
        today = date_type.today()

        with open(self.log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    tools = entry.get("tools", [])

                    if not tools:
                        key = "none"
                        counts[key] = counts.get(key, 0) + 1
                        continue

                    for tool in tools:
                        name = tool.get("name", "unknown")
                        date_str = tool.get("inputs", {}).get("date", "")
                        bucket = _date_bucket(date_str, today)
                        key = f"{name} / {bucket}"
                        counts[key] = counts.get(key, 0) + 1

                except Exception:
                    pass

        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"intent": k, "count": c} for k, c in sorted_items[:limit]]

    def top_tools(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most frequently called tools."""
        if not self.log_file.exists():
            return []
        counts: Dict[str, int] = {}
        with open(self.log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    for tool in entry.get("tools", []):
                        name = tool.get("name", "unknown")
                        counts[name] = counts.get(name, 0) + 1
                except Exception:
                    pass
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"tool": t, "count": c} for t, c in sorted_items[:limit]]

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the N most recent entries (newest first)."""
        if not self.log_file.exists():
            return []
        with open(self.log_file) as f:
            lines = f.readlines()
        entries = []
        for line in reversed(lines[-limit:]):
            try:
                entries.append(json.loads(line.strip()))
            except Exception:
                pass
        return entries


def _date_bucket(date_str: str, today: date_type) -> str:
    """Classify a YYYY-MM-DD date string relative to today."""
    if not date_str:
        return "-"
    try:
        d = date_type.fromisoformat(date_str)
        delta = (d - today).days
        if delta == 0:
            return "today"
        elif delta == 1:
            return "tomorrow"
        elif delta > 1:
            return "future"
        else:
            return "past"
    except ValueError:
        return "-"


class QueryTracker:
    """
    Tracks a single query in flight. Created by QueryAnalytics.start_query().
    Call record_tool() for each tool used, then finish() when done.
    """

    def __init__(self, query: str, query_type: str, log_file: Path, user: str = "Unknown"):
        self._query = query
        self._query_type = query_type
        self._log_file = log_file
        self._started_at = datetime.utcnow()
        self._tools: List[Dict[str, Any]] = []
        self._user = user

    def record_tool(self, name: str, inputs: Dict[str, Any], duration_s: float) -> None:
        """Record a tool call that happened during this query."""
        self._tools.append({
            "name": name,
            "inputs": inputs,
            "duration_s": round(duration_s, 2),
        })

    def finish(self, response_chars: int = 0) -> None:
        """Write the completed entry to the analytics log."""
        total_s = (datetime.utcnow() - self._started_at).total_seconds()
        entry = {
            "timestamp": self._started_at.isoformat(timespec="seconds") + "Z",
            "user": self._user,
            "query": self._query,
            "query_type": self._query_type,
            "tools": self._tools,
            "total_duration_s": round(total_s, 2),
            "response_chars": response_chars,
        }
        with open(self._log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
