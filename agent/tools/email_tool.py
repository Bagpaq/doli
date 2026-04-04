"""
EmailTool — Gmail API integration for appointment notifications.

Uses the Gmail API via a Google Service Account with domain-wide
delegation (or OAuth credentials) to send HTML emails.
"""

import asyncio
import base64
import logging
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TEMPLATES_DIR = Path(__file__).parents[2] / "templates"


class EmailTool:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.sender: str = os.getenv(
            "GMAIL_SENDER_EMAIL",
            config.get("gmail", {}).get("sender_email", ""),
        )
        self.clinic_name: str = config.get("clinic", {}).get("name", "Dental Clinic")
        self.clinic_address: str = config.get("clinic", {}).get("address", "")
        self.clinic_phone: str = config.get("clinic", {}).get("phone", "")
        self.timezone: str = config.get("clinic", {}).get("timezone", "America/New_York")
        self._service = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_confirmation(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
    ) -> bool:
        """Send appointment confirmation email. Returns True on success."""
        display_dt = _format_display_datetime(date, time, self.timezone)
        html = _load_template(
            "confirmation_email.html",
            patient_name=patient_name,
            clinic_name=self.clinic_name,
            clinic_address=self.clinic_address,
            clinic_phone=self.clinic_phone,
            appointment_datetime=display_dt,
            date=date,
            time=time,
        )
        subject = f"Your Appointment Confirmation — {self.clinic_name}"
        return await self._send(to=patient_email, subject=subject, html_body=html)

    async def send_cancellation(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
    ) -> bool:
        """Send appointment cancellation email. Returns True on success."""
        display_dt = _format_display_datetime(date, time, self.timezone)
        html = _load_template(
            "cancellation_email.html",
            patient_name=patient_name,
            clinic_name=self.clinic_name,
            clinic_address=self.clinic_address,
            clinic_phone=self.clinic_phone,
            appointment_datetime=display_dt,
            date=date,
            time=time,
        )
        subject = f"Appointment Cancellation — {self.clinic_name}"
        return await self._send(to=patient_email, subject=subject, html_body=html)

    async def send_reminder(
        self,
        patient_name: str,
        patient_email: str,
        date: str,
        time: str,
    ) -> bool:
        """Send a 24-hour reminder email."""
        display_dt = _format_display_datetime(date, time, self.timezone)
        # Reuse confirmation template for reminders
        html = _load_template(
            "confirmation_email.html",
            patient_name=patient_name,
            clinic_name=self.clinic_name,
            clinic_address=self.clinic_address,
            clinic_phone=self.clinic_phone,
            appointment_datetime=display_dt,
            date=date,
            time=time,
        )
        html = html.replace("Appointment Confirmed", "Appointment Reminder — Tomorrow")
        subject = f"Reminder: Your Appointment Tomorrow — {self.clinic_name}"
        return await self._send(to=patient_email, subject=subject, html_body=html)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send(self, to: str, subject: str, html_body: str) -> bool:
        try:
            raw = _build_raw_message(
                sender=self.sender,
                to=to,
                subject=subject,
                html_body=html_body,
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._service_call()
                    .users()
                    .messages()
                    .send(userId="me", body={"raw": raw})
                    .execute(),
            )
            logger.info("Email sent to %s | subject: %s", to, subject)
            return True
        except HttpError as exc:
            logger.error("Gmail send failed: %s", exc)
            return False

    def _service_call(self):
        if self._service is None:
            key_path = os.getenv(
                "GOOGLE_SERVICE_ACCOUNT_JSON_PATH",
                self.config.get("google", {}).get("service_account_json_path", ""),
            )
            creds = service_account.Credentials.from_service_account_file(
                key_path, scopes=SCOPES
            )
            # Domain-wide delegation: impersonate sender
            if self.sender:
                creds = creds.with_subject(self.sender)
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _load_template(filename: str, **kwargs) -> str:
    path = TEMPLATES_DIR / filename
    if not path.exists():
        logger.warning("Email template not found: %s", path)
        return "<p>Email template missing.</p>"
    html = path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        html = html.replace(f"{{{{{key}}}}}", str(value))
    return html


def _build_raw_message(sender: str, to: str, subject: str, html_body: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


def _format_display_datetime(date: str, time: str, timezone: str) -> str:
    try:
        tz = ZoneInfo(timezone)
        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        return dt.strftime("%A, %B %-d, %Y at %-I:%M %p %Z")
    except Exception:
        return f"{date} at {time}"
