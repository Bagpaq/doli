#!/usr/bin/env python3
"""
voice_demo.py — Sophia Dental Voice Agent: live voice call demo

You speak into your mic.  Sophia speaks back using OpenAI shimmer TTS.
Same system prompt, tools, and booking logic as the real agent.

Flow per turn:
  1. Press Enter  → starts recording your mic
  2. Press Enter  → stops recording, shows live dB meter while you talk
  3. Whisper API  → transcribes your speech
  4. GPT-4o       → runs the agent loop (may call calendar/email tools)
  5. TTS shimmer  → Sophia speaks the reply out loud via your speakers

Requirements:
    pip install openai sounddevice numpy scipy python-dotenv
    (PortAudio must be installed: brew install portaudio  /  apt install portaudio19-dev)

Usage:
    OPENAI_API_KEY=sk-...  python voice_demo.py
"""

import io
import json
import os
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ── Dependency check ─────────────────────────────────────────────────
_MISSING = []
try:
    import numpy as np
except ImportError:
    _MISSING.append("numpy")
try:
    import sounddevice as sd
except ImportError:
    _MISSING.append("sounddevice")
try:
    import scipy.io.wavfile as wavfile
except ImportError:
    _MISSING.append("scipy")
try:
    import openai
except ImportError:
    _MISSING.append("openai")
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if _MISSING:
    print(f"\n[setup] Installing: {', '.join(_MISSING)}")
    os.system(f"{sys.executable} -m pip install {' '.join(_MISSING)} -q")
    import importlib
    for m in _MISSING:
        importlib.import_module(m.split(".")[0])
    import numpy as np
    import sounddevice as sd
    import scipy.io.wavfile as wavfile

# ─────────────────────────────────────────────────────────────────────
# Audio constants
# ─────────────────────────────────────────────────────────────────────
MIC_RATE   = 16_000   # Whisper optimal sample rate
TTS_RATE   = 24_000   # OpenAI TTS PCM output rate
CHANNELS   = 1
DTYPE      = "int16"

# ─────────────────────────────────────────────────────────────────────
# Console colours
# ─────────────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD  = "\033[1m"
PINK  = "\033[95m"
CYAN  = "\033[96m"
GREY  = "\033[90m"
YELLOW= "\033[93m"
GREEN = "\033[92m"
RED   = "\033[91m"


def _wrap(text: str, width: int = 68, ind: str = "           ") -> str:
    out = []
    for para in text.strip().split("\n"):
        para = para.strip()
        if para:
            out.append(textwrap.fill(para, width=width, subsequent_indent=ind))
        else:
            out.append("")
    return "\n".join(out)


def _sophia(text: str):
    print(f"\n  {PINK}{BOLD}Sophia:{R}  {PINK}{_wrap(text)}{R}\n")


def _user_line(text: str):
    print(f"  {CYAN}{BOLD}   You:{R}  {CYAN}{text}{R}")


def _tool(name: str, args: dict, result: str):
    summary = result[:100] + ("…" if len(result) > 100 else "")
    print(f"  {GREY}[tool] {YELLOW}{name}{GREY} → {summary}{R}")


def _sys(msg: str):
    print(f"  {GREY}[sys]  {msg}{R}")


def _err(msg: str):
    print(f"  {RED}[err]  {msg}{R}")


# ─────────────────────────────────────────────────────────────────────
# Fake calendar (no Google API needed)
# ─────────────────────────────────────────────────────────────────────
BOOKED_TIMES: set[str] = {"09:00", "10:00", "14:00"}
CALENDAR: list[dict]   = []


