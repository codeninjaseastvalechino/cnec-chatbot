"""Tests for sites/mystudio/students.py — pure functions, no live HTTP."""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from sites.mystudio.students import (
    StudentRecord,
    find_student_by_name,
    get_student_attendance_this_week,
    get_student_sessions_by_type,
    get_student_upcoming_appointments,
    _parse_session_to_appointment,
)
from sites.mystudio.auth import MystudioOTPRequired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_post_session(status_code, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.post.return_value = resp
    return session


def _mock_get_session(status_code, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.get.return_value = resp
    return session


def _make_search_row(**overrides):
    row = {
        "customer_type": "participant",
        "student_id": "259103",
        "participant_id": "296114",
        "buyer_name": "Henry Kong",
        "buyer_fname": "Henry",
        "buyer_lname": "Kong",
        "student_mobile": "",
        "id": -296114,
    }
    row.update(overrides)
    return row


def _make_session_entry(**overrides):
    entry = {
        "class_reg_id": "2944124",
        "class_registration_detail_id": "11197811",
        "server_program_date": "2026-06-09",
        "start_time": "03:00 PM",
        "class_appointment_title": "CREATE (CODING)",
        "class_appointment_times_id": "27389",
        "class_appointment_id": "10797",
        "class_attendance_status": "Attended",
        "p_name": "Henry Kong",
        "student_id": "259103",
        "status": "Completed",
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# find_student_by_name
# ---------------------------------------------------------------------------

class TestFindStudentByName:
    def test_single_match_returns_one_record(self):
        mock_session = _mock_post_session(200, {"data": [_make_search_row()]})
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("henry")
        assert len(results) == 1
        assert results[0].name == "Henry Kong"
        assert results[0].student_id == "259103"
        assert results[0].participant_id == "296114"

    def test_multiple_matches_returns_all(self):
        rows = [
            _make_search_row(buyer_name="Henry Kong", participant_id="111"),
            _make_search_row(buyer_name="Henry Smith", participant_id="222"),
        ]
        mock_session = _mock_post_session(200, {"data": rows})
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("henry")
        assert len(results) == 2

    def test_no_match_returns_empty(self):
        mock_session = _mock_post_session(200, {"data": []})
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("nobody")
        assert results == []

    def test_non_participant_rows_filtered_out(self):
        rows = [
            _make_search_row(customer_type="student"),  # not "participant"
            _make_search_row(customer_type="participant"),
        ]
        mock_session = _mock_post_session(200, {"data": rows})
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("henry")
        assert len(results) == 1

    def test_401_raises_otp_required(self):
        mock_session = _mock_post_session(401)
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            with patch("sites.mystudio.students.clear_cached_cookies"):
                with pytest.raises(MystudioOTPRequired):
                    find_student_by_name("henry")

    def test_network_error_returns_empty(self):
        mock_session = MagicMock()
        mock_session.post.side_effect = Exception("connection error")
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("henry")
        assert results == []

    def test_belt_rank_and_parent_empty_before_enrich(self):
        mock_session = _mock_post_session(200, {"data": [_make_search_row()]})
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            results = find_student_by_name("henry")
        assert results[0].belt_rank == ""
        assert results[0].parent_name == ""


# ---------------------------------------------------------------------------
# get_student_attendance_this_week
# ---------------------------------------------------------------------------

class TestGetStudentAttendanceThisWeek:
    def _make_session_with_past_sessions(self, sessions):
        json_data = {"status": "Success", "msg": {"reg_details": sessions}}
        return _mock_get_session(200, json_data)

    def test_counts_attended_sessions(self):
        sessions = [
            _make_session_entry(class_attendance_status="Attended"),
            _make_session_entry(class_attendance_status="Attended"),
            _make_session_entry(class_attendance_status="Not Attended"),
        ]
        mock_session = self._make_session_with_past_sessions(sessions)
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            count = get_student_attendance_this_week("259103", "296114")
        assert count == 2

    def test_no_sessions_returns_zero(self):
        mock_session = self._make_session_with_past_sessions([])
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            count = get_student_attendance_this_week("259103", "296114")
        assert count == 0

    def test_case_insensitive_attended_status(self):
        sessions = [_make_session_entry(class_attendance_status="ATTENDED")]
        mock_session = self._make_session_with_past_sessions(sessions)
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            count = get_student_attendance_this_week("259103", "296114")
        assert count == 1

    def test_passes_monday_as_from_date(self):
        mock_session = self._make_session_with_past_sessions([])
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            with patch("sites.mystudio.students.date") as mock_date:
                mock_date.today.return_value = date(2026, 6, 4)  # Thursday
                mock_date.side_effect = lambda *a, **k: date(*a, **k)
                get_student_attendance_this_week("259103", "296114")
        call_params = mock_session.get.call_args[1]["params"]
        assert call_params["class_filter_date"] == "2026-06-01"  # Monday
        assert call_params["class_filter_days_value"] == "7"
        assert call_params["class_filter_type"] == "P"


# ---------------------------------------------------------------------------
# _parse_session_to_appointment
# ---------------------------------------------------------------------------

class TestParseSessionToAppointment:
    def test_basic_parse(self):
        appt = _parse_session_to_appointment(_make_session_entry())
        assert appt is not None
        assert appt.id == "2944124"
        assert appt.registration_detail_id == "11197811"
        assert appt.class_appointment_times_id == "27389"
        assert appt.class_appointment_id == "10797"
        assert appt.appointment_type == "CREATE (CODING)"
        assert appt.student_name == "Henry Kong"

    def test_start_time_parsed(self):
        appt = _parse_session_to_appointment(_make_session_entry())
        assert appt.start_time == datetime(2026, 6, 9, 15, 0, 0)

    def test_end_time_is_plus_one_hour(self):
        appt = _parse_session_to_appointment(_make_session_entry())
        assert appt.end_time.hour == appt.start_time.hour + 1

    def test_bad_date_returns_none(self):
        appt = _parse_session_to_appointment(_make_session_entry(server_program_date="not-a-date"))
        assert appt is None

    def test_m4_fields_populated(self):
        appt = _parse_session_to_appointment(_make_session_entry(
            class_reg_id="AAA",
            class_registration_detail_id="BBB",
            class_appointment_times_id="CCC",
            class_appointment_id="DDD",
        ))
        assert appt.id == "AAA"
        assert appt.registration_detail_id == "BBB"
        assert appt.class_appointment_times_id == "CCC"
        assert appt.class_appointment_id == "DDD"


# ---------------------------------------------------------------------------
# get_student_upcoming_appointments
# ---------------------------------------------------------------------------

class TestGetStudentUpcomingAppointments:
    def test_returns_sorted_by_start_time(self):
        sessions = [
            _make_session_entry(server_program_date="2026-06-16", start_time="03:00 PM", class_attendance_status="Not Attended"),
            _make_session_entry(server_program_date="2026-06-09", start_time="03:00 PM", class_attendance_status="Not Attended"),
        ]
        json_data = {"status": "Success", "msg": {"reg_details": sessions}}
        mock_session = _mock_get_session(200, json_data)
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            appts = get_student_upcoming_appointments("259103", "296114")
        assert len(appts) == 2
        assert appts[0].start_time < appts[1].start_time

    def test_skips_unparseable_entries(self):
        sessions = [
            _make_session_entry(server_program_date="bad-date"),
            _make_session_entry(server_program_date="2026-06-09"),
        ]
        json_data = {"status": "Success", "msg": {"reg_details": sessions}}
        mock_session = _mock_get_session(200, json_data)
        with patch("sites.mystudio.students.get_session", return_value=mock_session):
            appts = get_student_upcoming_appointments("259103", "296114")
        assert len(appts) == 1
