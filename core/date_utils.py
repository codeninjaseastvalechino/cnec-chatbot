"""
Date and time resolution utilities.

Accepts raw natural language phrases (as Claude extracts them) and resolves
them to Python datetime objects. All conflict detection and validation lives
here — no date logic in tool handlers or LLM prompts.
"""
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from typing import Optional

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DAY_SET = {d.lower() for d in _DAYS}
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def resolve_date(date_str: str, allow_past: bool = False) -> datetime:
    """
    Resolve a raw date phrase to a datetime (midnight, date portion only).

    Handles:
      - Relative words: "today", "tomorrow", "yesterday"
      - Day names: "Friday", "next Tuesday"
      - Month + day: "June 9th", "June 9"
      - Slash format: "6/22", "6/22/26", "6/22/2026"
      - Combos: "Friday June 9th" (conflict-checked)

    allow_past: if True, past dates are returned as-is instead of rolling forward
                to next year/month. Use for operations that target past sessions.

    Raises ValueError with a user-friendly message on conflict or parse failure.
    """
    s = date_str.strip().lower()
    today = date.today()

    if s == "today":
        return datetime.combine(today, datetime.min.time())
    if s == "tomorrow":
        return datetime.combine(today + timedelta(days=1), datetime.min.time())
    if s == "yesterday":
        return datetime.combine(today - timedelta(days=1), datetime.min.time())

    # Slash format: "6/22", "6/22/26", "6/22/2026"
    import re as _re
    slash_match = _re.match(r'^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$', s.strip())
    if slash_match:
        month = int(slash_match.group(1))
        day = int(slash_match.group(2))
        year_raw = slash_match.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            year = today.year
            if not allow_past and date(year, month, day) < today:
                year += 1
        try:
            return datetime.combine(date(year, month, day), datetime.min.time())
        except ValueError:
            raise ValueError(f"'{date_str}' is not a valid date.")

    # Ordinal-only: "8th", "the 8th", "11th", "1st", "2nd", "3rd"
    ordinal_match = _re.match(r'^(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?$', s.strip())
    if ordinal_match:
        day = int(ordinal_match.group(1))
        try:
            candidate = date(today.year, today.month, day)
            if not allow_past and candidate < today:
                # Roll to next month
                if today.month == 12:
                    candidate = date(today.year + 1, 1, day)
                else:
                    candidate = date(today.year, today.month + 1, day)
            return datetime.combine(candidate, datetime.min.time())
        except ValueError:
            raise ValueError(
                f"'{date_str}' doesn't look like a valid day of the month. "
                "Please use a format like 'June 8th', 'Friday', or 'tomorrow'."
            )

    tokens = s.replace(",", "").split()
    named_day = next((t for t in tokens if t in _DAY_SET), None)

    # Parse explicit month+day if present
    explicit_date: Optional[datetime] = None
    for i, token in enumerate(tokens):
        if token in _MONTH_MAP and i + 1 < len(tokens):
            day_num = "".join(c for c in tokens[i + 1] if c.isdigit())
            if day_num:
                month = _MONTH_MAP[token]
                day = int(day_num)
                year = today.year
                if not allow_past and date(year, month, day) < today:
                    year += 1
                explicit_date = datetime(year, month, day)
                break

    if explicit_date and named_day:
        actual = _DAYS[explicit_date.weekday()]
        if actual.lower() != named_day:
            target_idx = _DAYS.index(next(d for d in _DAYS if d.lower() == named_day))
            delta = (explicit_date.weekday() - target_idx) % 7 or 7
            nearest = explicit_date - timedelta(days=delta)
            raise ValueError(
                f"{explicit_date.strftime('%B %-d')} is a {actual}, not a {named_day.title()}. "
                f"Did you mean {named_day.title()} ({nearest.strftime('%B %-d')}) "
                f"or {actual} ({explicit_date.strftime('%B %-d')})?"
            )
        return explicit_date

    if explicit_date:
        return explicit_date

    if named_day:
        target_idx = _DAYS.index(next(d for d in _DAYS if d.lower() == named_day))
        days_ahead = (target_idx - today.weekday()) % 7 or 7
        return datetime.combine(today + timedelta(days=days_ahead), datetime.min.time())

    raise ValueError(
        f"Could not understand the date '{date_str}'. "
        "Please use a format like 'Friday', 'June 9th', or 'tomorrow'."
    )


def resolve_time(time_str: str) -> Tuple[int, int]:
    """
    Parse a time phrase into (hour, minute) in 24-hour format.

    Handles: '10am', '2:30 PM', '14:00', '9'
    Raises ValueError with a user-friendly message if unparseable.
    """
    s = time_str.strip().lower().replace(" ", "")
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        raise ValueError(
            f"Could not understand the time '{time_str}'. "
            "Please use a format like '10am' or '2:30 PM'."
        )
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(
            f"'{time_str}' is not a valid time. Please use a format like '10am' or '2:30 PM'."
        )
    return hour, minute


def resolve_datetime(date_str: str, time_str: str) -> datetime:
    """
    Resolve raw date and time phrases into a combined naive local datetime.

    Raises ValueError (with user-friendly message) on any parse or conflict failure.
    Callers should catch ValueError and return its message directly to the user.
    """
    resolved = resolve_date(date_str)
    hour, minute = resolve_time(time_str)
    return resolved.replace(hour=hour, minute=minute)
