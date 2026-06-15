"""
ChatbotEngine: LLM-agnostic chatbot with function calling.

Supports multiple LLM providers (Claude, Ollama) via provider abstraction.

Handles:
- Tool definitions for Milestone 1 (LineLeader GBS Tours)
- LLM API calls with tool use (provider-agnostic)
- Tool execution (calling Milestone 1 functions)
- Multi-turn conversation with automatic tool handling
"""

import json
import os
import asyncio
import time
from pathlib import Path
from typing import Any
from dotenv import dotenv_values

# Load .env file and manually set environment variables
env_path = Path(__file__).parent / ".env"
env_vars = dotenv_values(env_path)
for key, value in env_vars.items():
    if value is not None:
        os.environ[key] = value

from core.logger import get_logger
from config.settings import settings
from llm_provider import get_provider
from analytics import QueryAnalytics
from sites.lineleader.auth import get_bearer_token
from sites.lineleader.schedules import (
    get_todays_sessions,
    enrich_sessions_with_children,
    reschedule_tour,
)
from sites.mystudio.schedules import get_todays_appointments
from sites.mystudio.auth import MystudioOTPRequired, complete_otp_login
from sites.mystudio.camps import (
    get_all_upcoming_camps,
    get_camp_roster,
    format_camps_summary,
    format_camp_roster,
)
from format_tours import format_unified_schedule
from export_tours import create_unified_excel_file

logger = get_logger(__name__)


