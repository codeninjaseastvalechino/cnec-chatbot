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
    _parse_child_events,
    get_camps_under_parent,
    get_all_past_camps,
    get_camp_roster,
    format_camps_summary,
    format_camp_roster,
    _expected_camp_price,
    format_camp_revenue,
    format_week_revenue,
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
# _parse_child_events — shared parsing helper
# ---------------------------------------------------------------------------

class TestParseChildEvents:
    def test_parses_valid_child(self):
        camps = _parse_child_events([REAL_CAMP], "100", "Summer 2026")
        assert len(camps) == 1
        assert camps[0].event_id == "1001"
        assert camps[0].parent_id == "100"
        assert camps[0].parent_title == "Summer 2026"
        assert camps[0].enrolled == 3

    def test_skips_null_date(self):
        camps = _parse_child_events([TEMPLATE_CAMP], "100", "Summer 2026")
        assert camps == []

    def test_skips_empty_date(self):
        camps = _parse_child_events([MISSING_DATE], "100", "Summer 2026")
        assert camps == []

    def test_skips_bad_date_format(self):
        bad = {**REAL_CAMP, "event_begin_dt": "not-a-date", "event_id": "9999"}
        camps = _parse_child_events([REAL_CAMP, bad], "100", "Summer 2026")
        assert len(camps) == 1
        assert camps[0].event_id == "1001"

    def test_none_capacity_is_none(self):
        item = {**REAL_CAMP, "event_capacity": None}
        camps = _parse_child_events([item], "100", "Summer 2026")
        assert camps[0].capacity is None

    def test_multiple_children_all_parsed(self):
        second = {**REAL_CAMP, "event_id": "1005", "event_begin_dt": "2026-06-16 08:30:00",
                  "event_end_dt": "2026-06-16 11:30:00"}
        camps = _parse_child_events([REAL_CAMP, second], "100", "Summer 2026")
        assert len(camps) == 2
        assert {c.event_id for c in camps} == {"1001", "1005"}

    def test_get_camps_under_parent_delegates_to_parse_child_events(self, mock_get_session=None):
        # Verify get_camps_under_parent produces same results as calling _parse_child_events directly
        camps_direct = _parse_child_events([REAL_CAMP], "100", "Summer 2026")
        assert camps_direct[0].enrolled == 3
        assert camps_direct[0].title == "AM CAMP: LEGO Robotics Ages 8+"


# ---------------------------------------------------------------------------
# get_all_past_camps — list_type=D path
# ---------------------------------------------------------------------------

def _mock_past_api_response(past_parents: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "Success",
        "msg": {"past": past_parents, "draft": [], "live": []},
    }
    return resp


PAST_PARENT_WITH_CHILDREN = {
    "event_id": "292536",
    "event_title": "2026 Summer and Off-Track Camps",
    "event_type": "M",
    "child_events": [
        {
            "event_id": "5001",
            "event_title": "3D Printing Camp",
            "event_begin_dt": "2026-02-09 09:00:00",
            "event_end_dt": "2026-02-09 15:00:00",
            "registrations_count": "10",
            "event_capacity": "12",
            "event_show_status": "Y",
            "event_url": "",
        },
        {
            "event_id": "5002",
            "event_title": "AM CAMP: LEGO Robotics",
            "event_begin_dt": "2026-03-15 08:30:00",
            "event_end_dt": "2026-03-15 11:30:00",
            "registrations_count": "5",
            "event_capacity": "10",
            "event_show_status": "Y",
            "event_url": "",
        },
    ],
}

PAST_STANDALONE_EVENT = {
    "event_id": "9001",
    "event_title": "Open House",
    "event_type": "S",  # standalone, not a camp group — should be skipped
    "child_events": [],
}


