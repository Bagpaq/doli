"""
FAQFlow — returns canned answers from clinic YAML config.

All FAQ answers are editable by the clinic owner in dental-clinic.yaml.
The Realtime model answers FAQ questions directly from its system prompt,
but this module provides a programmatic lookup in case a tool call is used.
"""

import logging
from difflib import get_close_matches

logger = logging.getLogger(__name__)

# Canonical question keys to natural-language aliases
_ALIASES: dict[str, list[str]] = {
    "hours": ["hours", "open", "close", "schedule", "when are you open", "operating hours"],
    "address": ["address", "location", "where are you", "directions", "find you"],
    "parking": ["parking", "park", "car"],
    "insurance": ["insurance", "plan", "coverage", "accept insurance"],
    "emergency": ["emergency", "urgent", "after hours", "emergency line"],
    "phone": ["phone", "number", "call", "contact"],
    "email": ["email", "email address"],
}


class FAQFlow:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.faq: dict = config.get("faq", {})
        self.clinic: dict = config.get("clinic", {})
        self.hours: dict = config.get("hours", {})

    def answer(self, question: str) -> str:
        """
        Return the best FAQ answer for a natural-language question.
        Falls back to a polite 'I don't know' response.
        """
        question_lower = question.lower()

        # Try direct key match first
        for key, aliases in _ALIASES.items():
            if any(alias in question_lower for alias in aliases):
                return self._answer_for_key(key)

        # Fuzzy match against all FAQ keys
        all_keys = list(self.faq.keys())
        matches = get_close_matches(question_lower, all_keys, n=1, cutoff=0.5)
        if matches:
            return self.faq.get(matches[0], "")

        return (
            "That's a great question. I want to make sure I give you the right information — "
            "let me have one of our team members give you a call to answer that properly. "
            "Would that work for you?"
        )

    def _answer_for_key(self, key: str) -> str:
        if key == "hours":
            if self.hours:
                lines = ", ".join(f"{d}: {t}" for d, t in self.hours.items())
                return f"Our clinic hours are: {lines}."
            return self.faq.get("hours", "Please call us for our current hours.")
        if key == "address":
            addr = self.clinic.get("address", self.faq.get("address", ""))
            return f"We're located at {addr}." if addr else self.faq.get("address", "")
        if key == "phone":
            phone = self.clinic.get("phone", self.faq.get("phone", ""))
            return f"You can reach us at {phone}." if phone else self.faq.get("phone", "")
        if key == "email":
            email = self.clinic.get("email", self.faq.get("email", ""))
            return f"Our email address is {email}." if email else self.faq.get("email", "")
        return self.faq.get(key, "")
