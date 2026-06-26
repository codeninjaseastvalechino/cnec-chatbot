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


def _expected_camp_price(title: str) -> float:
    """Return standard price based on camp title — Full/All Day = $399, AM/PM = $249."""
    t = title.upper()
    if "FULL DAY" in t or "ALL DAY" in t:
        return settings.CAMP_FULL_DAY_PRICE
    return settings.CAMP_HALF_DAY_PRICE


def _get_roster_raw_rows(event_id: str, parent_id: str = "") -> Optional[List[Dict[str, Any]]]:
    """Return raw getFilterDetails rows for a camp (all fields, not just CampKid subset)."""
    session = get_session()

    filter_options = json.dumps({
        "event_list": {"event_list_type": "P"},
        "all_event": {"all_event_id": [parent_id] if parent_id else []},
        "child_event": {"child_event_type": "S", "child_event_id": [event_id]},
        "status": {"status_type": "O"},
        "all_ranks": {"ranks_id": [], "rank_mem_id": []},
        "all_ages": {"age_type": "A", "age_from": "", "age_to": "", "age_date": ""},
        "program_registration": {
            "program_reg_type": "DNS", "program_reg_id": [],
            "program_reg_selected_id": [], "program_reg_unselected_id": [],
            "program_reg_option_id": [], "program_reg_status": [],
        },
        "birthday": {"bd_type": "0", "bd_days": "", "bd_start_date": "", "bd_end_date": ""},
        "source": {"source_type": "N", "source_ids": []},
    })

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

    form_data: Dict[str, Any] = {
        "draw": "1", "order[0][column]": "3", "order[0][dir]": "desc",
        "start": "0", "length": "500", "search[value]": "", "search[regex]": "false",
        "company_id": COMPANY_ID, "filter_id": "9", "filter_category": "E",
        "filter_type": "AP", "filter_options": filter_options,
        "type": "datatable", "mobile_view": "N", "from": "",
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
        return resp.json().get("data", [])
    except MystudioOTPRequired:
        raise
    except Exception as e:
        logger.error("_get_roster_raw_rows failed for event_id=%s: %s", event_id, e)
        return None


def get_camp_revenue(camp: CampRecord) -> Dict[str, Any]:
    """
    Compute revenue for one camp via N+1 calls to getParticipantRegDetails.

    For each enrolled participant:
      - Finds their paid_amount for this event_id (Active entries only)
      - Flags comped ($0), discounted (< standard price), cancelled

    Returns a dict:
      {
        "camp": CampRecord,
        "total": float,
        "enrolled": int,
        "kids": [{"name", "buyer_name", "paid_amount", "status", "cancelled"}, ...]
      }
    """
    from sites.mystudio.students import find_student_by_name, get_student_details as _get_details

    expected = _expected_camp_price(camp.title)

    rows = _get_roster_raw_rows(camp.event_id, camp.parent_id)
    if rows is None:
        return {"error": "Failed to fetch roster", "camp": camp, "expected_price": expected}

    # Deduplicate by participant_id if available in row, else by name
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        pid = str(row.get("participant_id") or row.get("p_id") or "").strip()
        sid = str(row.get("student_id") or row.get("s_id") or "").strip()
        name = row.get("participant_name", "").strip()
        key = pid if pid else name
        if key and key not in seen:
            seen[key] = {
                "participant_id": pid,
                "student_id": sid,
                "name": name,
                "buyer_name": row.get("buyer_name", "").strip(),
            }

    if not seen:
        return {"camp": camp, "total": 0.0, "enrolled": 0, "kids": [], "expected_price": expected}
    kids_data: List[Dict[str, Any]] = []

    for key, p in seen.items():
        pid = p["participant_id"]
        sid = p["student_id"]
        name = p["name"]
        buyer = p["buyer_name"]

        # If roster didn't include IDs, find them via name search
        if not (pid and sid):
            results = find_student_by_name(name)
            if not results:
                logger.warning("camp_revenue: student not found by name: %s", name)
                kids_data.append({
                    "name": name, "buyer_name": buyer,
                    "paid_amount": 0.0, "status": "not_found", "cancelled": False,
                })
                continue
            # Match by buyer last name if possible
            buyer_last = buyer.split(",")[0].strip().lower()
            match = next(
                (r for r in results if buyer_last and buyer_last in r.parent_name.lower()),
                results[0],
            )
            pid = match.participant_id
            sid = match.student_id

        details = _get_details(sid, pid)
        if not details:
            logger.warning("camp_revenue: could not fetch details for %s (pid=%s)", name, pid)
            kids_data.append({
                "name": name, "buyer_name": buyer,
                "paid_amount": 0.0, "status": "fetch_error", "cancelled": False,
            })
            continue

        event_details = details.get("reg_details", {}).get("event_details", [])

        active_entry = next(
            (e for e in event_details
             if str(e.get("event_id")) == str(camp.event_id)
             and e.get("payment_status_label") == "Active"),
            None,
        )
        cancelled_entry = next(
            (e for e in event_details
             if str(e.get("event_id")) == str(camp.event_id)
             and e.get("payment_status_label") == "Cancelled"),
            None,
        )

        paid = float(active_entry["paid_amount"]) if active_entry else 0.0
        status = active_entry["payment_status_label"] if active_entry else (
            "cancelled" if cancelled_entry else "not_found"
        )
        renamed_from = None

        # Camp rename detection: if exact match shows $0, check for another Active
        # entry on the same camp date with a positive paid_amount. This handles the
        # case where a kid was migrated to a renamed event_id — revenue lives on the
        # old entry.
        if paid == 0.0 and status == "Active":
            camp_date_str = camp.start_dt.strftime("%b %-d, %Y")  # e.g. "Jun 22, 2026"
            same_date_paid = next(
                (e for e in event_details
                 if str(e.get("event_id")) != str(camp.event_id)
                 and e.get("payment_status_label") == "Active"
                 and float(e.get("paid_amount", 0)) > 0
                 and e.get("start_date", "") == camp_date_str),
                None,
            )
            if same_date_paid:
                paid = float(same_date_paid["paid_amount"])
                renamed_from = same_date_paid.get("event_title", "")
                logger.info(
                    "camp_revenue: %s — $0 on event %s, using $%.2f from renamed event '%s'",
                    name, camp.event_id, paid, renamed_from,
                )

        kids_data.append({
            "name": name,
            "buyer_name": buyer,
            "paid_amount": paid,
            "status": status,
            "cancelled": cancelled_entry is not None,
            "renamed_from": renamed_from,
        })

    total = sum(k["paid_amount"] for k in kids_data if k["status"] == "Active")
    return {
        "camp": camp,
        "total": total,
        "enrolled": len(kids_data),
        "expected_price": expected,
        "kids": kids_data,
    }


def format_camp_revenue(result: Dict[str, Any]) -> str:
    """Format a single camp's revenue result for chat display, with gotcha callouts."""
    if "error" in result:
        return f"Could not fetch revenue: {result['error']}"

    camp = result["camp"]
    kids = result["kids"]
    total = result["total"]
    expected = result["expected_price"]

    paying     = [k for k in kids if k["paid_amount"] == expected and k["status"] == "Active"]
    comped     = [k for k in kids if k["paid_amount"] == 0.0 and k["status"] == "Active" and not k.get("renamed_from")]
    discounted = [k for k in kids if 0.0 < k["paid_amount"] < expected and k["status"] == "Active"]
    cancelled  = [k for k in kids if k.get("cancelled")]

    lines = [
        f"**{camp.title}**",
        f"📅 {camp.start_dt.strftime('%a, %b %-d')} | 💰 Revenue: **${total:,.2f}**",
        f"👥 {result['enrolled']} enrolled — "
        f"{len(paying)} full price (${expected:.0f}) · "
        f"{len(comped)} comped · {len(discounted)} discounted",
    ]

    renamed = [k for k in kids if k.get("renamed_from") and k["status"] == "Active"]
    if renamed:
        lines.append(f"\nℹ️ **Camp renames (revenue recovered from original event):**")
        for k in renamed:
            lines.append(f"  • {k['name']} — paid ${k['paid_amount']:.2f} originally for: {k['renamed_from']}")

    if comped:
        lines.append(f"\n⚠️ **Comped ($0):**")
        for k in comped:
            lines.append(f"  • {k['name']} (parent: {k['buyer_name']})")

    if discounted:
        lines.append(f"\n⚠️ **Discounted:**")
        for k in discounted:
            lines.append(f"  • {k['name']} — paid ${k['paid_amount']:.2f} vs standard ${expected:.0f}")

    if cancelled:
        lines.append(f"\nℹ️ **Cancelled (excluded from revenue):**")
        for k in cancelled:
            lines.append(f"  • {k['name']}")

    # Family pattern: same buyer, multiple kids enrolled
    from collections import defaultdict
    by_buyer: Dict[str, List[Dict]] = defaultdict(list)
    for k in kids:
        if k["status"] == "Active":
            by_buyer[k["buyer_name"]].append(k)
    families = {b: ks for b, ks in by_buyer.items() if len(ks) > 1}
    if families:
        lines.append(f"\nℹ️ **Families (same parent, multiple kids):**")
        for buyer, ks in families.items():
            parts = []
            for kk in ks:
                flag = " [comped]" if kk["paid_amount"] == 0.0 else ""
                parts.append(f"{kk['name']} ${kk['paid_amount']:.0f}{flag}")
            lines.append(f"  • {buyer}: {' + '.join(parts)}")

    lines.append(f"\n**All enrollments:**")
    for k in sorted(kids, key=lambda x: x["name"]):
        if k["status"] == "Active":
            flag = ""
            if k.get("renamed_from"):
                flag = f"  [renamed — paid under original event]"
            elif k["paid_amount"] == 0.0:
                flag = "  [comped]"
            elif k["paid_amount"] < expected:
                flag = f"  [discounted: ${k['paid_amount']:.2f}]"
            lines.append(f"  • {k['name']:<32} ${k['paid_amount']:>6.2f}{flag}")

    return "\n".join(lines)


def format_week_revenue(results: List[Dict[str, Any]]) -> str:
    """Summarize revenue across multiple camps (e.g. a full week)."""
    week_total = sum(r.get("total", 0.0) for r in results if "error" not in r)
    lines = [f"**Camp Revenue Summary — ${week_total:,.2f} total**\n"]
    for result in results:
        if "error" in result:
            lines.append(f"• {result['camp'].title[:55]} — ERROR: {result['error']}")
            continue
        camp = result["camp"]
        expected = result["expected_price"]
        comped_count = sum(1 for k in result["kids"] if k["paid_amount"] == 0.0 and k["status"] == "Active")
        lines.append(
            f"• {camp.start_dt.strftime('%a %b %-d')}  {camp.title[:50]}\n"
            f"  ${result['total']:,.2f} | {result['enrolled']} enrolled"
            + (f" | {comped_count} comped" if comped_count else "")
        )
    return "\n".join(lines)


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
