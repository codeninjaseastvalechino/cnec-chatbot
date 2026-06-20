"""Tests for ChatbotEngine helper methods — no API calls, no LLM."""
import threading
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
    engine._last_gbs_sessions = None
    engine._last_appointments = None
    engine._last_export_label = None
    engine._chat_lock = threading.Lock()
    return engine


def _register_fake_tool(engine, name):
    """Register a no-op tool on the engine."""
    engine._tools[name] = {"handler": lambda _: f"result:{name}"}


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


# ---------------------------------------------------------------------------
# _execute_tool — flag tracking
# ---------------------------------------------------------------------------

class TestExecuteToolCaching:
    def test_unknown_tool_returns_error_message(self):
        engine = _make_engine()
        result = engine._execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_gbs_sessions_starts_none(self):
        engine = _make_engine()
        assert engine._last_gbs_sessions is None

    def test_non_schedule_tool_does_not_clear_gbs_cache(self):
        """lookup_student should not touch _last_gbs_sessions."""
        engine = _make_engine()
        fake_sessions = [MagicMock()]
        engine._last_gbs_sessions = fake_sessions
        _register_fake_tool(engine, "lookup_student")
        engine._execute_tool("lookup_student", {})
        assert engine._last_gbs_sessions is fake_sessions  # unchanged


# ---------------------------------------------------------------------------
# Export label — set correctly by each handler cache block
# ---------------------------------------------------------------------------

class TestExportLabel:
    def test_initial_export_label_is_none(self):
        engine = _make_engine()
        assert engine._last_export_label is None

    def test_gbs_tours_handler_sets_label(self):
        """_handle_get_gbs_tours must set _last_export_label = 'gbs_tours'."""
        from datetime import datetime
        engine = _make_engine()

        fake_session = MagicMock()
        fake_session.child_display = ["Journei (4y)"]
        fake_session.item_id = "123"
        fake_session.time_display.return_value = "3:00 PM"
        fake_session.date_display.return_value = "Monday, June 15"
        fake_session.student_name = "Wittie Hughes"
        fake_session.tour_type = "GBS"
        fake_session.assignee_name = "Venay"

        resolved_dt = datetime(2026, 6, 15, 0, 0)
        with patch.object(engine, "_resolve_tool_date", return_value=(resolved_dt, None)), \
             patch("sites.lineleader.schedules.get_sessions_for_date", return_value=[fake_session]), \
             patch("chatbot.enrich_sessions_with_children"):
            engine._handle_get_gbs_tours({"date_str": "today"})

        assert engine._last_export_label == "gbs_tours"
        assert engine._last_appointments == []
        assert engine._last_gbs_sessions == [fake_session]

    def test_upcoming_gbs_tours_handler_sets_label(self):
        """_handle_get_upcoming_gbs_tours must set _last_export_label = 'gbs_tours'."""
        fake_session = MagicMock()
        fake_session.child_display = []
        fake_session.item_id = "456"
        fake_session.time_display.return_value = "4:00 PM"
        fake_session.date_display.return_value = "Tuesday, June 16"
        fake_session.student_name = "Jane Doe"
        fake_session.tour_type = "JR GBS"
        fake_session.assignee_name = "Venay"

        with patch("chatbot.get_bearer_token", return_value="tok"), \
             patch("sites.lineleader.schedules.get_upcoming_gbs_tours", return_value=[fake_session]), \
             patch("chatbot.enrich_sessions_with_children"):
            engine = _make_engine()
            engine._handle_get_upcoming_gbs_tours({})

        assert engine._last_export_label == "gbs_tours"
        assert engine._last_appointments == []


# ---------------------------------------------------------------------------
# _has_tool_use_in_content  and  _sanitize_history
# ---------------------------------------------------------------------------

def _tool_use_block(tool_id="tu_abc"):
    return {"type": "tool_use", "id": tool_id, "name": "get_full_schedule", "input": {}}