class ChatbotEngine:
    """Handles conversations with any LLM provider, including tool execution."""

    def __init__(self, provider=None):
        self.provider = provider or get_provider()
        self.conversation_history = []
        self.bearer_token = None
        self._awaiting_mystudio_otp = False
        self._analytics = QueryAnalytics()
        self._last_camp_data = None    # Cache for Excel export: {"camps": [...], "rosters": {...}}
        self._last_schedule_fetched = False   # True when a schedule tool ran this turn
        self._last_any_tool_ran = False       # True when any tool ran this turn
        self._last_export_label = None        # Human label for what's cached: "full_schedule", "gbs_tours", "camps"

        # Tool registry: name → {definition, handler}
        # Add new tools via _register() in _register_tools() only
        self._tools = {}
        self._register_tools()

    # Friendly status messages shown to user while tools run
    _TOOL_STATUS = {
        "get_gbs_tours":            "Fetching GBS tours from LineLeader...",
        "reschedule_tour":          "Rescheduling tour...",
        "get_full_schedule":        "Fetching schedule from LineLeader and MyStudio...",
        "lookup_student":           "Looking up student in MyStudio...",
        "cancel_student_session":   "Cancelling session in MyStudio...",
        "move_student_session":     "Rescheduling session in MyStudio...",
        "get_camp_details":         "Fetching camp info from MyStudio...",
    }

    def chat(self, user_message: str, status_callback=None, user_name: str = "Unknown") -> str:
        """
        Send a message to the LLM and handle tool calls.

        status_callback: optional callable(str) called with status updates during tool execution.
        """
        # If waiting for MyStudio OTP, handle before passing to LLM
        if self._awaiting_mystudio_otp:
            result = self._handle_otp_submission(user_message)
            # Add to conversation history so Claude knows OTP was resolved
            # (without this, Claude sees the last assistant message as "🔐 OTP needed"
            # and keeps asking for it instead of calling tools)
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": result})
            return result

        self._last_schedule_fetched = False
        self._last_any_tool_ran = False
        logger.info("User query: %s", user_message[:120])
        request_start = time.monotonic()
        _tracker = self._analytics.start_query(user_message, query_type="natural_language", user=user_name)

        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        while True:
            response_data = self.provider.call(
                messages=self.conversation_history,
                system_prompt=self._get_system_prompt(),
                tools=self._get_tools(),
            )

            # Check if LLM wants to use a tool (may be multiple in one response)
            if response_data["type"] == "tool_use":
                tool_calls = response_data["content"]  # always a list now

                # Add assistant turn with all tool_use blocks first
                raw_response = response_data.get("raw")
                if raw_response and hasattr(raw_response, "content"):
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": raw_response.content
                    })
                else:
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"[Using tools: {[t['name'] for t in tool_calls]}]"
                    })

                # Execute every tool call and collect results
                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_input = tool_call["input"]
                    tool_id = tool_call["id"]

                    logger.info("Tool call: %s | inputs: %s", tool_name, json.dumps(tool_input))

                    if status_callback:
                        status_callback(self._TOOL_STATUS.get(tool_name, f"Running {tool_name}..."))

                    tool_start = time.monotonic()
                    tool_result = self._execute_tool(tool_name, tool_input)
                    tool_elapsed = time.monotonic() - tool_start
                    logger.info("Tool done: %s | %.1fs | result: %d chars", tool_name, tool_elapsed, len(tool_result))
                    _tracker.record_tool(tool_name, tool_input, tool_elapsed)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_result,
                    })

                # Add all results in one user message — Anthropic requires this
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                continue

            # LLM is done — extract text response
            elif response_data["type"] == "end_turn":
                text = response_data["content"]
                total_elapsed = time.monotonic() - request_start
                logger.info("Request complete | total: %.1fs | response: %d chars", total_elapsed, len(text or ""))
                _tracker.finish(response_chars=len(text or ""))

                # Add assistant's response to history
                # For Claude: use the raw response blocks to maintain conversation structure
                # For Ollama: use the text content
                raw_response = response_data.get("raw")
                if raw_response and hasattr(raw_response, "content"):
                    # Claude response - use original content blocks
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": raw_response.content
                    })
                else:
                    # Ollama or other providers - use text content
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": text
                    })

                return text if text else "No response generated."

            else:
                # Unexpected response type
                logger.warning("Unexpected response type: %s", response_data["type"])
                return f"Unexpected response: {response_data['type']}"

    def _get_system_prompt(self) -> str:
        """System prompt: identity, safety, tone only."""
        from datetime import date
        today = date.today()
        today_str = today.strftime("%A, %B %-d, %Y")  # e.g. "Thursday, June 4, 2026"
        return f"""You are an operations assistant for Code Ninjas Eastvale Chino.
You help staff manage daily schedules, student appointments, and tours
by querying the center's systems and taking action on their behalf.

Today is {today_str}. Use this as your anchor when resolving relative date
references like "today", "tomorrow", "Friday", "next week", etc.

You have access to tools that connect to LineLeader (tours) and MyStudio
(student classes). Use whichever tools are appropriate to fully answer
the user's question — you may call multiple tools if needed.

SAFETY RULES — non-negotiable:
- Never reschedule, cancel, or modify anything without first showing the
  user exactly what you're about to do and receiving explicit confirmation.
- If a request is ambiguous (e.g. two students with the same name),
  stop and ask before taking any action.
- If a tool returns an error or unexpected data, report it — do not guess
  or proceed.

Be concise and friendly. Staff are busy — get to the point."""

    def _register_tools(self):
        """
        Register all available tools.
        To add a new tool: add a _register() call here + a handler method below.
        Nothing else needs to change.
        """
        self._register(
            name="get_full_schedule",
            description=(
                "Fetches the complete schedule for a specified date: both GBS tours "
                "from LineLeader AND enrolled student class sessions from MyStudio "
                "(CREATE CODING, SCRATCH PLUS, JR, etc.), merged in chronological order. "
                "Use this whenever the user asks about a date's schedule, what's happening "
                "then, students coming in, or anything not limited to prospective family "
                "tours only. If no date is specified, defaults to today."
            ),
            parameters={
                "date_str": {
                    "type": "string",
                    "description": "The date exactly as the user said it (e.g. 'today', 'tomorrow', 'Friday', 'June 9th', 'Monday June 8th'). Do not resolve — pass the raw phrase. Omit if no date was mentioned.",
                }
            },
            handler=self._handle_get_full_schedule,
        )
        self._register(
            name="get_gbs_tours",
            description=(
                "Fetches GBS tour appointments from LineLeader for a specified date. "
                "These are visits by prospective families who have not enrolled yet — "
                "not current students. Returns guardian name, child name and age, "
                "tour type (GBS or JR GBS), scheduled time, and assigned staff member. "
                "If no date is specified, defaults to today."
            ),
            parameters={
                "date_str": {
                    "type": "string",
                    "description": "The date exactly as the user said it (e.g. 'today', 'tomorrow', 'Friday', 'June 9th', 'Monday June 8th'). Do not resolve — pass the raw phrase. Omit if no date was mentioned.",
                }
            },
            handler=self._handle_get_gbs_tours,
        )
        self._register(
            name="get_upcoming_gbs_tours",
            description=(
                "Fetches the next upcoming GBS tours from LineLeader, starting from a given date. "
                "Use this when the user asks about future tours without specifying an exact date — "
                "e.g. 'what tours do we have coming up?', 'any GBS after the 11th?', "
                "'what's the next tour?', 'tours this week'. "
                "Do NOT use this for a specific date — use get_gbs_tours instead."
            ),
            parameters={
                "after_date_str": {
                    "type": "string",
                    "description": "The date phrase exactly as the user said it (e.g. 'the 11th', 'June 11th', 'next Monday', 'today'). Do not resolve — pass the raw phrase. Omit if the user didn't mention a start date.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of tours to return. Defaults to 5.",
                },
            },
            handler=self._handle_get_upcoming_gbs_tours,
        )
        self._register(
            name="reschedule_tour",
            description=(
                "Reschedules a GBS tour to a new date and time. "
                "Requires the tour ID and the new datetime. "
                "Always confirm details with the user before calling this tool."
            ),
            parameters={
                "tour_id": {
                    "type": "string",
                    "description": "The tour ID to reschedule",
                },
                "date_str": {
                    "type": "string",
                    "description": "The date exactly as the user said it (e.g. 'Friday', 'June 6th', 'Friday June 6th', 'tomorrow', 'next Tuesday'). Do not resolve or interpret — pass the raw phrase.",
                },
                "time_str": {
                    "type": "string",
                    "description": "The time exactly as the user said it (e.g. '10am', '2:30 PM', '14:00'). Do not convert — pass the raw phrase.",
                },
            },
            handler=self._handle_reschedule_tour,
        )
        self._register(
            name="cancel_student_session",
            description=(
                "Cancels a student's scheduled MyStudio class session. "
                "Can cancel a single session on a specific date, or cancel that session "
                "and all future recurring sessions. "
                "Always call with confirmed=false first to show the user what will be cancelled, "
                "then call again with confirmed=true only after the user explicitly agrees."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "Student name exactly as the user said it.",
                },
                "date_str": {
                    "type": "string",
                    "description": "The date of the session to cancel, exactly as the user said it (e.g. 'June 27', 'Friday', 'the 27th'). Do not resolve — pass the raw phrase.",
                },
                "cancel_all_future": {
                    "type": "boolean",
                    "description": "True if the user wants to cancel this session AND all future recurring sessions. False (default) to cancel only the single session on that date.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Pass false (default) to preview the cancellation. Pass true only after the user has explicitly confirmed.",
                },
            },
            handler=self._handle_cancel_student_session,
        )
        self._register(
            name="move_student_session",
            description=(
                "Moves a student's MyStudio class session to a new date and time. "
                "Can move a single occurrence, or move all future recurring sessions. "
                "Always call with confirmed=false first to show the user what will change, "
                "then call again with confirmed=true only after the user explicitly agrees."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "Student name exactly as the user said it.",
                },
                "from_date_str": {
                    "type": "string",
                    "description": "The date of the session to move, exactly as the user said it. Do not resolve — pass the raw phrase.",
                },
                "to_date_str": {
                    "type": "string",
                    "description": "The target date, exactly as the user said it. Do not resolve — pass the raw phrase.",
                },
                "to_time_str": {
                    "type": "string",
                    "description": "The target time, exactly as the user said it (e.g. '2pm', '2:00 PM'). Do not resolve — pass the raw phrase.",
                },
                "move_all_future": {
                    "type": "boolean",
                    "description": "True if the user wants to move all future recurring sessions. False (default) to move only the single session.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Pass false (default) to preview the move. Pass true only after the user has explicitly confirmed.",
                },
            },
            handler=self._handle_move_student_session,
        )
        self._register(
            name="lookup_student",
            description=(
                "Look up a student by name in MyStudio. Returns their belt rank, "
                "parent contact info, attendance this week, attendance over the last "
                "14 and 30 days, and upcoming scheduled sessions. "
                "Use when staff ask about a specific student — e.g. 'how many days has "
                "Henry come this week?', 'what's Journei's upcoming schedule?', "
                "'look up Veshant'."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "The student name exactly as the user said it. Can be first name only, full name, or partial.",
                },
            },
            handler=self._handle_lookup_student,
        )
        self._register(
            name="get_camp_details",
            description=(
                "Fetch upcoming camp details from MyStudio. "
                "Returns camp names, dates, enrollment counts, and optionally the roster of enrolled kids. "
                "Use when staff ask about camps — e.g. 'what camps are coming up?', "
                "'how many kids are in the Minecraft camp?', 'who's enrolled in the June 15 camp?', "
                "'show me the summer camp schedule', 'list all camps this week'. "
                "Pass camp_name to filter by a specific camp title (fuzzy match). "
                "Use week_of_date_str when user says 'week of X' or 'that week' — finds all camps in the Mon–Fri week containing that date. "
                "Use after_date_str for open-ended 'after X' or 'from X' filters. "
                "Pass include_roster=true only when staff explicitly ask who is enrolled."
            ),
            parameters={
                "week_of_date_str": {
                    "type": "string",
                    "description": (
                        "Use when the user asks about a specific week, e.g. 'week of July 17', "
                        "'camps that week', 'next week'. Pass the raw date phrase — Python will find "
                        "the Monday of the week containing that date and return only camps that week. "
                        "Takes precedence over after_date_str when both are set."
                    ),
                },
                "after_date_str": {
                    "type": "string",
                    "description": (
                        "Optional. Pass the raw date phrase from the user (e.g. 'today', "
                        "'June 22') to filter camps starting on or after that date. "
                        "Leave empty to return all upcoming camps."
                    ),
                },
                "camp_name": {
                    "type": "string",
                    "description": (
                        "Optional. Camp title keyword to filter by, e.g. 'Minecraft', 'JR', 'PM CAMP'. "
                        "Leave empty to return all camps."
                    ),
                },
                "include_roster": {
                    "type": "boolean",
                    "description": (
                        "Set to true only when staff explicitly ask who is enrolled in a specific camp. "
                        "Triggers an extra API call per matching camp. "
                        "Requires camp_name to be set so we know which camp's roster to fetch."
                    ),
                },
            },
            handler=self._handle_get_camp_details,
        )

    def _register(self, name: str, description: str, parameters: dict, handler):
        """
        Register a single tool.

        name        — tool name Claude will use to call it
        description — what this tool does and when to use it (Claude reads this)
        parameters  — dict of parameter_name → {type, description} for required inputs
        handler     — the method to call when this tool is invoked
                      signature: handler(tool_input: dict) -> str
        """
        required_params = list(parameters.keys())
        self._tools[name] = {
            "definition": {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": parameters,
                    "required": required_params,
                },
            },
            "handler": handler,
        }

    def _get_tools(self) -> list:
        """Return tool definitions for the LLM. Auto-populated from registry."""
        return [entry["definition"] for entry in self._tools.values()]

    _SCHEDULE_TOOLS = {"get_full_schedule", "get_gbs_tours", "get_upcoming_gbs_tours"}

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """
        Dispatch a tool call to its registered handler.
        No if/elif chain needed — the registry handles routing.
        """
        if tool_name not in self._tools:
            logger.warning("Unknown tool requested: %s", tool_name)
            return f"Unknown tool: {tool_name}. Available tools: {list(self._tools.keys())}"
        self._last_any_tool_ran = True
        if tool_name in self._SCHEDULE_TOOLS:
            self._last_schedule_fetched = True
        try:
            return self._tools[tool_name]["handler"](tool_input)
        except Exception as e:
            logger.error("Tool execution failed: tool=%s error=%s", tool_name, e)
            return f"Error running {tool_name}: {str(e)}"

    def _resolve_tool_date(self, tool_input: dict, key: str = "date_str", default: str = "today"):
        """
        Resolve a raw date phrase from tool_input into a datetime.
        Returns (resolved_datetime, None) on success, (None, error_str) on failure.
        Handlers call this and return the error string immediately if it's not None.
        """
        from core.date_utils import resolve_date
        raw = tool_input.get(key, "").strip()
        try:
            return resolve_date(raw if raw else default), None
        except ValueError as e:
            return None, str(e)

    def _handle_get_gbs_tours(self, tool_input: dict) -> str:
        """Get GBS tours for a specified date (defaults to today)."""
        resolved, err = self._resolve_tool_date(tool_input)
        if err:
            return err
        date_str = resolved.strftime("%Y-%m-%d")

        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            from sites.lineleader.schedules import get_sessions_for_date
            sessions = get_sessions_for_date(self.bearer_token, date_str)
            enrich_sessions_with_children(self.bearer_token, sessions)

            # Cache for Excel export (GBS only — no MyStudio data)
            self._last_gbs_sessions = sessions
            self._last_appointments = []
            self._last_export_label = "gbs_tours"

            if not sessions:
                return f"No tours scheduled for {resolved.strftime('%A, %B %-d')}."

            date_display = sessions[0].date_display() if sessions else date_str
            lines = [f"Tours for {date_display}:\n"]
            for i, session in enumerate(sessions, 1):
                children_str = ", ".join(session.child_display) if session.child_display else "(no children listed)"
                lines.append(
                    f"{i}. [ID: {session.item_id}] {session.time_display()} - "
                    f"Parent: {session.student_name} | Children: {children_str} | "
                    f"Type: {session.tour_type} | Staff: {session.assignee_name}"
                )
            return "\n".join(lines)

        except Exception as e:
            raise RuntimeError(f"Failed to fetch tours for {date_str}: {e}")

    def _handle_get_upcoming_gbs_tours(self, tool_input: dict) -> str:
        """Fetch upcoming GBS tours from a given date forward."""
        from sites.lineleader.schedules import get_upcoming_gbs_tours

        limit = int(tool_input.get("limit", 5))

        after_date = ""
        label = "upcoming"
        if tool_input.get("after_date_str", "").strip():
            resolved, err = self._resolve_tool_date(tool_input, key="after_date_str")
            if err:
                return err
            from datetime import timedelta
            # "after June 16th" means strictly after — exclude the boundary date
            exclusive = resolved + timedelta(days=1)
            after_date = exclusive.strftime("%Y-%m-%d")
            label = f"after {resolved.strftime('%B %-d')}"

        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            sessions = get_upcoming_gbs_tours(self.bearer_token, after_date=after_date, limit=limit)
            enrich_sessions_with_children(self.bearer_token, sessions)

            # Cache for Excel export (GBS only — no MyStudio data)
            self._last_gbs_sessions = sessions
            self._last_appointments = []
            self._last_export_label = "gbs_tours"

            if not sessions:
                return f"No GBS tours found {label}."

            lines = [f"Next {len(sessions)} GBS tour(s) {label}:\n"]
            for i, session in enumerate(sessions, 1):
                children_str = ", ".join(session.child_display) if session.child_display else "(no children listed)"
                lines.append(
                    f"{i}. [ID: {session.item_id}] {session.date_display()} {session.time_display()} - "
                    f"Parent: {session.student_name} | Children: {children_str} | "
                    f"Type: {session.tour_type} | Staff: {session.assignee_name}"
                )
            return "\n".join(lines)

        except Exception as e:
            raise RuntimeError(f"Failed to fetch upcoming tours: {e}")

    def _handle_reschedule_tour(self, tool_input: dict) -> str:
        """Reschedule a tour. Python owns all date/time resolution — Claude passes raw phrases."""
        from core.date_utils import resolve_datetime

        tour_id = tool_input.get("tour_id", "")
        date_str = tool_input.get("date_str", "").strip()
        time_str = tool_input.get("time_str", "").strip()

        if not date_str:
            return "Please specify a date to reschedule to (e.g. 'Friday', 'June 9th')."
        if not time_str:
            return "Please specify a time to reschedule to (e.g. '10am', '2:30 PM')."

        try:
            new_local_dt = resolve_datetime(date_str, time_str)
        except ValueError as e:
            return str(e)

        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            sessions = get_todays_sessions(self.bearer_token)
            session = next((s for s in sessions if s.item_id == tour_id), None)

            if not session:
                return f"Tour {tour_id} not found."

            success, message = reschedule_tour(
                bearer_token=self.bearer_token,
                session=session,
                new_local_dt=new_local_dt,
            )

            if success:
                return f"Tour rescheduled successfully: {message}"
            else:
                return f"Failed to reschedule tour: {message}"

        except Exception as e:
            raise RuntimeError(f"Failed to reschedule tour: {e}")

    def _handle_cancel_student_session(self, tool_input: dict) -> str:
        """Cancel a student session — single or all-future. Dry-run until confirmed=True."""
        from sites.mystudio.students import get_student_upcoming_appointments
        from sites.mystudio.write import cancel_student_appointment

        student_name = tool_input.get("student_name", "").strip()
        date_str = tool_input.get("date_str", "").strip()
        cancel_all_future = bool(tool_input.get("cancel_all_future", False))
        confirmed = bool(tool_input.get("confirmed", False))

        if not student_name:
            return "Please specify the student's name."
        if not date_str:
            return "Please specify the date of the session to cancel."

        resolved, err = self._resolve_tool_date(tool_input, key="date_str")
        if err:
            return err
        target_date_str = resolved.strftime("%Y-%m-%d")

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            upcoming = get_student_upcoming_appointments(student.student_id, student.participant_id, days_ahead=60)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        session_match = next(
            (a for a in upcoming if a.start_time.strftime("%Y-%m-%d") == target_date_str),
            None,
        )
        if not session_match:
            return f"No upcoming session found for {student.name} on {resolved.strftime('%A, %B %-d')}."

        scope_label = "this session and all future recurring sessions" if cancel_all_future else "this single session"
        summary = (
            f"About to cancel: {student.name} — {session_match.appointment_type}\n"
            f"Date: {resolved.strftime('%A, %B %-d')} at {session_match.time_display()}\n"
            f"Scope: {scope_label}"
        )

        if not confirmed:
            return f"{summary}\n\nReply 'yes' to confirm or 'no' to cancel."

        try:
            success, msg = cancel_student_appointment(
                student_id=student.student_id,
                participant_id=student.participant_id,
                class_reg_id=session_match.id,
                class_registration_detail_id=session_match.registration_detail_id,
                class_appointment_id=session_match.class_appointment_id,
                class_appointment_times_id=session_match.class_appointment_times_id,
                selected_date=target_date_str,
                cancel_all_future=cancel_all_future,
            )
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        if success:
            return f"Cancelled: {student.name} — {session_match.appointment_type} on {resolved.strftime('%A, %B %-d')}. {msg}"
        return f"Cancel failed: {msg}"

    def _handle_move_student_session(self, tool_input: dict) -> str:
        """Move a student session to a new date/time — single or all-future. Dry-run until confirmed=True."""
        from core.date_utils import resolve_datetime
        from sites.mystudio.students import get_student_upcoming_appointments, get_available_slots
        from sites.mystudio.write import move_student_appointment

        student_name = tool_input.get("student_name", "").strip()
        from_date_str = tool_input.get("from_date_str", "").strip()
        to_date_str = tool_input.get("to_date_str", "").strip()
        to_time_str = tool_input.get("to_time_str", "").strip()
        move_all_future = bool(tool_input.get("move_all_future", False))
        confirmed = bool(tool_input.get("confirmed", False))

        if not student_name:
            return "Please specify the student's name."
        if not from_date_str:
            return "Please specify the date of the session to move."
        if not to_date_str or not to_time_str:
            return "Please specify both the target date and time."

        resolved_from, err = self._resolve_tool_date(tool_input, key="from_date_str")
        if err:
            return err
        try:
            resolved_to = resolve_datetime(to_date_str, to_time_str)
        except ValueError as e:
            return str(e)

        from_date = resolved_from.strftime("%Y-%m-%d")
        to_date = resolved_to.strftime("%Y-%m-%d")
        to_time_display = resolved_to.strftime("%I:%M %p").lstrip("0")

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            upcoming = get_student_upcoming_appointments(student.student_id, student.participant_id, days_ahead=60)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        session_match = next(
            (a for a in upcoming if a.start_time.strftime("%Y-%m-%d") == from_date),
            None,
        )
        if not session_match:
            return f"No upcoming session found for {student.name} on {resolved_from.strftime('%A, %B %-d')}."

        # Find target slot — match by class title + time on target date
        try:
            available = get_available_slots(to_date)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        target_time_api = resolved_to.strftime("%I:%M %p").lstrip("0")
        target_slot = next(
            (s for s in available
             if s["class_title"] == session_match.appointment_type
             and s["start_time"].lstrip("0") == target_time_api),
            None,
        )
        if not target_slot:
            all_times = sorted(set(
                s["start_time"] for s in available
                if s["class_title"] == session_match.appointment_type
            ))
            times_str = ", ".join(all_times) if all_times else "none"
            return (
                f"No available {session_match.appointment_type} slot at {to_time_display} "
                f"on {resolved_to.strftime('%A, %B %-d')}.\n"
                f"Available times: {times_str}"
            )

        scope_label = "all future recurring sessions" if move_all_future else "this single session"
        summary = (
            f"About to move: {student.name} — {session_match.appointment_type}\n"
            f"From: {resolved_from.strftime('%A, %B %-d')} at {session_match.time_display()}\n"
            f"To:   {resolved_to.strftime('%A, %B %-d')} at {to_time_display}\n"
            f"Scope: {scope_label}"
        )

        if not confirmed:
            return f"{summary}\n\nReply 'yes' to confirm or 'no' to cancel."

        try:
            success, msg = move_student_appointment(
                student_id=student.student_id,
                participant_id=student.participant_id,
                class_reg_id=session_match.id,
                class_registration_detail_id=session_match.registration_detail_id,
                class_appointment_id=session_match.class_appointment_id,
                class_appointment_times_id=session_match.class_appointment_times_id,
                program_date=from_date,
                new_class_appointment_times_id=target_slot["class_appointment_times_id"],
                new_program_date=to_date,
                move_all_future=move_all_future,
            )
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        if success:
            return (
                f"Moved: {student.name} — {session_match.appointment_type}\n"
                f"From {resolved_from.strftime('%A, %B %-d')} → "
                f"{resolved_to.strftime('%A, %B %-d')} at {to_time_display}. {msg}"
            )
        return f"Move failed: {msg}"

    def _resolve_student(self, student_name: str):
        """
        Look up a student by name, handling duplicates by checking active programs.

        Returns (StudentRecord, None) on success.
        Returns (None, error_string) when not found, ambiguous, or OTP needed.

        Duplicate resolution: for each match, fetch active memberships
        (mem_status == "Active"). If exactly one match has active programs,
        auto-select it. If multiple do, return a disambiguation message showing
        parent name and enrolled programs.
        """
        from sites.mystudio.students import find_student_by_name, get_student_details

        try:
            students = find_student_by_name(student_name)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return None, self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        if not students:
            return None, (
                f"No student found matching '{student_name}'. "
                "If that's a parent name, try the student's name instead."
            )

        if len(students) == 1:
            return students[0], None

        # Multiple matches — resolve by active programs
        active = []  # List of (StudentRecord, programs_str)
        for s in students:
            try:
                d = get_student_details(s.student_id, s.participant_id)
                if not d:
                    continue
                memberships = d.get("reg_details", {}).get("membership_details", [])
                active_memberships = [m for m in memberships if m.get("mem_status") == "Active"]
                if not active_memberships:
                    continue
                s.parent_name = d.get("participant_details", {}).get("buyer_name", "")
                s.belt_rank = active_memberships[0].get("rank_status", "")
                programs = ", ".join(
                    m.get("membership_category_title", "") for m in active_memberships
                )
                active.append((s, programs))
            except Exception:
                pass

        if len(active) == 1:
            return active[0][0], None

        if len(active) > 1:
            lines = [f"Found {len(active)} active students named '{student_name}'. Which one?"]
            for s, programs in active:
                lines.append(f"- {s.name} | Parent: {s.parent_name} | Programs: {programs}")
            return None, "\n".join(lines)

        # No active memberships found — fall back to first result
        return students[0], None

    def _otp_prompt(self, gmail_error: str = None) -> str:
        if gmail_error:
            prefix = "⚠️ Couldn't auto-fetch the OTP from Gmail.\n\n"
        else:
            prefix = ""
        return (
            "🔐 **MyStudio verification needed.**\n\n"
            + prefix
            + f"Please check **{settings.GMAIL_ADDRESS}** for an email from MyStudio "
            "and reply here with the **6-digit code**.\n\n"
            "_(Reply with the code, or anything else to cancel and file a request.)_"
        )

    def _handle_lookup_student(self, tool_input: dict) -> str:
        """Look up a student by name — attendance, belt rank, upcoming schedule."""
        from sites.mystudio.students import (
            get_student_details,
            get_student_sessions_by_type,
            get_student_attendance_this_week,
            get_student_upcoming_appointments,
        )
        import calendar as _calendar
        from datetime import date as _date, datetime as _datetime

        student_name = tool_input.get("student_name", "").strip()
        if not student_name:
            return "Please provide a student name to look up."

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            details = get_student_details(student.student_id, student.participant_id)
            billing_cycle_str = ""
            attended_this_cycle = 0
            total_this_cycle = 0
            attendance_14 = "0"
            attendance_30 = "0"

            if details:
                p = details.get("participant_details", {})
                student.parent_name = p.get("buyer_name", "")
                student.phone = p.get("student_mobile", "")
                membership_list = details.get("reg_details", {}).get("membership_details", [])
                active_mem = next((m for m in membership_list if m.get("mem_status") == "Active"), None)
                if active_mem:
                    student.belt_rank = active_mem.get("rank_status", "")
                    attendance_14 = active_mem.get("attendance_last_14_days", "0")
                    attendance_30 = active_mem.get("attendance_last_30_days", "0")
                    next_pay_str = active_mem.get("next_payment_date", "")
                    if next_pay_str:
                        try:
                            next_pay = _datetime.strptime(next_pay_str, "%b %d, %Y").date()
                            month = next_pay.month - 1 or 12
                            year = next_pay.year if next_pay.month > 1 else next_pay.year - 1
                            try:
                                billing_start = next_pay.replace(year=year, month=month)
                            except ValueError:
                                last_day = _calendar.monthrange(year, month)[1]
                                billing_start = next_pay.replace(year=year, month=month, day=last_day)

                            today = _date.today()
                            days_in_period = (today - billing_start).days + 1
                            cycle_sessions = get_student_sessions_by_type(
                                student.student_id, student.participant_id,
                                filter_type="P",
                                from_date=today.strftime("%Y-%m-%d"),
                                days=days_in_period,
                            )
                            attended_this_cycle = sum(
                                1 for s in cycle_sessions
                                if s.get("class_attendance_status", "").lower() == "attended"
                            )
                            total_this_cycle = len(cycle_sessions)
                            billing_cycle_str = f"{billing_start.strftime('%b %-d')} – {next_pay_str}"
                        except Exception:
                            pass

            attended_this_week = get_student_attendance_this_week(
                student.student_id, student.participant_id
            )
            upcoming = get_student_upcoming_appointments(
                student.student_id, student.participant_id, days_ahead=30
            )

        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        lines = [
            f"Student: {student.name}",
            f"Parent: {student.parent_name or 'N/A'} | Phone: {student.phone or 'N/A'}",
            f"Belt: {student.belt_rank or 'N/A'}",
        ]
        if billing_cycle_str:
            lines.append(f"Billing cycle: {billing_cycle_str} | Attended: {attended_this_cycle} / {total_this_cycle} session(s) this cycle")
        lines.append(f"Attendance: {attended_this_week} session(s) this week | {attendance_14} in last 14 days | {attendance_30} in last 30 days")
        lines.append("")

        if upcoming:
            lines.append(f"Upcoming sessions ({len(upcoming)}):")
            for appt in upcoming:
                day = appt.start_time.strftime("%A, %b %-d")
                lines.append(f"  - {day} at {appt.time_display()} — {appt.appointment_type}")
        else:
            lines.append("No upcoming sessions in the next 30 days.")

        return "\n".join(lines)

    def _handle_otp_submission(self, user_message: str) -> str:
        """Handle OTP code submitted via chat."""
        otp = user_message.strip()
        if not (otp.isdigit() and len(otp) == 6):
            self._awaiting_mystudio_otp = False
            return (
                "❌ MyStudio login cancelled. "
                "Please file a request or try again by asking for the schedule."
            )
        try:
            complete_otp_login(otp)
            self._awaiting_mystudio_otp = False
            return (
                "✅ MyStudio connected! Cookies cached for 30 days.\n\n"
                "Please ask your question again and I'll fetch the full schedule."
            )
        except Exception as e:
            return f"❌ OTP failed: {e}\n\nPlease check the code and try again."

    def _handle_get_full_schedule(self, tool_input: dict) -> str:
        """Get full schedule (GBS tours + student appointments) for a specified date (defaults to today)."""
        resolved, err = self._resolve_tool_date(tool_input)
        if err:
            return err
        date_str = resolved.strftime("%Y-%m-%d")

        try:
            # Fetch GBS tours from LineLeader
            from sites.lineleader.schedules import get_sessions_for_date
            ll_token = asyncio.run(get_bearer_token())
            gbs_sessions = get_sessions_for_date(ll_token, date_str)
            enrich_sessions_with_children(ll_token, gbs_sessions)

            # Fetch student appointments from MyStudio
            appointments = []
            try:
                from sites.mystudio.schedules import get_appointments_for_date
                appointments = get_appointments_for_date(date_str)
            except MystudioOTPRequired as _otp_exc:
                self._awaiting_mystudio_otp = True
                return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))
            except Exception as e:
                logger.warning("Failed to fetch MyStudio appointments for %s: %s", date_str, e)
                appointments = []

            # Cache for Excel export (avoids double API calls)
            self._last_gbs_sessions = gbs_sessions
            self._last_appointments = appointments
            self._last_export_label = "full_schedule"

            formatted = format_unified_schedule(gbs_sessions, appointments, date=resolved)

            if not formatted or (not gbs_sessions and not appointments):
                return f"No schedule found for {resolved.strftime('%A, %B %-d, %Y')}."

            return formatted

        except Exception as e:
            raise RuntimeError(f"Failed to fetch full schedule for {date_str}: {e}")

    def _handle_get_camp_details(self, tool_input: dict) -> str:
        """Fetch upcoming camps, optionally filtered by name/date, optionally with roster."""
        from datetime import datetime, timedelta

        after_date = None
        week_end = None  # set when filtering to a specific week

        week_of_str = (tool_input.get("week_of_date_str") or "").strip()
        after_date_str = (tool_input.get("after_date_str") or "").strip()

        if week_of_str:
            # Find Monday of the week containing the given date
            resolved, err = self._resolve_tool_date(
                {"date_str": week_of_str}, key="date_str", default="today"
            )
            if err:
                return err
            monday = resolved - timedelta(days=resolved.weekday())
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            after_date = monday
            week_end = monday + timedelta(days=7)
        elif after_date_str:
            resolved, err = self._resolve_tool_date(
                {"date_str": after_date_str}, key="date_str", default="today"
            )
            if err:
                return err
            after_date = resolved

        camp_name_filter = (tool_input.get("camp_name") or "").strip().lower()
        include_roster = bool(tool_input.get("include_roster", False))

        try:
            camps = get_all_upcoming_camps(from_date=after_date)
            if week_end:
                camps = [c for c in camps if c.start_dt < week_end]
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))
        except Exception as e:
            logger.error("get_all_upcoming_camps failed: %s", e)
            return "Sorry, I couldn't fetch camp data from MyStudio right now."

        if not camps:
            return "No upcoming camps found in MyStudio."

        # Always cache the full unfiltered list so Excel export gets everything
        self._last_camp_data = {"all_camps": camps, "camps": camps, "rosters": {}}

        # Apply name filter
        if camp_name_filter:
            filtered = [c for c in camps if camp_name_filter in c.title.lower()]
            if not filtered:
                return (
                    f"No upcoming camps matching '{tool_input.get('camp_name')}' found.\n\n"
                    "Available camps this season:\n" + format_camps_summary(camps)
                )
        else:
            filtered = camps

        # Roster mode: only when a specific camp name was given
        if include_roster and camp_name_filter:
            if len(filtered) == 1:
                camp = filtered[0]
                kids = get_camp_roster(camp.event_id, camp.parent_id)
                self._last_camp_data["rosters"][camp.event_id] = kids
                return format_camp_roster(camp, kids)
            elif len(filtered) <= 4:
                parts = []
                for camp in filtered:
                    kids = get_camp_roster(camp.event_id, camp.parent_id)
                    self._last_camp_data["rosters"][camp.event_id] = kids
                    parts.append(format_camp_roster(camp, kids))
                return "\n\n---\n\n".join(parts)
            else:
                return (
                    f"Found {len(filtered)} camps matching '{tool_input.get('camp_name')}'. "
                    "Please be more specific (e.g. include the date or time) so I can pull the right roster.\n\n"
                    + format_camps_summary(filtered)
                )

        return format_camps_summary(filtered)
