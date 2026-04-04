"""
ReminderCaller — outbound appointment reminder module.

Reads tomorrow's appointments from Google Calendar and calls each patient
via LiveKit SIP to remind them of their upcoming visit. Patients can
confirm or cancel during the call.

Usage (run as a standalone cron/scheduler):
    python -m outbound.reminder_caller

Or schedule via the provided docker-compose service.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from livekit import api as lk_api
from livekit.agents import AgentSession, WorkerOptions, cli
from livekit.plugins import openai as lk_openai
from livekit.plugins import silero

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parents[1] / "agent"))

from config_loader import load_clinic_config
from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool

load_dotenv()
logger = logging.getLogger(__name__)

CLINIC_CONFIG_PATH = os.getenv("CLINIC_CONFIG_PATH", "config/businesses/dental-clinic.yaml")


class ReminderCaller:
    """
    Fetches tomorrow's calendar appointments and places outbound SIP calls
    to remind patients using Sophia's voice.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.calendar = CalendarTool(config)
        self.email = EmailTool(config)
        self.timezone = config.get("clinic", {}).get("timezone", "America/New_York")

    async def run_daily_reminders(self) -> None:
        """Main entry point — call this once per day (e.g. at 10 AM)."""
        tomorrow = (datetime.now(tz=ZoneInfo(self.timezone)) + timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info("Fetching appointments for %s", tomorrow)

        appointments = await self._get_tomorrows_appointments(tomorrow)

        if not appointments:
            logger.info("No appointments tomorrow — nothing to do.")
            return

        logger.info("Found %d appointment(s) — placing reminder calls.", len(appointments))

        for appt in appointments:
            await self._place_reminder_call(appt)
            await asyncio.sleep(5)   # Brief gap between calls

    async def _get_tomorrows_appointments(self, date_str: str) -> list[dict]:
        """Return all calendar events on date_str that look like patient appointments."""
        tz = ZoneInfo(self.timezone)
        slots = await self.calendar.get_available_slots(
            preferred_date=date_str,
            time_preference="any",
            duration_minutes=60,
        )
        # We actually want *booked* events, not free slots — use events.list directly
        day_start = datetime(
            *[int(x) for x in date_str.split("-")], 0, 0, tzinfo=tz
        )
        day_end = day_start + timedelta(days=1)

        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.calendar._service_call().events().list(
                    calendarId=self.calendar.calendar_id,
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute(),
            )
        except Exception as exc:
            logger.error("Could not fetch calendar events: %s", exc)
            return []

        results = []
        for ev in raw.get("items", []):
            attendees = ev.get("attendees", [])
            if not attendees:
                continue
            patient = attendees[0]
            results.append({
                "event_id": ev["id"],
                "patient_name": patient.get("displayName", "Valued Patient"),
                "patient_email": patient.get("email", ""),
                "date": date_str,
                "time": ev["start"].get("dateTime", "")[-14:-9] if "T" in ev["start"].get("dateTime", "") else "",
                "summary": ev.get("summary", "Dental Appointment"),
            })
        return results

    async def _place_reminder_call(self, appt: dict) -> None:
        """
        Initiate an outbound SIP call via LiveKit to the patient.

        The patient's phone number must be stored in the calendar event
        description or in a separate contacts store. This implementation
        reads it from the event description field in the format:
            Phone: +15125550100
        """
        phone = self._extract_phone(appt)
        if not phone:
            logger.warning(
                "No phone number found for %s — skipping call, sending email instead.",
                appt["patient_name"],
            )
            # Fall back to email reminder
            await self.email.send_reminder(
                patient_name=appt["patient_name"],
                patient_email=appt["patient_email"],
                date=appt["date"],
                time=appt["time"],
            )
            return

        logger.info(
            "Calling %s at %s for appointment on %s %s",
            appt["patient_name"], phone, appt["date"], appt["time"],
        )

        livekit_url = os.getenv("LIVEKIT_URL", "")
        api_key = os.getenv("LIVEKIT_API_KEY", "")
        api_secret = os.getenv("LIVEKIT_API_SECRET", "")

        try:
            lk_client = lk_api.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)

            # Create a room for this reminder call
            room_name = f"reminder-{appt['event_id'][:8]}"
            await lk_client.room.create_room(lk_api.CreateRoomRequest(name=room_name))

            # Dispatch an agent job with reminder metadata
            await lk_client.agent.create_agent_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    agent_name="dental-reminder-agent",
                    room=room_name,
                    metadata=str({
                        "mode": "outbound_reminder",
                        "patient_name": appt["patient_name"],
                        "patient_email": appt["patient_email"],
                        "date": appt["date"],
                        "time": appt["time"],
                        "phone": phone,
                    }),
                )
            )

            # Create SIP participant (outbound call)
            sip_trunk_id = os.getenv("LIVEKIT_SIP_TRUNK_ID", "")
            if sip_trunk_id:
                await lk_client.sip.create_sip_participant(
                    lk_api.CreateSIPParticipantRequest(
                        sip_trunk_id=sip_trunk_id,
                        sip_url=f"sip:{phone}",
                        room_name=room_name,
                        participant_name=appt["patient_name"],
                    )
                )

            logger.info("Outbound call placed to %s (%s)", appt["patient_name"], phone)

        except Exception as exc:
            logger.error("Failed to place call to %s: %s", appt["patient_name"], exc)
            # Fallback to email
            await self.email.send_reminder(
                patient_name=appt["patient_name"],
                patient_email=appt["patient_email"],
                date=appt["date"],
                time=appt["time"],
            )

    def _extract_phone(self, appt: dict) -> str:
        """Extract phone number from the event description field."""
        description = appt.get("description", "")
        for line in description.splitlines():
            if line.lower().startswith("phone:"):
                return line.split(":", 1)[1].strip()
        return ""


# ------------------------------------------------------------------
# Standalone entrypoint for cron / Docker
# ------------------------------------------------------------------

async def _main() -> None:
    config = load_clinic_config(CLINIC_CONFIG_PATH)
    caller = ReminderCaller(config)
    await caller.run_daily_reminders()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