def _tool_result_block(tool_id="tu_abc"):
    return {"type": "tool_result", "tool_use_id": tool_id, "content": "some result"}

def _text_block():
    return {"type": "text", "text": "Here is the schedule."}

# Minimal Anthropic-SDK-style object (has .type attribute, not a dict)
class _FakeBlock:
    def __init__(self, type_):
        self.type = type_

class TestHasToolUseInContent:
    def _e(self):
        return _make_engine()

    def test_empty_list_returns_false(self):
        assert self._e()._has_tool_use_in_content([]) is False

    def test_plain_string_returns_false(self):
        assert self._e()._has_tool_use_in_content("some text") is False

    def test_text_block_dict_returns_false(self):
        assert self._e()._has_tool_use_in_content([_text_block()]) is False

    def test_tool_result_dict_returns_false(self):
        assert self._e()._has_tool_use_in_content([_tool_result_block()]) is False

    def test_tool_use_dict_returns_true(self):
        assert self._e()._has_tool_use_in_content([_tool_use_block()]) is True

    def test_mixed_blocks_with_tool_use_returns_true(self):
        content = [_text_block(), _tool_use_block()]
        assert self._e()._has_tool_use_in_content(content) is True

    def test_sdk_style_object_tool_use_returns_true(self):
        # Anthropic SDK stores ToolUseBlock objects with a .type attribute
        content = [_FakeBlock("tool_use")]
        assert self._e()._has_tool_use_in_content(content) is True

    def test_sdk_style_object_text_returns_false(self):
        content = [_FakeBlock("text")]
        assert self._e()._has_tool_use_in_content(content) is False


