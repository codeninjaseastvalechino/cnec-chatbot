"""
run_milestone1.py
=================
CLI entry point for Milestone 1: LineLeader login + today's session pull + reschedule.

Run from the project root:
    python3 run_milestone1.py

What it does:
  1. Checks for a cached Bearer token (skips login if still valid)
  2. If no valid token: launches Playwright, logs in, extracts Bearer token
  3. Calls the ChildCareCRM API directly with the token
  4. Enriches sessions with child names, ages, and GBS vs JR GBS type
  5. Displays today's GBS Tours in a formatted table
  6. Prompts to reschedule a tour (optional)
"""

import asyncio
import sys
from datetime import date, datetime
from typing import List, Optional

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

from sites.lineleader.auth import get_bearer_token
from sites.lineleader.schedules import (
    get_todays_sessions,
    enrich_sessions_with_children,
    reschedule_tour,
    GBSSession,
)
from core.logger import get_logger

logger = get_logger(__name__)
console = Console()


async def main() -> None:
    console.rule("[bold cyan]CNEC Chatbot — Milestone 1[/bold cyan]")
    console.print(
        f"[dim]Fetching sessions for {date.today().strftime('%A, %B %d, %Y')}[/dim]\n"
    )

    try:
        # ── Step 1: Authenticate ──────────────────────────────────────────────
        console.print("[yellow]→[/yellow] Authenticating with LineLeader...")
        bearer_token = await get_bearer_token()
        console.print("[green]✓[/green] Authenticated\n")

        # ── Step 2: Fetch today's GBS Tours ──────────────────────────────────
        console.print("[yellow]→[/yellow] Fetching today's GBS Tours...")
        sessions = get_todays_sessions(bearer_token)
        console.print(f"[green]✓[/green] Done — {len(sessions)} tour(s) found\n")

        # ── Step 2b: Enrich with child names, ages, tour type ─────────────────
        if sessions:
            console.print("[yellow]→[/yellow] Looking up child names...")
            enrich_sessions_with_children(bearer_token, sessions)
            console.print("[green]✓[/green] Ready\n")

        _display_sessions(sessions)

        if not sessions:
            return

        # ── Step 3: Offer to reschedule ───────────────────────────────────────
        console.print()
        if not Confirm.ask("[yellow]Reschedule a tour?[/yellow]", default=False):
            return

        # Pick which tour
        session = _pick_session(sessions)
        if session is None:
            return

        # Pick new date and time
        new_dt_str = Prompt.ask(
            f"  New date/time for [bold]{session.student_name}[/bold] "
            f"(e.g. [dim]3 PM[/dim], [dim]Friday at 3 PM[/dim], [dim]tomorrow at 5 PM[/dim])"
        )
        new_local_dt = _parse_datetime(new_dt_str)
        if new_local_dt is None:
            console.print(f"[red]Could not parse:[/red] {new_dt_str!r}")
            console.print("[dim]Try: '3 PM', 'Friday at 3 PM', 'tomorrow at 5 PM'[/dim]")
            return

        # Confirm before writing
        same_day = new_local_dt.date() == session.start_time.astimezone().date()
        date_label = (
            "today" if same_day
            else new_local_dt.strftime("%A, %B %-d")
        )
        console.print(
            f"\n  [bold]Confirm:[/bold] Move [cyan]{session.student_name}[/cyan]"
            f" from [bold]{session.time_display()}[/bold]"
            f" → [bold]{new_local_dt.strftime('%-I:%M %p')}[/bold] {date_label}"
        )
        if not Confirm.ask("  Proceed?", default=False):
            console.print("[dim]Cancelled — no changes made.[/dim]")
            return

        # Execute reschedule
        console.print("\n[yellow]→[/yellow] Rescheduling...")
        success, message = reschedule_tour(bearer_token, session, new_local_dt)

        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗ Reschedule failed:[/red] {message}")

    except EnvironmentError as e:
        console.print(f"\n[bold red]Configuration error:[/bold red] {e}")
        console.print("[dim]Check your .env file against .env.example[/dim]")
        sys.exit(1)

    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    except Exception as e:
        logger.exception("Unexpected error in run_milestone1")
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
        console.print("[dim]Check logs/cnec_chatbot.log for full details[/dim]")
        sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _display_sessions(sessions: List[GBSSession]) -> None:
    """Display GBS Tours in a formatted table."""
    if not sessions:
        console.print("[bold yellow]No GBS Tours found for today.[/bold yellow]")
        return

    table = Table(
        title=f"Today's GBS Tours — {date.today().strftime('%A, %B %d, %Y')}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Time", style="bold", min_width=10)
    table.add_column("Student", min_width=22)
    table.add_column("Tour Type", style="cyan", min_width=12)
    table.add_column("Child", style="dim", min_width=24)

    for i, session in enumerate(sessions, start=1):
        table.add_row(
            str(i),
            session.time_display(),
            session.student_name,
            session.tour_type,
            ", ".join(session.child_display) if session.child_display else "",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(sessions)} tour(s)[/dim]")


