"""
Mock chatbot for testing UI without hitting the real Claude API.

Usage:
    Set TEST_MODE=true environment variable to use this instead of ChatbotEngine.

    Example:
        TEST_MODE=true python3 app.py
"""

import time
import random
from typing import List, Dict


class MockChatbotEngine:
    """Mock implementation of ChatbotEngine for testing UI."""

    def __init__(self):
        self.conversation_history = []
        self.call_count = 0

    def chat(self, user_message: str, status_callback=None, user_name: str = "Unknown") -> str:
        """
        Simulate a chat response with realistic tour data.
        Includes a slight delay to simulate API processing.
        """
        self.call_count += 1
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Simulate API latency and emit status
        time.sleep(0.3)
        if status_callback:
            status_callback("Fetching schedule from LineLeader and MyStudio...")
        time.sleep(0.5)

        # Route to mock handlers based on message content
        message_lower = user_message.lower()

        # Check for full schedule (GBS + appointments)
        if (("full schedule" in message_lower or "complete schedule" in message_lower or "all appointments" in message_lower) and
            "today" in message_lower):
            response = self._mock_todays_full_schedule()
        # Check for today's schedule (various phrasings)
        elif (("tour" in message_lower or "schedule" in message_lower or "calendar" in message_lower) and
            ("today" in message_lower or "scheduled" in message_lower)):
            response = self._mock_todays_tours()
        # Check for tour details
        elif ("detail" in message_lower or "tell me" in message_lower or "info" in message_lower) and ("tour" in message_lower or "#" in message_lower):
            response = self._mock_tour_details()
        # Check for reschedule
        elif "reschedule" in message_lower or "move" in message_lower or "change" in message_lower or "time" in message_lower:
            response = self._mock_reschedule()
        # Check for JR GBS filter
        elif "jr gbs" in message_lower or "junior" in message_lower or "jr " in message_lower:
            response = self._mock_filter_junior()
        # Check for tour count/summary
        elif "how many" in message_lower or "count" in message_lower or "summary" in message_lower:
            response = self._mock_tour_count()
        else:
            response = self._mock_generic()

        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def _mock_todays_tours(self) -> str:
        """Mock response for 'what tours are scheduled today?'"""
        from format_tours import get_sample_sessions, format_tours_as_bullets

        sessions = get_sample_sessions()
        formatted = format_tours_as_bullets(sessions)

        gbs_count = sum(1 for s in sessions if s.tour_type == "GBS")
        jrgbs_count = sum(1 for s in sessions if s.tour_type == "JR GBS")

        return f"""Here are the GBS tours scheduled for today:

{formatted}

**Summary:** {len(sessions)} tours total ({gbs_count} GBS, {jrgbs_count} JR GBS)

📥 **Download as Excel:** You can [download this schedule as Excel](/api/export/tours) to print or share on WhatsApp. 😊"""

    def _mock_todays_full_schedule(self) -> str:
        """Mock response for 'what's my full schedule today?' (GBS + appointments merged)"""
        from datetime import datetime
        from format_tours import get_sample_sessions, format_unified_schedule
        from sites.mystudio.appointments import StudentAppointment

        # Get mock GBS sessions
        gbs_sessions = get_sample_sessions()

        # Create mock student appointments matching real MyStudio data shape
        today = datetime.now()
        def appt(id, student, parent, phone, rank, type, hour, minute):
            return StudentAppointment(
                id=id,
                student_name=student,
                student_id="",
                parent_name=parent,
                phone=phone,
                rank=rank,
                appointment_type=type,
                start_time=today.replace(hour=hour, minute=minute, second=0, microsecond=0),
                end_time=today.replace(hour=hour+1, minute=minute, second=0, microsecond=0),
                duration_minutes=60,
                instructor_name="",
                location="",
                notes=None,
            )

        appointments = [
            # 3:00 PM CREATE (CODING)
            appt("001", "Khai Collins",    "Orlando Collins",  "909-555-0101", "White Belt",  "CREATE (CODING)", 15, 0),
            appt("002", "Levi Otubuah",    "Edmund Otubuah",   "909-555-0102", "White Belt",  "CREATE (CODING)", 15, 0),
            appt("003", "Lucia Zamarripa", "Karla Zamarripa",  "909-555-0103", "Yellow Belt", "CREATE (CODING)", 15, 0),
            # 3:00 PM SCRATCH PLUS
            appt("004", "Musa Khan",       "Rabab Khan",       "909-555-0104", "ScratchJR",   "SCRATCH PLUS",    15, 0),
            appt("005", "Jacob Niu",       "Meng Niu",         "909-555-0105", "ScratchJR",   "SCRATCH PLUS",    15, 0),
            # 4:00 PM CREATE (CODING)
            appt("006", "Aiden Park",      "Ji-Yeon Park",     "909-555-0106", "Orange Belt", "CREATE (CODING)", 16, 0),
            appt("007", "Sofia Rivera",    "Maria Rivera",     "909-555-0107", "Green Belt",  "CREATE (CODING)", 16, 0),
            # 5:00 PM JR
            appt("008", "Noah Williams",   "Lisa Williams",    "909-555-0108", "White Belt",  "JR",              17, 0),
            appt("009", "Zoe Martinez",    "Ana Martinez",     "909-555-0109", "White Belt",  "JR",              17, 0),
            appt("010", "Ethan Brown",     "Karen Brown",      "909-555-0110", "Yellow Belt", "JR",              17, 0),
        ]

        formatted = format_unified_schedule(gbs_sessions, appointments)
        total_items = len(gbs_sessions) + len(appointments)

        return f"""{formatted}

**Summary:** {total_items} items total ({len(gbs_sessions)} GBS tours, {len(appointments)} student appointments)

📥 **Download as Excel:** You can [download this schedule as Excel](/api/export/tours) to print or share. 😊"""

    def _mock_tour_details(self) -> str:
        """Mock response for 'tell me about tour...'"""
        return """Tour Details:
  **ID:** 1995970
  **Time:** 9:30 AM
  **Guardian:** John Smith
  **Children:** Alex Smith (7y), Emma Smith (5y)
  **Tour Type:** GBS
  **Assigned To:** Venay Bhatia
  **Location:** Eastvale-Chino, CA

This is a standard GBS (Game Building Session) tour. The children are both school-age and interested in coding. Is there anything else you'd like to know? 🎮"""

    def _mock_reschedule(self) -> str:
        """Mock response for reschedule requests."""
        return """I'd be happy to help reschedule a tour!

To reschedule, I need:
1. The **tour ID** (e.g., 1995970)
2. The **new date and time** (e.g., tomorrow at 11:00 AM)

For example, you could say: "Reschedule tour 1995970 to tomorrow at 11:00 AM"

Which tour would you like to reschedule? 📅"""

    def _mock_filter_junior(self) -> str:
        """Mock response for JR GBS filter."""
        from format_tours import get_sample_sessions, format_tours_as_bullets

        all_sessions = get_sample_sessions()
        jr_sessions = [s for s in all_sessions if s.tour_type == "JR GBS"]
        formatted = format_tours_as_bullets(jr_sessions)

        return f"""Here are the **JR GBS** tours scheduled for today:

{formatted}

There is **1 JR GBS tour** today. Would you like more details or to reschedule it? 👶"""

    def _mock_tour_count(self) -> str:
        """Mock response for tour count."""
        return """Tour Summary for Today (May 28):
- **Total tours:** 3
- **GBS tours:** 2
- **JR GBS tours:** 1
- **Assigned to Venay Bhatia:** 3

All tours are on schedule! Is there anything else you need? 📊"""

    def _mock_generic(self) -> str:
        """Generic mock response for unrecognized queries."""
        return """I can help you with GBS tours and student appointments! Here are some things you can ask:

✅ **"What's my full schedule today?"** — See GBS tours + appointments (Milestone 2)
✅ **"What tours are scheduled today?"** — See just the GBS tours
✅ **"Tell me about tour #1995970"** — Get details about a specific tour
✅ **"Reschedule tour #1995970 to 11:00 AM tomorrow"** — Reschedule a tour
✅ **"Are there any JR GBS tours?"** — Filter by tour type
✅ **"How many tours are scheduled?"** — Get a summary

What would you like to do? 😊"""
