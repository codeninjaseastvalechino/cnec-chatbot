"""
sites/mystudio/camps.py
=======================
MyStudio API calls for fetching camp/event details and rosters.

Confirmed endpoints (from Playwright capture + probe 2026-06-14):
  GET  /v43/Api/PortalApi/geteventdetails  - list parent groups or child camps
  POST /v43/Api/PortalApi/getFilterDetails - roster of enrolled kids per camp

Data model (two-level):
  Parent event  — "2026 Summer and Off-Track Camps" (event_type="M", parent_id=null)
  Child camp    — "PM CAMP: Minecraft Animation Ages 8+"  (event_type="C", parent_id=<parent>)

Discovery flow (parent_id is dynamic — changes each year):
  1. GET geteventdetails?parent_id=   → msg.live[] → list of parent event groups
  2. GET geteventdetails?parent_id=X  → msg[]      → list of child camps under X
  3. Filter children: event_show_status=="Y" and event_begin_dt != "0000-00-00 00:00:00"
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from config.settings import settings
from core.logger import get_logger
from sites.mystudio.auth import get_session, clear_cached_cookies, MystudioOTPRequired

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
COMPANY_ID = settings.MYSTUDIO_COMPANY_ID

_NULL_DATE = "0000-00-00 00:00:00"


@dataclass
class CampRecord:
    """One scheduled camp session (child event)."""
    event_id: str
    parent_id: str
    parent_title: str
    title: str
    start_dt: datetime
    end_dt: datetime
    enrolled: int
    capacity: Optional[int]
    event_show_status: str        # "Y" = visible to public, "N" = hidden
    event_url: str = ""

    def week_label(self) -> str:
        """Return 'Jun 15 – Jun 19' style week label."""
        if self.start_dt.month == self.end_dt.month:
            return f"{self.start_dt.strftime('%b %-d')} – {self.end_dt.strftime('%-d')}"
        return f"{self.start_dt.strftime('%b %-d')} – {self.end_dt.strftime('%b %-d')}"

    def time_range(self) -> str:
        """Return '8:30 AM – 3:00 PM' style time label."""
        def _fmt(dt: datetime) -> str:
            return dt.strftime("%-I:%M %p")
        return f"{_fmt(self.start_dt)} – {_fmt(self.end_dt)}"

    def spots_left(self) -> Optional[int]:
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.enrolled)


@dataclass
class CampKid:
    """One enrolled kid in a camp."""
    participant_name: str
    buyer_name: str          # parent name
    phone: str
    email: str
    status: str              # "Active", "Cancelled", etc.
    event_title: str
    age: Optional[str] = ""  # p_age from API, e.g. "8"


def get_live_parent_events() -> List[Dict[str, Any]]:
    """
    Fetch top-level live camp groups (parent_id empty = top-level).

    Returns list of raw dicts with keys: event_id, event_title, registrations_count, etc.
    Only returns live (not past or draft) groups.
    """
    session = get_session()
    resp = session.get(f"{BASE_URL}/geteventdetails", params={
        "company_id": COMPANY_ID,
        "franchise_master_id": "5",
        "franchise_program_id": "9",
        "from": "W",
        "limit": "20",
        "list_type": "P",
        "parent_id": "",
    }, timeout=30)

    if resp.status_code == 401:
        clear_cached_cookies()
        raise MystudioOTPRequired("MyStudio session expired.")
    resp.raise_for_status()

    data = resp.json()
    if data.get("status") != "Success":
        logger.warning("geteventdetails (parents) returned: %s", data.get("status"))
        return []

    msg = data.get("msg", {})
    # Top-level returns {"past": [], "draft": [], "live": [...]}
    live = msg.get("live", []) if isinstance(msg, dict) else []
    logger.info("Found %d live parent camp groups", len(live))
    return live


def get_camps_under_parent(parent_event_id: str, parent_title: str) -> List[CampRecord]:
    """
    Fetch all child camp sessions under a given parent event ID.

    Only returns camps that are actually scheduled:
      - event_show_status == "Y" OR has real enrollment (registrations_count > 0)
      - event_begin_dt is not a null date
    """
    session = get_session()
    resp = session.get(f"{BASE_URL}/geteventdetails", params={
        "company_id": COMPANY_ID,
        "franchise_master_id": "5",
        "franchise_program_id": "9",
        "from": "W",
        "limit": "200",
        "list_type": "P",
        "parent_id": parent_event_id,
    }, timeout=30)

    if resp.status_code == 401:
        clear_cached_cookies()
        raise MystudioOTPRequired("MyStudio session expired.")
    resp.raise_for_status()

    data = resp.json()
    if data.get("status") != "Success":
        logger.warning("geteventdetails (children) returned: %s", data.get("status"))
        return []

    raw_camps = data.get("msg", [])
    # Child level returns a plain list (not the live/past/draft dict)
    if isinstance(raw_camps, dict):
        raw_camps = raw_camps.get("live", [])

    camps = []
    for item in raw_camps:
        begin_str = item.get("event_begin_dt", _NULL_DATE)
        end_str = item.get("event_end_dt", _NULL_DATE)

        # Skip template/placeholder camps with no real date
        if begin_str == _NULL_DATE or not begin_str:
            continue

        try:
            start_dt = datetime.strptime(begin_str, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning("Could not parse dates for camp %s: %s / %s",
                           item.get("event_id"), begin_str, end_str)
            continue

        enrolled = int(item.get("registrations_count") or 0)
        raw_cap = item.get("event_capacity")
        capacity = int(raw_cap) if raw_cap is not None else None

        camps.append(CampRecord(
            event_id=str(item.get("event_id", "")),
            parent_id=parent_event_id,
            parent_title=parent_title,
            title=item.get("event_title", ""),
            start_dt=start_dt,
            end_dt=end_dt,
            enrolled=enrolled,
            capacity=capacity,
            event_show_status=item.get("event_show_status", "N"),
            event_url=item.get("event_url", ""),
        ))

    logger.info("Parsed %d scheduled camps under parent %s", len(camps), parent_event_id)
    return camps


def get_all_upcoming_camps(from_date: Optional[datetime] = None) -> List[CampRecord]:
    """
    Fetch all upcoming camps across all live parent groups.

    Discovers parent event IDs dynamically — no hardcoded IDs.

    Args:
        from_date: Only return camps starting on or after this date.
                   Defaults to today.

    Returns:
        List of CampRecord sorted by start_dt.
    """
    if from_date is None:
        from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    parents = get_live_parent_events()
    if not parents:
        logger.info("No live parent camp groups found")
        return []

    all_camps: List[CampRecord] = []
    for parent in parents:
        parent_id = str(parent.get("event_id", ""))
        parent_title = parent.get("event_title", "Unknown")
        camps = get_camps_under_parent(parent_id, parent_title)
        all_camps.extend(camps)

    upcoming = [c for c in all_camps if c.start_dt >= from_date]
    upcoming.sort(key=lambda c: c.start_dt)
    logger.info("Found %d upcoming camps (from %s)", len(upcoming), from_date.strftime("%Y-%m-%d"))
    return upcoming


def get_camp_roster(event_id: str, parent_id: str = "") -> Optional[List[CampKid]]:
    """
    Fetch enrolled kids for a specific camp (child event_id).

    Uses getFilterDetails with the exact column/filter format captured from the browser.
    parent_id should be the parent event group ID (e.g. "292536") — required for filtering.
    Returns list of CampKid sorted by participant_name, or None on failure.
    """
    session = get_session()

    filter_options = json.dumps({
        "event_list": {"event_list_type": "P"},
        "all_event": {"all_event_id": [parent_id] if parent_id else []},
        "child_event": {"child_event_type": "S", "child_event_id": [event_id]},
        "status": {"status_type": "O"},
        "all_ranks": {"ranks_id": [], "rank_mem_id": []},
        "all_ages": {"age_type": "A", "age_from": "", "age_to": "", "age_date": ""},
        "program_registration": {
            "program_reg_type": "DNS",
            "program_reg_id": [],
            "program_reg_selected_id": [],
            "program_reg_unselected_id": [],
            "program_reg_option_id": [],
            "program_reg_status": [],
        },
        "birthday": {"bd_type": "0", "bd_days": "", "bd_start_date": "", "bd_end_date": ""},
        "source": {"source_type": "N", "source_ids": []},
    })

    # 36-column layout matching what the browser actually sends
    col_names = [
        "", "participant_name", "buyer_name", "registration_date",
        "event_reg_status", "cancelled_dt", "p_b_dt", "p_age",
        "participant_email", "", "participant_phone", "parent_title",
        "event_title", "quantity", "payment_amount", "paid_amount",
        "balance_due", "cancelled_payments", "refund_amnt", "event_reg_type_user",
        "event_source_name", "paid_marketing_id", "rank_name", "category_title",
        "l_adv", "att_req", "First Day in Program", "Ninja Username",
        "", "", "", "", "", "", "", "",
    ]
    orderable = {1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25}

    form_data: Dict[str, str] = {
        "draw": "1",
        "order[0][column]": "3",
        "order[0][dir]": "desc",
        "start": "0",
        "length": "500",
        "search[value]": "",
        "search[regex]": "false",
        "company_id": COMPANY_ID,
        "filter_id": "9",
        "filter_category": "E",
        "filter_type": "AP",
        "filter_options": filter_options,
        "type": "datatable",
        "mobile_view": "N",
        "from": "",
    }
    for i, col in enumerate(col_names):
        form_data[f"columns[{i}][data]"] = col
        form_data[f"columns[{i}][name]"] = ""
        form_data[f"columns[{i}][searchable]"] = "true"
        form_data[f"columns[{i}][orderable]"] = "true" if i in orderable else "false"
        form_data[f"columns[{i}][search][value]"] = ""
        form_data[f"columns[{i}][search][regex]"] = "false"

    try:
        resp = session.post(f"{BASE_URL}/getFilterDetails", data=form_data, timeout=30)
        if resp.status_code == 401:
            clear_cached_cookies()
            raise MystudioOTPRequired("MyStudio session expired.")
        resp.raise_for_status()
        data = resp.json()
    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("getFilterDetails failed for event_id=%s: %s", event_id, e)
        return None

    if data.get("status") == "Failed":
        logger.warning("getFilterDetails returned Failed for event %s: %s", event_id, data.get("msg"))
        return None

    kids = []
    for row in data.get("data", []):
        kids.append(CampKid(
            participant_name=row.get("participant_name", ""),
            buyer_name=row.get("buyer_name", ""),
            phone=row.get("participant_phone", ""),
            email=row.get("participant_email", ""),
            status=row.get("event_reg_status", ""),
            event_title=row.get("event_title", ""),
            age=str(row.get("p_age", "")) if row.get("p_age") else "",
        ))

    kids.sort(key=lambda k: k.participant_name)
    logger.info("Roster for event %s: %d kids", event_id, len(kids))
    return kids


def format_camps_summary(camps: List[CampRecord], include_hidden: bool = False) -> str:
    """
    Format camp list as a readable summary grouped by week.

    Args:
        camps: List of CampRecord (should already be filtered/sorted by start_dt)
        include_hidden: If True, include camps with event_show_status=="N"
    """
    if not include_hidden:
        camps = [c for c in camps if c.event_show_status == "Y"]

    if not camps:
        return "No upcoming camps found."

    # Group by week (start_dt date of the Monday = week key)
    from collections import OrderedDict
    weeks: Dict[str, List[CampRecord]] = OrderedDict()
    for camp in camps:
        # Use start date as week key (camps run Mon–Fri so group by start date)
        week_key = camp.start_dt.strftime("%Y-%m-%d")
        if week_key not in weeks:
            weeks[week_key] = []
        weeks[week_key].append(camp)

    lines = []
    for week_key, week_camps in weeks.items():
        # Header: "Week of Jun 15 – Jun 19"
        first = week_camps[0]
        last = week_camps[-1]
        lines.append(f"\n**{first.week_label()} ({first.start_dt.strftime('%A')}–{last.end_dt.strftime('%A')})**")
        for camp in week_camps:
            spots = camp.spots_left()
            spots_str = f", {spots} spot{'s' if spots != 1 else ''} left" if spots is not None else ""
            enrolled_str = f"{camp.enrolled}/{camp.capacity}" if camp.capacity else str(camp.enrolled)
            lines.append(f"  • {camp.title} | {camp.time_range()} | {enrolled_str} enrolled{spots_str}")

    return "\n".join(lines)


def format_camp_roster(camp: CampRecord, kids: Optional[List[CampKid]]) -> str:
    """Format a single camp's roster for chat display."""
    lines = [
        f"**{camp.title}**",
        f"📅 {camp.week_label()} | ⏰ {camp.time_range()}",
        f"👥 {camp.enrolled} enrolled" + (f" / {camp.capacity} capacity" if camp.capacity else ""),
        "",
    ]

    if kids is None:
        lines.append("_(Roster unavailable via API — check MyStudio directly for the full list.)_")
        return "\n".join(lines)

    active = [k for k in kids if k.status.lower() in ("active", "")]
    cancelled = [k for k in kids if k.status.lower() == "cancelled"]

    if active:
        lines.append(f"**Enrolled kids ({len(active)}):**")
        for kid in active:
            lines.append(f"  • {kid.participant_name} (parent: {kid.buyer_name}  📞 {kid.phone})")
    else:
        lines.append("No active enrollments found.")

    if cancelled:
        lines.append(f"\n**Cancelled ({len(cancelled)}):**")
        for kid in cancelled:
            lines.append(f"  • {kid.participant_name}")

    return "\n".join(lines)