def _resolve_date(phrase: str) -> str:
    tz = ZoneInfo("America/Chicago")
    today = datetime.now(tz=tz).date()
    p = phrase.strip().lower()
    if p in ("today",):
        return today.strftime("%Y-%m-%d")
    if p in ("tomorrow",):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    WD = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for prefix, offset_base in (("next ", 7), ("this ", 0)):
        if p.startswith(prefix):
            name = p[len(prefix):]
            if name in WD:
                idx = WD.index(name)
                days = (idx - today.weekday() + offset_base) % 7 or offset_base
                return (today + timedelta(days=days)).strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(phrase.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return (today + timedelta(days=1)).strftime("%Y-%m-%d")


def tool_check_slots(preferred_date: str, time_preference: str = "any", duration_minutes: int = 60) -> dict:
    date_str = _resolve_date(preferred_date)
    windows = {"morning": range(8,12), "afternoon": range(12,17), "evening": range(17,20), "any": range(8,18)}
    hours = windows.get(time_preference, range(8, 18))
    tz = ZoneInfo("America/Chicago")
    slots = []
    for h in hours:
        t = f"{h:02d}:00"
        if t not in BOOKED_TIMES:
            y, mo, d = map(int, date_str.split("-"))
            dt = datetime(y, mo, d, h, 0, tzinfo=tz)
            slots.append({"date": date_str, "time": t, "display": dt.strftime("%A, %B %-d at %-I:%M %p")})
        if len(slots) == 3:
            break
    return {"available": bool(slots), "slots": slots}


def tool_book(patient_name, patient_email, date, time, reason, duration_minutes=60) -> dict:
    eid = f"EVT-{len(CALENDAR)+1:04d}"
    CALENDAR.append({"event_id": eid, "patient_name": patient_name,
                     "patient_email": patient_email, "date": date,
                     "time": time, "reason": reason})
    BOOKED_TIMES.add(time)
    _sys(f"[EMAIL CONFIRMATION] → {patient_email} | {patient_name} | {date} {time}")
    return {"success": True, "event_id": eid, "date": date, "time": time,
            "message": f"All booked! {patient_name.split()[0]}'s confirmation email is on its way."}


def tool_cancel(patient_name, patient_email, appointment_date) -> dict:
    for a in CALENDAR:
        if patient_name.lower() in a["patient_name"].lower() and a["date"] == appointment_date:
            CALENDAR.remove(a)
            BOOKED_TIMES.discard(a["time"])
            _sys(f"[EMAIL CANCELLATION] → {patient_email} | {patient_name} | {appointment_date}")
            return {"success": True, "message": f"Cancelled. Confirmation sent to {patient_email}."}
    return {"success": False, "message": f"No appointment found for {patient_name} on {appointment_date}."}


def tool_reschedule(patient_name, patient_email, original_date, new_date, new_time) -> dict:
    for a in CALENDAR:
        if patient_name.lower() in a["patient_name"].lower() and a["date"] == original_date:
            BOOKED_TIMES.discard(a["time"])
            a["date"], a["time"] = new_date, new_time
            BOOKED_TIMES.add(new_time)
            _sys(f"[EMAIL RESCHEDULE] → {patient_email} | {patient_name} | {new_date} {new_time}")
            return {"success": True, "message": f"Rescheduled to {new_date} at {new_time}. Confirmation sent."}
    return {"success": False, "message": f"No appointment found for {patient_name} on {original_date}."}


def tool_find(patient_name, approximate_date="") -> dict:
    matches = [a for a in CALENDAR if patient_name.lower() in a["patient_name"].lower()]
    return {"appointments": matches}


def dispatch(name: str, args: dict) -> str:
    fns = {
        "check_available_slots":   tool_check_slots,
        "book_appointment":        tool_book,
        "cancel_appointment":      tool_cancel,
        "reschedule_appointment":  tool_reschedule,
        "get_appointment_by_name": tool_find,
        "send_confirmation_email": lambda **kw: {"sent": True},
        "send_cancellation_email": lambda **kw: {"sent": True},
    }
    fn = fns.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    result = fn(**args)
    return json.dumps(result)


# ─────────────────────────────────────────────────────────────────────
# OpenAI tool schemas
# ─────────────────────────────────────────────────────────────────────
TOOLS = [
    {"type":"function","function":{"name":"check_available_slots","description":"Check available slots. Call BEFORE offering times.","parameters":{"type":"object","properties":{"preferred_date":{"type":"string"},"time_preference":{"type":"string","enum":["morning","afternoon","evening","any"]},"duration_minutes":{"type":"integer","default":60}},"required":["preferred_date"]}}},
    {"type":"function","function":{"name":"book_appointment","description":"Book appointment. Only after verbal confirmation.","parameters":{"type":"object","properties":{"patient_name":{"type":"string"},"patient_email":{"type":"string"},"date":{"type":"string"},"time":{"type":"string"},"reason":{"type":"string"},"duration_minutes":{"type":"integer","default":60}},"required":["patient_name","patient_email","date","time","reason"]}}},
    {"type":"function","function":{"name":"cancel_appointment","description":"Cancel an existing appointment.","parameters":{"type":"object","properties":{"patient_name":{"type":"string"},"patient_email":{"type":"string"},"appointment_date":{"type":"string"}},"required":["patient_name","patient_email","appointment_date"]}}},
    {"type":"function","function":{"name":"reschedule_appointment","description":"Move appointment to new slot.","parameters":{"type":"object","properties":{"patient_name":{"type":"string"},"patient_email":{"type":"string"},"original_date":{"type":"string"},"new_date":{"type":"string"},"new_time":{"type":"string"}},"required":["patient_name","patient_email","original_date","new_date","new_time"]}}},
    {"type":"function","function":{"name":"get_appointment_by_name","description":"Find appointments by patient name.","parameters":{"type":"object","properties":{"patient_name":{"type":"string"},"approximate_date":{"type":"string"}},"required":["patient_name"]}}},
]

TODAY_STR = datetime.now(ZoneInfo("America/Chicago")).strftime("%A, %B %-d, %Y")

SYSTEM_PROMPT = f"""\
You are Sophia, the warm and professional virtual receptionist for Bright Smile Dental.
Speak in a calm, soft, reassuring tone — like a trusted friend who works at a dental office.
Never robotic, never rushed. Always make patients feel at ease.
Today is {TODAY_STR}.

CLINIC: Bright Smile Dental | 123 Maplewood Drive, Austin TX | (512) 555-0199
HOURS: Mon-Fri 8 AM-5 PM | Sat 9 AM-1 PM | Sun closed

BOOKING RULES:
- Always call check_available_slots before offering times.
- Confirm patient name, email, and slot before calling book_appointment.
- Never invent time slots.

FAQ:
- Insurance: Delta Dental, Cigna, Aetna, BCBS, MetLife accepted.
- Parking: Free lot behind the building.
- Emergency after-hours: (512) 555-0911.

STYLE: Slow, warm, clear. End every call using the patient's first name.
"""


# ─────────────────────────────────────────────────────────────────────
# Audio I/O
# ─────────────────────────────────────────────────────────────────────

def _db(frame: np.ndarray) -> float:
    rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
    return 20 * np.log10(max(rms, 1e-9))


def record_push_to_talk() -> np.ndarray:
    """
    Press Enter to start recording.
    Press Enter again to stop.
    Shows a live dB bar while recording.
    """
    print(f"\n  {GREY}──────────────────────────────────────{R}")
    input(f"  {CYAN}  [ Press Enter to speak… ]{R}  ")

    frames: list[np.ndarray] = []
    stop_event = threading.Event()

    def _callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=MIC_RATE, channels=CHANNELS,
        dtype=DTYPE, callback=_callback, blocksize=1024,
    )

    # Meter thread
    def _meter():
        bar_chars = 30
        while not stop_event.is_set():
            if frames:
                db = _db(frames[-1])
                level = max(0, min(bar_chars, int((db + 60) * bar_chars / 60)))
                bar = f"{'█' * level}{'░' * (bar_chars - level)}"
                colour = GREEN if level > 5 else GREY
                print(f"\r  {colour}  🎙  {bar}  {db:+.0f} dB{R}     ", end="", flush=True)
            time.sleep(0.05)
        print(f"\r{' ' * 60}\r", end="", flush=True)

    meter_thread = threading.Thread(target=_meter, daemon=True)

    with stream:
        meter_thread.start()
        input(f"  {GREY}  [ Recording — press Enter to send ]{R}  ")
        stop_event.set()

    meter_thread.join(timeout=0.3)

    if not frames:
        return np.zeros((1,), dtype=np.int16)
    return np.concatenate(frames, axis=0)