def _pick_session(sessions: List[GBSSession]) -> Optional[GBSSession]:
    """
    Prompt user to pick a tour by number, or match by name.
    Matches against guardian name AND child names (case-insensitive substring).
    """
    if len(sessions) == 1:
        console.print(
            f"  [dim]Only one tour — selecting[/dim] [bold]{sessions[0].student_name}[/bold]"
        )
        return sessions[0]

    console.print("  Which tour? Enter a number or part of the name:")
    for i, s in enumerate(sessions, start=1):
        children_str = (
            f" [dim]— kids: {', '.join(s.child_names)}[/dim]"
            if s.child_names else ""
        )
        console.print(
            f"    [dim]{i}.[/dim] {s.student_name} [dim]({s.time_display()})[/dim]{children_str}"
        )

    choice = Prompt.ask("  Selection").strip()

    # Try numeric
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
        console.print(f"[red]No tour #{choice}[/red]")
        return None

    # Try name match — guardian name OR any child name (case-insensitive substring)
    matches = [s for s in sessions if _name_matches(choice, s)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        console.print(f"[yellow]Multiple matches for {choice!r} — be more specific.[/yellow]")
        return None

    console.print(f"[red]No tour matching {choice!r}[/red]")
    return None


def _name_matches(query: str, session: GBSSession) -> bool:
    """Return True if query matches the guardian name or any child name."""
    q = query.lower()
    if q in session.student_name.lower():
        return True
    return any(q in child.lower() for child in session.child_names)


def _parse_datetime(dt_str: str) -> Optional[datetime]:
    """
    Parse a natural date+time string into a timezone-aware local datetime.

    Supported formats:
        "3 PM"               → today at 3:00 PM
        "8:30 PM"            → today at 8:30 PM
        "Friday at 3 PM"     → upcoming Friday at 3:00 PM
        "tomorrow at 5 PM"   → tomorrow at 5:00 PM
        "today at 3 PM"      → today at 3:00 PM
        "May 29 at 3 PM"     → May 29 (current year) at 3:00 PM
    """
    import re
    from datetime import timedelta

    s = dt_str.strip()

    # Split on "at" to separate date and time parts
    if " at " in s.lower():
        parts = re.split(r"\s+at\s+", s, maxsplit=1, flags=re.IGNORECASE)
        date_part = parts[0].strip()
        time_part = parts[1].strip()
    else:
        date_part = "today"
        time_part = s

    # Resolve date
    target_date = _resolve_date(date_part)
    if target_date is None:
        return None

    # Resolve time
    t = _resolve_time(time_part)
    if t is None:
        return None

    local_dt = datetime(
        target_date.year, target_date.month, target_date.day,
        t.hour, t.minute, 0
    ).astimezone()
    return local_dt


def _resolve_date(date_str: str) -> Optional[date]:
    """Resolve a date string like 'Friday', 'tomorrow', 'today', 'May 29'."""
    from datetime import timedelta
    import calendar

    s = date_str.strip().lower()
    today = date.today()

    if s in ("today", ""):
        return today

    if s == "tomorrow":
        return today + timedelta(days=1)

    # Day of week: Monday–Sunday (full or 3-letter)
    day_names = list(calendar.day_name)        # Monday, Tuesday, ...
    day_abbrs = list(calendar.day_abbr)        # Mon, Tue, ...
    for i, (full, abbr) in enumerate(zip(day_names, day_abbrs)):
        if s in (full.lower(), abbr.lower()):
            days_ahead = (i - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # "Monday" when today IS Monday → next Monday
            return today + timedelta(days=days_ahead)

    # "May 29", "May 29th", etc.
    for fmt in ("%B %d", "%b %d", "%m/%d", "%m-%d"):
        try:
            parsed = datetime.strptime(s, fmt)
            target = date(today.year, parsed.month, parsed.day)
            if target < today:
                target = date(today.year + 1, parsed.month, parsed.day)
            return target
        except ValueError:
            continue

    return None


def _resolve_time(time_str: str) -> Optional[datetime]:
    """Parse a time string like '3 PM', '8:30 PM', '15:00'."""
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"):
        try:
            return datetime.strptime(time_str.strip().upper(), fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    asyncio.run(main())
