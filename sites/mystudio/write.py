"""
sites/mystudio/write.py
=======================
MyStudio write operations: cancel and move student appointments.

Imports student lookup from students.py — no duplication of find/resolve logic.

Endpoints:
  POST /v43/Api/PortalApi/removeParticipant         — cancel single or all-future
  POST /Api/v2/RescheduleCurrentAppointment         — move single or all-future

Book (stripeClassAppointmentRegistration) is deferred — requires a student-session
token not available from staff auth flow.
"""

from typing import Tuple

from config.settings import settings
from core.logger import get_logger
from sites.mystudio.auth import get_session, clear_cached_cookies, MystudioOTPRequired

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
BASE_URL_V2 = settings.MYSTUDIO_API_V2_URL
COMPANY_ID = settings.MYSTUDIO_COMPANY_ID
USER_ID = settings.MYSTUDIO_USER_ID


def cancel_student_appointment(
    student_id: str,
    participant_id: str,
    class_reg_id: str,
    class_registration_detail_id: str,
    class_appointment_id: str,
    class_appointment_times_id: str,
    selected_date: str,
    cancel_all_future: bool = False,
) -> Tuple[bool, str]:
    """
    Cancel a student's class appointment.

    cancel_all_future=False: cancel this single session only
    cancel_all_future=True:  cancel this and all future recurring sessions

    selected_date: YYYY-MM-DD of the session being cancelled.
    Returns (True, success_message) or (False, error_message).
    Raises MystudioOTPRequired if session is expired.
    """
    session = get_session()
    url = f"{BASE_URL}/removeParticipant"

    payload = {
        "company_id": COMPANY_ID,
        "class_reg_id": class_reg_id,
        "student_id": student_id,
        "participant_id": participant_id,
        "class_appointment_id": class_appointment_id,
        "class_appointment_times_id": class_appointment_times_id,
        "selected_date": selected_date,
        "class_registration_detail_id": class_registration_detail_id,
        "user_id": USER_ID,
        "refund_allowed": "N",
        "payment_from": "S",
        "class_scheduler_verion": 2,
        "cancel_registration_type": "Y" if cancel_all_future else "N",
    }

    headers = {"Content-Type": "application/json; charset=utf-8"}

    try:
        resp = session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "Success":
            scope = "all future sessions" if cancel_all_future else "session"
            msg = data.get("msg", "Cancelled successfully.")
            logger.info("Cancel success: student_id=%s date=%s all_future=%s", student_id, selected_date, cancel_all_future)
            return True, msg
        else:
            logger.warning("Cancel non-success: %s", data)
            return False, f"MyStudio returned: {data.get('msg', 'Unknown error')}"

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("Cancel failed: student_id=%s error=%s", student_id, e)
        return False, f"Cancel failed: {str(e)}"


def move_student_appointment(
    student_id: str,
    participant_id: str,
    class_reg_id: str,
    class_registration_detail_id: str,
    class_appointment_id: str,
    class_appointment_times_id: str,
    program_date: str,
    new_class_appointment_times_id: str,
    new_program_date: str,
    move_all_future: bool = False,
) -> Tuple[bool, str]:
    """
    Move a student's appointment to a new time slot.

    move_all_future=False: move this single session only
    move_all_future=True:  move all recurring sessions from this date forward

    program_date / new_program_date: YYYY-MM-DD
    Returns (True, success_message) or (False, error_message).
    Raises MystudioOTPRequired if session is expired.
    """
    session = get_session()
    url = f"{BASE_URL_V2}/RescheduleCurrentAppointment"

    recurring_flag = "Y" if move_all_future else "N"

    payload = {
        "new_program_date": new_program_date,
        "new_class_appointment_times_id": new_class_appointment_times_id,
        "class_reg_id": class_reg_id,
        "participant_id": participant_id,
        "student_id": student_id,
        "company_id": COMPANY_ID,
        "class_appointment_id": class_appointment_id,
        "class_appointment_times_id": class_appointment_times_id,
        "program_date": program_date,
        "class_registration_detail_id": class_registration_detail_id,
        "from_flag": "U",
        "user_id": USER_ID,
        "reg_type_user": "SP",
        "refund_allowed": "N",
        "customer_id": "",
        "postal_code": "",
        "method_id": "",
        "intent_id": "",
        "credit_card_category": "",
        "credit_card_id": "",
        "credit_card_state": "",
        "ach_bank_account_id": "",
        "new_payment_method": "",
        "cc_type": "",
        "payment_from": "S",
        "payment_amount": 0,
        "class_scheduler_verion": 2,
        "selected_reschedule_type": recurring_flag,
        "allow_recurring_reschedule": recurring_flag,
        "checkout_flag": "N",
        "override_failed_payment": "N",
        "override_popup": "N",
        "iscardpresent_flag": "N",
        "reader_intent_id": "",
    }

    headers = {"Content-Type": "application/json; charset=utf-8"}

    try:
        resp = session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "Success":
            scope = "all future sessions" if move_all_future else "session"
            logger.info("Move success: student_id=%s from=%s to=%s all_future=%s", student_id, program_date, new_program_date, move_all_future)
            return True, f"Rescheduled successfully ({scope})."
        else:
            logger.warning("Move non-success: %s", data)
            return False, f"MyStudio returned: {data.get('msg', 'Unknown error')}"

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("Move failed: student_id=%s error=%s", student_id, e)
        return False, f"Move failed: {str(e)}"
