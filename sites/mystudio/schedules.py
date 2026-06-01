"""
sites/mystudio/schedules.py
===========================
MyStudio API calls for fetching today's class schedule and student rosters.

Confirmed endpoints (from Playwright network capture 2026-05-31):
  GET  /Api/PortalApi/getClassScheduledetails  - class time slots for a date
  POST /Api/PortalApi/getClassdatatabledetails - student roster per time slot
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date

from config.settings import settings
from core.logger import get_logger
from sites.mystudio.auth import get_session
from sites.mystudio.appointments import StudentAppointment

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
COMPANY_ID = settings.MYSTUDIO_COMPANY_ID


def get_todays_appointments() -> List[StudentAppointment]:
    """
    Fetch today's student appointments from MyStudio.

    Flow:
    1. GET getClassScheduledetails for today → list of classes + time slots
    2. For each time slot, POST getClassdatatabledetails → student roster
    3. Deduplicate (a student may appear in multiple time slots) by student_id
    4. Return sorted by start_time

    Returns:
        List of StudentAppointment objects sorted by start_time
    """
    today_str = date.today().strftime("%Y-%m-%d")
    logger.info("Fetching MyStudio schedule for %s", today_str)

    session = get_session()

    # Step 1: Get class schedule (time slots)
    schedule = _get_class_schedule(session, today_str)
    if not schedule:
        logger.info("No classes scheduled for %s", today_str)
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

    logger.info("Found %d time slots across all classes", len(time_slots))

    # Step 3: Fetch student roster for each time slot
    seen_class_reg_ids = set()
    appointments = []

    for slot in time_slots:
        if int(slot.get("reg_count", "0")) == 0:
            continue  # Skip empty slots

        students = _get_slot_roster(session, slot["class_appointment_times_id"], today_str)
        for student in students:
            reg_id = student.get("class_reg_id", "")
            if reg_id in seen_class_reg_ids:
                continue
            seen_class_reg_ids.add(reg_id)

            appt = _parse_student_to_appointment(student, slot)
            if appt:
                appointments.append(appt)

    appointments.sort(key=lambda a: a.start_time)
    logger.info("Returning %d student appointments", len(appointments))
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
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "Success":
            logger.warning("getClassScheduledetails returned non-success: %s", data.get("status"))
            return []

        return data.get("msg", [])

    except Exception as e:
        logger.error("Failed to fetch class schedule: %s", e)
        return []


def _get_slot_roster(session, class_appointment_times_id: str, date_str: str) -> List[Dict]:
    """
    POST getClassdatatabledetails for a specific time slot.

    Uses DataTables form format (application/x-www-form-urlencoded).
    Returns the list of student records.
    """
    url = f"{BASE_URL}/getClassdatatabledetails"

    # DataTables column definitions (must match what browser sends)
    data = (
        "draw=1"
        "&columns%5B0%5D%5Bdata%5D=&columns%5B0%5D%5Bname%5D=&columns%5B0%5D%5Bsearchable%5D=true&columns%5B0%5D%5Borderable%5D=false&columns%5B0%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B0%5D%5Bsearch%5D%5Bregex%5D=false"
        "&columns%5B1%5D%5Bdata%5D=show_icon&columns%5B1%5D%5Bname%5D=&columns%5B1%5D%5Bsearchable%5D=true&columns%5B1%5D%5Borderable%5D=false&columns%5B1%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B1%5D%5Bsearch%5D%5Bregex%5D=false"
        "&columns%5B2%5D%5Bdata%5D=Participant&columns%5B2%5D%5Bname%5D=&columns%5B2%5D%5Bsearchable%5D=true&columns%5B2%5D%5Borderable%5D=true&columns%5B2%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B2%5D%5Bsearch%5D%5Bregex%5D=false"
        "&columns%5B3%5D%5Bdata%5D=Buyer&columns%5B3%5D%5Bname%5D=&columns%5B3%5D%5Bsearchable%5D=true&columns%5B3%5D%5Borderable%5D=true&columns%5B3%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B3%5D%5Bsearch%5D%5Bregex%5D=false"
        "&columns%5B4%5D%5Bdata%5D=rank_status&columns%5B4%5D%5Bname%5D=&columns%5B4%5D%5Bsearchable%5D=true&columns%5B4%5D%5Borderable%5D=true&columns%5B4%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B4%5D%5Bsearch%5D%5Bregex%5D=false"
        "&start=0&length=200&search%5Bvalue%5D=&search%5Bregex%5D=false"
        f"&company_id={COMPANY_ID}"
        f"&class_appointment_times_id={class_appointment_times_id}"
        f"&selected_date={date_str}"
    )

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    try:
        resp = session.post(url, data=data, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result.get("data", [])

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
