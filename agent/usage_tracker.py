"""Tracks API usage and enforces the 8%-of-weekly-budget daily limit."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (claude-opus-4-6)
INPUT_COST_PER_M = 5.00
OUTPUT_COST_PER_M = 25.00


def tokens_to_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * INPUT_COST_PER_M + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M


class UsageTracker:
    def __init__(self, memory, daily_budget_usd: float) -> None:
        self.memory = memory
        self.daily_budget_usd = daily_budget_usd
        self._session_input = 0
        self._session_output = 0
        self._session_cost = 0.0

    def record(self, usage) -> None:
        """Record token usage from an API response."""
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cost = tokens_to_cost(inp, out)

        self._session_input += inp
        self._session_output += out
        self._session_cost += cost

        self.memory.add_usage(inp, out, cost)

        logger.debug(
            "Usage: +%d in / +%d out = $%.4f | session total $%.4f | day total $%.4f / $%.4f budget",
            inp, out, cost,
            self._session_cost,
            self.today_cost,
            self.daily_budget_usd,
        )

    @property
    def today_cost(self) -> float:
        return self.memory.get_daily_usage()["cost_usd"]

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.daily_budget_usd - self.today_cost)

    @property
    def budget_pct_used(self) -> float:
        if self.daily_budget_usd == 0:
            return 100.0
        return min(100.0, (self.today_cost / self.daily_budget_usd) * 100)

    def daily_budget_exceeded(self) -> bool:
        return self.today_cost >= self.daily_budget_usd

    def status_line(self) -> str:
        return (
            f"Daily budget: ${self.today_cost:.4f} used / ${self.daily_budget_usd:.4f} "
            f"({self.budget_pct_used:.1f}%) | Remaining: ${self.budget_remaining:.4f}"
        )
