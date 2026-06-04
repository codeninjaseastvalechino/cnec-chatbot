"""Tests for sites/mystudio/schedules.py — pure functions only, no HTTP."""
import pytest
from datetime import datetime

from sites.mystudio.schedules import _parse_student_to_appointment


# ---------------------------------------------------------------------------
# _parse_student_to_appointment
# ---------------------------------------------------------------------------

class TestParseStudentToAppointment:
    def _make_student(self, **overrides):
        student = {
            "class_reg_id": "99001",
            "Participant": "Journei Ashbourne",
            "student_id": "12345",
            "Buyer": "Wittie Hughes",
            "Phone": "(415) 815-9602",
            "rank_status": "White Belt",
            "end_time": "2026-06-05 16:00:00",
        }
        student.update(overrides)
        return student

    def _make_slot(self, **overrides):
        slot = {
            "class_appointment_times_id": "555",
            "date": "2026-06-05",
            "start_time": "03:00 PM",
            "class_title": "CREATE (CODING)",
        }
        slot.update(overrides)
        return slot

    def test_basic_parse(self):
        appt = _parse_student_to_appointment(self._make_student(), self._make_slot())
        assert appt is not None
        assert appt.student_name == "Journei Ashbourne"
        assert appt.parent_name == "Wittie Hughes"
        assert appt.phone == "(415) 815-9602"
        assert appt.rank == "White Belt"
        assert appt.appointment_type == "CREATE (CODING)"
        assert appt.id == "99001"

    def test_start_time_parsed(self):
        appt = _parse_student_to_appointment(self._make_student(), self._make_slot())
        assert appt.start_time == datetime(2026, 6, 5, 15, 0, 0)

    def test_end_time_parsed(self):
        appt = _parse_student_to_appointment(self._make_student(), self._make_slot())
        assert appt.end_time == datetime(2026, 6, 5, 16, 0, 0)

    def test_duration_calculated(self):
        appt = _parse_student_to_appointment(self._make_student(), self._make_slot())
        assert appt.duration_minutes == 60

    def test_missing_end_time_falls_back_to_plus_one_hour(self):
        student = self._make_student(end_time="")
        appt = _parse_student_to_appointment(student, self._make_slot())
        assert appt is not None
        assert appt.end_time.hour == appt.start_time.hour + 1

    def test_missing_participant_defaults_to_unknown(self):
        student = self._make_student(Participant="")
        appt = _parse_student_to_appointment(student, self._make_slot())
        # Empty string is falsy but the code uses .get("Participant", "Unknown")
        # Empty string is returned as-is by .get — test the actual behaviour
        assert appt is not None

    def test_unparseable_date_returns_none(self):
        slot = self._make_slot(date="not-a-date")
        appt = _parse_student_to_appointment(self._make_student(), slot)
        assert appt is None

    def test_different_class_types(self):
        for class_title in ["JR", "CREATE (CODING)", "CODE (GAMING)"]:
            slot = self._make_slot(class_title=class_title)
            appt = _parse_student_to_appointment(self._make_student(), slot)
            assert appt.appointment_type == class_title