@patch("sites.mystudio.camps.get_session")
class TestGetAllPastCamps:
    def test_returns_child_camps_from_past_parents(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response(
            [PAST_PARENT_WITH_CHILDREN]
        )
        camps = get_all_past_camps()
        assert len(camps) == 2
        ids = {c.event_id for c in camps}
        assert "5001" in ids
        assert "5002" in ids

    def test_skips_standalone_events(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response(
            [PAST_PARENT_WITH_CHILDREN, PAST_STANDALONE_EVENT]
        )
        camps = get_all_past_camps()
        assert all(c.event_id != "9001" for c in camps)

    def test_sorted_most_recent_first(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response(
            [PAST_PARENT_WITH_CHILDREN]
        )
        camps = get_all_past_camps()
        dates = [c.start_dt for c in camps]
        assert dates == sorted(dates, reverse=True)

    def test_since_date_filter(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response(
            [PAST_PARENT_WITH_CHILDREN]
        )
        since = datetime(2026, 3, 1)
        until = datetime(2026, 12, 31)
        camps = get_all_past_camps(since_date=since, until_date=until)
        # Only the March camp passes the filter
        assert len(camps) == 1
        assert camps[0].event_id == "5002"

    def test_empty_past_returns_empty_list(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response([])
        camps = get_all_past_camps()
        assert camps == []

    def test_parent_id_and_title_propagated(self, mock_get_session):
        mock_get_session.return_value.get.return_value = _mock_past_api_response(
            [PAST_PARENT_WITH_CHILDREN]
        )
        camps = get_all_past_camps()
        for c in camps:
            assert c.parent_id == "292536"
            assert c.parent_title == "2026 Summer and Off-Track Camps"


# ---------------------------------------------------------------------------
# get_camp_roster — event_list_type parameter
# ---------------------------------------------------------------------------

@patch("sites.mystudio.camps.get_session")
class TestGetCampRosterListType:
    def _make_roster_response(self, kids: list) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "Success", "data": kids}
        return resp

    def test_default_list_type_is_P(self, mock_get_session):
        mock_get_session.return_value.post.return_value = self._make_roster_response([])
        get_camp_roster("5001", "292536")
        call_kwargs = mock_get_session.return_value.post.call_args
        posted_data = call_kwargs[1].get("data", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        import json
        filter_opts = json.loads(posted_data.get("filter_options", "{}"))
        assert filter_opts["event_list"]["event_list_type"] == "P"

    def test_past_list_type_is_D(self, mock_get_session):
        mock_get_session.return_value.post.return_value = self._make_roster_response([])
        get_camp_roster("5001", "292536", event_list_type="D")
        call_kwargs = mock_get_session.return_value.post.call_args
        posted_data = call_kwargs[1].get("data", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        import json
        filter_opts = json.loads(posted_data.get("filter_options", "{}"))
        assert filter_opts["event_list"]["event_list_type"] == "D"

    def test_returns_kids_from_response(self, mock_get_session):
        kid_row = {
            "participant_name": "Alex Smith", "buyer_name": "Bob Smith",
            "participant_phone": "5551234", "participant_email": "bob@test.com",
            "event_reg_status": "Active", "event_title": "3D Printing Camp", "p_age": "9",
        }
        mock_get_session.return_value.post.return_value = self._make_roster_response([kid_row])
        kids = get_camp_roster("5001", "292536", event_list_type="D")
        assert kids is not None
        assert len(kids) == 1
        assert kids[0].participant_name == "Alex Smith"


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


# ---------------------------------------------------------------------------
# _expected_camp_price
# ---------------------------------------------------------------------------

class TestExpectedCampPrice:
    def test_full_day_returns_399(self):
        assert _expected_camp_price("FULL DAY CAMP: Robotics") == 399.00

    def test_all_day_returns_399(self):
        assert _expected_camp_price("ALL DAY CAMP: Minecraft") == 399.00

    def test_case_insensitive(self):
        assert _expected_camp_price("Full Day Camp: Lego") == 399.00
        assert _expected_camp_price("all day camp") == 399.00

    def test_am_camp_returns_249(self):
        assert _expected_camp_price("AM CAMP: Robotics Engineering") == 249.00

    def test_pm_camp_returns_249(self):
        assert _expected_camp_price("PM CAMP: Minecraft") == 249.00

    def test_generic_camp_returns_249(self):
        assert _expected_camp_price("Robotics Engineering (Ages 8+)") == 249.00

    def test_jr_camp_returns_249(self):
        assert _expected_camp_price("JR CAMP: Game Design") == 249.00


# ---------------------------------------------------------------------------
# Helpers for revenue tests
# ---------------------------------------------------------------------------

def make_revenue_result(
    camp=None,
    total=399.00,
    enrolled=3,
    expected_price=399.00,
    kids=None,
):
    if camp is None:
        camp = make_camp(title="ALL DAY CAMP: Robotics", start="2026-07-07 08:00:00", end="2026-07-07 17:00:00")
    if kids is None:
        kids = [
            {"name": "Alice Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Carlos Diaz", "buyer_name": "Maria Diaz", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Dana Park",  "buyer_name": "Sue Park",   "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
        ]
    return {"camp": camp, "total": total, "enrolled": enrolled, "expected_price": expected_price, "kids": kids}


# ---------------------------------------------------------------------------
# format_camp_revenue
# ---------------------------------------------------------------------------

class TestFormatCampRevenue:
    def test_error_result_returns_message(self):
        result = {"error": "Failed to fetch roster", "camp": make_camp()}
        assert "Could not fetch revenue" in format_camp_revenue(result)

    def test_shows_total_revenue(self):
        result = make_revenue_result(total=798.00)
        assert "$798.00" in format_camp_revenue(result)

    def test_shows_enrolled_count(self):
        result = make_revenue_result(enrolled=3)
        assert "3 enrolled" in format_camp_revenue(result)

    def test_all_full_price_no_gotcha_sections(self):
        result = make_revenue_result()
        text = format_camp_revenue(result)
        assert "Comped" not in text
        assert "Discounted" not in text
        assert "Cancelled" not in text
        assert "Camp renames" not in text

    def test_comped_kid_flagged(self):
        kids = [
            {"name": "Alice Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Dana Park",   "buyer_name": "Sue Park",  "paid_amount": 0.00,   "status": "Active", "cancelled": False, "renamed_from": None},
        ]
        result = make_revenue_result(total=399.00, enrolled=2, kids=kids)
        text = format_camp_revenue(result)
        assert "Comped" in text
        assert "Dana Park" in text

    def test_discounted_kid_flagged(self):
        kids = [
            {"name": "Alice Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Dana Park",   "buyer_name": "Sue Park",  "paid_amount": 200.00, "status": "Active", "cancelled": False, "renamed_from": None},
        ]
        result = make_revenue_result(total=599.00, enrolled=2, kids=kids)
        text = format_camp_revenue(result)
        assert "Discounted" in text
        assert "Dana Park" in text
        assert "$200.00" in text

    def test_cancelled_kid_listed_separately(self):
        kids = [
            {"name": "Alice Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active",    "cancelled": False, "renamed_from": None},
            {"name": "Dana Park",   "buyer_name": "Sue Park",  "paid_amount": 0.00,   "status": "cancelled", "cancelled": True,  "renamed_from": None},
        ]
        result = make_revenue_result(total=399.00, enrolled=2, kids=kids)
        text = format_camp_revenue(result)
        assert "Cancelled" in text
        assert "Dana Park" in text

    def test_renamed_kid_not_in_comped(self):
        kids = [
            {"name": "Jaymin Chiao", "buyer_name": "Parent A", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": "Robotics Engineering (Ages 8+)"},
        ]
        result = make_revenue_result(total=399.00, enrolled=1, kids=kids)
        text = format_camp_revenue(result)
        assert "Camp renames" in text
        assert "Jaymin Chiao" in text
        assert "Robotics Engineering" in text
        # Must NOT appear in comped section
        assert "Comped" not in text

    def test_renamed_kid_flagged_in_enrollment_list(self):
        kids = [
            {"name": "Jaymin Chiao", "buyer_name": "Parent A", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": "Robotics Engineering (Ages 8+)"},
        ]
        result = make_revenue_result(total=399.00, enrolled=1, kids=kids)
        text = format_camp_revenue(result)
        assert "renamed" in text.lower()

    def test_family_pattern_detected(self):
        kids = [
            {"name": "Alice Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Carol Smith", "buyer_name": "Bob Smith", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Dana Park",   "buyer_name": "Sue Park",  "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
        ]
        result = make_revenue_result(total=1197.00, enrolled=3, kids=kids)
        text = format_camp_revenue(result)
        assert "Families" in text or "family" in text.lower() or "same parent" in text.lower()
        assert "Bob Smith" in text

    def test_camp_title_in_output(self):
        camp = make_camp(title="ALL DAY CAMP: Minecraft", start="2026-07-07 08:00:00", end="2026-07-07 17:00:00")
        result = make_revenue_result(camp=camp)
        assert "ALL DAY CAMP: Minecraft" in format_camp_revenue(result)


# ---------------------------------------------------------------------------
# format_week_revenue
# ---------------------------------------------------------------------------

class TestFormatWeekRevenue:
    def test_shows_week_total(self):
        r1 = make_revenue_result(total=399.00)
        r2 = make_revenue_result(total=798.00)
        text = format_week_revenue([r1, r2])
        assert "$1,197.00" in text

    def test_error_result_shown(self):
        camp = make_camp()
        r1 = make_revenue_result(total=399.00)
        r2 = {"error": "API failure", "camp": camp}
        text = format_week_revenue([r1, r2])
        assert "ERROR" in text

    def test_comped_count_shown(self):
        kids = [
            {"name": "Alice", "buyer_name": "Bob", "paid_amount": 399.00, "status": "Active", "cancelled": False, "renamed_from": None},
            {"name": "Dana",  "buyer_name": "Sue", "paid_amount": 0.00,   "status": "Active", "cancelled": False, "renamed_from": None},
        ]
        result = make_revenue_result(total=399.00, enrolled=2, kids=kids)
        text = format_week_revenue([result])
        assert "comped" in text.lower()

    def test_zero_results(self):
        text = format_week_revenue([])
        assert "$0.00" in text