def transcribe(client: openai.OpenAI, audio: np.ndarray) -> str:
    """Send recorded audio to Whisper and return transcript."""
    buf = io.BytesIO()
    wavfile.write(buf, MIC_RATE, audio)
    buf.seek(0)
    buf.name = "speech.wav"

    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language="en",
    )
    return result.text.strip()


def speak(client: openai.OpenAI, text: str) -> None:
    """
    Stream shimmer TTS as raw PCM and play through speakers immediately.
    PCM from OpenAI = 24 kHz, 16-bit, mono, little-endian.
    """
    print(f"  {PINK}  🔊 Sophia is speaking…{R}", flush=True)

    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice="shimmer",
        input=text,
        response_format="pcm",   # raw s16le, 24 kHz
        speed=0.92,              # slightly slower — calm, clear dental voice
    ) as response:
        raw = b"".join(response.iter_bytes(chunk_size=4096))

    audio = np.frombuffer(raw, dtype=np.int16)
    sd.play(audio, samplerate=TTS_RATE)
    sd.wait()


# ─────────────────────────────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────────────────────────────

def agent_turn(client: openai.OpenAI, messages: list) -> str:
    """Run GPT-4o with tool loop until a plain-text reply is ready."""
    while True:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.6,
            max_tokens=200,   # keep responses concise for voice
        )
        choice = resp.choices[0]

        if not choice.message.tool_calls:
            text = choice.message.content or ""
            messages.append({"role": "assistant", "content": text})
            return text

        messages.append(choice.message)
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = dispatch(tc.function.name, args)
            _tool(tc.function.name, args, result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(f"\n{RED}[!] OPENAI_API_KEY not set.{R}")
        print("    Export it or add it to .env and re-run.\n")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)

    # Quick audio device check
    try:
        devices = sd.query_devices()
        input_ok  = any(d["max_input_channels"] > 0  for d in devices)
        output_ok = any(d["max_output_channels"] > 0 for d in devices)
        if not input_ok:
            print(f"\n{RED}[!] No microphone detected. Check your audio input device.{R}\n")
            sys.exit(1)
        if not output_ok:
            print(f"\n{RED}[!] No speaker/output device detected.{R}\n")
            sys.exit(1)
    except Exception as e:
        print(f"\n{RED}[!] Audio device error: {e}{R}\n")
        sys.exit(1)

    print(f"""
{PINK}{BOLD}╔══════════════════════════════════════════════════════════════════╗
║        Sophia — Bright Smile Dental  ·  LIVE VOICE DEMO         ║
╠══════════════════════════════════════════════════════════════════╣
║  Voice:  OpenAI shimmer TTS  (same as real agent)               ║
║  STT:    Whisper-1  (your mic → text)                           ║
║  Brain:  GPT-4o  + dental booking tools                         ║
╠══════════════════════════════════════════════════════════════════╣
║  HOW TO USE:                                                     ║
║    1. Press Enter  →  start speaking                             ║
║    2. Press Enter  →  stop & send                                ║
║    3. Listen to Sophia's voice reply                             ║
║    Type  'quit'  to end the call                                 ║
╚══════════════════════════════════════════════════════════════════╝{R}
""")

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ── Opening greeting (voice only, no mic) ────────────────────────
    greeting_text = (
        "Hello, thank you for calling Bright Smile Dental. "
        "This is Sophia speaking. How can I help you today?"
    )
    _sophia(greeting_text)
    speak(client, greeting_text)
    messages.append({"role": "assistant", "content": greeting_text})

    # ── Conversation loop ────────────────────────────────────────────
    while True:
        # Record
        audio = record_push_to_talk()

        if audio.size < MIC_RATE * 0.3:   # less than 0.3 s → probably empty
            print(f"  {GREY}(no audio detected — try again){R}")
            continue

        # Transcribe
        print(f"  {GREY}  transcribing…{R}", end="\r", flush=True)
        try:
            user_text = transcribe(client, audio)
        except openai.OpenAIError as e:
            _err(f"Whisper error: {e}")
            continue

        if not user_text:
            print(f"  {GREY}(could not understand — try again){R}")
            continue

        _user_line(user_text)

        if user_text.strip().lower() in ("quit", "exit", "goodbye", "bye", "hang up"):
            farewell = "Thank you for calling Bright Smile Dental. Have a wonderful day — goodbye!"
            _sophia(farewell)
            speak(client, farewell)
            break

        messages.append({"role": "user", "content": user_text})

        # Agent turn
        print(f"  {GREY}  thinking…{R}", end="\r", flush=True)
        try:
            reply = agent_turn(client, messages)
        except openai.OpenAIError as e:
            _err(f"API error: {e}")
            continue

        _sophia(reply)
        speak(client, reply)


if __name__ == "__main__":
    main()
