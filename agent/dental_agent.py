"""
DentalAgent — core LiveKit VoicePipelineAgent subclass for Sophia.

Wires conversation-flow logic and function-calling tools into the
OpenAI Realtime API session.
"""

import json
import logging
from typing import Any

from livekit.agents import Agent, AgentSession
from livekit.agents.llm import FunctionTool, TypeInfo
from livekit import rtc

from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool
from flows.booking import BookingFlow
from flows.reschedule import RescheduleFlow
from flows.cancel import CancelFlow
from flows.faq import FAQFlow

logger = logging.getLogger(__name__)


class DentalAgent(Agent):
    """
    Sophia — the dental clinic voice receptionist.

    Responsibilities:
      • Manage multi-turn booking / reschedule / cancel flows.
      • Expose Google Calendar + Gmail as function-calling tools.
      • Provide FAQ answers directly from config.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(instructions=None)  # instructions set via main.py system prompt
        self.config = config
        self.calendar = CalendarTool(config)
        self.email = EmailTool(config)
        self.booking_flow = BookingFlow(self.calendar, self.email, config)
        self.reschedule_flow = RescheduleFlow(self.calendar, self.email, config)
        self.cancel_flow = CancelFlow(self.calendar, self.email, config)
        self.faq_flow = FAQFlow(config)

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_tools(self, session: AgentSession) -> None:
        """Register all function-calling tools on the live session."""
        tools = [
            self._tool_check_available_slots(),
            self._tool_book_appointment(),
            self._tool_reschedule_appointment(),
            self._tool_cancel_appointment(),
            self._tool_get_appointment_by_name(),
            self._tool_send_confirmation_email(),
            self._tool_send_cancellation_email(),
        ]
        for tool in tools:
            session.add_tool(tool)

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    def _tool_check_available_slots(self) -> FunctionTool:
        calendar = self.calendar

        async def check_available_slots(
            preferred_date: str,
            time_preference: str = "any",
            duration_minutes: int = 60,
        ) -> str:
            """
            Check available appointment slots on the dental clinic calendar.

            Args:
                preferred_date: Date in YYYY-MM-DD format, or a natural phrase
                    like 'next Monday', 'this Friday', 'tomorrow'.
                time_preference: 'morning', 'afternoon', 'evening', or 'any'.
                duration_minutes: Appointment length in minutes (default 60).

            Returns:
                JSON string with a list of available time slots.
            """
            slots = await calendar.get_available_slots(
                preferred_date=preferred_date,
                time_preference=time_preference,
                duration_minutes=duration_minutes,
            )
            if not slots:
                return json.dumps({"available": False, "slots": []})
            return json.dumps({"available": True, "slots": slots[:3]})

        return FunctionTool.from_callable(check_available_slots)

    def _tool_book_appointment(self) -> FunctionTool:
        booking = self.booking_flow

        async def book_appointment(
            patient_name: str,
            patient_email: str,
            date: str,
            time: str,
            reason: str,
            duration_minutes: int = 60,
        ) -> str:
            """
            Book a dental appointment and send a confirmation email.

            Args:
                patient_name: Full name of the patient.
                patient_email: Patient's email address for confirmation.
                date: Appointment date in YYYY-MM-DD format.
                time: Appointment time in HH:MM (24h) format.
                reason: Reason for visit (e.g. 'cleaning', 'checkup', 'emergency').
                duration_minutes: Appointment duration in minutes.

            Returns:
                JSON with booking confirmation details or an error message.
            """
            result = await booking.execute(
                patient_name=patient_name,
                patient_email=patient_email,
                date=date,
                time=time,
                reason=reason,
                duration_minutes=duration_minutes,
            )
            return json.dumps(result)

        return FunctionTool.from_callable(book_appointment)

    def _tool_reschedule_appointment(self) -> FunctionTool:
        reschedule = self.reschedule_flow

        async def reschedule_appointment(
            patient_name: str,
            patient_email: str,
            original_date: str,
            new_date: str,
            new_time: str,
        ) -> str:
            """
            Reschedule an existing appointment to a new date and time.

            Args:
                patient_name: Full name of the patient.
                patient_email: Patient's email address.
                original_date: Original appointment date in YYYY-MM-DD.
                new_date: New appointment date in YYYY-MM-DD.
                new_time: New appointment time in HH:MM (24h) format.

            Returns:
                JSON with updated booking details or an error message.
            """
            result = await reschedule.execute(
                patient_name=patient_name,
                patient_email=patient_email,
                original_date=original_date,
                new_date=new_date,
                new_time=new_time,
            )
            return json.dumps(result)

        return FunctionTool.from_callable(reschedule_appointment)

    def _tool_cancel_appointment(self) -> FunctionTool:
        cancel = self.cancel_flow

        async def cancel_appointment(
            patient_name: str,
            patient_email: str,
            appointment_date: str,
        ) -> str:
            """
            Cancel an existing dental appointment.

            Args:
                patient_name: Full name of the patient.
                patient_email: Patient's email address.
                appointment_date: Date of appointment to cancel in YYYY-MM-DD.

            Returns:
                JSON confirmation of cancellation or error.
            """
            result = await cancel.execute(
                patient_name=patient_name,
                patient_email=patient_email,
                appointment_date=appointment_date,
            )
            return json.dumps(result)

        return FunctionTool.from_callable(cancel_appointment)

    def _tool_get_appointment_by_name(self) -> FunctionTool:
        calendar = self.calendar

        async def get_appointment_by_name(
            patient_name: str,
            approximate_date: str = "",
        ) -> str:
            """
            Look up an existing appointment by patient name.

            Args:
                patient_name: Full or partial name to search for.
                approximate_date: Optional date hint in YYYY-MM-DD to narrow search.

            Returns:
                JSON with found appointments or empty list.
            """
            appointments = await calendar.find_by_patient_name(
                patient_name=patient_name,
                approximate_date=approximate_date,
            )
            return json.dumps({"appointments": appointments})

        return FunctionTool.from_callable(get_appointment_by_name)

    def _tool_send_confirmation_email(self) -> FunctionTool:
        email = self.email

        async def send_confirmation_email(
            patient_name: str,
            patient_email: str,
            date: str,
            time: str,
        ) -> str:
            """
            Send a booking confirmation email to the patient.

            Args:
                patient_name: Full name of the patient.
                patient_email: Recipient email address.
                date: Appointment date in YYYY-MM-DD format.
                time: Appointment time in HH:MM (24h) format.

            Returns:
                JSON success/failure status.
            """
            ok = await email.send_confirmation(
                patient_name=patient_name,
                patient_email=patient_email,
                date=date,
                time=time,
            )
            return json.dumps({"sent": ok})

        return FunctionTool.from_callable(send_confirmation_email)

    def _tool_send_cancellation_email(self) -> FunctionTool:
        email = self.email

        async def send_cancellation_email(
            patient_name: str,
            patient_email: str,
            date: str,
            time: str,
        ) -> str:
            """
            Send a cancellation confirmation email to the patient.

            Args:
                patient_name: Full name of the patient.
                patient_email: Recipient email address.
                date: Cancelled appointment date in YYYY-MM-DD.
                time: Cancelled appointment time in HH:MM (24h).

            Returns:
                JSON success/failure status.
            """
            ok = await email.send_cancellation(
                patient_name=patient_name,
                patient_email=patient_email,
                date=date,
                time=time,
            )
            return json.dumps({"sent": ok})

        return FunctionTool.from_callable(send_cancellation_email)