class TestSanitizeHistory:
    """
    Verify _sanitize_history() removes orphaned tool_use blocks from the
    conversation history tail without touching valid history.
    """

    def _e(self, history):
        engine = _make_engine()
        engine.conversation_history = history
        return engine

    # ------------------------------------------------------------------
    # Cases that should NOT change history
    # ------------------------------------------------------------------

    def test_empty_history_unchanged(self):
        e = self._e([])
        e._sanitize_history()
        assert e.conversation_history == []

    def test_clean_text_only_history_unchanged(self):
        history = [
            {"role": "user", "content": "What is the schedule?"},
            {"role": "assistant", "content": [_text_block()]},
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 2

    def test_valid_tool_use_with_results_unchanged(self):
        """tool_use immediately followed by tool_results is valid — must not be trimmed."""
        history = [
            {"role": "user", "content": "What is the schedule?"},
            {"role": "assistant", "content": [_tool_use_block("tu_1")]},
            {"role": "user", "content": [_tool_result_block("tu_1")]},
            {"role": "assistant", "content": [_text_block()]},
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 4

    def test_multi_turn_all_valid_unchanged(self):
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "assistant", "content": [_tool_use_block("tu_1")]},
            {"role": "user", "content": [_tool_result_block("tu_1")]},
            {"role": "assistant", "content": [_text_block()]},
            {"role": "user", "content": "who is Veshant?"},
            {"role": "assistant", "content": [_tool_use_block("tu_2")]},
            {"role": "user", "content": [_tool_result_block("tu_2")]},
            {"role": "assistant", "content": [_text_block()]},
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 8

    # ------------------------------------------------------------------
    # Cases that SHOULD trim history
    # ------------------------------------------------------------------

    def test_orphaned_tool_use_at_end_trimmed(self):
        """
        assistant[tool_use] with nothing after it → must be removed.
        The prior clean assistant[text] becomes the new tail.
        """
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "assistant", "content": [_text_block()]},      # clean end state
            {"role": "user", "content": "who is Veshant?"},
            {"role": "assistant", "content": [_tool_use_block()]},  # orphaned
        ]
        e = self._e(history)
        e._sanitize_history()
        # Should keep only the first two messages (up to and including the clean assistant)
        assert len(e.conversation_history) == 2
        assert e.conversation_history[-1]["role"] == "assistant"
        assert not e._has_tool_use_in_content(e.conversation_history[-1]["content"])

    def test_orphaned_tool_use_followed_by_plain_user_msg_trimmed(self):
        """
        assistant[tool_use] followed by a plain user text (not tool_results) is
        also corrupt — the plain user message is part of the corrupted turn.
        """
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "assistant", "content": [_text_block()]},      # clean
            {"role": "user", "content": "who is Veshant?"},
            {"role": "assistant", "content": [_tool_use_block()]},  # orphaned
            {"role": "user", "content": "What is my full schedule today?"},  # new request on top
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 2
        assert e.conversation_history[-1]["role"] == "assistant"

    def test_orphaned_at_very_start_clears_all(self):
        """
        If there is no prior clean assistant[text] to fall back to,
        the entire history is cleared.
        """
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "assistant", "content": [_tool_use_block()]},  # orphaned, nothing before it
        ]
        e = self._e(history)
        e._sanitize_history()
        assert e.conversation_history == []

    def test_orphaned_preserves_earlier_valid_turns(self):
        """
        Multiple valid turns followed by one corrupt turn: only the corrupt
        turn is removed; earlier valid history is preserved.
        """
        history = [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": [_tool_use_block("tu_1")]},
            {"role": "user", "content": [_tool_result_block("tu_1")]},
            {"role": "assistant", "content": [_text_block()]},   # valid end ← cutoff here
            {"role": "user", "content": "turn 2"},
            {"role": "assistant", "content": [_tool_use_block("tu_2")]},  # orphaned
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 4
        assert e.conversation_history[-1]["content"] == [_text_block()]

    def test_idempotent_after_clean(self):
        """Calling sanitize twice on already-clean history is a no-op."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [_text_block()]},
        ]
        e = self._e(history)
        e._sanitize_history()
        e._sanitize_history()
        assert len(e.conversation_history) == 2

    # ------------------------------------------------------------------
    # Mode B: orphaned tool_results (no preceding tool_use) — race condition
    # ------------------------------------------------------------------

    def test_orphaned_tool_results_at_end_trimmed(self):
        """
        user[tool_results] whose preceding message is NOT assistant[tool_use]
        (Mode B — the race condition seen in Railway: a concurrent thread slips
        a plain user message between the tool_use append and tool_results append,
        so tool_results ends up paired with the wrong predecessor).
        """
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "assistant", "content": [_text_block()]},           # clean ← keep
            {"role": "user", "content": "who is Veshant?"},              # interloper
            {"role": "user", "content": [_tool_result_block("tu_x")]},  # orphaned
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 2
        assert e.conversation_history[-1]["role"] == "assistant"

    def test_valid_tool_results_preceded_by_tool_use_unchanged(self):
        """Mode B detector must not flag a correctly-paired tool_results message."""
        history = [
            {"role": "user", "content": "who is Veshant?"},
            {"role": "assistant", "content": [_tool_use_block("tu_1")]},
            {"role": "user", "content": [_tool_result_block("tu_1")]},
            {"role": "assistant", "content": [_text_block()]},
        ]
        e = self._e(history)
        e._sanitize_history()
        assert len(e.conversation_history) == 4

    def test_mode_b_no_prior_clean_state_clears_all(self):
        """Mode B: orphaned tool_results with no prior assistant[text] → clear all."""
        history = [
            {"role": "user", "content": "schedule?"},
            {"role": "user", "content": [_tool_result_block("tu_x")]},
        ]
        e = self._e(history)
        e._sanitize_history()
        assert e.conversation_history == []

    # ------------------------------------------------------------------
    # Thread-safety
    # ------------------------------------------------------------------

    def test_chat_lock_exists(self):
        """ChatbotEngine must expose _chat_lock so concurrent requests are serialized."""
        import threading
        e = _make_engine()
        assert hasattr(e, "_chat_lock")
        # threading.Lock() returns a _thread.lock; isinstance check via a known lock
        lock = threading.Lock()
        assert type(e._chat_lock) == type(lock)
