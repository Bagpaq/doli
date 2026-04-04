#!/usr/bin/env python3
"""
demo.py — Sophia Dental Voice Agent: interactive terminal demo

Simulates a real phone call without LiveKit or any API keys.
Sophia is played by GPT-4o (text mode) using the same system prompt,
tools, and flows as the real agent.

Usage:
    pip install openai pyyaml python-dotenv
    export OPENAI_API_KEY=sk-...
    python demo.py

    # Or pass a key inline:
    OPENAI_API_KEY=sk-... python demo.py
"""

import json
import os
import sys
import textwrap
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ── Minimal deps check ────────────────────────────────────────────────
try:
    import openai
    import yaml
    from dotenv import load_dotenv
except ImportError:
    print("\n[setup] Installing required packages...\n")
    os.system(f"{sys.executable} -m pip install openai pyyaml python-dotenv -q")
    import openai
    import yaml
    from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────
# Fake calendar — generates realistic free slots without any Google API
# ─────────────────────────────────────────────────────────────────────

FAKE_BOOKED_SLOTS = {
    # Pre-booked slots so the calendar isn't totally empty
    "09:00", "10:00", "14:00",
}

def fake_check_available_slots(preferred_date: str, time_preference: str = "any", duration_minutes: int = 60) -> dict:
    tz = ZoneInfo("America/Chicago")
    today = datetime.now(tz=tz).date()

    # Resolve natural phrases
    phrase = preferred_date.strip().lower()
    if phrase == "today":
        target = today
    elif phrase == "tomorrow":
        target = today + timedelta(days=1)
    elif phrase.startswith("next "):
        wd = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        name = phrase[5:]
        if name in wd:
            idx = wd.index(name)
            days = (idx - today.weekday() + 7) % 7 or 7
            target = today + timedelta(days=days)
        else:
            target = today + timedelta(days=1)
    else:
        try:
            target = datetime.strptime(preferred_date, "%Y-%m-%d").date()
        except ValueError:
            target = today + timedelta(days=1)

    windows = {
        "morning":   range(8, 12),
        "afternoon": range(12, 17),
        "evening":   range(17, 20),
        "any":       range(8, 18),
    }
    hours = windows.get(time_preference, range(8, 18))

    free = []
    for h in hours:
        slot_time = f"{h:02d}:00"
        if slot_time not in FAKE_BOOKED_SLOTS:
            slot_dt = datetime(target.year, target.month, target.day, h, 0, tzinfo=tz)
            free.append({
                "date": target.strftime("%Y-%m-%d"),
                "time": slot_time,
                "display": slot_dt.strftime("%A, %B %-d at %-I:%M %p"),
            })
        if len(free) == 3:
            break

    return {"available": bool(free), "slots": free}


FAKE_CALENDAR: list[dict] = []  # Appointments booked during this session

def fake_book_appointment(patient_name, patient_email, date, time, reason, duration_minutes=60) -> dict:
    event_id = f"EVT-{len(FAKE_CALENDAR)+1:04d}"
    FAKE_CALENDAR.append({
        "event_id": event_id,
        "patient_name": patient_name,
        "patient_email": patient_email,
        "date": date,
        "time": time,
        "reason": reason,
    })
    FAKE_BOOKED_SLOTS.add(time)
    return {
        "success": True,
        "event_id": event_id,
        "patient_name": patient_name,
        "date": date,
        "time": time,
        "message": (
            f"Wonderful! I've got you booked for {date} at {time}. "
            f"A confirmation email has been sent to {patient_email}. "
            f"We look forward to seeing you, {patient_name.split()[0]}. Take care!"
        ),
    }

def fake_cancel_appointment(patient_name, patient_email, appointment_date) -> dict:
    for appt in FAKE_CALENDAR:
        if patient_name.lower() in appt["patient_name"].lower() and appt["date"] == appointment_date:
            FAKE_CALENDAR.remove(appt)
            FAKE_BOOKED_SLOTS.discard(appt["time"])
            first = patient_name.split()[0]
            return {
                "success": True,
                "message": (
                    f"Done, {first}. Your appointment on {appointment_date} has been cancelled. "
                    "A cancellation confirmation has been sent to your email. "
                    "If you'd like to rebook in the future, don't hesitate to call us. Take care!"
                ),
            }
    return {
        "success": False,
        "message": (
            f"I couldn't find an appointment for {patient_name} on {appointment_date}. "
            "Could you double-check the date?"
        ),
    }

def fake_reschedule_appointment(patient_name, patient_email, original_date, new_date, new_time) -> dict:
    for appt in FAKE_CALENDAR:
        if patient_name.lower() in appt["patient_name"].lower() and appt["date"] == original_date:
            FAKE_BOOKED_SLOTS.discard(appt["time"])
            appt["date"] = new_date
            appt["time"] = new_time
            FAKE_BOOKED_SLOTS.add(new_time)
            first = patient_name.split()[0]
            return {
                "success": True,
                "message": (
                    f"All done, {first}! Your appointment has been moved to "
                    f"{new_date} at {new_time}. "
                    "An updated confirmation has been sent to your email. We'll see you then!"
                ),
            }
    return {
        "success": False,
        "message": f"I couldn't find an existing appointment for {patient_name} on {original_date}.",
    }

