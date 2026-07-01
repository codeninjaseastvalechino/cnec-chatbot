"""
sites/mystudio/schedules.py
===========================
MyStudio API calls for fetching today's class schedule and student rosters.

Confirmed endpoints (from Playwright network capture 2026-05-31):
  GET  /Api/PortalApi/getClassScheduledetails  - class time slots for a date
  POST /Api/PortalApi/getClassdatatabledetails - student roster per time slot
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlencode

from config.settings import settings
from core.date_utils import today_local
from core.logger import get_logger
from sites.mystudio.auth import get_session, clear_cached_cookies, MystudioOTPRequired
from sites.mystudio.appointments import StudentAppointment

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
COMPANY_ID = settings.MYSTUDIO_COMPANY_ID


def _initialize_session(session) -> None:
    """
    Call initialization endpoints that the browser calls after login.
    These must be called before getClassdatatabledetails will work.
    """
    try:
        # checkClassScheduleFeatureAvailabilty
        session.get(f"{BASE_URL}/checkClassScheduleFeatureAvailabilty", params={
            "class_scheduler_verion": "2",
            "company_id": COMPANY_ID,
        }, timeout=10)
        logger.debug("Called checkClassScheduleFeatureAvailabilty")

        # getMenuNames
        session.get(f"{BASE_URL}/getMenuNames", params={
            "company_id": COMPANY_ID,
        }, timeout=10)
        logger.debug("Called getMenuNames")

        # getCustomFieldTitle
        session.get(f"{BASE_URL}/getCustomFieldTitle", params={
            "company_id": COMPANY_ID,
            "from": "R",
        }, timeout=10)
        logger.debug("Called getCustomFieldTitle")

    except Exception as e:
        logger.warning("Error during session initialization: %s", e)
        # Don't fail if init calls fail, continue anyway


def get_todays_appointments() -> List[StudentAppointment]:
    """
    Fetch today's student appointments from MyStudio.

    Returns:
        List of StudentAppointment objects sorted by start_time
    """
    today_str = today_local().strftime("%Y-%m-%d")
    return get_appointments_for_date(today_str)


def get_appointments_for_date(date_str: str) -> List[StudentAppointment]:
    """
    Fetch student appointments from MyStudio for a specified date.

    Args:
        date_str: Date string in YYYY-MM-DD format (e.g., "2026-06-03")

    Flow:
    1. Authenticate session
    2. Call initialization endpoints (checkClassScheduleFeatureAvailabilty, getMenuNames, etc.)
    3. GET getClassScheduledetails for the date → list of classes + time slots
    4. For each time slot, POST getClassdatatabledetails → student roster
    5. Deduplicate (a student may appear in multiple time slots) by student_id
    6. Return sorted by start_time

    Returns:
        List of StudentAppointment objects sorted by start_time
    """
    logger.info("Fetching MyStudio schedule for %s", date_str)

    session = get_session()

    # Step 0: Initialize session with required endpoints (from browser capture)
    _initialize_session(session)

    # Step 1: Get class schedule (time slots)
    # If the cached session expired (401), re-authenticate once and retry.
    # Without this, the 401 bubbles up as MystudioOTPRequired before auto-OTP
    # has had a chance to run — the user would be asked for a code that was never sent.
    try:
        schedule = _get_class_schedule(session, date_str)
    except MystudioOTPRequired:
        logger.info("Session expired mid-fetch — re-authenticating and retrying")
        session = get_session()  # clears cache → calls _start_login() → auto-OTP or raises (email sent this time)
        _initialize_session(session)
        schedule = _get_class_schedule(session, date_str)
    if not schedule:
        logger.info("No classes scheduled for %s", date_str)
        return []

    # Step 2: Collect all time slots across all class types
    time_slots = []
    for day_entry in schedule:
        for class_entry in day_entry.get("c_details", []):
            class_title = class_entry.get("class_appointment_title", "")
            for slot in class_entry.get("child_details", []):
                time_slots.append({
                    "class_appointment_times_id": slot["class_appointment_times_id"],
                    "class_occurrence_id": slot.get("class_appointment_occurrence_id", ""),
                    "start_time": slot["start_time"],
                    "date": slot["server_date_format"],
                    "capacity": slot.get("capacity_value", "0"),
                    "reg_count": slot.get("reg_count_time", "0"),
                    "class_title": class_title,
                })

    non_empty = [s for s in time_slots if int(s.get("reg_count", "0")) > 0]
    logger.info(
        "Found %d time slots across all classes (%d non-empty)",
        len(time_slots), len(non_empty),
    )

    # Step 3: Fetch student rosters for all non-empty slots in parallel.
    # Each roster is an independent ~1s MyStudio call, so fetching them
    # concurrently turns an N-serial wait into roughly one round trip. The
    # shared keep-alive Session's pool (maxsize=25) handles the concurrency.
    # Dedup + parse run after collection so no shared state is mutated across
    # threads; executor.map preserves slot order, so "first slot wins" dedup
    # behaves exactly as the old sequential loop.
    # Cap sized to a full center day (~11 non-empty slots: 3:00–6:30 half-hour
    # blocks + JR + AI/Robotics) plus headroom, so a busy day fetches in one
    # wave instead of two. Peak is well under the Session pool (maxsize=25).
    roster_start = time.monotonic()
    workers = min(12, len(non_empty))
    if workers <= 1:
        rosters = [
            _get_slot_roster(session, s["class_appointment_times_id"], date_str)
            for s in non_empty
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rosters = list(executor.map(
                lambda s: _get_slot_roster(session, s["class_appointment_times_id"], date_str),
                non_empty,
            ))

    seen_class_reg_ids = set()
    appointments = []
    for slot, students in zip(non_empty, rosters):
        for student in students:
            reg_id = student.get("class_reg_id", "")
            if reg_id in seen_class_reg_ids:
                continue
            seen_class_reg_ids.add(reg_id)

            appt = _parse_student_to_appointment(student, slot)
            if appt:
                appointments.append(appt)

    appointments.sort(key=lambda a: a.start_time)
    roster_elapsed = time.monotonic() - roster_start
    logger.info(
        "MyStudio done | %d appointments from %d slots | roster fetch: %.1fs",
        len(appointments), len(non_empty), roster_elapsed,
    )
    return appointments


def _get_class_schedule(session, date_str: str) -> List[Dict]:
    """
    GET getClassScheduledetails for a given date.

    Returns the raw schedule list from the API response.
    """
    url = f"{BASE_URL}/getClassScheduledetails"
    params = {
        "class_appointment_times_id": "",
        "class_scheduler_verion": "2",
        "company_id": COMPANY_ID,
        "selected_date": date_str,
        "view_roster_flag": "N",
    }

    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 401:
            logger.warning("MyStudio returned 401 — cookies expired, clearing cache")
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired. OTP re-authentication required.")
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "Success":
            logger.warning("getClassScheduledetails returned non-success: %s", data.get("status"))
            return []

        return data.get("msg", [])

    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("Failed to fetch class schedule: %s", e)
        return []


def _get_slot_roster(session, class_appointment_times_id: str, date_str: str) -> List[Dict]:
    """
    POST getClassdatatabledetails for a specific time slot.

    Returns the list of student records.
    Sends full DataTables request with all 23 column definitions (from working curl).
    """
    url = f"{BASE_URL}/getClassdatatabledetails"

    # Full DataTables request matching the working curl command
    data = {
        "draw": "1",
        "company_id": COMPANY_ID,
        "class_appointment_times_id": class_appointment_times_id,
        "selected_date": date_str,
        "start": "0",
        "length": "81",
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "9",
        "order[0][dir]": "desc",
        "from": "",
        "start_date": "",
        "end_date": "",
        "show_participant_pic": "N",
    }

    # Add all 23 column definitions
    columns = [
        ("", False),           # 0
        ("show_icon", False),  # 1
        ("Participant", True), # 2
        ("Buyer", True),       # 3
        ("rank_status", True), # 4
        ("att_req", True),     # 5
        ("membership_end_date", True), # 6
        ("Email", True),       # 7
        ("Phone", True),       # 8
        ("Detail", True),      # 9
        ("class_attendance_status", False), # 10
        ("Registration_Date", False),  # 11
        ("Registration_Method", False), # 12
        ("First Day in Program", False), # 13
        ("Ninja Username", False), # 14
        ("", False),  # 15
        ("", False),  # 16
        ("", False),  # 17
        ("", False),  # 18
        ("", False),  # 19
        ("", False),  # 20
        ("", False),  # 21
        ("", False),  # 22
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
        logger.debug("Fetching roster for slot %s on %s", class_appointment_times_id, date_str)
        resp = session.post(url, data=data, headers=headers, timeout=30)

        resp.raise_for_status()
        result = resp.json()
        students = result.get("data", [])

        logger.info("Got %d students for slot %s", len(students), class_appointment_times_id)
        return students

    except Exception as e:
        logger.error("Failed to fetch slot roster (slot=%s): %s", class_appointment_times_id, e)
        return []


def _parse_student_to_appointment(student: Dict, slot: Dict) -> Optional[StudentAppointment]:
    """
    Convert a student record from getClassdatatabledetails into a StudentAppointment.
    """
    try:
        # Parse start time from slot
        date_str = slot.get("date", "")  # e.g. "2026-06-01"
        time_str = slot.get("start_time", "12:00 PM")  # e.g. "03:00 PM"
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")

        # Parse end time from student record (e.g. "2026-06-01 16:00:00")
        end_str = student.get("end_time", "")
        if end_str:
            end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        else:
            end_dt = start_dt.replace(hour=start_dt.hour + 1)  # fallback: +1 hour

        duration = int((end_dt - start_dt).total_seconds() / 60)

        return StudentAppointment(
            id=student.get("class_reg_id", ""),
            student_name=student.get("Participant", "Unknown"),
            student_id=student.get("student_id", ""),
            parent_name=student.get("Buyer", ""),
            phone=student.get("Phone", ""),
            rank=student.get("rank_status", ""),
            appointment_type=slot.get("class_title", "Class"),
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=duration,
            instructor_name="",  # Not in this API response
            location="",
            notes=None,
        )

    except Exception as e:
        logger.warning("Failed to parse student record: %s — %s", student.get("Participant"), e)
        return None
