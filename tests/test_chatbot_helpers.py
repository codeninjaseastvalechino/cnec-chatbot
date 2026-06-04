"""Tests for ChatbotEngine helper methods — no API calls, no LLM."""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock


def _make_engine():
    """Instantiate ChatbotEngine with all external calls stubbed out."""
    from chatbot import ChatbotEngine
    engine = ChatbotEngine.__new__(ChatbotEngine)
    engine.bearer_token = "fake-token"
    engine._tools = {}
    engine._awaiting_mystudio_otp = False
    return engine


class TestResolveToolDate:
    TODAY = date(2026, 6, 4)  # Thursday

    def _resolve(self, tool_input, key="date_str", default="today"):
        engine = _make_engine()
        with patch("core.date_utils.date") as mock_date:
            mock_date.today.return_value = self.TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            return engine._resolve_tool_date(tool_input, key=key, default=default)

    def test_returns_resolved_date_on_success(self):
        resolved, err = self._resolve({"date_str": "Friday"})
        assert err is None
        assert resolved.date() == date(2026, 6, 5)

    def test_returns_none_error_on_conflict(self):
        resolved, err = self._resolve({"date_str": "Friday June 6th"})
        assert resolved is None
        assert "Saturday" in err
        assert "Friday" in err

    def test_defaults_to_today_when_key_missing(self):
        resolved, err = self._resolve({})
        assert err is None
        assert resolved.date() == self.TODAY

    def test_defaults_to_today_when_value_empty(self):
        resolved, err = self._resolve({"date_str": ""})
        assert err is None
        assert resolved.date() == self.TODAY

    def test_custom_key(self):
        resolved, err = self._resolve({"after_date_str": "Friday"}, key="after_date_str")
        assert err is None
        assert resolved.date() == date(2026, 6, 5)

    def test_explicit_date_resolves(self):
        resolved, err = self._resolve({"date_str": "June 9th"})
        assert err is None
        assert resolved.date() == date(2026, 6, 9)

    def test_tomorrow_resolves(self):
        resolved, err = self._resolve({"date_str": "tomorrow"})
        assert err is None
        assert resolved.date() == date(2026, 6, 5)

    def test_ordinal_only_resolves(self):
        # "8th" alone — today is June 4, so June 8
        resolved, err = self._resolve({"date_str": "8th"})
        assert err is None
        assert resolved.date() == date(2026, 6, 8)
