"""
sites/lineleader/schedules.py
==============================
Fetches today's GBS sessions from LineLeader / ChildCareCRM (Site 2).

Strategy — direct API calls with Bearer token:
  1. Get a valid Bearer token from auth.py (login if needed)
  2. Call live.childcarecrm.com/api/v3/action-items directly with requests
  3. Filter results to Tours only (all Tours are GBS Tours)
  4. Enrich with child names, ages, and tour type (GBS vs JR GBS)
  5. Return as typed GBSSession objects

API endpoint confirmed via live site inspection:
  GET /api/v3/action-items
    ?tasks_dash_mode=true
    &task_dash_dates[0]=today
    &org_id=101178
    &include_meetings=true

Response structure confirmed:
  {
    "items": [
      {
        "item_type": "task",
        "item_id": "1995970",
        "guardian_first_name": "Keadrick",
        "guardian_last_name": "Washington",
        "display_type": "Tour",         ← we filter on this
        "date_time": "2026-05-26T22:00:00+00:00",
        "description": "JR GBS",        ← used to detect JR GBS
        "task_type_id": 89,
        "task_group_id": 4
      }
    ],
    "counts": {"today": 7, "future": 25, ...}
  }
"""

import requests
from datetime import date, datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GBSSession:
    """Represents a single scheduled GBS Tour from LineLeader."""
    student_name: str
    start_time: datetime
    display_type: str           # always "Tour" after filtering
    description: str = ""       # free-text notes field ("GBS", "JR GBS", or blank)
    location_name: str = ""
    item_id: str = ""
    assignee_name: str = ""
    tour_type: str = "GBS"      # "GBS" or "JR GBS" — set from description or family custom_values
    family_id: str = ""         # populated by enrich_sessions_with_children()
    child_names: List[str] = field(default_factory=list)        # plain names for matching
    child_display: List[str] = field(default_factory=list)      # "Name (Xy)" for display
    raw_data: dict = field(default_factory=dict, repr=False)

    def time_display(self) -> str:
        """Human-readable local time string, e.g. '3:00 PM'"""
        local_dt = self.start_time.astimezone()
        return local_dt.strftime("%-I:%M %p")

    def date_display(self) -> str:
        """Human-readable date string, e.g. 'Monday, May 26'"""
        local_dt = self.start_time.astimezone()
        return local_dt.strftime("%A, %B %d")


# ---------------------------------------------------------------------------
# Main public functions
# ---------------------------------------------------------------------------

def get_todays_sessions(bearer_token: str) -> List[GBSSession]:
    """
    Fetch all GBS Tours scheduled for today from the ChildCareCRM API.

    Returns:
        List of GBSSession objects sorted by start time.
    """
    today = date.today()
    logger.info("Fetching today's sessions for %s", today.isoformat())

    raw_items = _fetch_action_items(bearer_token, date_filter="today")
    if raw_items is None:
        return []

    sessions = _parse_items(raw_items, today)
    sessions.sort(key=lambda s: s.start_time)

    logger.info("Found %d session(s) for today", len(sessions))
    return sessions


def get_sessions_for_date(bearer_token: str, target_date: date) -> List[GBSSession]:
    """
    Fetch GBS Tours for a specific date.
    Uses 'future' filter then filters client-side to the target date.
    """
    logger.info("Fetching sessions for %s", target_date.isoformat())

    raw_items = _fetch_action_items(bearer_token, date_filter="future")
    if raw_items is None:
        return []

    sessions = _parse_items(raw_items, target_date)
    sessions.sort(key=lambda s: s.start_time)

    logger.info("Found %d session(s) for %s", len(sessions), target_date.isoformat())
    return sessions


# ---------------------------------------------------------------------------
# Family enrichment — child names, ages, tour type fallback
# ---------------------------------------------------------------------------

def _calculate_age(dob_str: str) -> Optional[int]:
    """Calculate age in years from an ISO date string (e.g. '2021-12-09')."""
    try:
        from datetime import date as _date
        dob = _date.fromisoformat(dob_str)
        today = _date.today()
        return today.year - dob.year - (
            (today.month, today.day) < (dob.month, dob.day)
        )
    except (ValueError, TypeError):
        return None


