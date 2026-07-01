"""Tests for app.get_engine() — per-browser-session engine registry.

Runs the app in TEST_MODE so engines are MockChatbotEngine (no LLM/network).
TEST_MODE is set before importing app so the mock factory is wired up.
"""
import os

os.environ["TEST_MODE"] = "true"

import app as app_module  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from flask import session  # noqa: E402


def _get_engine_with_sid(sid=None):
    """Drive get_engine() inside a request context, optionally with a fixed sid."""
    with app_module.app.test_request_context("/"):
        if sid is not None:
            session["sid"] = sid
        engine = app_module.get_engine()
        resolved_sid = session["sid"]
    return engine, resolved_sid


class TestGetEngine:
    def setup_method(self):
        app_module._engines.clear()

    def test_same_session_reuses_same_engine(self):
        e1, sid = _get_engine_with_sid("A")
        e2, _ = _get_engine_with_sid(sid)
        assert e1 is e2  # follow-ups keep their conversation

    def test_distinct_sessions_get_distinct_engines(self):
        a, _ = _get_engine_with_sid("A")
        b, _ = _get_engine_with_sid("B")
        assert a is not b  # no cross-user context bleed
        assert set(app_module._engines) == {"A", "B"}

    def test_missing_sid_is_assigned(self):
        with app_module.app.test_request_context("/"):
            assert "sid" not in session
            app_module.get_engine()
            assert session.get("sid")  # a fresh id was minted

    def test_idle_session_starts_fresh(self):
        a1, _ = _get_engine_with_sid("A")
        # Age this session past the idle threshold.
        app_module._engines["A"]["last_seen"] = (
            datetime.now() - (app_module._SESSION_IDLE + timedelta(minutes=1))
        )
        a2, _ = _get_engine_with_sid("A")
        assert a1 is not a2  # stale context dropped, new engine created

    def test_recent_session_survives_below_threshold(self):
        a1, _ = _get_engine_with_sid("A")
        # Simulate a follow-up well within the window (e.g. 10 min later).
        app_module._engines["A"]["last_seen"] = datetime.now() - timedelta(minutes=10)
        a2, _ = _get_engine_with_sid("A")
        assert a1 is a2  # e.g. an 11:55pm -> 12:05am follow-up keeps context

    def test_stale_sessions_are_evicted(self):
        _get_engine_with_sid("old")
        app_module._engines["old"]["last_seen"] = (
            datetime.now() - (app_module._SESSION_IDLE + timedelta(minutes=1))
        )
        _get_engine_with_sid("new")  # any request triggers the sweep
        assert "old" not in app_module._engines  # memory stays bounded
        assert "new" in app_module._engines
