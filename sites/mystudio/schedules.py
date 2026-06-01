"""
sites/mystudio/schedules.py
===========================
MyStudio API calls for fetching student appointments.

Pattern mirrors LineLeader (sites/lineleader/schedules.py).
"""

from typing import List, Dict, Any
from datetime import datetime

import requests

from config.settings import settings
from core.logger import get_logger
from sites.mystudio.auth import get_bearer_token
from sites.mystudio.appointments import StudentAppointment

logger = get_logger(__name__)


async def get_todays_appointments() -> List[StudentAppointment]:
    """
    Fetch today's student appointments from MyStudio.

    Returns:
        List of StudentAppointment objects, sorted by start_time
    """
    logger.info(
        "Fetching today's appointments from MyStudio",
        extra={"module": "sites.mystudio.schedules"},
    )

    token = await get_bearer_token()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # TODO: Confirm actual endpoint and parameters via Chrome DevTools live site inspection
    # Placeholder endpoint — will be replaced after site inspection
    url = f"{settings.MYSTUDIO_API_URL}/appointments"
    params = {
        "date": today,
        "org_id": settings.MYSTUDIO_ORG_ID,
    }

    headers = {
        "Authorization": token,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://cn.mystudio.io",
        "Referer": "https://cn.mystudio.io/",
        "User-Agent": "Mozilla/5.0",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)

        if response.status_code == 401:
            logger.warning(
                "Bearer token invalid (401), will re-login on next request",
                extra={"module": "sites.mystudio.schedules"},
            )
            # Token will be refreshed on next get_bearer_token() call
            raise Exception("Bearer token expired")

        response.raise_for_status()

        data = response.json()
        appointments = [_parse_appointment_response(item) for item in data.get("items", [])]

        # Sort by start_time
        appointments.sort(key=lambda a: a.start_time)

        logger.info(
            "Appointments fetched successfully",
            extra={
                "module": "sites.mystudio.schedules",
                "count": len(appointments),
                "date": today,
            },
        )

        return appointments

    except requests.RequestException as e:
        logger.error(
            "Failed to fetch appointments from MyStudio",
            extra={
                "module": "sites.mystudio.schedules",
                "error": str(e),
                "url": url,
            },
        )
        raise


async def get_future_appointments(days: int = 30) -> List[StudentAppointment]:
    """
    Fetch future student appointments from MyStudio.

    Args:
        days: Number of days ahead to fetch (default 30)

    Returns:
        List of StudentAppointment objects, sorted by start_time
    """
    # TODO: Implement after confirming endpoint structure
    raise NotImplementedError("get_future_appointments not yet implemented")


async def get_student_details(student_id: str) -> Dict[str, Any]:
    """
    Fetch student info from MyStudio.

    Args:
        student_id: MyStudio student ID

    Returns:
        Dict with student details
    """
    # TODO: Implement after confirming endpoint structure
    raise NotImplementedError("get_student_details not yet implemented")


def _parse_appointment_response(item: Dict[str, Any]) -> StudentAppointment:
    """
    Convert API response JSON to StudentAppointment object.

    Args:
        item: Raw appointment object from MyStudio API

    Returns:
        StudentAppointment dataclass

    TODO: Confirm actual JSON structure via live site inspection
          Current implementation is a placeholder based on typical API patterns.
    """
    # Placeholder parsing — adjust field names after confirming actual API response
    return StudentAppointment(
        id=item.get("id", ""),
        student_name=item.get("student_name", ""),
        student_id=item.get("student_id", ""),
        appointment_type=item.get("type", ""),
        start_time=datetime.fromisoformat(
            item.get("start_time", "").replace("Z", "+00:00")
        ),
        end_time=datetime.fromisoformat(
            item.get("end_time", "").replace("Z", "+00:00")
        ),
        duration_minutes=item.get("duration_minutes", 0),
        instructor_name=item.get("instructor_name", ""),
        location=item.get("location", ""),
        notes=item.get("notes", None),
    )