def fetch_family(bearer_token: str, family_id: str) -> Optional[Dict[str, Any]]:
    """
    GET /api/v3/families/{family_id}
    Returns full family record including children[].
    """
    url = f"{settings.CHILDCARECRM_API_URL}/families/{family_id}"
    headers = {
        "Authorization": bearer_token,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://my.childcarecrm.com",
        "Referer": "https://my.childcarecrm.com/",
        "x-ui-request": "true",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logger.debug("Fetched family %s", family_id)
        return response.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch family %s: %s", family_id, e)
        return None


def enrich_sessions_with_children(
    bearer_token: str,
    sessions: List[GBSSession],
) -> None:
    """
    For each session, look up the family to get child names, ages, and
    confirm/correct the tour type (GBS vs JR GBS).

    Populates session.family_id, session.child_names, session.child_display,
    and may update session.tour_type in-place.

    Lookup chain: GET /tasks/{item_id} → family.id → GET /families/{id} → children[]

    Adds ~2 API calls per session. Fine for 3-5 tours/day.
    """
    for session in sessions:
        try:
            task = fetch_task(bearer_token, session.item_id)
            if not task:
                continue

            family_val = task.get("family")
            family_id = (
                str(family_val["id"]) if isinstance(family_val, dict)
                else str(family_val) if family_val else None
            )
            if not family_id:
                continue

            session.family_id = family_id

            family_data = fetch_family(bearer_token, family_id)
            if not family_data:
                continue

            # Build child names and display strings
            children = family_data.get("children", [])
            session.child_names = []
            session.child_display = []

            for c in children:
                first = c.get("first_name", "").strip()
                last = c.get("last_name", "").strip()
                name = f"{first} {last}".strip()
                if not name:
                    continue

                session.child_names.append(name)

                age = _calculate_age(c.get("date_of_birth"))
                age_str = f" ({age}y)" if age is not None else ""
                session.child_display.append(f"{name}{age_str}")

            if session.child_names:
                logger.debug(
                    "Session %s — children: %s",
                    session.item_id, session.child_display,
                )

            # Fallback: if tour_type is still "GBS" but family has JUNIOR custom value → JR GBS
            # Catches cases where description is blank but lead path is JUNIOR
            if session.tour_type == "GBS":
                custom_groups = family_data.get("custom_values", [])
                for group in custom_groups:
                    for cv in group.get("custom_values", []):
                        if cv.get("values", {}).get("value", "").upper() == "JUNIOR":
                            session.tour_type = "JR GBS"
                            logger.debug(
                                "Session %s — tour_type set to JR GBS via family custom_value",
                                session.item_id,
                            )
                            break

        except Exception as e:
            logger.warning(
                "Could not enrich session %s with children: %s",
                session.item_id, e,
            )


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _fetch_action_items(
    bearer_token: str,
    date_filter: str = "today",
    limit: int = 100,
) -> Optional[List[Dict[str, Any]]]:
    """
    Call the ChildCareCRM action-items API and return the raw item list.

    Args:
        bearer_token: Valid Bearer token.
        date_filter: "today", "future", or "past".
        limit: Max results to return.

    Returns:
        List of raw item dicts, or None if the request fails.
    """
    url = f"{settings.CHILDCARECRM_API_URL}/action-items"

    params = {
        "offset": 0,
        "limit": limit,
        "tasks_dash_mode": "true",
        "org_id": settings.LINELEADER_ORG_ID,
        "only_mine": "false",
        "task_dash_dates[0]": date_filter,
        "include_meetings": "true",
        "search": "",
        "sort_keys[0]": "datetime",
        "sort_dir[0]": "asc",
    }

    headers = {
        "Authorization": bearer_token,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://my.childcarecrm.com",
        "Referer": "https://my.childcarecrm.com/",
        "x-ui-request": "true",
    }

    logger.debug("Calling action-items API with date_filter=%s", date_filter)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])
        counts = data.get("counts", {})

        logger.debug("API returned %d items (counts: %s)", len(items), counts)
        return items

    except requests.HTTPError as e:
        if e.response.status_code == 401:
            logger.error(
                "API returned 401 Unauthorized — Bearer token has expired or is invalid. "
                "Delete %s to force a fresh login.",
                settings.LINELEADER_TOKEN_FILE,
            )
        else:
            logger.error("API request failed with status %s: %s", e.response.status_code, e)
        return None

    except requests.RequestException as e:
        logger.error("API request failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_items(
    items: List[Dict[str, Any]],
    target_date: date,
) -> List[GBSSession]:
    """Parse raw API item dicts into GBSSession objects, filtered to target_date."""
    sessions = []
    for item in items:
        try:
            session = _parse_single_item(item, target_date)
            if session is not None:
                sessions.append(session)
        except Exception as e:
            logger.warning("Could not parse item %s: %s", item.get("item_id"), e)
    return sessions


