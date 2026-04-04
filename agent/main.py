"""
Dental Voice Agent - LiveKit entrypoint
Connects to LiveKit SIP, spins up a Realtime API session as Sophia.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import openai as lk_openai
from livekit.plugins import silero

from dental_agent import DentalAgent
from config_loader import load_clinic_config

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLINIC_CONFIG_PATH = os.getenv("CLINIC_CONFIG_PATH", "config/businesses/dental-clinic.yaml")


async def entrypoint(ctx: JobContext) -> None:
    """Called once per incoming (or outgoing) SIP call."""
    config = load_clinic_config(CLINIC_CONFIG_PATH)

    logger.info("New call — room: %s | config: %s", ctx.room.name, config["clinic"]["name"])

    await ctx.connect()

    # Voice Activity Detection
    vad = silero.VAD.load()

    # OpenAI Realtime model — shimmer voice, low temperature for consistency
    realtime_model = lk_openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice=config["agent"]["voice"],          # shimmer
        temperature=config["agent"]["temperature"],  # 0.6
        instructions=_build_system_prompt(config),
        turn_detection=lk_openai.realtime.ServerVadOptions(
            threshold=0.5,
            prefix_padding_ms=300,
            silence_duration_ms=600,
        ),
    )

    dental_agent = DentalAgent(config=config)

    session = AgentSession(
        vad=vad,
        llm=realtime_model,
    )

    # Register all function-calling tools onto the session
    dental_agent.register_tools(session)

    await session.start(
        room=ctx.room,
        agent=dental_agent,
    )


def _build_system_prompt(config: dict) -> str:
    clinic = config["clinic"]
    agent_cfg = config["agent"]
    hours = config.get("hours", {})
    faq = config.get("faq", {})

    hours_lines = "\n".join(
        f"  - {day}: {times}" for day, times in hours.items()
    )
    faq_lines = "\n".join(
        f"  - {k}: {v}" for k, v in faq.items()
    )

    return f"""
{agent_cfg['personality']}

CLINIC DETAILS:
  Name:    {clinic['name']}
  Address: {clinic['address']}
  Phone:   {clinic['phone']}
  Email:   {clinic['email']}

BUSINESS HOURS:
{hours_lines}

FREQUENTLY ASKED QUESTIONS:
{faq_lines}

BOOKING RULES:
  - Appointments are 60 minutes by default.
  - ALWAYS call the check_available_slots tool before offering time slots.
  - ALWAYS confirm the patient's name, email address, and chosen slot before booking.
  - NEVER invent available times — only offer slots returned by the calendar tool.
  - If you cannot help the caller, offer to have a human call them back.

CONVERSATION STYLE:
  - Speak slowly and clearly — this is a medical context.
  - Be warm, calm, and reassuring at all times.
  - Confirm important details back to the patient before acting.
  - End every call warmly by name.
""".strip()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
            ws_url=os.getenv("LIVEKIT_URL"),
        )
    )
