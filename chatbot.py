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
from sites.lineleader.auth import get_bearer_token
from sites.lineleader.schedules import (
    get_todays_sessions,
    enrich_sessions_with_children,
    reschedule_tour,
)
from sites.mystudio.schedules import get_todays_appointments
from sites.mystudio.auth import MystudioOTPRequired, complete_otp_login
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

    # Friendly status messages shown to user while tools run
    _TOOL_STATUS = {
        "get_todays_gbs_tours":      "Fetching GBS tours from LineLeader...",
        "get_tour_details":          "Looking up tour details...",
        "reschedule_tour":           "Rescheduling tour...",
        "get_todays_full_schedule":  "Fetching schedule from LineLeader and MyStudio...",
    }

    def chat(self, user_message: str, status_callback=None) -> str:
        """
        Send a message to the LLM and handle tool calls.

        status_callback: optional callable(str) called with status updates during tool execution.
        """
        # If waiting for MyStudio OTP, handle before passing to LLM
        if self._awaiting_mystudio_otp:
            return self._handle_otp_submission(user_message)

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

            logger.info("LLM response: type=%s", response_data["type"])

            # Check if LLM wants to use a tool
            if response_data["type"] == "tool_use":
                tool_content = response_data["content"]
                tool_name = tool_content["name"]
                tool_input = tool_content["input"]
                tool_id = tool_content["id"]

                # Notify user what we're doing
                if status_callback:
                    status_msg = self._TOOL_STATUS.get(tool_name, f"Running {tool_name}...")
                    status_callback(status_msg)

                # Execute the tool
                tool_result = self._execute_tool(tool_name, tool_input)

                # Add assistant's response to history
                # For Claude: use the raw response blocks (required for proper tool_result matching)
                # For Ollama: just use the tool info as text
                raw_response = response_data.get("raw")
                if raw_response and hasattr(raw_response, "content"):
                    # Claude response - use original content blocks
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": raw_response.content
                    })
                else:
                    # Ollama or other providers - use text representation
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"[Using tool: {tool_name}]"
                    })

                # Add tool result to history
                self.conversation_history.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_result,
                    }]
                })

                # Continue the loop to get LLM's response based on tool result
                continue

            # LLM is done — extract text response
            elif response_data["type"] == "end_turn":
                text = response_data["content"]

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
        """System prompt for the chatbot."""
        return """You are an operations assistant for Code Ninjas Eastvale Chino.
You help staff manage daily schedules, student appointments, and tours
by querying the center's systems and taking action on their behalf.

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

    def _get_tools(self) -> list:
        """Define tools for Claude to use."""
        return [
            {
                "name": "get_todays_gbs_tours",
                "description": (
                    "Fetches today's GBS tour appointments from LineLeader. "
                    "These are visits by prospective families who have not enrolled yet — "
                    "not current students. Returns guardian name, child name and age, "
                    "tour type (GBS or JR GBS), scheduled time, and assigned staff member."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_tour_details",
                "description": "Get detailed information about a specific tour, including child names and ages",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tour_id": {
                            "type": "string",
                            "description": "The tour ID (item_id from the session list)"
                        }
                    },
                    "required": ["tour_id"]
                }
            },
            {
                "name": "reschedule_tour",
                "description": "Reschedule a tour to a new date and time",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tour_id": {
                            "type": "string",
                            "description": "The tour ID to reschedule"
                        },
                        "new_datetime": {
                            "type": "string",
                            "description": "New date and time in ISO 8601 format (e.g., 2026-05-28T14:30:00Z)"
                        }
                    },
                    "required": ["tour_id", "new_datetime"]
                }
            },
            {
                "name": "get_todays_full_schedule",
                "description": (
                    "Fetches today's complete schedule: both GBS tours from LineLeader "
                    "AND enrolled student class sessions from MyStudio (CREATE CODING, "
                    "SCRATCH PLUS, JR, etc.), merged in chronological order. Use this "
                    "whenever the user asks about today's schedule, what's happening "
                    "today, students coming in, or anything that is not specifically "
                    "limited to prospective family tours only."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """
        Execute a tool and return the result as a string.

        This is where Milestone 1 functions are called.
        """
        try:
            if tool_name == "get_todays_gbs_tours":
                return self._handle_get_todays_tours()
            elif tool_name == "get_tour_details":
                return self._handle_get_tour_details(tool_input)
            elif tool_name == "reschedule_tour":
                return self._handle_reschedule_tour(tool_input)
            elif tool_name == "get_todays_full_schedule":
                return self._handle_get_todays_full_schedule()
            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            logger.error("Tool execution failed: %s", e)
            return f"Error: {str(e)}"

    def _handle_get_todays_tours(self) -> str:
        """Get today's GBS tours."""
        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            sessions = get_todays_sessions(self.bearer_token)
            enrich_sessions_with_children(self.bearer_token, sessions)

            if not sessions:
                return "No tours scheduled for today."

            # Format as readable text with item_id included so Claude can reference it
            lines = [f"Tours for {sessions[0].date_display()}:\n"]
            for i, session in enumerate(sessions, 1):
                children_str = ", ".join(session.child_display) if session.child_display else "(no children listed)"
                lines.append(
                    f"{i}. [ID: {session.item_id}] {session.time_display()} - "
                    f"Parent: {session.student_name} | Children: {children_str} | "
                    f"Type: {session.tour_type} | Staff: {session.assignee_name}"
                )

            result = "\n".join(lines)
            result += "\n\n📥 **Download as Excel:** [Download this schedule](/api/export/tours)"
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to fetch tours: {e}")

    def _handle_get_tour_details(self, tool_input: dict) -> str:
        """Get details about a specific tour."""
        tour_id = tool_input.get("tour_id", "")

        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            sessions = get_todays_sessions(self.bearer_token)
            enrich_sessions_with_children(self.bearer_token, sessions)

            # Find the session by item_id
            session = next((s for s in sessions if s.item_id == tour_id), None)
            if not session:
                return f"Tour {tour_id} not found in today's schedule."

            lines = [
                f"Tour Details:",
                f"  ID: {session.item_id}",
                f"  Time: {session.time_display()}",
                f"  Guardian: {session.student_name}",
                f"  Children: {', '.join(session.child_display) if session.child_display else 'Not available'}",
                f"  Tour Type: {session.tour_type}",
                f"  Assigned To: {session.assignee_name}",
                f"  Location: {session.location_name}",
            ]
            return "\n".join(lines)

        except Exception as e:
            raise RuntimeError(f"Failed to get tour details: {e}")

    def _handle_reschedule_tour(self, tool_input: dict) -> str:
        """Reschedule a tour (calls Milestone 1's reschedule_tour function)."""
        from datetime import datetime

        tour_id = tool_input.get("tour_id", "")
        new_datetime_str = tool_input.get("new_datetime", "")

        try:
            if not self.bearer_token:
                self.bearer_token = asyncio.run(get_bearer_token())

            # Fetch all sessions to find the one to reschedule
            sessions = get_todays_sessions(self.bearer_token)
            session = next((s for s in sessions if s.item_id == tour_id), None)

            if not session:
                return f"Tour {tour_id} not found."

            # Parse the ISO datetime string to a datetime object
            new_local_dt = datetime.fromisoformat(new_datetime_str.replace('Z', '+00:00'))

            # Call the Milestone 1 reschedule function
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

    def _handle_otp_submission(self, user_message: str) -> str:
        """Handle OTP code submitted via chat."""
        otp = user_message.strip()
        if not (otp.isdigit() and len(otp) == 6):
            return (
                "That doesn't look like a 6-digit code. "
                f"Please check {settings.MYSTUDIO_USERNAME} for the OTP email and enter the 6-digit code."
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

    def _handle_get_todays_full_schedule(self) -> str:
        """Get today's full schedule (GBS tours + student appointments, merged and sorted)."""
        try:
            # Fetch GBS tours from LineLeader
            ll_token = asyncio.run(get_bearer_token())
            gbs_sessions = get_todays_sessions(ll_token)
            enrich_sessions_with_children(ll_token, gbs_sessions)

            # Fetch student appointments from MyStudio
            appointments = []
            try:
                appointments = get_todays_appointments()
            except MystudioOTPRequired:
                self._awaiting_mystudio_otp = True
                return (
                    "🔐 **MyStudio verification needed.**\n\n"
                    f"An OTP code was sent to **{settings.MYSTUDIO_USERNAME}**.\n\n"
                    "Please check your email and reply with the **6-digit code** to continue."
                )
            except Exception as e:
                logger.warning("Failed to fetch MyStudio appointments: %s", e)
                appointments = []

            # Cache for Excel export (avoids double API calls)
            self._last_gbs_sessions = gbs_sessions
            self._last_appointments = appointments

            # Format unified schedule
            formatted = format_unified_schedule(gbs_sessions, appointments)

            result = formatted
            result += "\n\n📥 **Download as Excel:** [Download this schedule](/api/export/tours)"
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to fetch full schedule: {e}")
