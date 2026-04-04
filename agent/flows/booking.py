"""
BookingFlow — orchestrates the appointment booking sequence.

This is called by the book_appointment function-calling tool
after the Realtime model has collected all required fields from the patient.
"""

import logging

from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool

logger = logging.getLogger(__name__)


class BookingFlow:
    """
    Executes the calendar booking and sends a confirmation email.

    The multi-turn conversation itself is handled by the Realtime model
    guided by the system prompt.  This class is invoked once all required
    details have been gathered.
    """

    def __init__(self, calendar: CalendarTool, email: EmailTool, config: dict) -> None:
        self.calendar = calendar
        self.email = email
        self.config = config

    async def execute(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
        reason: str,
        duration_minutes: int = 60,
    ) -> dict:
        """
        1. Create calendar event.
        2. Send confirmation email.
        3. Return structured result for the model to relay to patient.
        """
        logger.info(
            "Booking: %s <%s> on %s %s for '%s'",
            patient_name, patient_email, date, time, reason,
        )

        # Step 1: create calendar event
        booking = await self.calendar.book_appointment(
            patient_name=patient_name,
            patient_email=patient_email,
            date=date,
            time=time,
            reason=reason,
            duration_minutes=duration_minutes,
        )

        if not booking.get("success"):
            return {
                "success": False,
                "message": (
                    "I'm sorry — I wasn't able to complete the booking due to a calendar error. "
                    "A team member will call you back to confirm your appointment."
                ),
            }

        # Step 2: send email confirmation
        email_sent = await self.email.send_confirmation(
            patient_name=patient_name,
            patient_email=patient_email,
            date=date,
            time=time,
        )

        return {
            "success": True,
            "event_id": booking["event_id"],
            "patient_name": patient_name,
            "date": date,
            "time": time,
            "reason": reason,
            "email_sent": email_sent,
            "message": (
                f"Wonderful! I've got you booked for {date} at {time}. "
                + (
                    f"A confirmation email has been sent to {patient_email}. "
                    if email_sent
                    else ""
                )
                + f"We look forward to seeing you, {patient_name.split()[0]}. Take care!"
            ),
        }
