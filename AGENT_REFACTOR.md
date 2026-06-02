# CNEC Chatbot — Agent Architecture Refactor
**Prepared for implementation | June 2026**

---

## Why This Refactor

The current `chatbot.py` works, but the system prompt and tool definitions are
doing jobs they shouldn't be doing. As we add Milestones 3–6, the prompt will
accumulate routing rules, format templates, and tool-selection logic that has
to be manually updated every time a new capability is added. That's a
maintenance trap.

This document describes what to change, why, and exactly how to do it.

---

## The Core Diagnosis

The system prompt is currently doing two separate jobs:

1. **Agent identity** — who Claude is, what it can do, what it must never do
   without confirmation. This should be *stable* — it rarely changes.

2. **Procedural instruction** — which tool to call when, how to format output,
   which emoji to use in which position. This is the part that rots as the
   project grows.

Every new milestone currently means editing the system prompt. After this
refactor, adding a new milestone means adding a `_register()` call and a
handler method. The system prompt never changes.

---

## Change 1 — Rewrite the System Prompt

### Current problem

The prompt contains routing rules:

```
IMPORTANT TOOL SELECTION RULES:
- If the user asks for "schedule", "today's schedule"... → use get_todays_full_schedule
- Only use get_todays_gbs_tours if the user specifically asks about "tours"...
- When in doubt, use get_todays_full_schedule
```

And format templates:

```
When displaying schedules, use this nested bullet format:
📅 Date
  ⏰ Time
    👨‍👩‍👧 Parent Name
    ...

ALWAYS include this at the end of every schedule display:
📥 **Download as Excel:** [Download this schedule](/api/export/tours)
```

These rules exist because the tool descriptions weren't clear enough to let
Claude decide on its own. The fix is better tool descriptions — not more rules
in the prompt.

### What the prompt should contain

An agent system prompt has three things and only three things:

1. **Identity** — who you are and who you serve
2. **Safety constraints** — what you must never do without confirmation
3. **Tone** — how you communicate

### New system prompt

```python
def _get_system_prompt(self) -> str:
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
```

That's it. No format instructions. No tool routing rules. No emoji templates.

---

## Change 2 — Fix the Tool Descriptions

Routing rules exist in the system prompt *because* the tool descriptions
aren't unambiguous enough to let Claude decide on its own. Better descriptions
eliminate the need for the rules.

### Principle

Tool descriptions should answer: *"What data does this tool return, and when
is it the right tool to reach for?"* They should NOT describe routing logic
("use X not Y when the user says Z").

### Current descriptions (the problem)

```python
# get_todays_gbs_tours
"Get ONLY the GBS tours... Use this only when the user specifically
asks about tours or GBS tours. For general schedule questions, use
get_todays_full_schedule instead."

# get_todays_full_schedule
"Get today's COMPLETE schedule... Use this for any general question
about today's schedule, students, or classes."
```

The second sentence of each description is routing instruction. That's what
forced you to add `IMPORTANT TOOL SELECTION RULES` to the prompt.

### New descriptions (the fix)

```python
{
    "name": "get_todays_gbs_tours",
    "description": (
        "Fetches today's GBS tour appointments from LineLeader. "
        "These are visits by prospective families who have not enrolled yet — "
        "not current students. Returns guardian name, child name and age, "
        "tour type (GBS or JR GBS), scheduled time, and assigned staff member."
    ),
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
},
```

Now Claude can choose the right tool without being told. The routing rules in
the system prompt become unnecessary and can be removed.

---

## Change 3 — Move Format Instructions Into Tool Handlers

### Current problem

The system prompt tells Claude how to render schedule output:

```
When displaying schedules, use this nested bullet format:
📅 Date
  ⏰ Time
    👨‍👩‍👧 Parent Name
    ...
```

This is fragile. If you change the output format, you must remember to update
the system prompt. If Claude doesn't follow the template exactly, output is
inconsistent.

### The fix

Format the data *before* returning it from the tool. Claude's job is to
understand intent and call tools. Python's job is to present data well.

You already have `format_unified_schedule()` in `format_tours.py`. The tool
handlers should return pre-formatted, human-readable text. Claude then adds a
sentence of context and passes it through — no formatting instructions needed.

The Excel download link (`📥 **Download as Excel:**...`) is already appended
by the tool handler. Keep doing that — it's the right pattern. Remove the
copy of that instruction from the system prompt.

**Before (system prompt carries format responsibility):**
```
System prompt: "use this nested bullet format: 📅 Date ⏰ Time..."
Tool returns: raw data
Claude renders: formatted output (sometimes correctly, sometimes not)
```

**After (tool handler carries format responsibility):**
```
System prompt: nothing about format
Tool returns: already-formatted, human-readable text
Claude renders: passes through with light framing
```

---

## Change 4 — Replace the Tool List With a Registry Pattern

### Current problem

All tools are defined in one `_get_tools()` method and dispatched in one
`_execute_tool()` if/elif chain. Adding a Milestone 3 tool means editing both
methods. As the project grows, these become walls of code.

### The fix — a tool registry

Each tool is registered once with its definition and its handler attached
together. Adding a new tool is one `_register()` call and one handler method.
`_get_tools()` and `_execute_tool()` never need to be touched again.

