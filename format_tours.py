"""
Format GBS tours for display and export.
"""

from typing import List


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
