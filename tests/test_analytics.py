"""Tests for QueryAnalytics — ordering, limit, user field, UTC timestamps."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone


def _make_analytics(tmp_path):
    from analytics import QueryAnalytics
    return QueryAnalytics(log_dir=str(tmp_path))


def _write_entries(log_file: Path, entries: list):
    with open(log_file, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


class TestRecentOrdering:
    def test_newest_first(self, tmp_path):
        a = _make_analytics(tmp_path)
        _write_entries(a.log_file, [
            {"timestamp": "2026-06-14T08:00:00Z", "query": "oldest"},
            {"timestamp": "2026-06-14T09:00:00Z", "query": "middle"},
            {"timestamp": "2026-06-14T10:00:00Z", "query": "newest"},
        ])
        result = a.recent(limit=10)
        assert result[0]["query"] == "newest"
        assert result[-1]["query"] == "oldest"

    def test_respects_limit(self, tmp_path):
        a = _make_analytics(tmp_path)
        entries = [{"timestamp": f"2026-06-14T{i:02d}:00:00Z", "query": f"q{i}"} for i in range(10)]
        _write_entries(a.log_file, entries)
        result = a.recent(limit=3)
        assert len(result) == 3
        assert result[0]["query"] == "q9"

    def test_empty_file_returns_empty(self, tmp_path):
        a = _make_analytics(tmp_path)
        assert a.recent() == []

    def test_missing_file_returns_empty(self, tmp_path):
        a = _make_analytics(tmp_path)
        assert a.recent() == []


class TestQueryTrackerUTC:
    def test_timestamp_ends_with_z(self, tmp_path):
        a = _make_analytics(tmp_path)
        tracker = a.start_query("test query")
        tracker.finish(response_chars=100)
        entries = a.recent(limit=1)
        assert entries[0]["timestamp"].endswith("Z"), "timestamp must be UTC (ends with Z)"

    def test_timestamp_is_parseable_utc(self, tmp_path):
        a = _make_analytics(tmp_path)
        tracker = a.start_query("test query")
        tracker.finish()
        entries = a.recent(limit=1)
        ts = entries[0]["timestamp"]
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_user_field_stored(self, tmp_path):
        a = _make_analytics(tmp_path)
        tracker = a.start_query("test query", user="Prashant")
        tracker.finish()
        entries = a.recent(limit=1)
        assert entries[0]["user"] == "Prashant"

    def test_user_field_defaults_to_unknown(self, tmp_path):
        a = _make_analytics(tmp_path)
        tracker = a.start_query("test query")
        tracker.finish()
        entries = a.recent(limit=1)
        assert entries[0]["user"] == "Unknown"
