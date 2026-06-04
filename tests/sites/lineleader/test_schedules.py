"""Tests for sites/lineleader/schedules.py — pure functions only, no HTTP."""
import pytest
from datetime import date, datetime, timezone

from unittest.mock import patch
from sites.lineleader.schedules import (
    _calculate_age,
    _is_junior,
    _build_put_payload,
    _parse_tasks,
    _parse_single_item,
    get_upcoming_gbs_tours,
)


# ---------------------------------------------------------------------------
# _calculate_age
# ---------------------------------------------------------------------------

class TestCalculateAge:
    def test_basic_age(self):
        from unittest.mock import patch
        with patch("sites.lineleader.schedules.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 4)
            mock_date.fromisoformat = date.fromisoformat
            assert _calculate_age("2020-06-04") == 6   # birthday today
            assert _calculate_age("2020-06-05") == 5   # birthday tomorrow (not yet)
            assert _calculate_age("2020-06-03") == 6   # birthday yesterday

    def test_invalid_dob_returns_none(self):
        assert _calculate_age("not-a-date") is None
        assert _calculate_age("") is None
        assert _calculate_age(None) is None


# ---------------------------------------------------------------------------
# _is_junior
# ---------------------------------------------------------------------------

class TestIsJunior:
    def test_jr_in_description(self):
        assert _is_junior("JR GBS") is True
        assert _is_junior("jr gbs") is True

    def test_junior_in_description(self):
        assert _is_junior("JUNIOR") is True
        assert _is_junior("Junior GBS") is True

    def test_jrs_in_description(self):
        assert _is_junior("JRS") is True

    def test_gbs_only_not_junior(self):
        assert _is_junior("GBS") is False
        assert _is_junior("") is False

    def test_partial_word_does_not_match(self):
        # "jr" is a substring check — this is intentional per the implementation
        assert _is_junior("major") is False  # "jr" not present as standalone


# ---------------------------------------------------------------------------
# _build_put_payload
# ---------------------------------------------------------------------------

class TestBuildPutPayload:
    def _make_task(self, **overrides):
        task = {
            "id": 2003102,
            "family": {"id": 929179, "values": {"name": "Venay Bhatia"}},
            "type": {"id": 89, "values": {"value": "Tour"}},
            "assigned_to_staff": {"id": 58347, "values": {"first_name": "Venay"}},
            "assigned_by_user_id": 58347,
            "description": "",
            "is_completed": False,
            "completed_by_user_id": None,
            "completed_date_time": None,
            "result_type": None,
            "result_description": "",
            "is_canceled": False,
            "duration": 30,
        }
        task.update(overrides)
        return task

    def test_expanded_objects_flattened_to_ids(self):
        payload = _build_put_payload(self._make_task(), "2026-06-09T17:00:00Z")
        assert payload["family"] == 929179
        assert payload["type"] == 89
        assert payload["assigned_to_staff"] == 58347

    def test_due_date_time_set(self):
        payload = _build_put_payload(self._make_task(), "2026-06-09T17:00:00Z")
        assert payload["due_date_time"] == "2026-06-09T17:00:00Z"

    def test_plain_id_fields_pass_through(self):
        payload = _build_put_payload(self._make_task(), "2026-06-09T17:00:00Z")
        assert payload["assigned_by_user_id"] == 58347
        assert payload["id"] == 2003102

    def test_none_values_preserved(self):
        payload = _build_put_payload(self._make_task(), "2026-06-09T17:00:00Z")
        assert payload["completed_by_user_id"] is None
        assert payload["completed_date_time"] is None
        assert payload["result_type"] is None

    def test_description_defaults_to_empty_string(self):
        task = self._make_task(description=None)
        payload = _build_put_payload(task, "2026-06-09T17:00:00Z")
        assert payload["description"] == ""

    def test_result_description_defaults_to_empty_string(self):
        task = self._make_task(result_description=None)
        payload = _build_put_payload(task, "2026-06-09T17:00:00Z")
        assert payload["result_description"] == ""

    def test_only_expected_keys_present(self):
        payload = _build_put_payload(self._make_task(), "2026-06-09T17:00:00Z")
        expected_keys = {
            "id", "family", "type", "assigned_to_staff", "assigned_by_user_id",
            "due_date_time", "description", "is_completed", "completed_by_user_id",
            "completed_date_time", "result_type", "result_description",
            "is_canceled", "duration",
        }
        assert set(payload.keys()) == expected_keys


# ---------------------------------------------------------------------------
# _parse_tasks
# ---------------------------------------------------------------------------

class TestParseTasks:
    def _make_task(self, due_date_time, type_id=89, **overrides):
        task = {
            "id": "1234",
            "due_date_time": due_date_time,
            "type": {"id": type_id, "values": {"value": "Tour"}},
            "family": {"id": 929179, "values": {"name": "Test Family"}},
            "assigned_to_staff": {"id": 58347, "values": {"first_name": "Venay", "last_name": "Bhatia"}},
            "result_description": "",
            "description": "",
            "center": {"values": {"name": "Eastvale-Chino, CA"}},
        }
        task.update(overrides)
        return task

    def test_parses_tour_on_target_date(self):
        # 2026-06-05 10:00 AM PDT = 2026-06-05T17:00:00Z
        tasks = [self._make_task("2026-06-05T17:00:00+00:00")]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert len(sessions) == 1
        assert sessions[0].student_name == "Test Family"

    def test_filters_out_wrong_date(self):
        tasks = [self._make_task("2026-06-06T17:00:00+00:00")]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert len(sessions) == 0

    def test_filters_out_non_tour_type(self):
        tasks = [self._make_task("2026-06-05T17:00:00+00:00", type_id=99)]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert len(sessions) == 0

    def test_jr_gbs_detection(self):
        tasks = [self._make_task("2026-06-05T17:00:00+00:00", result_description="JR GBS")]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert sessions[0].tour_type == "JR GBS"

    def test_gbs_default(self):
        tasks = [self._make_task("2026-06-05T17:00:00+00:00")]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert sessions[0].tour_type == "GBS"

    def test_assignee_name_parsed(self):
        tasks = [self._make_task("2026-06-05T17:00:00+00:00")]
        sessions = _parse_tasks(tasks, date(2026, 6, 5))
        assert sessions[0].assignee_name == "Venay Bhatia"

    def test_missing_due_date_skipped(self):
        task = self._make_task("2026-06-05T17:00:00+00:00")
        task["due_date_time"] = ""
        sessions = _parse_tasks([task], date(2026, 6, 5))
        assert len(sessions) == 0

    def test_empty_list_returns_empty(self):
        assert _parse_tasks([], date(2026, 6, 5)) == []


# ---------------------------------------------------------------------------
# _parse_single_item
# ---------------------------------------------------------------------------

class TestParseSingleItem:
    def _make_item(self, **overrides):
        item = {
            "item_id": "1995970",
            "date_time": "2026-06-05T22:00:00+00:00",  # 3pm PDT
            "display_type": "Tour",
            "description": "",
            "guardian_first_name": "Kira",
            "guardian_last_name": "Holland",
            "assignee_first_name": "Venay",
            "assignee_last_name": "Bhatia",
            "location_name": "Eastvale-Chino, CA",
        }
        item.update(overrides)
        return item

    def test_parses_tour(self):
        session = _parse_single_item(self._make_item(), date(2026, 6, 5))
        assert session is not None
        assert session.student_name == "Kira Holland"
        assert session.assignee_name == "Venay Bhatia"
        assert session.display_type == "Tour"

    def test_filters_non_tour(self):
        item = self._make_item(display_type="Meeting")
        assert _parse_single_item(item, date(2026, 6, 5)) is None

    def test_filters_wrong_date(self):
        assert _parse_single_item(self._make_item(), date(2026, 6, 6)) is None

    def test_missing_date_time_returns_none(self):
        assert _parse_single_item(self._make_item(date_time=""), date(2026, 6, 5)) is None

    def test_jr_gbs_from_description(self):
        session = _parse_single_item(self._make_item(description="JR GBS"), date(2026, 6, 5))
        assert session.tour_type == "JR GBS"

    def test_gbs_default(self):
        session = _parse_single_item(self._make_item(), date(2026, 6, 5))
        assert session.tour_type == "GBS"


# ---------------------------------------------------------------------------
# get_upcoming_gbs_tours — filtering logic (no HTTP)
# ---------------------------------------------------------------------------

class TestGetUpcomingGbsTours:
    def _make_action_item(self, date_time, display_type="Tour", item_id="1", description=""):
        return {
            "item_id": item_id,
            "date_time": date_time,
            "display_type": display_type,
            "description": description,
            "guardian_first_name": "Test",
            "guardian_last_name": "Family",
            "assignee_first_name": "Venay",
            "assignee_last_name": "Bhatia",
            "location_name": "Eastvale-Chino, CA",
        }

    def _run(self, today_items, future_items, after_date="", limit=5):
        with patch("sites.lineleader.schedules._fetch_action_items") as mock_fetch:
            mock_fetch.side_effect = lambda token, date_filter, limit: (
                today_items if date_filter == "today" else future_items
            )
            return get_upcoming_gbs_tours("fake-token", after_date=after_date, limit=limit)

    def test_returns_tours_sorted_by_time(self):
        items = [
            self._make_action_item("2026-06-12T22:00:00+00:00", item_id="2"),  # 3pm PDT
            self._make_action_item("2026-06-12T20:00:00+00:00", item_id="1"),  # 1pm PDT
        ]
        sessions = self._run([], items)
        assert sessions[0].item_id == "1"
        assert sessions[1].item_id == "2"

    def test_filters_out_non_tours(self):
        items = [
            self._make_action_item("2026-06-12T20:00:00+00:00", display_type="Meeting"),
            self._make_action_item("2026-06-12T21:00:00+00:00", display_type="Tour"),
        ]
        sessions = self._run([], items)
        assert len(sessions) == 1

    def test_after_date_filter(self):
        items = [
            self._make_action_item("2026-06-10T20:00:00+00:00", item_id="1"),  # before cutoff
            self._make_action_item("2026-06-12T20:00:00+00:00", item_id="2"),  # after cutoff
        ]
        sessions = self._run([], items, after_date="2026-06-11")
        assert len(sessions) == 1
        assert sessions[0].item_id == "2"

    def test_deduplicates_across_today_and_future(self):
        item = self._make_action_item("2026-06-12T20:00:00+00:00", item_id="99")
        sessions = self._run([item], [item])  # same item in both buckets
        assert len(sessions) == 1

    def test_respects_limit(self):
        items = [
            self._make_action_item(f"2026-06-{12+i}T20:00:00+00:00", item_id=str(i))
            for i in range(10)
        ]
        sessions = self._run([], items, limit=3)
        assert len(sessions) == 3

    def test_empty_returns_empty(self):
        assert self._run([], []) == []

    def test_jr_gbs_detected(self):
        items = [self._make_action_item("2026-06-12T20:00:00+00:00", description="JR GBS")]
        sessions = self._run([], items)
        assert sessions[0].tour_type == "JR GBS"

    def test_boundary_date_excluded_when_cutoff_is_day_after(self):
        # Simulates "after June 16th" → cutoff becomes June 17
        items = [
            self._make_action_item("2026-06-16T20:00:00+00:00", item_id="1"),  # June 16 — excluded
            self._make_action_item("2026-06-17T20:00:00+00:00", item_id="2"),  # June 17 — included
        ]
        sessions = self._run([], items, after_date="2026-06-17")
        assert len(sessions) == 1
        assert sessions[0].item_id == "2"