def fake_get_appointment_by_name(patient_name, approximate_date="") -> dict:
    matches = [
        a for a in FAKE_CALENDAR
        if patient_name.lower() in a["patient_name"].lower()
    ]
    return {"appointments": matches}

def fake_send_email(kind: str, patient_name: str, patient_email: str, date: str, time: str) -> dict:
    # Just logs to console in demo mode
    _print_system(
        f"[EMAIL {kind.upper()}] → {patient_email} | "
        f"{patient_name} | {date} {time}"
    )
    return {"sent": True}


# ─────────────────────────────────────────────────────────────────────
# Tool definitions sent to the OpenAI API
# ─────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_available_slots",
            "description": "Check available appointment slots. Call this BEFORE offering times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preferred_date": {"type": "string", "description": "YYYY-MM-DD or 'tomorrow', 'next Monday' etc."},
                    "time_preference": {"type": "string", "enum": ["morning", "afternoon", "evening", "any"]},
                    "duration_minutes": {"type": "integer", "default": 60},
                },
                "required": ["preferred_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment and send confirmation email. Only call after verbal confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":     {"type": "string"},
                    "patient_email":    {"type": "string"},
                    "date":             {"type": "string", "description": "YYYY-MM-DD"},
                    "time":             {"type": "string", "description": "HH:MM (24h)"},
                    "reason":           {"type": "string"},
                    "duration_minutes": {"type": "integer", "default": 60},
                },
                "required": ["patient_name", "patient_email", "date", "time", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Move an existing appointment to a new date and time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":   {"type": "string"},
                    "patient_email":  {"type": "string"},
                    "original_date":  {"type": "string", "description": "YYYY-MM-DD"},
                    "new_date":       {"type": "string", "description": "YYYY-MM-DD"},
                    "new_time":       {"type": "string", "description": "HH:MM (24h)"},
                },
                "required": ["patient_name", "patient_email", "original_date", "new_date", "new_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":       {"type": "string"},
                    "patient_email":      {"type": "string"},
                    "appointment_date":   {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["patient_name", "patient_email", "appointment_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointment_by_name",
            "description": "Look up existing appointments by patient name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":    {"type": "string"},
                    "approximate_date": {"type": "string"},
                },
                "required": ["patient_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_confirmation_email",
            "description": "Send booking confirmation email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":  {"type": "string"},
                    "patient_email": {"type": "string"},
                    "date":          {"type": "string"},
                    "time":          {"type": "string"},
                },
                "required": ["patient_name", "patient_email", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_cancellation_email",
            "description": "Send cancellation confirmation email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name":  {"type": "string"},
                    "patient_email": {"type": "string"},
                    "date":          {"type": "string"},
                    "time":          {"type": "string"},
                },
                "required": ["patient_name", "patient_email", "date", "time"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────
# Tool dispatcher
# ─────────────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "check_available_slots":
        return json.dumps(fake_check_available_slots(**args))
    if name == "book_appointment":
        return json.dumps(fake_book_appointment(**args))
    if name == "cancel_appointment":
        return json.dumps(fake_cancel_appointment(**args))
    if name == "reschedule_appointment":
        return json.dumps(fake_reschedule_appointment(**args))
    if name == "get_appointment_by_name":
        return json.dumps(fake_get_appointment_by_name(**args))
    if name == "send_confirmation_email":
        return json.dumps(fake_send_email("confirmation", **args))
    if name == "send_cancellation_email":
        return json.dumps(fake_send_email("cancellation", **args))
    return json.dumps({"error": f"Unknown tool: {name}"})


# ─────────────────────────────────────────────────────────────────────
# System prompt (identical to what the real Realtime agent uses)
# ─────────────────────────────────────────────────────────────────────

TODAY = datetime.now(ZoneInfo("America/Chicago")).strftime("%A, %B %-d, %Y")

SYSTEM_PROMPT = f"""\
You are Sophia, the warm and professional virtual receptionist for Bright Smile Dental.
You speak in a calm, soft, reassuring tone — like a trusted friend who happens to work
at a dental office. You are never robotic, never rushed, and always make patients feel at ease.

Today's date is {TODAY}.

Your goal is to help patients book, reschedule, or cancel appointments efficiently and warmly.
Always confirm details back to the patient before finalising anything.
Never make up available time slots — always call check_available_slots first.
If you cannot help, offer to have a human call them back.

CLINIC DETAILS:
  Name:    Bright Smile Dental
  Address: 123 Maplewood Drive, Suite 4, Austin, TX 78701
  Phone:   (512) 555-0199
  Email:   hello@brightsmileaustin.com

BUSINESS HOURS:
  Monday–Friday: 8:00 AM – 5:00 PM
  Saturday:      9:00 AM – 1:00 PM
  Sunday:        Closed

FREQUENTLY ASKED QUESTIONS:
  Q: insurance
  A: We accept Delta Dental, Cigna, Aetna, BlueCross BlueShield, and MetLife.
     We also offer flexible payment plans for uninsured patients.

  Q: parking
  A: Free parking is available in the lot directly behind our building on Maplewood Drive.

  Q: emergency
  A: For after-hours dental emergencies, call (512) 555-0911.
     For severe pain or swelling, go to the nearest ER.

  Q: new patients
  A: New patients are always welcome! Please arrive 15 minutes early for paperwork.

BOOKING RULES:
  - Appointments are 60 minutes by default.
  - ALWAYS call check_available_slots before offering any time slots.
  - ALWAYS confirm patient name, email, and chosen slot before calling book_appointment.
  - NEVER invent available times.

CONVERSATION STYLE:
  - Speak slowly and clearly — this is a medical context.
  - Be warm, calm, and reassuring at all times.
  - End every call warmly, using the patient's first name.
"""


# ─────────────────────────────────────────────────────────────────────
# Console formatting
# ─────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GREY   = "\033[90m"
PINK   = "\033[95m"


def _wrap(text: str, width: int = 72, indent: str = "    ") -> str:
    lines = []
    for paragraph in text.split("\n"):
        if paragraph.strip():
            lines.append(textwrap.fill(paragraph, width=width, subsequent_indent=indent))
        else:
            lines.append("")
    return "\n".join(lines)


def _print_sophia(text: str) -> None:
    print(f"\n{PINK}{BOLD}  Sophia:{RESET}  {PINK}{_wrap(text)}{RESET}\n")


def _print_user(text: str) -> None:
    print(f"{CYAN}{BOLD}    You:{RESET}  {CYAN}{text}{RESET}")


def _print_tool(name: str, args: dict, result: str) -> None:
    short = json.loads(result)
    # Only show a brief summary
    summary = json.dumps(short, ensure_ascii=False)[:120]
    if len(json.dumps(short)) > 120:
        summary += "…"
    print(f"  {GREY}[tool] {YELLOW}{name}{GREY}({json.dumps(args)[:60]}…){RESET}")
    print(f"  {GREY}       → {summary}{RESET}")


def _print_system(msg: str) -> None:
    print(f"  {GREY}[sys]  {msg}{RESET}")


def _print_divider() -> None:
    print(f"\n{GREY}{'─' * 72}{RESET}")


def _print_calendar() -> None:
    if not FAKE_CALENDAR:
        print(f"  {GREY}(calendar is empty){RESET}")
        return
    for a in FAKE_CALENDAR:
        print(
            f"  {GREEN}✓{RESET}  {BOLD}{a['patient_name']}{RESET}"
            f"  |  {a['date']} {a['time']}"
            f"  |  {a['reason']}"
            f"  |  {a['patient_email']}"
        )


# ─────────────────────────────────────────────────────────────────────
# Main conversation loop
# ─────────────────────────────────────────────────────────────────────

def run_demo() -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(f"\n{YELLOW}[!] OPENAI_API_KEY not set.{RESET}")
        print("    Set it in your environment or .env file and re-run.\n")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)

    print(f"""
{PINK}{BOLD}╔══════════════════════════════════════════════════════════════════╗
║          Sophia — Bright Smile Dental  (DEMO MODE)              ║
║   Simulates a live phone call using the same logic as the        ║
║   real LiveKit + OpenAI Realtime agent.                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Commands:  'quit' or 'exit' to end  |  'calendar' to peek      ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
""")

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Sophia opens the call
    opening = _get_sophia_reply(client, messages)
    messages.append({"role": "assistant", "content": opening})
    _print_sophia(opening)

    while True:
        try:
            user_input = input(f"{CYAN}{BOLD}    You:{RESET}  ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[call ended]\n")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
            print(f"\n{GREY}[call ended by user]{RESET}\n")
            break

        if user_input.lower() == "calendar":
            _print_divider()
            print(f"  {BOLD}Current calendar:{RESET}")
            _print_calendar()
            _print_divider()
            continue

        messages.append({"role": "user", "content": user_input})

        # Run the agent (may call tools in a loop)
        response_text = _agent_turn(client, messages)
        _print_sophia(response_text)


def _get_sophia_reply(client: openai.OpenAI, messages: list) -> str:
    """Single non-tool response from the model."""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS,
        temperature=0.6,
        max_tokens=300,
    )
    return resp.choices[0].message.content or ""


def _agent_turn(client: openai.OpenAI, messages: list) -> str:
    """
    Full agentic loop: calls the model, executes any tool calls,
    feeds results back, repeats until the model returns a plain text reply.
    """
    while True:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.6,
            max_tokens=400,
        )
        choice = resp.choices[0]

        # No tool calls — plain text reply
        if not choice.message.tool_calls:
            final_text = choice.message.content or ""
            messages.append({"role": "assistant", "content": final_text})
            return final_text

        # Tool calls — execute them and loop
        messages.append(choice.message)

        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = dispatch_tool(tc.function.name, args)
            _print_tool(tc.function.name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        # Loop — model will now see tool results and continue


# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_demo()
