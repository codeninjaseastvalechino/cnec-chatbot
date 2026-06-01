"""
sites/mystudio/appointments.py
==============================
Data models for MyStudio student appointments.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class StudentAppointment:
    """Represents a student appointment in MyStudio."""

    id: str
    student_name: str
    student_id: str
    appointment_type: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    instructor_name: str
    location: str
    notes: Optional[str] = None

    @property
    def start_time_local(self) -> datetime:
        """Convert UTC to local timezone (for display)."""
        # TODO: Implement timezone conversion based on center location
        # For now, return as-is. Will add pytz or tzlocal when testing with real data.
        return self.start_time

    def __str__(self) -> str:
        return f"{self.start_time.strftime('%I:%M %p')} | {self.appointment_type} ({self.student_name})"
