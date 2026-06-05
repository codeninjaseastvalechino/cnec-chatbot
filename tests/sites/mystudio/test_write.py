"""Tests for sites/mystudio/write.py — cancel and move operations."""
import pytest
from unittest.mock import MagicMock, patch

from sites.mystudio.write import cancel_student_appointment, move_student_appointment
from sites.mystudio.auth import MystudioOTPRequired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session(status_code, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.post.return_value = resp
    return session


CANCEL_KWARGS = dict(
    student_id="245419",
    participant_id="279704",
    class_reg_id="3028857",
    class_registration_detail_id="11420559",
    class_appointment_id="10797",
    class_appointment_times_id="28287",
    selected_date="2026-06-27",
)

MOVE_KWARGS = dict(
    student_id="245419",
    participant_id="279704",
    class_reg_id="3127901",
    class_registration_detail_id="11774990",
    class_appointment_id="10797",
    class_appointment_times_id="28283",
    program_date="2026-06-13",
    new_class_appointment_times_id="30015",
    new_program_date="2026-06-14",
)


# ---------------------------------------------------------------------------
# cancel_student_appointment
# ---------------------------------------------------------------------------

class TestCancelStudentAppointment:
    def test_single_cancel_success(self):
        mock_session = _mock_session(200, {"status": "Success", "msg": "Class/appointment was deleted successfully."})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = cancel_student_appointment(**CANCEL_KWARGS, cancel_all_future=False)
        assert ok is True
        assert "deleted" in msg.lower()

    def test_all_future_cancel_success(self):
        mock_session = _mock_session(200, {"status": "Success", "msg": "This and all ongoing future class/appointments were deleted successfully."})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = cancel_student_appointment(**CANCEL_KWARGS, cancel_all_future=True)
        assert ok is True

    def test_single_sets_cancel_type_n(self):
        mock_session = _mock_session(200, {"status": "Success", "msg": "ok"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            cancel_student_appointment(**CANCEL_KWARGS, cancel_all_future=False)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["cancel_registration_type"] == "N"

    def test_all_future_sets_cancel_type_y(self):
        mock_session = _mock_session(200, {"status": "Success", "msg": "ok"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            cancel_student_appointment(**CANCEL_KWARGS, cancel_all_future=True)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["cancel_registration_type"] == "Y"

    def test_sends_correct_user_id(self):
        mock_session = _mock_session(200, {"status": "Success", "msg": "ok"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            cancel_student_appointment(**CANCEL_KWARGS)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["user_id"] == "9901"

    def test_non_success_status_returns_false(self):
        mock_session = _mock_session(200, {"status": "Error", "msg": "Something went wrong"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = cancel_student_appointment(**CANCEL_KWARGS)
        assert ok is False
        assert "Something went wrong" in msg

    def test_401_raises_otp_required(self):
        mock_session = _mock_session(401)
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            with patch("sites.mystudio.write.clear_cached_cookies"):
                with pytest.raises(MystudioOTPRequired):
                    cancel_student_appointment(**CANCEL_KWARGS)

    def test_network_error_returns_false(self):
        mock_session = MagicMock()
        mock_session.post.side_effect = Exception("connection refused")
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = cancel_student_appointment(**CANCEL_KWARGS)
        assert ok is False
        assert "connection refused" in msg


# ---------------------------------------------------------------------------
# move_student_appointment
# ---------------------------------------------------------------------------

class TestMoveStudentAppointment:
    def test_single_move_success(self):
        mock_session = _mock_session(200, {"status": "Success", "available_list_count": 1, "available_list": []})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = move_student_appointment(**MOVE_KWARGS, move_all_future=False)
        assert ok is True

    def test_all_future_move_success(self):
        mock_session = _mock_session(200, {"status": "Success", "available_list_count": 26, "available_list": []})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = move_student_appointment(**MOVE_KWARGS, move_all_future=True)
        assert ok is True

    def test_single_sets_recurring_flag_n(self):
        mock_session = _mock_session(200, {"status": "Success"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            move_student_appointment(**MOVE_KWARGS, move_all_future=False)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["selected_reschedule_type"] == "N"
        assert payload["allow_recurring_reschedule"] == "N"

    def test_all_future_sets_recurring_flag_y(self):
        mock_session = _mock_session(200, {"status": "Success"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            move_student_appointment(**MOVE_KWARGS, move_all_future=True)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["selected_reschedule_type"] == "Y"
        assert payload["allow_recurring_reschedule"] == "Y"

    def test_sends_correct_ids(self):
        mock_session = _mock_session(200, {"status": "Success"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            move_student_appointment(**MOVE_KWARGS)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["class_reg_id"] == "3127901"
        assert payload["new_class_appointment_times_id"] == "30015"
        assert payload["new_program_date"] == "2026-06-14"
        assert payload["user_id"] == "9901"

    def test_non_success_status_returns_false(self):
        mock_session = _mock_session(200, {"status": "Error", "msg": "Slot unavailable"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = move_student_appointment(**MOVE_KWARGS)
        assert ok is False
        assert "Slot unavailable" in msg

    def test_401_raises_otp_required(self):
        mock_session = _mock_session(401)
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            with patch("sites.mystudio.write.clear_cached_cookies"):
                with pytest.raises(MystudioOTPRequired):
                    move_student_appointment(**MOVE_KWARGS)

    def test_network_error_returns_false(self):
        mock_session = MagicMock()
        mock_session.post.side_effect = Exception("timeout")
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            ok, msg = move_student_appointment(**MOVE_KWARGS)
        assert ok is False
        assert "timeout" in msg

    def test_uses_v2_url(self):
        mock_session = _mock_session(200, {"status": "Success"})
        with patch("sites.mystudio.write.get_session", return_value=mock_session):
            move_student_appointment(**MOVE_KWARGS)
        call_url = mock_session.post.call_args[0][0]
        assert "/Api/v2/RescheduleCurrentAppointment" in call_url
