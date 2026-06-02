"""
Format GBS tours and student appointments for display and export.
"""

from typing import List, Union
from datetime import datetime


def format_tours_as_bullets(sessions) -> str:
    """
    Format tours as nested bullets for chat display.

    Format:
    📅 Thursday, May 28, 2026
      ⏰ 9:30 AM
        👨‍👩‍👧 John Smith
        👧 Alex Smith (7y), Emma Smith (5y)
        🎮 GBS
      ⏰ 2:00 PM
        ...
    """
    if not sessions:
        return "No tours scheduled."

    # Group by date
    by_date = {}
    for session in sessions:
        date_key = session.date_display()
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(session)

    lines = []
    for date, day_sessions in by_date.items():
        lines.append(f"📅 {date}")

        for session in day_sessions:
            lines.append(f"  ⏰ {session.time_display()}")
            lines.append(f"    👨‍👩‍👧 {session.student_name}")

            if session.child_display:
                children_text = ", ".join(session.child_display)
                lines.append(f"    👧 {children_text}")

            lines.append(f"    🎮 {session.tour_type}")

    return "\n".join(lines)


def format_unified_schedule(gbs_sessions, appointments, date=None) -> str:
    """
    Format unified schedule (GBS tours + student appointments) as nested bullets.

    Merges both lists, sorts by start_time, and displays with appropriate icons.

    Format:
    📅 Today's Schedule (May 31, 2026)
    ├── 10:00 AM | GBS Junior (Journei Ashbourne)
    │   └── Staff: Venay Bhatia
    ├── 11:30 AM | Lesson (Emma Johnson)
    │   └── Instructor: Sarah Smith
    └── 1:30 PM | GBS (Tyler Chen)
        └── Staff: Alex Martinez

    Args:
        gbs_sessions: List of GBSSession objects
        appointments: List of StudentAppointment objects
        date: Optional datetime for header (default: today)

    Returns:
        Formatted string for display
    """
    if not gbs_sessions and not appointments:
        return "No schedule for today."

    if not date:
        date = datetime.now()

    # Create unified list with (start_time, type, name, detail) tuples
    items = []

    # Add GBS sessions
    for session in gbs_sessions:
        children_str = ", ".join(session.child_display) if session.child_display else "children TBD"
        items.append({
            "time": session.start_time,
            "type": session.tour_type,
            "name": f"Parent: {session.student_name} | Child: {children_str}",
            "instructor": f"Staff: {session.assignee_name}",
            "icon": "🎯",
        })

    # Add appointments
    for appt in appointments:
        parent = getattr(appt, "parent_name", "") or appt.instructor_name
        items.append({
            "time": appt.start_time,
            "type": appt.appointment_type,
            "name": f"Student: {appt.student_name} ({appt.rank}) | Parent: {parent}",
            "instructor": f"Phone: {appt.phone}" if appt.phone else "",
            "icon": "💻",
        })

    # Sort by time — strip timezone info so naive and aware datetimes can be compared
    items.sort(key=lambda x: x["time"].astimezone().replace(tzinfo=None) if x["time"].tzinfo else x["time"])

    # Format output
    date_str = date.strftime("%B %d, %Y")  # e.g., "May 31, 2026"
    lines = [f"📅 Today's Schedule ({date_str})"]

    if not items:
        lines.append("No appointments scheduled.")
        return "\n".join(lines)

    for i, item in enumerate(items):
        t = item["time"]
        if t.tzinfo is not None:
            t = t.astimezone()  # Convert UTC → local time for GBS sessions
        time_str = t.strftime("%I:%M %p").lstrip("0")
        is_last = (i == len(items) - 1)
        prefix = "└── " if is_last else "├── "

        lines.append(f"{prefix}{time_str} | {item['type']} ({item['name']})")
        lines.append(f"{'    ' if is_last else '│   '}└── {item['icon']} {item['instructor']}")

    return "\n".join(lines)


def get_sample_sessions():
    """
    Create sample GBSSession objects for testing.
    """
    from sites.lineleader.schedules import GBSSession
    from datetime import datetime, timedelta

    today = datetime.now()

    sessions = [
        GBSSession(
            student_name="John Smith",
            start_time=today.replace(hour=9, minute=30, second=0, microsecond=0),
            tour_type="GBS",
            display_type="Tour",
            description="GBS",
            item_id="1995970",
            assignee_name="Venay Bhatia",
            location_name="Eastvale-Chino, CA",
            family_id="929179",
            child_names=["Alex Smith", "Emma Smith"],
            child_display=["Alex Smith (7y)", "Emma Smith (5y)"]
        ),
        GBSSession(
            student_name="Sarah Johnson",
            start_time=today.replace(hour=11, minute=0, second=0, microsecond=0),
            tour_type="JR GBS",
            display_type="Tour",
            description="JR GBS",
            item_id="1995971",
            assignee_name="Venay Bhatia",
            location_name="Eastvale-Chino, CA",
            family_id="929180",
            child_names=["Maya Johnson"],
            child_display=["Maya Johnson (3y)"]
        ),
        GBSSession(
            student_name="Michael Chen",
            start_time=today.replace(hour=13, minute=30, second=0, microsecond=0),
            tour_type="GBS",
            display_type="Tour",
            description="GBS",
            item_id="1995972",
            assignee_name="Venay Bhatia",
            location_name="Eastvale-Chino, CA",
            family_id="929181",
            child_names=["Lucas Chen", "Sophia Chen"],
            child_display=["Lucas Chen (8y)", "Sophia Chen (6y)"]
        ),
        GBSSession(
            student_name="Jessica Martinez",
            start_time=today.replace(hour=15, minute=0, second=0, microsecond=0),
            tour_type="GBS",
            display_type="Tour",
            description="GBS",
            item_id="1995973",
            assignee_name="Venay Bhatia",
            location_name="Eastvale-Chino, CA",
            family_id="929182",
            child_names=["Diego Martinez"],
            child_display=["Diego Martinez (6y)"]
        ),
        GBSSession(
            student_name="David Lee",
            start_time=today.replace(hour=16, minute=30, second=0, microsecond=0),
            tour_type="JR GBS",
            display_type="Tour",
            description="JR GBS",
            item_id="1995974",
            assignee_name="Venay Bhatia",
            location_name="Eastvale-Chino, CA",
            family_id="929183",
            child_names=["Ethan Lee", "Sophie Lee"],
            child_display=["Ethan Lee (4y)", "Sophie Lee (2y)"]
        ),
    ]

    return sessions
