"""
ChatbotEngine: LLM-agnostic chatbot with function calling.

Provider-agnostic via the LLMProvider abstraction (Claude today).

Handles:
- Tool definitions for Milestone 1 (LineLeader GBS Tours)
- LLM API calls with tool use (provider-agnostic)
- Tool execution (calling Milestone 1 functions)
- Multi-turn conversation with automatic tool handling
"""

import json
import os
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
from core.date_utils import now_local, today_local, start_of_today_local, week_bounds, relative_week_anchor
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
    get_all_past_camps,
    get_camp_roster,
    get_camp_revenue,
    format_camps_summary,
    format_camp_roster,
    format_camp_revenue,
    format_week_revenue,
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
        self._last_gbs_sessions = None        # Set when any schedule tool runs; None = nothing fetched yet
        self._last_appointments = None        # Companion to _last_gbs_sessions
        self._last_export_label = None        # "full_schedule", "gbs_tours", or "camps"

        # Serialize all chat() calls — Flask runs with threaded=True so concurrent
        # requests share this singleton and race on conversation_history.
        self._chat_lock = threading.Lock()

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
        "get_camp_revenue":         "Calculating camp revenue — fetching payment details per kid...",
    }

    @staticmethod
    def _has_tool_use_in_content(content) -> bool:
        """Return True if content contains any tool_use blocks."""
        if not isinstance(content, list):
            return False
        for block in content:
            block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if block_type == "tool_use":
                return True
        return False

    @staticmethod
    def _is_tool_results_message(msg) -> bool:
        """Return True if msg is a user message whose content is a list of tool_result blocks."""
        if msg.get("role") != "user":
            return False
        content = msg.get("content", [])
        return (
            isinstance(content, list)
            and bool(content)
            and isinstance(content[0], dict)
            and content[0].get("type") == "tool_result"
        )

    def _sanitize_history(self) -> None:
        """
        Remove any corrupted tail from conversation_history.

        Two corruption modes (both cause a 400 on the next API call):

        Mode A — orphaned tool_use: assistant[tool_use] not immediately followed
        by user[tool_results].  Caused by an exception mid-loop or a concurrent
        request slipping a plain user message between the two appends.

        Mode B — orphaned tool_results: user[tool_results] not preceded by
        assistant[tool_use].  Caused by concurrent threads: one thread appends
        assistant[tool_use], another thread appends its own user message, then the
        first thread appends tool_results — leaving the tool_results paired with
        the wrong predecessor.

        Strategy: walk backwards, find the first broken pair, then truncate back
        to the last clean assistant[text] message.
        """
        n = len(self.conversation_history)

        def _clean_end_before(idx):
            """Index of last assistant[text] strictly before idx, or -1."""
            for j in range(idx - 1, -1, -1):
                m = self.conversation_history[j]
                if m.get("role") == "assistant" and not self._has_tool_use_in_content(m.get("content")):
                    return j
            return -1

        for i in range(n - 1, -1, -1):
            msg = self.conversation_history[i]

            # --- Mode A: assistant[tool_use] not followed by tool_results ---
            if msg.get("role") == "assistant" and self._has_tool_use_in_content(msg.get("content")):
                if i + 1 < n and self._is_tool_results_message(self.conversation_history[i + 1]):
                    break  # valid pair — stop scanning
                clean_end = _clean_end_before(i)
                cutoff = clean_end + 1
                logger.warning(
                    "Sanitizing history (Mode A): orphaned tool_use at index %d — "
                    "trimming %d message(s)", i, n - cutoff,
                )
                self.conversation_history = self.conversation_history[:cutoff]
                return

            # --- Mode B: user[tool_results] not preceded by assistant[tool_use] ---
            if self._is_tool_results_message(msg):
                if i > 0 and self._has_tool_use_in_content(self.conversation_history[i - 1].get("content")):
                    break  # valid pair — stop scanning
                clean_end = _clean_end_before(i)
                cutoff = clean_end + 1
                logger.warning(
                    "Sanitizing history (Mode B): orphaned tool_results at index %d — "
                    "trimming %d message(s)", i, n - cutoff,
                )
                self.conversation_history = self.conversation_history[:cutoff]
                return

    def chat(self, user_message: str, status_callback=None, user_name: str = "Unknown") -> str:
        """
        Send a message to the LLM and handle tool calls.

        Holds self._chat_lock for the entire call: Flask runs threaded=True so
        concurrent HTTP requests share this singleton — without the lock, two
        requests race on conversation_history and corrupt it.

        status_callback: optional callable(str) called with status updates during tool execution.
        """
        with self._chat_lock:
            return self._chat_impl(user_message, status_callback=status_callback, user_name=user_name)

    def _chat_impl(self, user_message: str, status_callback=None, user_name: str = "Unknown") -> str:
        """Actual chat logic — called only while holding _chat_lock."""
        # If waiting for MyStudio OTP, handle before passing to LLM
        if self._awaiting_mystudio_otp:
            result = self._handle_otp_submission(user_message)
            # Add to conversation history so Claude knows OTP was resolved
            # (without this, Claude sees the last assistant message as "🔐 OTP needed"
            # and keeps asking for it instead of calling tools)
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": result})
            return result

        logger.info("User query: %s", user_message[:120])
        request_start = time.monotonic()
        _tracker = self._analytics.start_query(user_message, query_type="natural_language", user=user_name)

        # Per-turn memoization for expensive read tools. Claude sometimes fires
        # the same query twice in one turn under two phrasings (e.g. "next week"
        # and "week of July 7th") that resolve to the identical window. Handlers
        # key results here so the second call returns instantly instead of
        # redoing the whole fetch. Reset every turn — never persists across turns.
        self._turn_cache = {}

        # Remove any orphaned tool_use blocks left by a previously interrupted turn.
        # Must run before appending the new user message so we don't create two
        # consecutive user messages on top of a dangling assistant[tool_use].
        self._sanitize_history()

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

                # Execute every tool call and collect results.
                # Wrapped in try/except so tool_results are ALWAYS appended even if
                # something unexpected fires mid-loop (analytics, logger, status_callback).
                # An orphaned assistant[tool_use] with no following tool_results causes a
                # 400 on the very next API call.
                tool_results = []
                try:
                    for tool_call in tool_calls:
                        tool_name = tool_call["name"]
                        tool_input = tool_call["input"]
                        tool_id = tool_call["id"]

                        logger.info("Tool call: %s | inputs: %s", tool_name, json.dumps(tool_input, default=str))

                        if status_callback:
                            try:
                                status_callback(self._TOOL_STATUS.get(tool_name, f"Running {tool_name}..."))
                            except Exception:
                                pass

                        tool_start = time.monotonic()
                        tool_result = self._execute_tool(tool_name, tool_input)
                        tool_elapsed = time.monotonic() - tool_start
                        logger.info("Tool done: %s | %.1fs | result: %d chars", tool_name, tool_elapsed, len(tool_result))
                        try:
                            _tracker.record_tool(tool_name, tool_input, tool_elapsed)
                        except Exception:
                            pass

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": tool_result,
                        })
                except Exception as _tool_exc:
                    logger.error("Unexpected exception during tool execution batch: %s", _tool_exc)
                    # Backfill synthetic errors for any tool calls that didn't complete.
                    completed_ids = {r["tool_use_id"] for r in tool_results}
                    for tc in tool_calls:
                        if tc["id"] not in completed_ids:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tc["id"],
                                "content": "Internal error — tool did not complete.",
                            })

                # Add all results in one user message — Anthropic requires this,
                # and must happen unconditionally to keep history valid.
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

                # Add assistant's response to history. Claude returns structured
                # content blocks — preserve them to keep the conversation shape;
                # a text-only provider falls back to the extracted text.
                raw_response = response_data.get("raw")
                if raw_response and hasattr(raw_response, "content"):
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": raw_response.content
                    })
                else:
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
        # now_local() is anchored to CENTER_TIMEZONE so "today" is correct on any
        # host (e.g. UTC on Railway), not the server's local clock.
        now = now_local()
        today_str = now.strftime("%A, %B %-d, %Y")   # e.g. "Tuesday, June 30, 2026"
        time_str = now.strftime("%-I:%M %p")          # e.g. "3:15 PM"
        return f"""You are an operations assistant for Code Ninjas Eastvale Chino.
You help staff manage daily schedules, student appointments, and tours
by querying the center's systems and taking action on their behalf.

The current date and time is {today_str}, {time_str} ({settings.CENTER_TIMEZONE}).
This is the single source of truth for "today", "now", "tomorrow", "this week",
and every other relative date reference. Never infer the date from earlier
messages, tool outputs, or anything else in the conversation — only from this line.

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

When a staff member says "my schedule", "our schedule", or "today's schedule",
they mean the center's schedule — GBS tours and student classes. Always call
the appropriate tools to fetch it rather than assuming you don't have access.

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
                "Look up a student by name in MyStudio. Returns their program enrollment "
                "(e.g. CREATE: Plus 2x/Week), belt rank, parent contact info, billing cycle "
                "attendance vs expected sessions and sessions remaining, attendance this week "
                "and over 14/30 days, and upcoming scheduled sessions. "
                "Use for any question about a specific student — e.g. 'how many classes left "
                "for Arhaan this month?', 'how many has he attended this billing cycle?', "
                "'what program is Journei in?', 'look up Veshant', 'what's Henry's schedule?'. "
                "'This month' and 'this billing cycle' mean the same thing here — use the "
                "billing cycle attended/expected/remaining fields to answer those questions "
                "directly without asking follow-up questions."
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
            name="get_student_recent_appointments",
            description=(
                "Fetch a student's most recent past sessions with actual attendance status for each. "
                "Use when staff ask about recent or past appointments — e.g. "
                "'show me Ayaan's last 5 appointments', 'what are his recent sessions?', "
                "'show me her appointment history'. "
                "Do NOT use for missed-only queries (use get_student_missed_appointments) "
                "or for a specific date (use get_student_session_on_date)."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "The student name exactly as the user said it.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent sessions to return. Defaults to 5.",
                },
            },
            handler=self._handle_get_student_recent_appointments,
        )
        self._register(
            name="get_student_session_on_date",
            description=(
                "Look up a student's session on a specific date — past or upcoming. "
                "Returns what was scheduled and the attendance status (Attended, Not Attended, Scheduled). "
                "Use when staff ask about a specific date — e.g. 'show me Ayaan's June 22nd appointment', "
                "'did Alex attend on Friday?', 'what was scheduled for Journei on the 20th?'."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "The student name exactly as the user said it.",
                },
                "date_str": {
                    "type": "string",
                    "description": "The date to look up, exactly as the user said it. Do not resolve — pass the raw phrase.",
                },
            },
            handler=self._handle_get_student_session_on_date,
        )
        self._register(
            name="get_student_missed_appointments",
            description=(
                "Fetch a student's past sessions that were missed (Not Attended, Absent, No Show). "
                "Use ONLY when staff explicitly ask about missed, skipped, or not-attended sessions — e.g. "
                "'show me Ayaan's missed appointments', 'what sessions did Alex miss?', "
                "'list his not attended classes', 'which sessions did she skip?'. "
                "Do NOT use for general appointment history or 'last N appointments' queries. "
                "Returns up to the most recent missed sessions, most recent first."
            ),
            parameters={
                "student_name": {
                    "type": "string",
                    "description": "The student name exactly as the user said it.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of missed sessions to return. Defaults to 5 if not specified.",
                },
            },
            handler=self._handle_get_student_missed_appointments,
        )
        self._register(
            name="get_camp_details",
            description=(
                "Fetch camp details from MyStudio — both upcoming AND past camps. "
                "Returns camp names, dates, enrollment counts, and optionally the roster of enrolled kids. "
                "Use when staff ask about camps — e.g. 'what camps are coming up?', "
                "'how many kids are in the Minecraft camp?', 'who's enrolled in the June 15 camp?', "
                "'show me the summer camp schedule', 'list all camps this week', "
                "'find past 3D printing camps', 'what camps ran in February?'. "
                "When camp_name is given without a date, this tool automatically searches both "
                "upcoming and past camps and returns all matches — always call this tool for camp name searches, "
                "never answer from context alone. "
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

        self._register(
            name="get_camp_revenue",
            description=(
                "Calculate revenue for upcoming camps — how much has been collected from enrolled families. "
                "Use when staff ask: 'how much revenue will next week's camp generate?', "
                "'what did the Minecraft camp bring in?', 'show me camp revenue for July', "
                "'how much have we collected for summer camps?'. "
                "Use week_of_date_str to scope by week (e.g. 'next week', 'week of July 6'). "
                "Use camp_name to filter to a specific camp. "
                "Returns total revenue, per-camp breakdown, and flags anomalies: "
                "comped kids ($0), discounts, cancelled registrations, and family patterns. "
                "IMPORTANT: call this tool exactly ONCE per question. Pass the user's raw "
                "phrase verbatim in week_of_date_str — do not resolve it to a date yourself "
                "and do not also issue a second call with a rephrased/resolved date."
            ),
            parameters={
                "week_of_date_str": {
                    "type": "string",
                    "description": (
                        "Pass the raw week phrase from the user, e.g. 'next week', 'week of July 6', "
                        "'this week'. Python resolves to the Mon–Sun window. "
                        "Leave empty to use all upcoming camps."
                    ),
                },
                "camp_name": {
                    "type": "string",
                    "description": (
                        "Optional camp title keyword to filter, e.g. 'Minecraft', 'Robotics', 'JR'. "
                        "Leave empty for all camps in the week."
                    ),
                },
            },
            handler=self._handle_get_camp_revenue,
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

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """
        Dispatch a tool call to its registered handler.
        No if/elif chain needed — the registry handles routing.
        """
        if tool_name not in self._tools:
            logger.warning("Unknown tool requested: %s", tool_name)
            return f"Unknown tool: {tool_name}. Available tools: {list(self._tools.keys())}"
        try:
            return self._tools[tool_name]["handler"](tool_input)
        except Exception as e:
            logger.error("Tool execution failed: tool=%s error=%s", tool_name, e)
            return f"Error running {tool_name}: {str(e)}"

    def _resolve_tool_date(self, tool_input: dict, key: str = "date_str", default: str = "today", allow_past: bool = False):
        """
        Resolve a raw date phrase from tool_input into a datetime.
        Returns (resolved_datetime, None) on success, (None, error_str) on failure.
        Handlers call this and return the error string immediately if it's not None.
        allow_past: pass True for operations targeting past sessions (skips year-roll).
        """
        from core.date_utils import resolve_date
        raw = tool_input.get(key, "").strip()
        try:
            return resolve_date(raw if raw else default, allow_past=allow_past), None
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

            from datetime import datetime as _dt, timezone as _tz
            # start_time is UTC-aware; compare against UTC now to avoid TypeError
            if session.start_time < _dt.now(_tz.utc):
                local_dt = session.start_time.astimezone()
                return (
                    f"That tour has already passed "
                    f"({local_dt.strftime('%I:%M %p').lstrip('0')} today). "
                    "Past sessions can't be rescheduled — you can cancel it instead, "
                    "and set up a new appointment directly in LineLeader."
                )

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
        """Cancel a student session — single or all-future. Dry-run until confirmed=True.

        Checks upcoming sessions first. If the date is in the past, falls back to
        past Not Attended sessions (missed classes that can still be cleaned up).
        """
        from sites.mystudio.students import (
            get_student_upcoming_appointments,
            get_student_past_not_attended_appointments,
        )
        from sites.mystudio.write import cancel_student_appointment

        student_name = tool_input.get("student_name", "").strip()
        date_str = tool_input.get("date_str", "").strip()
        cancel_all_future = bool(tool_input.get("cancel_all_future", False))
        confirmed = bool(tool_input.get("confirmed", False))

        if not student_name:
            return "Please specify the student's name."
        if not date_str:
            return "Please specify the date of the session to cancel."

        resolved, err = self._resolve_tool_date(tool_input, key="date_str", allow_past=True)
        if err:
            return err
        target_date_str = resolved.strftime("%Y-%m-%d")

        student, err = self._resolve_student(student_name)
        if err:
            return err

        # Try upcoming sessions first
        is_past_session = False
        try:
            upcoming = get_student_upcoming_appointments(student.student_id, student.participant_id, days_ahead=60)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        session_match = next(
            (a for a in upcoming if a.start_time.strftime("%Y-%m-%d") == target_date_str),
            None,
        )

        # Fall back to past not-attended sessions if no upcoming match
        if not session_match:
            try:
                past = get_student_past_not_attended_appointments(student.student_id, student.participant_id)
            except MystudioOTPRequired as _otp_exc:
                self._awaiting_mystudio_otp = True
                return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

            session_match = next(
                (a for a in past if a.start_time.strftime("%Y-%m-%d") == target_date_str),
                None,
            )
            if session_match:
                is_past_session = True

        if not session_match:
            return (
                f"No session found for {student.name} on {resolved.strftime('%A, %B %-d')}. "
                f"If this was a missed session, it may have already been cancelled or marked Attended."
            )

        scope_label = "this session and all future recurring sessions" if cancel_all_future else "this single session"
        past_note = " (missed — Not Attended)" if is_past_session else ""
        summary = (
            f"About to cancel: {student.name} — {session_match.appointment_type}{past_note}\n"
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

        from datetime import datetime as _dt
        if session_match.start_time < _dt.now():
            return (
                f"That session has already passed "
                f"({session_match.start_time.strftime('%A, %B %-d')} at {session_match.time_display()}). "
                "Past sessions can't be rescheduled. You can ask me to cancel it if needed, "
                "then log into MyStudio to create a new appointment."
            )

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
        reason = gmail_error or "connection timed out"
        return (
            "⚠️ **MyStudio login failed — couldn't auto-fetch the verification code.**\n\n"
            f"Reason: {reason}\n\n"
            "Please try again by asking your question in a new browser tab. "
            "If it keeps happening, let Prashant know."
        )

    def _handle_lookup_student(self, tool_input: dict) -> str:
        """Look up a student by name — attendance, belt rank, upcoming schedule."""
        from sites.mystudio.students import (
            get_student_details,
            get_student_attendance_this_week,
            get_student_upcoming_appointments,
            get_membership_reg_details,
        )
        from datetime import datetime as _datetime
        import math as _math

        student_name = tool_input.get("student_name", "").strip()
        if not student_name:
            return "Please provide a student name to look up."

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            # details, attendance, and upcoming are independent (they need only
            # the resolved student IDs), so fetch them concurrently. membership
            # depends on reg_id from details, so it runs afterward.
            with ThreadPoolExecutor(max_workers=3) as _ex:
                _f_details = _ex.submit(get_student_details, student.student_id, student.participant_id)
                _f_attend = _ex.submit(get_student_attendance_this_week, student.student_id, student.participant_id)
                _f_upcoming = _ex.submit(
                    get_student_upcoming_appointments,
                    student.student_id, student.participant_id, days_ahead=30,
                )
                details = _f_details.result()
                attended_this_week = _f_attend.result()
                upcoming = _f_upcoming.result()

            billing_cycle_str = ""
            attended_this_cycle = 0
            expected_this_cycle = 0
            membership_title = ""
            attendance_14 = "0"
            attendance_30 = "0"
            cycle_end = None

            if details:
                p = details.get("participant_details", {})
                student.parent_name = p.get("buyer_name", "")
                student.phone = p.get("student_mobile", "")
                reg_id = p.get("reg_id", "")

                membership_list = details.get("reg_details", {}).get("membership_details", [])
                active_mem = next((m for m in membership_list if m.get("mem_status") == "Active"), None)
                if active_mem:
                    student.belt_rank = active_mem.get("rank_status", "")
                    attendance_14 = active_mem.get("attendance_last_14_days", "0")
                    attendance_30 = active_mem.get("attendance_last_30_days", "0")
                    attended_this_cycle = int(active_mem.get("act_att", "0") or 0)

                # Fetch plan details: frequency + exact billing cycle dates
                if reg_id:
                    plan = get_membership_reg_details(reg_id)
                    if plan:
                        membership_title = plan.get("membership_title", "")
                        sessions_per_week = int(plan.get("reg_no_of_classes", "0") or 0)
                        cycle_start_str = plan.get("preceding_payment_date", "")
                        next_pay_str = plan.get("next_payment_date", "")
                        if cycle_start_str and next_pay_str:
                            try:
                                cycle_start = _datetime.strptime(cycle_start_str, "%Y-%m-%d").date()
                                cycle_end = _datetime.strptime(next_pay_str, "%Y-%m-%d").date()
                                weeks = (cycle_end - cycle_start).days / 7.0
                                expected_this_cycle = _math.floor(weeks * sessions_per_week)
                                billing_cycle_str = (
                                    f"{cycle_start.strftime('%b %-d')} – "
                                    f"{cycle_end.strftime('%b %-d, %Y')}"
                                )
                            except Exception:
                                cycle_end = None

        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        lines = [
            f"Student: {student.name}",
            f"Parent: {student.parent_name or 'N/A'} | Phone: {student.phone or 'N/A'}",
            f"Belt: {student.belt_rank or 'N/A'}",
        ]
        if membership_title:
            lines.append(f"Program: {membership_title}")
        if billing_cycle_str:
            remaining = max(0, expected_this_cycle - attended_this_cycle) if expected_this_cycle else None
            cycle_str = f"Billing cycle ({billing_cycle_str}): attended {attended_this_cycle}"
            if expected_this_cycle:
                cycle_str += f" / {expected_this_cycle} expected"
            if remaining is not None:
                cycle_str += f" | {remaining} session(s) remaining this cycle"
            lines.append(cycle_str)
        lines.append(f"Attendance: {attended_this_week} session(s) this week | {attendance_14} in last 14 days | {attendance_30} in last 30 days")
        lines.append("")

        if upcoming:
            lines.append(f"Upcoming sessions ({len(upcoming)}):")
            for appt in upcoming:
                day = appt.start_time.strftime("%A, %b %-d")
                next_cycle = cycle_end and appt.start_time.date() >= cycle_end
                suffix = " [next billing cycle]" if next_cycle else ""
                lines.append(f"  - {day} at {appt.time_display()} — {appt.appointment_type}{suffix}")
        else:
            lines.append("No upcoming sessions in the next 30 days.")

        return "\n".join(lines)

    def _handle_get_student_recent_appointments(self, tool_input: dict) -> str:
        """Return the last N past sessions for a student with real attendance status."""
        from sites.mystudio.students import get_student_sessions_by_type

        student_name = tool_input.get("student_name", "").strip()
        limit = int(tool_input.get("limit") or 5)

        if not student_name:
            return "Please provide a student name."

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            raw = get_student_sessions_by_type(
                student.student_id, student.participant_id,
                filter_type="P",
                from_date=today_local().strftime("%Y-%m-%d"),
                days=90,
            )
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        if not raw:
            return f"No past sessions found for {student.name} in the last 90 days."

        # Sort most-recent-first, take limit
        raw_sorted = sorted(raw, key=lambda s: s.get("server_program_date", ""), reverse=True)
        shown = raw_sorted[:limit]

        lines = [f"Last {len(shown)} session(s) for {student.name} (most recent first):"]
        for s in shown:
            date_label = s.get("p_date", s.get("server_program_date", ""))
            time_str = s.get("start_time", "")
            title = s.get("class_appointment_title", "Class")
            status = s.get("class_attendance_status", "Unknown")
            lines.append(f"  - {date_label} at {time_str} — {title} [{status}]")

        return "\n".join(lines)

    def _handle_get_student_session_on_date(self, tool_input: dict) -> str:
        """Look up a student's session on a specific date — past or upcoming."""
        from sites.mystudio.students import get_student_upcoming_appointments, get_student_sessions_by_type

        student_name = tool_input.get("student_name", "").strip()
        if not student_name:
            return "Please provide a student name."
        if not tool_input.get("date_str", "").strip():
            return "Please provide a date to look up."

        resolved, err = self._resolve_tool_date(tool_input, key="date_str", allow_past=True)
        if err:
            return err
        target_date_str = resolved.strftime("%Y-%m-%d")
        date_label = resolved.strftime("%A, %b %-d")

        student, err = self._resolve_student(student_name)
        if err:
            return err

        is_past = resolved.date() < today_local()

        try:
            if not is_past:
                appointments = get_student_upcoming_appointments(student.student_id, student.participant_id, days_ahead=90)
                match = next((a for a in appointments if a.start_time.strftime("%Y-%m-%d") == target_date_str), None)
                if match:
                    return (
                        f"{student.name} on {date_label}:\n"
                        f"  {match.appointment_type} at {match.time_display()} — Scheduled"
                    )
                return f"No session found for {student.name} on {date_label}."

            # Past date — fetch raw sessions to get attendance status
            days_back = (today_local() - resolved.date()).days + 1
            raw = get_student_sessions_by_type(
                student.student_id, student.participant_id,
                filter_type="P",
                from_date=today_local().strftime("%Y-%m-%d"),
                days=days_back,
            )
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        matches = [s for s in raw if s.get("server_program_date", "") == target_date_str]
        if not matches:
            return f"No session found for {student.name} on {date_label}."

        lines = [f"{student.name} on {date_label}:"]
        for s in matches:
            title = s.get("class_appointment_title", "Class")
            status = s.get("class_attendance_status", "Unknown")
            time_str = s.get("start_time", "")
            lines.append(f"  {title} at {time_str} — {status}")
        return "\n".join(lines)

    def _handle_get_student_missed_appointments(self, tool_input: dict) -> str:
        """List a student's past Not Attended sessions."""
        from sites.mystudio.students import get_student_past_not_attended_appointments

        student_name = tool_input.get("student_name", "").strip()
        limit = int(tool_input.get("limit") or 5)

        if not student_name:
            return "Please provide a student name."

        student, err = self._resolve_student(student_name)
        if err:
            return err

        try:
            missed = get_student_past_not_attended_appointments(student.student_id, student.participant_id)
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        if not missed:
            return f"No missed (Not Attended) sessions found for {student.name} in the last 90 days."

        shown = missed[:limit]
        lines = [f"Missed sessions for {student.name} (showing {len(shown)} of {len(missed)}):"]
        for appt in shown:
            day = appt.start_time.strftime("%A, %b %-d")
            lines.append(f"  - {day} at {appt.time_display()} — {appt.appointment_type}")

        return "\n".join(lines)

    def _handle_otp_submission(self, user_message: str) -> str:
        """Handle any message received while waiting for OTP (auto-fetch failed)."""
        self._awaiting_mystudio_otp = False
        return (
            "Please try asking your question again in a new browser tab — "
            "I'll attempt to reconnect to MyStudio automatically."
        )

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
            # Find Monday of the week containing the given date.
            # allow_past=True so "June 19" resolves to 2026-06-19, not 2027-06-19.
            resolved, err = self._resolve_tool_date(
                {"date_str": week_of_str}, key="date_str", default="today", allow_past=True
            )
            if err:
                return err
            after_date, week_end = week_bounds(resolved)
        elif after_date_str:
            resolved, err = self._resolve_tool_date(
                {"date_str": after_date_str}, key="date_str", default="today", allow_past=True
            )
            if err:
                return err
            after_date = resolved

        camp_name_filter = (tool_input.get("camp_name") or "").strip().lower()
        include_roster = bool(tool_input.get("include_roster", False))

        today = start_of_today_local()
        is_past = week_end is not None and week_end <= today

        def _camp_matches(query: str, title: str) -> bool:
            """Match camp name with fallback: exact substring → all words → any meaningful word."""
            t = title.lower()
            if query in t:
                return True
            words = query.split()
            if len(words) > 1 and all(w in t for w in words):
                return True
            # OR-match on words ≥4 chars — handles typos and partial queries
            meaningful = [w for w in words if len(w) >= 4]
            return bool(meaningful and any(w in t for w in meaningful))

        try:
            if is_past:
                camps = get_all_past_camps(since_date=after_date, until_date=week_end)
            else:
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
            label = "past" if is_past else "upcoming"
            return f"No {label} camps found for that period."

        # Always cache the full unfiltered list so Excel export gets everything
        self._last_camp_data = {"all_camps": camps, "camps": camps, "rosters": {}}

        # Apply name filter
        searched_all_time = False
        if camp_name_filter:
            filtered = [c for c in camps if _camp_matches(camp_name_filter, c.title)]
            if not is_past and week_end is None:
                # No date specified — also search past camps so name searches are complete
                try:
                    past_camps = get_all_past_camps()
                except MystudioOTPRequired as _otp_exc:
                    self._awaiting_mystudio_otp = True
                    return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))
                except Exception as e:
                    logger.error("get_all_past_camps fallback failed: %s", e)
                    past_camps = []
                past_matches = [c for c in past_camps if _camp_matches(camp_name_filter, c.title)]
                # Merge: past first (oldest → newest), then upcoming
                past_matches.sort(key=lambda c: c.start_dt)
                filtered = past_matches + filtered
                searched_all_time = True
            if not filtered:
                label = "past" if is_past else "upcoming"
                return (
                    f"No {label} camps matching '{tool_input.get('camp_name')}' found.\n\n"
                    "Available camps this season:\n" + format_camps_summary(camps)
                )
        else:
            filtered = camps

        # Roster mode: only when a specific camp name was given
        roster_list_type = "D" if is_past else "P"
        if include_roster and camp_name_filter:
            if len(filtered) == 1:
                camp = filtered[0]
                kids = get_camp_roster(camp.event_id, camp.parent_id, event_list_type=roster_list_type)
                self._last_camp_data["rosters"][camp.event_id] = kids
                return format_camp_roster(camp, kids)
            elif len(filtered) <= 4:
                parts = []
                for camp in filtered:
                    elt = "D" if camp.start_dt < today else "P"
                    kids = get_camp_roster(camp.event_id, camp.parent_id, event_list_type=elt)
                    self._last_camp_data["rosters"][camp.event_id] = kids
                    parts.append(format_camp_roster(camp, kids))
                return "\n\n---\n\n".join(parts)
            else:
                return (
                    f"Found {len(filtered)} camps matching '{tool_input.get('camp_name')}'. "
                    "Please be more specific (e.g. include the date or time) so I can pull the right roster.\n\n"
                    + format_camps_summary(filtered)
                )

        result = format_camps_summary(filtered)
        if searched_all_time:
            year = today.year
            result += f"\n\n[Searched all camps: Jan 1 {year} through end of season. This is the complete list.]"
        return result

    def _handle_get_camp_revenue(self, tool_input: dict) -> str:
        """Calculate revenue for camps in a given week, with per-kid gotcha callouts."""
        from datetime import datetime, timedelta

        week_of_str = (tool_input.get("week_of_date_str") or "").strip()
        camp_name_filter = (tool_input.get("camp_name") or "").strip().lower()

        after_date = None
        week_end = None

        if week_of_str:
            # Relative-week phrases ("next week", "this week", "last week") aren't
            # understood by resolve_date — it only handles concrete dates and
            # "week of <date>". Map them here so the phrases the tool advertises
            # actually work instead of returning "could not understand the date".
            anchor = relative_week_anchor(week_of_str, start_of_today_local())
            if anchor is not None:
                after_date, week_end = week_bounds(anchor)
            else:
                resolved, err = self._resolve_tool_date(
                    {"date_str": week_of_str}, key="date_str", default="today", allow_past=True
                )
                if err:
                    return err
                after_date, week_end = week_bounds(resolved)
        else:
            # Default to next week if no date specified
            after_date, week_end = week_bounds(start_of_today_local() + timedelta(days=7))

        today = start_of_today_local()
        is_past = week_end is not None and week_end <= today

        # Collapse duplicate calls within a turn: two phrasings ("next week" /
        # "week of July 7th") resolve to the same window, so key on the resolved
        # window + camp filter, not the raw phrase.
        if not hasattr(self, "_turn_cache"):
            self._turn_cache = {}
        cache_key = ("camp_revenue", after_date, week_end, camp_name_filter)
        if cache_key in self._turn_cache:
            logger.info("camp_revenue: turn-cache hit — skipping duplicate fetch for %s", cache_key)
            return self._turn_cache[cache_key]

        try:
            if is_past:
                camps = get_all_past_camps(since_date=after_date, until_date=week_end)
            else:
                camps = get_all_upcoming_camps(from_date=after_date)
                if week_end:
                    camps = [c for c in camps if c.start_dt < week_end]
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))
        except Exception as e:
            logger.error("get_camp_revenue: failed to fetch camps: %s", e)
            return "Sorry, I couldn't fetch camp data from MyStudio right now."

        if not camps:
            label = "past" if is_past else "upcoming"
            return f"No {label} camps found for that week."

        if camp_name_filter:
            camps = [c for c in camps if camp_name_filter in c.title.lower()]
            if not camps:
                return f"No camps matching '{tool_input.get('camp_name')}' found for that week."

        # Cap raised from 8 → 15: camps are now computed concurrently (see the
        # ThreadPoolExecutor below), so a full school-track week of ~12 camps
        # finishes in ~7s. 15 leaves headroom without risking a runaway batch.
        if len(camps) > 15:
            return (
                f"Found {len(camps)} camps — that's a lot to compute revenue for individually. "
                "Try narrowing by camp name or a specific week."
            )

        logger.info(
            "camp_revenue: computing %d camp(s) for %s–%s: %s",
            len(camps),
            after_date.strftime("%b %-d") if after_date else "?",
            week_end.strftime("%b %-d") if week_end else "?",
            ", ".join(c.title[:35] for c in camps),
        )
        rev_t0 = time.perf_counter()

        # Compute camps concurrently. Each get_camp_revenue() also parallelizes
        # its own kids, so peak connections ≈ outer × inner. Cap the outer pool
        # at 6 (a normal week's camp count) — with our small camps the realistic
        # peak is ~24 connections. Drop this to 3 if MyStudio ever rate-limits.
        # OTP expiry can't early-return from inside a worker, so we let it raise
        # out of the pool and handle it here; all other per-camp errors are
        # isolated so one bad camp doesn't sink the batch. map() preserves order.
        def _safe_revenue(camp):
            try:
                return get_camp_revenue(camp)
            except MystudioOTPRequired:
                raise  # bubble up to trigger the OTP prompt below
            except Exception as e:
                logger.error("get_camp_revenue failed for %s: %s", camp.event_id, e)
                return {"error": str(e), "camp": camp}

        try:
            workers = min(6, len(camps))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(_safe_revenue, camps))
        except MystudioOTPRequired as _otp_exc:
            self._awaiting_mystudio_otp = True
            return self._otp_prompt(gmail_error=getattr(_otp_exc, "gmail_error", None))

        grand_total = sum(r.get("total", 0.0) for r in results)
        logger.info(
            "camp_revenue: %d camp(s) done in %.1fs | grand total $%.2f",
            len(results), time.perf_counter() - rev_t0, grand_total,
        )

        if len(results) == 1:
            output = format_camp_revenue(results[0])
        else:
            parts = [format_week_revenue(results), ""]
            for r in results:
                parts.append(format_camp_revenue(r))
                parts.append("")
            output = "\n".join(parts)

        self._turn_cache[cache_key] = output
        return output
