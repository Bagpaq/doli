"""
CalendarTool — Google Calendar integration for Sophia.

Uses a Google Service Account (JSON key file) to read/write events
on the clinic's Google Calendar.

All public methods are async-friendly (run_in_executor wraps sync SDK calls).
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Slot durations returned as ISO 8601 strings like "10:00" or "14:30"
_TIME_WINDOWS = {
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 20),
    "any": (8, 20),
}


class CalendarTool:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.calendar_id: str = os.getenv(
            "GOOGLE_CALENDAR_ID",
            config.get("google", {}).get("calendar_id", "primary"),
        )
        self.timezone: str = config.get("clinic", {}).get("timezone", "America/New_York")
        self._service = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_available_slots(
        self,
        preferred_date: str,
        time_preference: str = "any",
        duration_minutes: int = 60,
    ) -> list[dict]:
        """
        Return up to 5 free slots on `preferred_date`.

        preferred_date: "YYYY-MM-DD" or natural phrase resolved by _parse_date().
        time_preference: 'morning' | 'afternoon' | 'evening' | 'any'
        duration_minutes: length of the desired appointment.

        Returns list of dicts: [{"date": "YYYY-MM-DD", "time": "HH:MM", "display": "..."}]
        """
        target_date = _parse_date(preferred_date, self.timezone)
        if target_date is None:
            logger.warning("Could not parse date: %s", preferred_date)
            return []

        start_hour, end_hour = _TIME_WINDOWS.get(time_preference, (8, 20))

        # Fetch busy periods for the day
        tz = ZoneInfo(self.timezone)
        day_start = datetime.combine(target_date, dt_time(start_hour, 0), tzinfo=tz)
        day_end = datetime.combine(target_date, dt_time(end_hour, 0), tzinfo=tz)

        busy = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._get_busy_periods(day_start, day_end),
        )

        free_slots = _compute_free_slots(
            day_start, day_end, busy, duration_minutes
        )

        return [
            {
                "date": slot.strftime("%Y-%m-%d"),
                "time": slot.strftime("%H:%M"),
                "display": slot.strftime("%A, %B %-d at %-I:%M %p"),
            }
            for slot in free_slots[:5]
        ]

    async def book_appointment(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
        reason: str,
        duration_minutes: int = 60,
    ) -> dict:
        """Create a Google Calendar event. Returns event dict with 'event_id'."""
        tz = ZoneInfo(self.timezone)
        dt_start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        dt_end = dt_start + timedelta(minutes=duration_minutes)

        clinic = self.config.get("clinic", {})
        event_body = {
            "summary": f"Dental Appt — {patient_name}",
            "description": (
                f"Reason: {reason}\n"
                f"Patient: {patient_name}\n"
                f"Email: {patient_email}\n"
                f"Booked via Sophia (AI Receptionist)"
            ),
            "location": clinic.get("address", ""),
            "start": {
                "dateTime": dt_start.isoformat(),
                "timeZone": self.timezone,
            },
            "end": {
                "dateTime": dt_end.isoformat(),
                "timeZone": self.timezone,
            },
            "attendees": [
                {"email": patient_email, "displayName": patient_name},
            ],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 60},
                ],
            },
        }

        try:
            created = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._service_call().events().insert(
                    calendarId=self.calendar_id,
                    body=event_body,
                    sendUpdates="all",
                ).execute(),
            )
            logger.info("Booked event %s for %s", created["id"], patient_name)
            return {
                "success": True,
                "event_id": created["id"],
                "date": date,
                "time": time,
                "patient_name": patient_name,
            }
        except HttpError as exc:
            logger.error("Calendar booking failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def cancel_appointment(self, event_id: str) -> dict:
        """Delete a calendar event by event_id."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._service_call().events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                    sendUpdates="all",
                ).execute(),
            )
            logger.info("Cancelled event %s", event_id)
            return {"success": True, "event_id": event_id}
        except HttpError as exc:
            logger.error("Calendar cancel failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def reschedule_appointment(
        self,
        event_id: str,
        new_date: str,
        new_time: str,
        duration_minutes: int = 60,
    ) -> dict:
        """Move an existing event to new_date / new_time."""
        tz = ZoneInfo(self.timezone)
        dt_start = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        dt_end = dt_start + timedelta(minutes=duration_minutes)

        patch_body = {
            "start": {"dateTime": dt_start.isoformat(), "timeZone": self.timezone},
            "end":   {"dateTime": dt_end.isoformat(),   "timeZone": self.timezone},
        }
        try:
            updated = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._service_call().events().patch(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                    body=patch_body,
                    sendUpdates="all",
                ).execute(),
            )
            return {
                "success": True,
                "event_id": updated["id"],
                "new_date": new_date,
                "new_time": new_time,
            }
        except HttpError as exc:
            logger.error("Calendar reschedule failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def find_by_patient_name(
        self,
        patient_name: str,
        approximate_date: str = "",
    ) -> list[dict]:
        """Search upcoming events whose summary contains patient_name."""
        tz = ZoneInfo(self.timezone)
        if approximate_date:
            try:
                base = datetime.strptime(approximate_date, "%Y-%m-%d").replace(tzinfo=tz)
                time_min = (base - timedelta(days=7)).isoformat()
                time_max = (base + timedelta(days=7)).isoformat()
            except ValueError:
                time_min = datetime.now(tz=tz).isoformat()
                time_max = (datetime.now(tz=tz) + timedelta(days=90)).isoformat()
        else:
            time_min = datetime.now(tz=tz).isoformat()
            time_max = (datetime.now(tz=tz) + timedelta(days=90)).isoformat()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._service_call().events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    q=patient_name,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute(),
            )
            items = result.get("items", [])
            return [
                {
                    "event_id": ev["id"],
                    "summary": ev.get("summary", ""),
                    "date": ev["start"].get("dateTime", ev["start"].get("date", ""))[:10],
                    "time": ev["start"].get("dateTime", "")[-14:-9] if "T" in ev["start"].get("dateTime", "") else "",
                    "description": ev.get("description", ""),
                }
                for ev in items
            ]
        except HttpError as exc:
            logger.error("Calendar search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _service_call(self):
        if self._service is None:
            key_path = os.getenv(
                "GOOGLE_SERVICE_ACCOUNT_JSON_PATH",
                self.config.get("google", {}).get("service_account_json_path", ""),
            )
            creds = service_account.Credentials.from_service_account_file(
                key_path, scopes=SCOPES
            )
            self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _get_busy_periods(
        self, day_start: datetime, day_end: datetime
    ) -> list[tuple[datetime, datetime]]:
        body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "timeZone": self.timezone,
            "items": [{"id": self.calendar_id}],
        }
        result = self._service_call().freebusy().query(body=body).execute()
        busy_raw = result.get("calendars", {}).get(self.calendar_id, {}).get("busy", [])
        tz = ZoneInfo(self.timezone)
        return [
            (
                datetime.fromisoformat(b["start"]).astimezone(tz),
                datetime.fromisoformat(b["end"]).astimezone(tz),
            )
            for b in busy_raw
        ]


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _parse_date(phrase: str, timezone: str) -> Any:
    """Parse 'YYYY-MM-DD' or simple natural phrases into a date object."""
    from datetime import date
    tz = ZoneInfo(timezone)
    today = datetime.now(tz=tz).date()

    phrase_lower = phrase.strip().lower()

    if phrase_lower == "today":
        return today
    if phrase_lower == "tomorrow":
        return today + timedelta(days=1)
    if phrase_lower.startswith("next "):
        weekday_name = phrase_lower[5:]
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        if weekday_name in weekdays:
            target_wd = weekdays.index(weekday_name)
            days_ahead = (target_wd - today.weekday() + 7) % 7 or 7
            return today + timedelta(days=days_ahead)
    if phrase_lower.startswith("this "):
        weekday_name = phrase_lower[5:]
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        if weekday_name in weekdays:
            target_wd = weekdays.index(weekday_name)
            days_ahead = (target_wd - today.weekday()) % 7
            return today + timedelta(days=days_ahead)

    # Try ISO format
    try:
        return datetime.strptime(phrase.strip(), "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try common formats
    for fmt in ("%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(phrase.strip(), fmt).date()
        except ValueError:
            continue

    return None


def _compute_free_slots(
    day_start: datetime,
    day_end: datetime,
    busy: list[tuple[datetime, datetime]],
    duration_minutes: int,
) -> list[datetime]:
    """Walk the day in 30-minute increments and collect free slots."""
    slots = []
    slot_duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=30)
    current = day_start

    while current + slot_duration <= day_end:
        slot_end = current + slot_duration
        overlaps = any(
            b_start < slot_end and b_end > current
            for b_start, b_end in busy
        )
        if not overlaps:
            slots.append(current)
        current += step

    return slots
