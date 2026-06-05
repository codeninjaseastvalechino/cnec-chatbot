"""
sites/mystudio/students.py
==========================
Student lookup, attendance, and upcoming schedule.

Shared foundation for Milestone 3 (read) and Milestone 4 (write).
All M4 write handlers import find_student_by_name() and get_available_slots()
from here — no duplication.

Endpoints:
  POST /v43/Api/PortalApi/getstudent                    — search by name
  GET  /v43/Api/PortalApi/getParticipantRegDetails      — profile, rank, sessions
  GET  /v43/Api/PortalApi/getParticipantRegDetailsByType — filtered sessions by type
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

from config.settings import settings
from core.logger import get_logger
from sites.mystudio.auth import get_session, clear_cached_cookies, MystudioOTPRequired
from sites.mystudio.appointments import StudentAppointment

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
COMPANY_ID = settings.MYSTUDIO_COMPANY_ID


@dataclass
class StudentRecord:
    student_id: str       # buyer/account ID in MyStudio (confusingly named in their DB)
    participant_id: str   # child/participant ID
    name: str             # participant (child) full name
    belt_rank: str
    parent_name: str
    phone: str


def find_student_by_name(name: str) -> List[StudentRecord]:
    """
    Search MyStudio participants by name (case-insensitive, partial match).

    Note: MyStudio's getstudent endpoint uses confusing field names — in the
    search response, 'buyer_name' contains the *participant* (child) name,
    not the parent. Parent name requires a separate getParticipantRegDetails call.

    Returns [] for no match, multiple entries if ambiguous.
    Raises MystudioOTPRequired if session is expired.
    """
    session = get_session()
    url = f"{BASE_URL}/getstudent"

    data = {
        "draw": "1",
        "company_id": COMPANY_ID,
        "customerstatus": "all",
        "type": "",
        "source_mobile_portal_access_flag": "",
        "start": "0",
        "length": "10",
        "search[value]": name,
        "search[regex]": "false",
        "order[0][column]": "1",
        "order[0][dir]": "asc",
    }
    columns = [
        ("", False),
        ("buyer_name", True),
        ("type", False),
        ("member_portal", False),
        ("last_contact", True),
        ("total_payments", True),
        ("past_due", True),
        ("customer_for", True),
        ("username", False),
        ("student_email", False),
        ("", False),
        ("phone_number", False),
    ]
    for i, (col_name, orderable) in enumerate(columns):
        data[f"columns[{i}][data]"] = col_name
        data[f"columns[{i}][name]"] = ""
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true" if orderable else "false"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    try:
        resp = session.post(url, data=data, headers=headers, timeout=15)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        rows = resp.json().get("data", [])

        seen_participant_ids = set()
        results = []
        for row in rows:
            if row.get("customer_type") != "participant":
                continue
            pid = str(row.get("participant_id", ""))
            if pid in seen_participant_ids:
                continue
            seen_participant_ids.add(pid)
            results.append(StudentRecord(
                student_id=str(row.get("student_id", "")),
                participant_id=pid,
                name=row.get("buyer_name", "").strip(),
                belt_rank="",
                parent_name="",
                phone="",
            ))

        logger.info("Student search '%s' → %d result(s)", name, len(results))
        return results

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("Student search failed for '%s': %s", name, e)
        return []


def get_student_details(student_id: str, participant_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full student profile: parent name, phone, rank, upcoming/recent sessions.

    Returns the 'msg' dict from getParticipantRegDetails, or None on failure.
    Raises MystudioOTPRequired if session is expired.

    Relevant keys in the returned dict:
      msg.participant_details.buyer_name          — parent name
      msg.participant_details.student_mobile      — parent phone
      msg.reg_details.membership_details[0].rank_status
      msg.reg_details.membership_details[0].attendance_last_14_days
      msg.reg_details.membership_details[0].attendance_last_30_days
      msg.reg_details.class_reg_details[]         — recent + upcoming sessions
    """
    session = get_session()
    url = f"{BASE_URL}/getParticipantRegDetails"
    params = {
        "company_id": COMPANY_ID,
        "mobile_view": "N",
        "participant_id": participant_id,
        "student_id": student_id,
    }

    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "Success":
            logger.warning("getParticipantRegDetails non-success: %s", data.get("status"))
            return None
        return data.get("msg", {})

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("getParticipantRegDetails failed (student_id=%s): %s", student_id, e)
        return None


