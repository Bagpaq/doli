"""
RescheduleFlow — find existing appointment, cancel it, book a new one.
"""

import logging

from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool

logger = logging.getLogger(__name__)


class RescheduleFlow:
    def __init__(self, calendar: CalendarTool, email: EmailTool, config: dict) -> None:
        self.calendar = calendar
        self.email = email
        self.config = config

    async def execute(
        self,
        patient_name: str,
        patient_email: str,
        original_date: str,
        new_date: str,
        new_time: str,
    ) -> dict:
        """
        1. Find the existing appointment by patient name + original_date.
        2. Update (patch) the calendar event to the new slot.
        3. Send a reschedule confirmation email.
        """
        logger.info(
            "Reschedule: %s from %s → %s %s",
            patient_name, original_date, new_date, new_time,
        )

        # Step 1: locate event
        appointments = await self.calendar.find_by_patient_name(
            patient_name=patient_name,
            approximate_date=original_date,
        )

        if not appointments:
            return {
                "success": False,
                "message": (
                    f"I wasn't able to find an existing appointment for {patient_name} "
                    f"around {original_date}. Could you double-check the date, or would you "
                    "like me to book a new appointment instead?"
                ),
            }

        # Take the closest match
        event = appointments[0]
        event_id = event["event_id"]

        # Step 2: patch the event
        result = await self.calendar.reschedule_appointment(
            event_id=event_id,
            new_date=new_date,
            new_time=new_time,
        )

        if not result.get("success"):
            return {
                "success": False,
                "message": (
                    "I'm sorry — I had trouble updating the calendar. "
                    "A team member will reach out to confirm your new appointment."
                ),
            }

        # Step 3: email confirmation
        email_sent = await self.email.send_confirmation(
            patient_name=patient_name,
            patient_email=patient_email,
            date=new_date,
            time=new_time,
        )

        first_name = patient_name.split()[0]
        return {
            "success": True,
            "event_id": event_id,
            "new_date": new_date,
            "new_time": new_time,
            "email_sent": email_sent,
            "message": (
                f"All done, {first_name}! Your appointment has been moved to "
                f"{new_date} at {new_time}. "
                + (f"An updated confirmation has been sent to {patient_email}. " if email_sent else "")
                + "We'll see you then — take care!"
            ),
        }