def _parse_single_item(
    item: Dict[str, Any],
    target_date: date,
) -> Optional[GBSSession]:
    """
    Parse one API item into a GBSSession.
    Returns None if not on target_date or not a Tour.
    """
    # Parse datetime — format confirmed: "2026-05-26T22:00:00+00:00"
    date_time_raw = item.get("date_time", "")
    if not date_time_raw:
        return None

    try:
        start_time = datetime.fromisoformat(date_time_raw)
    except ValueError:
        logger.debug("Could not parse date_time: %s", date_time_raw)
        return None

    # Filter to target date (local time)
    local_dt = start_time.astimezone()
    if local_dt.date() != target_date:
        return None

    # Only care about Tours — all Tours are GBS Tours
    display_type = item.get("display_type", "")
    description = item.get("description", "")
    if display_type != "Tour":
        return None

    # Determine tour type from description
    # "JR GBS" if description contains "JR", otherwise default to "GBS"
    # May be overridden during enrichment if description is blank
    tour_type = "JR GBS" if "JR" in description.upper() else "GBS"

    # Build names
    first = item.get("guardian_first_name", "").strip()
    last = item.get("guardian_last_name", "").strip()
    student_name = f"{first} {last}".strip() or "Unknown"

    a_first = item.get("assignee_first_name", "").strip()
    a_last = item.get("assignee_last_name", "").strip()
    assignee_name = f"{a_first} {a_last}".strip()

    logger.debug(
        "Parsed item %s: guardian='%s %s', assignee='%s %s', student_name='%s'",
        str(item.get("item_id")), first, last, a_first, a_last, student_name
    )

    return GBSSession(
        student_name=student_name,
        start_time=start_time,
        display_type=display_type,
        description=description,
        tour_type=tour_type,
        location_name=item.get("location_name", ""),
        item_id=str(item.get("item_id", "")),
        assignee_name=assignee_name,
        raw_data=item,
    )


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------

def fetch_task(bearer_token: str, item_id: str) -> Optional[Dict[str, Any]]:
    """
    GET /api/v3/tasks/{item_id}
    Fetch the full task object needed before a PUT update.
    """
    url = f"{settings.CHILDCARECRM_API_URL}/tasks/{item_id}"
    headers = {
        "Authorization": bearer_token,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://my.childcarecrm.com",
        "Referer": "https://my.childcarecrm.com/",
        "x-ui-request": "true",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logger.debug("Fetched task %s", item_id)
        return response.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch task %s: %s", item_id, e)
        return None


def reschedule_tour(
    bearer_token: str,
    session: GBSSession,
    new_local_dt: datetime,
) -> Tuple[bool, str]:
    """
    Reschedule a GBS Tour to a new date/time.

    Args:
        bearer_token: Valid Bearer token.
        session:      The GBSSession to reschedule (must have item_id).
        new_local_dt: New date/time in local time (timezone-aware or naive local).

    Returns:
        (success: bool, message: str)

    NOTE: Caller is responsible for showing confirmation before calling this.
    This function writes to the live site immediately.
    """
    # Convert local time → UTC
    if new_local_dt.tzinfo is None:
        new_local_dt = new_local_dt.astimezone()
    new_utc = new_local_dt.astimezone(timezone.utc)
    new_utc_str = new_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: GET full current task object
    logger.info("Fetching full task object for item_id=%s", session.item_id)
    task = fetch_task(bearer_token, session.item_id)
    if task is None:
        return False, "Could not fetch task from API."

    logger.debug("Raw GET response for task %s: %s", session.item_id, task)

    # Step 2: Build normalized PUT payload
    # GET returns expanded objects (family: {id, ...}) but PUT expects plain IDs
    payload = _build_put_payload(task, new_utc_str)
    logger.info("Rescheduling task %s → %s (UTC)", session.item_id, new_utc_str)

    # Step 3: PUT modified task back
    url = f"{settings.CHILDCARECRM_API_URL}/tasks/{session.item_id}"
    headers = {
        "Authorization": bearer_token,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://my.childcarecrm.com",
        "Referer": "https://my.childcarecrm.com/",
        "x-ui-request": "true",
    }

    try:
        response = requests.put(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info("Task %s rescheduled successfully", session.item_id)
        return True, f"Rescheduled to {new_local_dt.strftime('%-I:%M %p')}."
    except requests.HTTPError as e:
        msg = f"API returned {e.response.status_code}: {e.response.text[:300]}"
        logger.error("Reschedule failed for task %s: %s", session.item_id, msg)
        return False, msg
    except requests.RequestException as e:
        logger.error("Reschedule request failed: %s", e)
        return False, str(e)


def _build_put_payload(
    task: Dict[str, Any],
    new_utc_str: str,
) -> Dict[str, Any]:
    """
    Build a clean PUT payload from a GET response.

    The GET endpoint returns expanded objects for relational fields
    (e.g. family → {id, name, ...}) but PUT expects plain integer IDs.
    This function flattens those back to IDs.
    """
    def _id(val: Any) -> Any:
        """Extract .id from an object, or return the value as-is."""
        if isinstance(val, dict):
            return val.get("id")
        return val

    return {
        "id":                   _id(task.get("id")),
        "family":               _id(task.get("family")),
        "type":                 _id(task.get("type")),
        "assigned_to_staff":    _id(task.get("assigned_to_staff")),
        "assigned_by_user_id":  _id(task.get("assigned_by_user_id")),
        "due_date_time":        new_utc_str,
        "description":          task.get("description") or "",
        "is_completed":         task.get("is_completed", False),
        "completed_by_user_id": _id(task.get("completed_by_user_id")),
        "completed_date_time":  task.get("completed_date_time"),
        "result_type":          _id(task.get("result_type")),
        "result_description":   task.get("result_description") or "",
        "is_canceled":          task.get("is_canceled", False),
        "duration":             task.get("duration", 30),
    }