def get_student_sessions_by_type(
    student_id: str,
    participant_id: str,
    filter_type: str,
    from_date: Optional[str] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Fetch class sessions filtered by type.

    filter_type: "U" = upcoming, "P" = past/completed
    from_date:   YYYY-MM-DD anchor date (defaults to today)
    days:        window size in days from from_date

    Returns raw class_reg_details list. Each entry has:
      class_reg_id, class_registration_detail_id, server_program_date,
      start_time, class_appointment_title, class_appointment_times_id,
      class_appointment_id, class_attendance_status, status

    Raises MystudioOTPRequired if session is expired.
    """
    session = get_session()
    url = f"{BASE_URL}/getParticipantRegDetailsByType"
    params = {
        "class_filter_date": from_date or date.today().strftime("%Y-%m-%d"),
        "class_filter_days_value": str(days),
        "class_filter_type": filter_type,
        "company_id": COMPANY_ID,
        "mobile_view": "N",
        "participant_id": participant_id,
        "show_more_type": "A",
        "student_id": student_id,
        "type_for": "C",
    }

    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "Success":
            return []
        return data.get("msg", {}).get("reg_details", [])

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("getParticipantRegDetailsByType failed (student_id=%s, type=%s): %s", student_id, filter_type, e)
        return []


def get_student_attendance_this_week(student_id: str, participant_id: str) -> int:
    """
    Count sessions with class_attendance_status == "Attended" in the current Mon–Sun week.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sessions = get_student_sessions_by_type(
        student_id, participant_id,
        filter_type="P",
        from_date=monday.strftime("%Y-%m-%d"),
        days=7,
    )
    count = sum(
        1 for s in sessions
        if s.get("class_attendance_status", "").lower() == "attended"
    )
    logger.info("Attendance this week (student_id=%s): %d/%d sessions attended", student_id, count, len(sessions))
    return count


def get_student_upcoming_appointments(
    student_id: str,
    participant_id: str,
    days_ahead: int = 14,
) -> List[StudentAppointment]:
    """
    Return StudentAppointment objects for this student's upcoming sessions.

    Each appointment's extra fields are populated for M4 use:
      .registration_detail_id  — class_registration_detail_id (cancel/move)
      .class_appointment_times_id — slot ID (move target validation)
      .class_appointment_id       — class type ID (move target validation)
    """
    today = date.today().strftime("%Y-%m-%d")
    sessions = get_student_sessions_by_type(
        student_id, participant_id,
        filter_type="U",
        from_date=today,
        days=days_ahead,
    )

    appointments = []
    for s in sessions:
        appt = _parse_session_to_appointment(s)
        if appt:
            appointments.append(appt)

    appointments.sort(key=lambda a: a.start_time)
    return appointments


def get_available_slots(date_str: str) -> List[Dict[str, Any]]:
    """
    Return class time slots on date_str that have remaining capacity.
    date_str: YYYY-MM-DD

    Used by M4 move/book handlers to present and validate target slots.
    Each dict: class_appointment_id, class_appointment_times_id, class_title,
               start_time, date, spots_left, capacity.
    """
    from sites.mystudio.schedules import _get_class_schedule
    session = get_session()
    schedule = _get_class_schedule(session, date_str)

    available = []
    for day_entry in schedule:
        for class_entry in day_entry.get("c_details", []):
            class_title = class_entry.get("class_appointment_title", "")
            class_appointment_id = class_entry.get("class_appointment_id", "")
            for slot in class_entry.get("child_details", []):
                capacity = int(slot.get("capacity_value", "0") or 0)
                registered = int(slot.get("reg_count_time", "0") or 0)
                if capacity > 0 and registered < capacity:
                    available.append({
                        "class_appointment_id": class_appointment_id,
                        "class_appointment_times_id": slot["class_appointment_times_id"],
                        "class_title": class_title,
                        "start_time": slot["start_time"],
                        "date": slot["server_date_format"],
                        "spots_left": capacity - registered,
                        "capacity": capacity,
                    })

    logger.info("Available slots on %s: %d", date_str, len(available))
    return available


def _parse_session_to_appointment(s: Dict[str, Any]) -> Optional[StudentAppointment]:
    """Parse a class_reg_details entry into a StudentAppointment."""
    try:
        date_str = s.get("server_program_date", "")
        time_str = s.get("start_time", "12:00 PM")
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        end_dt = start_dt.replace(hour=min(start_dt.hour + 1, 23))

        return StudentAppointment(
            id=s.get("class_reg_id", ""),
            student_name=s.get("p_name", ""),
            student_id=s.get("student_id", ""),
            parent_name="",
            phone="",
            rank="",
            appointment_type=s.get("class_appointment_title", "Class"),
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=60,
            registration_detail_id=s.get("class_registration_detail_id", ""),
            class_appointment_times_id=s.get("class_appointment_times_id", ""),
            class_appointment_id=s.get("class_appointment_id", ""),
        )
    except Exception as e:
        logger.warning("Failed to parse session dict: %s — %s", s.get("p_name"), e)
        return None
