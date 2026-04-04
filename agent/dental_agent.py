"""
DentalAgent — core LiveKit VoicePipelineAgent for Sophia.

Extends livekit.agents.Agent and exposes appointment-management
function-calling tools to the OpenAI Realtime API session.
"""

import json
import logging

from livekit.agents import Agent, AgentSession, JobContext, function_tool
from livekit.plugins import noise_cancellation

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

    Exposes 7 function-calling tools to the Realtime model:
      • check_available_slots
      • book_appointment
      • reschedule_appointment
      • cancel_appointment
      • get_appointment_by_name
      • send_confirmation_email
      • send_cancellation_email
    """

    def __init__(self, config: dict, realtime_model, nc) -> None:
        super().__init__()
        self.config = config
        self.realtime_model = realtime_model
        self.nc = nc

        self.calendar = CalendarTool(config)
        self.email = EmailTool(config)
        self.booking_flow = BookingFlow(self.calendar, self.email, config)
        self.reschedule_flow = RescheduleFlow(self.calendar, self.email, config)
        self.cancel_flow = CancelFlow(self.calendar, self.email, config)
        self.faq_flow = FAQFlow(config)

    async def start(self, ctx: JobContext) -> None:
        """Initialise and start the agent session for this call."""
        session = AgentSession(llm=self.realtime_model)

        await session.start(
            room=ctx.room,
            agent=self,
        )

    # ------------------------------------------------------------------
    # Function-calling tools (livekit-agents >= 1.0 decorator style)
    # ------------------------------------------------------------------

    @function_tool(
        name="check_available_slots",
        description=(
            "Check available appointment slots on the dental clinic calendar. "
            "Call this BEFORE offering any times to the patient."
        ),
    )
    async def check_available_slots(
        self,
        preferred_date: str,
        time_preference: str = "any",
        duration_minutes: int = 60,
    ) -> str:
        """
        Args:
            preferred_date: Date in YYYY-MM-DD or natural phrase
                ('tomorrow', 'next Monday', 'this Friday').
            time_preference: 'morning' | 'afternoon' | 'evening' | 'any'.
            duration_minutes: Appointment length in minutes.
        """
        slots = await self.calendar.get_available_slots(
            preferred_date=preferred_date,
            time_preference=time_preference,
            duration_minutes=duration_minutes,
        )
        if not slots:
            return json.dumps({"available": False, "slots": []})
        return json.dumps({"available": True, "slots": slots[:3]})

    @function_tool(
        name="book_appointment",
        description=(
            "Book a dental appointment and send a confirmation email. "
            "Only call this after verbally confirming all details with the patient."
        ),
    )
    async def book_appointment(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
        reason: str,
        duration_minutes: int = 60,
    ) -> str:
        """
        Args:
            patient_name: Full name of the patient.
            patient_email: Patient's email address for confirmation.
            date: Appointment date in YYYY-MM-DD.
            time: Appointment time in HH:MM (24h).
            reason: Reason for visit (e.g. 'cleaning', 'checkup', 'emergency').
            duration_minutes: Appointment length in minutes.
        """
        result = await self.booking_flow.execute(
            patient_name=patient_name,
            patient_email=patient_email,
            date=date,
            time=time,
            reason=reason,
            duration_minutes=duration_minutes,
        )
        return json.dumps(result)

    @function_tool(
        name="reschedule_appointment",
        description="Move an existing patient appointment to a new date and time.",
    )
    async def reschedule_appointment(
        self,
        patient_name: str,
        patient_email: str,
        original_date: str,
        new_date: str,
        new_time: str,
    ) -> str:
        """
        Args:
            patient_name: Full name of the patient.
            patient_email: Patient's email address.
            original_date: Original appointment date in YYYY-MM-DD.
            new_date: New appointment date in YYYY-MM-DD.
            new_time: New appointment time in HH:MM (24h).
        """
        result = await self.reschedule_flow.execute(
            patient_name=patient_name,
            patient_email=patient_email,
            original_date=original_date,
            new_date=new_date,
            new_time=new_time,
        )
        return json.dumps(result)

    @function_tool(
        name="cancel_appointment",
        description="Cancel an existing dental appointment.",
    )
    async def cancel_appointment(
        self,
        patient_name: str,
        patient_email: str,
        appointment_date: str,
    ) -> str:
        """
        Args:
            patient_name: Full name of the patient.
            patient_email: Patient's email address.
            appointment_date: Date of appointment to cancel in YYYY-MM-DD.
        """
        result = await self.cancel_flow.execute(
            patient_name=patient_name,
            patient_email=patient_email,
            appointment_date=appointment_date,
        )
        return json.dumps(result)

    @function_tool(
        name="get_appointment_by_name",
        description="Look up an existing appointment by patient name.",
    )
    async def get_appointment_by_name(
        self,
        patient_name: str,
        approximate_date: str = "",
    ) -> str:
        """
        Args:
            patient_name: Full or partial name to search for.
            approximate_date: Optional date hint in YYYY-MM-DD to narrow search.
        """
        appointments = await self.calendar.find_by_patient_name(
            patient_name=patient_name,
            approximate_date=approximate_date,
        )
        return json.dumps({"appointments": appointments})

    @function_tool(
        name="send_confirmation_email",
        description="Send a booking confirmation email to the patient.",
    )
    async def send_confirmation_email(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
    ) -> str:
        """
        Args:
            patient_name: Full name of the patient.
            patient_email: Recipient email address.
            date: Appointment date in YYYY-MM-DD.
            time: Appointment time in HH:MM (24h).
        """
        ok = await self.email.send_confirmation(
            patient_name=patient_name,
            patient_email=patient_email,
            date=date,
            time=time,
        )
        return json.dumps({"sent": ok})

    @function_tool(
        name="send_cancellation_email",
        description="Send a cancellation confirmation email to the patient.",
    )
    async def send_cancellation_email(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
    ) -> str:
        """
        Args:
            patient_name: Full name of the patient.
            patient_email: Recipient email address.
            date: Cancelled appointment date in YYYY-MM-DD.
            time: Cancelled appointment time in HH:MM (24h).
        """
        ok = await self.email.send_cancellation(
            patient_name=patient_name,
            patient_email=patient_email,
            date=date,
            time=time,
        )
        return json.dumps({"sent": ok})
