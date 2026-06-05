"""
sites/mystudio/appointments.py
==============================
Data models for MyStudio student appointments.

Fields confirmed from live API (getClassdatatabledetails response 2026-05-31):
  Participant, Buyer, Phone, rank_status, class_reg_id, student_id,
  reschedule_Date, end_time, Detail (class category)
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class StudentAppointment:
    """Represents a student appointment slot in MyStudio."""

    id: str                      # class_reg_id
    student_name: str            # Participant field
    student_id: str              # student_id field
    parent_name: str             # Buyer field
    phone: str                   # Phone field
    rank: str                    # rank_status (e.g., "White Belt")
    appointment_type: str        # class title (e.g., "CREATE (CODING)", "JR")
    start_time: datetime         # from slot start_time
    end_time: datetime           # from end_time field in response
    duration_minutes: int        # computed from start/end
    instructor_name: str = ""    # not in API response — placeholder
    location: str = ""           # not in API response — placeholder
    notes: Optional[str] = None
    # M4 write fields — populated by get_student_upcoming_appointments()
    registration_detail_id: str = ""      # class_registration_detail_id (needed for cancel/move)
    class_appointment_times_id: str = ""  # slot ID (needed for move)
    class_appointment_id: str = ""        # class type ID (needed for move)

    def time_display(self) -> str:
        """Format start time as '3:00 PM'."""
        return self.start_time.strftime("%I:%M %p").lstrip("0")

    def __str__(self) -> str:
        return f"{self.time_display()} | {self.appointment_type} ({self.student_name})"
