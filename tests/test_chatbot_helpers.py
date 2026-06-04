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
    engine.conversation_history = []
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


# ---------------------------------------------------------------------------
# OTP exchange added to conversation_history
# ---------------------------------------------------------------------------

class TestOtpConversationHistory:
    def test_otp_exchange_added_to_history(self):
        engine = _make_engine()
        engine._awaiting_mystudio_otp = True

        # Stub out the actual OTP handler
        engine._handle_otp_submission = MagicMock(return_value="✅ MyStudio connected!")

        result = engine.chat("621458")

        assert result == "✅ MyStudio connected!"
        # Both user message and assistant response must be in history
        assert any(m["role"] == "user" and m["content"] == "621458"
                   for m in engine.conversation_history)
        assert any(m["role"] == "assistant" and "✅" in m["content"]
                   for m in engine.conversation_history)

    def test_otp_failure_still_added_to_history(self):
        engine = _make_engine()
        engine._awaiting_mystudio_otp = True
        engine._handle_otp_submission = MagicMock(return_value="❌ OTP failed: wrong code")

        engine.chat("000000")

        assert any(m["role"] == "user" for m in engine.conversation_history)
        assert any(m["role"] == "assistant" for m in engine.conversation_history)