```python
class ChatbotEngine:

    def __init__(self, provider=None):
        self.provider = provider or get_provider()
        self.conversation_history = []
        self.bearer_token = None
        self._awaiting_mystudio_otp = False

        # Tool registry: name → {definition, handler}
        # Add new tools via _register() in _register_tools() only
        self._tools = {}
        self._register_tools()

    def _register_tools(self):
        """
        Register all available tools.
        To add a new tool: add a _register() call here + a handler method below.
        Nothing else needs to change.
        """
        self._register(
            name="get_todays_full_schedule",
            description=(
                "Fetches today's complete schedule: both GBS tours from LineLeader "
                "AND enrolled student class sessions from MyStudio (CREATE CODING, "
                "SCRATCH PLUS, JR, etc.), merged in chronological order. Use this "
                "whenever the user asks about today's schedule, what's happening "
                "today, students coming in, or anything that is not specifically "
                "limited to prospective family tours only."
            ),
            parameters={},
            handler=self._handle_get_todays_full_schedule,
        )
        self._register(
            name="get_todays_gbs_tours",
            description=(
                "Fetches today's GBS tour appointments from LineLeader. "
                "These are visits by prospective families who have not enrolled yet — "
                "not current students. Returns guardian name, child name and age, "
                "tour type (GBS or JR GBS), scheduled time, and assigned staff member."
            ),
            parameters={},
            handler=self._handle_get_todays_tours,
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
                "new_datetime": {
                    "type": "string",
                    "description": "New date and time in ISO 8601 format (e.g. 2026-05-28T14:30:00Z)",
                },
            },
            handler=self._handle_reschedule_tour,
        )
        # MILESTONE 3 — uncomment when implemented:
        # self._register(
        #     name="lookup_student",
        #     description="Look up a student by name...",
        #     parameters={"student_name": {"type": "string", "description": "..."}},
        #     handler=self._handle_lookup_student,
        # )

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
```

Note: handler signatures change slightly. Instead of some handlers taking
`(self)` and others taking `(self, tool_input)`, all handlers now take
`(self, tool_input: dict)`. Handlers that don't need input just ignore it.

```python
# Before (inconsistent signatures):
def _handle_get_todays_tours(self) -> str: ...
def _handle_reschedule_tour(self, tool_input: dict) -> str: ...

# After (consistent — all handlers take tool_input):
def _handle_get_todays_tours(self, tool_input: dict) -> str: ...
def _handle_get_todays_full_schedule(self, tool_input: dict) -> str: ...
def _handle_reschedule_tour(self, tool_input: dict) -> str: ...
```

---

## What Doesn't Change

- The agentic loop in `chat()` — it's clean and correct as-is
- The OTP handling flow — keep `_awaiting_mystudio_otp` and `_handle_otp_submission()`
- The provider abstraction in `llm_provider.py` — it's the right pattern
- `_TOOL_STATUS` for user-facing status messages — useful, keep it
- Token caching (`self.bearer_token`) — keep as-is
- The `_last_gbs_sessions` / `_last_appointments` cache for Excel export — keep

---

## What Each Milestone Looks Like After This Refactor

### Adding Milestone 3 — Student Lookup

```python
# In _register_tools(), add:
self._register(
    name="lookup_student",
    description=(
        "Looks up a student by name and returns their attendance this week "
        "and upcoming scheduled sessions. Use when the user asks how many "
        "times a student has come in, what their schedule looks like, or "
        "anything about a specific named student."
    ),
    parameters={
        "student_name": {
            "type": "string",
            "description": "First name, last name, or partial name of the student",
        }
    },
    handler=self._handle_lookup_student,
)

# Then add the handler:
def _handle_lookup_student(self, tool_input: dict) -> str:
    student_name = tool_input.get("student_name", "")
    # ... implementation ...
```

System prompt: unchanged. `_get_tools()`: unchanged. `_execute_tool()`: unchanged.

---

## Summary Table

| Area | Current | After refactor |
|------|---------|----------------|
| System prompt | Routing rules + format templates + identity | Identity + safety rules + tone only |
| Tool descriptions | Include routing instructions ("use X not Y") | Describe data returned + when appropriate |
| Format instructions | In the system prompt as emoji templates | In Python tool handlers; Claude passes through |
| Tool registration | One `_get_tools()` list + one `_execute_tool()` if/elif chain | Registry: `_register()` per tool, handler attached |
| Adding a new tool | Edit `_get_tools()` + edit `_execute_tool()` + maybe edit system prompt | Add one `_register()` call + one handler method |
| Handler signatures | Inconsistent (`self` vs `self, tool_input`) | Consistent: all take `(self, tool_input: dict)` |

---

## Implementation Notes for Claude Code

- Rewrite `_get_system_prompt()` with the new prompt above
- Replace `_get_tools()` and `_execute_tool()` with the registry pattern above
- Add `_register_tools()` and `_register()` methods
- Update all handler signatures to `(self, tool_input: dict)`
- Remove `get_tour_details` from the tool list — it's not called in practice
  and `get_todays_full_schedule` covers the use case. Can be re-added later
  if needed as a focused tool.
- Keep all existing handler logic intact — this refactor is structural,
  not a rewrite of the underlying API calls

The existing `chat()` agentic loop does not need changes.
