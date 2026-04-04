"""
CancelFlow — locate and delete a patient's appointment.
"""

import logging

from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool

logger = logging.getLogger(__name__)


class CancelFlow:
    def __init__(self, calendar: CalendarTool, email: EmailTool, config: dict) -> None:
        self.calendar = calendar
        self.email = email
        self.config = config

    async def execute(
        self,
        patient_name: str,
        patient_email: str,
        appointment_date: str,
    ) -> dict:
        """
        1. Find the appointment by patient name + date.
        2. Delete from Google Calendar.
        3. Send cancellation email.
        """
        logger.info("Cancellation request: %s on %s", patient_name, appointment_date)

        # Locate event
        appointments = await self.calendar.find_by_patient_name(
            patient_name=patient_name,
            approximate_date=appointment_date,
        )

        if not appointments:
            return {
                "success": False,
                "message": (
                    f"I couldn't find an appointment for {patient_name} on {appointment_date}. "
                    "Could you double-check the date? If you need further help, I can have "
                    "someone from our team call you back."
                ),
            }

        event = appointments[0]
        event_id = event["event_id"]
        event_time = event.get("time", "")

        # Delete event
        result = await self.calendar.cancel_appointment(event_id=event_id)

        if not result.get("success"):
            return {
                "success": False,
                "message": (
                    "I'm sorry — I ran into a problem cancelling the appointment. "
                    "Please call us directly and we'll take care of it right away."
                ),
            }

        # Send cancellation email
        email_sent = await self.email.send_cancellation(
            patient_name=patient_name,
            patient_email=patient_email,
            date=appointment_date,
            time=event_time,
        )

        first_name = patient_name.split()[0]
        return {
            "success": True,
            "event_id": event_id,
            "cancelled_date": appointment_date,
            "email_sent": email_sent,
            "message": (
                f"Done, {first_name}. Your appointment on {appointment_date} has been cancelled. "
                + (f"A confirmation has been sent to {patient_email}. " if email_sent else "")
                + "If you'd like to reschedule in the future, don't hesitate to call us. Take care!"
            ),
        }
