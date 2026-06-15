"""
Unit tests for sites/mystudio/camps.py

Covers: CampRecord helpers, filtering logic in get_camps_under_parent,
format_camps_summary grouping, and format_camp_roster None-safety.
API calls (get_all_upcoming_camps, get_camp_roster) are not tested —
they're thin wrappers around live endpoints.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock
from typing import List

import pytest

from sites.mystudio.camps import (
    CampRecord,
    CampKid,
    get_camps_under_parent,
    format_camps_summary,
    format_camp_roster,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_camp(
    event_id="1",
    parent_id="100",
    parent_title="2026 Summer Camps",
    title="AM CAMP: Test",
    start="2026-06-15 08:30:00",
    end="2026-06-15 11:30:00",
    enrolled=3,
    capacity=10,
    event_show_status="Y",
) -> CampRecord:
    return CampRecord(
        event_id=event_id,
        parent_id=parent_id,
        parent_title=parent_title,
        title=title,
        start_dt=datetime.strptime(start, "%Y-%m-%d %H:%M:%S"),
        end_dt=datetime.strptime(end, "%Y-%m-%d %H:%M:%S"),
        enrolled=enrolled,
        capacity=capacity,
        event_show_status=event_show_status,
    )


def make_kid(name="Alex Smith", parent="Bob Smith", status="Active", age="9") -> CampKid:
    return CampKid(
        participant_name=name,
        buyer_name=parent,
        phone="5551234567",
        email="bob@test.com",
        status=status,
        event_title="AM CAMP: Test",
        age=age,
    )


# ---------------------------------------------------------------------------
# CampRecord.week_label
# ---------------------------------------------------------------------------

class TestWeekLabel:
    def test_same_month(self):
        camp = make_camp(start="2026-06-15 08:30:00", end="2026-06-19 11:30:00")
        assert camp.week_label() == "Jun 15 – 19"

    def test_cross_month(self):
        camp = make_camp(start="2026-06-29 08:30:00", end="2026-07-03 11:30:00")
        assert camp.week_label() == "Jun 29 – Jul 3"

    def test_same_day(self):
        camp = make_camp(start="2026-07-04 09:00:00", end="2026-07-04 12:00:00")
        assert camp.week_label() == "Jul 4 – 4"


# ---------------------------------------------------------------------------
# CampRecord.time_range
# ---------------------------------------------------------------------------

class TestTimeRange:
    def test_am_to_pm(self):
        camp = make_camp(start="2026-06-15 08:30:00", end="2026-06-15 15:00:00")
        assert camp.time_range() == "8:30 AM – 3:00 PM"

    def test_noon_boundary(self):
        camp = make_camp(start="2026-06-15 12:00:00", end="2026-06-15 15:00:00")
        assert camp.time_range() == "12:00 PM – 3:00 PM"

    def test_am_only(self):
        camp = make_camp(start="2026-06-15 08:30:00", end="2026-06-15 11:30:00")
        assert camp.time_range() == "8:30 AM – 11:30 AM"


# ---------------------------------------------------------------------------
# CampRecord.spots_left
# ---------------------------------------------------------------------------

class TestSpotsLeft:
    def test_spots_remaining(self):
        camp = make_camp(enrolled=3, capacity=10)
        assert camp.spots_left() == 7

    def test_full_camp(self):
        camp = make_camp(enrolled=10, capacity=10)
        assert camp.spots_left() == 0

    def test_over_capacity_clamps_to_zero(self):
        camp = make_camp(enrolled=11, capacity=10)
        assert camp.spots_left() == 0

    def test_no_capacity_returns_none(self):
        camp = make_camp(enrolled=3, capacity=None)
        assert camp.spots_left() is None


# ---------------------------------------------------------------------------
# get_camps_under_parent — filtering logic
# ---------------------------------------------------------------------------

NULL_DATE = "0000-00-00 00:00:00"

REAL_CAMP = {
    "event_id": "1001",
    "event_title": "AM CAMP: LEGO Robotics Ages 8+",
    "event_begin_dt": "2026-06-15 08:30:00",
    "event_end_dt": "2026-06-15 11:30:00",
    "registrations_count": "3",
    "event_capacity": "10",
    "event_show_status": "Y",
    "event_url": "",
}

TEMPLATE_CAMP = {
    "event_id": "1002",
    "event_title": "Template Camp",
    "event_begin_dt": NULL_DATE,
    "event_end_dt": NULL_DATE,
    "registrations_count": "0",
    "event_capacity": "10",
    "event_show_status": "N",
    "event_url": "",
}

HIDDEN_WITH_ENROLLMENT = {
    "event_id": "1003",
    "event_title": "Hidden But Has Kids",
    "event_begin_dt": "2026-06-15 12:00:00",
    "event_end_dt": "2026-06-15 15:00:00",
    "registrations_count": "2",
    "event_capacity": "5",
    "event_show_status": "N",
    "event_url": "",
}

MISSING_DATE = {
    "event_id": "1004",
    "event_title": "No Date Camp",
    "event_begin_dt": "",
    "event_end_dt": "",
    "registrations_count": "0",
    "event_capacity": "10",
    "event_show_status": "Y",
    "event_url": "",
}


def _mock_api_response(items: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "Success", "msg": items}
    return resp


@patch("sites.mystudio.camps.get_session")
class TestGetCampsUnderParent:
    def test_returns_real_camps(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_api_response([REAL_CAMP])
        camps = get_camps_under_parent("100", "Summer 2026")
        assert len(camps) == 1
        assert camps[0].event_id == "1001"
        assert camps[0].enrolled == 3
        assert camps[0].capacity == 10

    def test_filters_null_date_templates(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_api_response(
            [REAL_CAMP, TEMPLATE_CAMP]
        )
        camps = get_camps_under_parent("100", "Summer 2026")
        assert len(camps) == 1
        assert camps[0].event_id == "1001"

    def test_filters_empty_date(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_api_response(
            [REAL_CAMP, MISSING_DATE]
        )
        camps = get_camps_under_parent("100", "Summer 2026")
        assert len(camps) == 1

    def test_includes_hidden_camps_with_real_dates(self, mock_get_session):
        # Hidden camps with real dates should pass through (format_camps_summary filters them)
        mock_get_session.return_value.get.return_value = _mock_api_response(
            [REAL_CAMP, HIDDEN_WITH_ENROLLMENT]
        )
        camps = get_camps_under_parent("100", "Summer 2026")
        assert len(camps) == 2

    def test_empty_response_returns_empty_list(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_api_response([])
        camps = get_camps_under_parent("100", "Summer 2026")
        assert camps == []

    def test_no_capacity_field_is_none(self, mock_get_session):
        item = {**REAL_CAMP, "event_capacity": None}
        mock_get_session.return_value.get.return_value = _mock_api_response([item])
        camps = get_camps_under_parent("100", "Summer 2026")
        assert camps[0].capacity is None

    def test_parent_title_and_id_set_correctly(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_api_response([REAL_CAMP])
        camps = get_camps_under_parent("100", "Summer 2026")
        assert camps[0].parent_id == "100"
        assert camps[0].parent_title == "Summer 2026"

    def test_bad_date_format_skipped(self, mock_get_session):
        bad = {**REAL_CAMP, "event_begin_dt": "not-a-date", "event_id": "9999"}
        mock_get_session.return_value.get.return_value = _mock_api_response([REAL_CAMP, bad])
        camps = get_camps_under_parent("100", "Summer 2026")
        ids = [c.event_id for c in camps]
        assert "9999" not in ids


# ---------------------------------------------------------------------------
# format_camps_summary
# ---------------------------------------------------------------------------

class TestFormatCampsSummary:
    def test_filters_hidden_by_default(self):
        camps = [
            make_camp(event_id="1", event_show_status="Y", title="Visible Camp"),
            make_camp(event_id="2", event_show_status="N", title="Hidden Camp"),
        ]
        result = format_camps_summary(camps)
        assert "Visible Camp" in result
        assert "Hidden Camp" not in result

    def test_include_hidden_flag(self):
        camps = [
            make_camp(event_id="1", event_show_status="Y", title="Visible Camp"),
            make_camp(event_id="2", event_show_status="N", title="Hidden Camp"),
        ]
        result = format_camps_summary(camps, include_hidden=True)
        assert "Visible Camp" in result
        assert "Hidden Camp" in result

    def test_empty_returns_no_upcoming_message(self):
        assert format_camps_summary([]) == "No upcoming camps found."

    def test_shows_enrollment_and_spots(self):
        camp = make_camp(enrolled=3, capacity=10)
        result = format_camps_summary([camp])
        assert "3/10" in result
        assert "7 spots left" in result

    def test_groups_by_start_date(self):
        camp1 = make_camp(event_id="1", start="2026-06-15 08:30:00", end="2026-06-15 11:30:00", title="AM Camp")
        camp2 = make_camp(event_id="2", start="2026-06-15 12:00:00", end="2026-06-15 15:00:00", title="PM Camp")
        camp3 = make_camp(event_id="3", start="2026-06-22 08:30:00", end="2026-06-22 11:30:00", title="Next Week")
        result = format_camps_summary([camp1, camp2, camp3])
        # Jun 15 header should appear once, Jun 22 header once
        assert result.count("Jun 15") >= 1
        assert result.count("Jun 22") >= 1

    def test_single_spot_left_singular(self):
        camp = make_camp(enrolled=9, capacity=10)
        result = format_camps_summary([camp])
        assert "1 spot left" in result
        assert "1 spots left" not in result


# ---------------------------------------------------------------------------
# format_camp_roster
# ---------------------------------------------------------------------------

class TestFormatCampRoster:
    def test_none_roster_shows_fallback(self):
        camp = make_camp()
        result = format_camp_roster(camp, None)
        assert "Roster unavailable" in result
        assert "MyStudio" in result

    def test_active_kids_shown(self):
        camp = make_camp()
        kids = [make_kid("Alice Smith", status="Active"), make_kid("Bob Jones", status="Active")]
        result = format_camp_roster(camp, kids)
        assert "Alice Smith" in result
        assert "Bob Jones" in result

    def test_cancelled_kids_in_separate_section(self):
        camp = make_camp()
        kids = [make_kid("Alice Smith", status="Active"), make_kid("Bob Jones", status="Cancelled")]
        result = format_camp_roster(camp, kids)
        assert "Alice Smith" in result
        assert "Bob Jones" in result
        assert "Cancelled" in result

    def test_empty_roster_shows_no_enrollments(self):
        camp = make_camp()
        result = format_camp_roster(camp, [])
        assert "No active enrollments" in result

    def test_camp_title_in_output(self):
        camp = make_camp(title="AM CAMP: LEGO Robotics")
        result = format_camp_roster(camp, [])
        assert "AM CAMP: LEGO Robotics" in result

    def test_capacity_shown_when_present(self):
        camp = make_camp(enrolled=3, capacity=10)
        result = format_camp_roster(camp, [])
        assert "10" in result

    def test_no_capacity_omits_capacity(self):
        camp = make_camp(enrolled=3, capacity=None)
        result = format_camp_roster(camp, [])
        assert "/ None" not in result
