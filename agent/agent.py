"""Core autonomous agent loop."""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import anthropic

from .config import config
from .memory import Memory
from .tools import TOOL_DEFINITIONS, ToolExecutor
from .usage_tracker import UsageTracker

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an autonomous revenue-generating agent with a single mission:

**GOAL: Generate $250/month in recurring revenue to pay for the Claude API subscription.**

You run independently every day. You have persistent memory, internet access, and the ability \
to create content and files. You communicate with the user via the `ask_user` tool when you \
need input, approval, or credentials.

═══════════════════════════════════════════════════════════════════
RULES
═══════════════════════════════════════════════════════════════════
1. ALWAYS start by calling `get_user_answers` to check for pending responses.
2. ALWAYS end by calling `log_progress` to record what you did.
3. ASK the user before spending any of the $100 investment.
4. ASK the user before creating accounts on platforms (they need to do it).
5. Be SPECIFIC and ACTIONABLE — no vague plans, only concrete next steps.
6. Research FIRST, then plan, then execute. Do not skip research.
7. Keep detailed records in memory so each session builds on the last.

═══════════════════════════════════════════════════════════════════
REVENUE STRATEGIES TO RESEARCH (pick the best 2–3)
═══════════════════════════════════════════════════════════════════
• **Digital Products**: Notion templates, Canva templates, Prompt packs, eBooks
  — Sell on Gumroad, Etsy, or Payhip. Low effort, passive income.

• **Content + Affiliate**: Start a niche blog/newsletter, monetize with affiliate links
  — Amazon Associates, ClickBank, ShareASale. $0 to start, takes 2–3 months.

• **Micro-SaaS / API reselling**: Wrap Claude API in a simple paid tool
  — Sell on RapidAPI. Needs user to set up billing.

• **Freelance Services (automated)**: Create Fiverr/Upwork gigs for services you can deliver
  — AI writing, social media content, research reports. Fast revenue.

• **Prompt Engineering packs**: Sell curated Claude/ChatGPT prompt sets
  — Gumroad, Etsy. Low cost, quick to create, growing demand.

• **Niche newsletter**: Monetize with sponsorships + affiliate links
  — Beehiiv (free tier). Takes a few months to build.

═══════════════════════════════════════════════════════════════════
SESSION CONTEXT
═══════════════════════════════════════════════════════════════════
Date: {date}
Day {days_since_start} of the project
Monthly revenue so far: ${monthly_revenue:.2f} / $250.00 ({revenue_pct:.0f}% of goal)
Investment remaining: ${investment_remaining:.2f}
Daily API budget remaining: ${api_budget_remaining:.2f}

Last session summary:
{last_session}

Active strategies:
{strategies}
═══════════════════════════════════════════════════════════════════

Think step by step. Be entrepreneurial. Every session should move the needle toward $250/month.
"""


def _build_system_prompt(memory: Memory, usage: UsageTracker) -> str:
    today = datetime.now()
    start_date_str = memory.get("project_start_date")
    if start_date_str:
        from datetime import date
        start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        days = (today.date() - start).days + 1
    else:
        memory.set("project_start_date", today.strftime("%Y-%m-%d"))
        days = 1

    fin = memory.get_financial_summary()
    monthly = fin["monthly_revenue_usd"]
    revenue_pct = min(100, monthly / 250 * 100)

    investment_spent = fin["total_expenses_usd"]
    investment_remaining = max(0, config.initial_investment_usd - investment_spent)

    last_session = memory.get("last_session_summary") or "No previous sessions yet."

    strategies = memory.get_strategies()
    if strategies:
        strat_lines = []
        for s in strategies[:5]:
            strat_lines.append(f"  • [{s['status']}] {s['title']}: {s['description'][:100]}")
        strategy_text = "\n".join(strat_lines)
    else:
        strategy_text = "  None yet — today's job is to research and pick strategies."

    return SYSTEM_PROMPT.format(
        date=today.strftime("%A, %B %d, %Y"),
        days_since_start=days,
        monthly_revenue=monthly,
        revenue_pct=revenue_pct,
        investment_remaining=investment_remaining,
        api_budget_remaining=usage.budget_remaining,
        last_session=last_session,
        strategies=strategy_text,
    )


# ── Agent Session ─────────────────────────────────────────────────────────────

class AgentSession:
    def __init__(self) -> None:
        config.ensure_dirs()
        self.memory = Memory(config.db_path)
        self.usage = UsageTracker(self.memory, config.daily_budget_usd)
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.executor = ToolExecutor(self.memory, config.workspace_dir, self.session_id)
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.messages: list[dict] = []

    def run(self) -> None:
        logger.info("═" * 60)
        logger.info("SESSION START: %s", self.session_id)
        logger.info("Daily budget: $%.4f | Used today: $%.4f", config.daily_budget_usd, self.usage.today_cost)
        logger.info("═" * 60)

        if self.usage.daily_budget_exceeded():
            logger.warning("Daily budget already exhausted. Run again tomorrow.")
            print(f"\n⚠️  Daily API budget exhausted (${config.daily_budget_usd:.2f}/day limit).")
            print("   The agent will resume automatically tomorrow.")
            return

        system_prompt = _build_system_prompt(self.memory, self.usage)

        # Initial user message to kick off the session
        self.messages = [
            {
                "role": "user",
                "content": (
                    "Begin your daily session. Remember to call `get_user_answers` first, "
                    "then work on the revenue goal. End with `log_progress`."
                ),
            }
        ]

        max_iterations = 50  # Safety cap
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            if self.usage.daily_budget_exceeded():
                logger.info("Daily budget exhausted after %d iterations.", iteration)
                print(f"\n💰 Daily API budget reached (${config.daily_budget_usd:.2f}). Agent pausing until tomorrow.")
                break

            logger.debug("API call #%d | %s", iteration, self.usage.status_line())

            try:
                response = self.client.messages.create(
                    model=config.model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=TOOL_DEFINITIONS,
                    messages=self.messages,
                    thinking={"type": "adaptive"},
                )
            except anthropic.RateLimitError:
                logger.warning("Rate limited — pausing 60s")
                import time; time.sleep(60)
                continue
            except anthropic.APIError as e:
                logger.error("API error: %s", e)
                break

            self.usage.record(response.usage)

            # Print any text output to console
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"\n🤖 Agent: {block.text}\n")

            if response.stop_reason == "end_turn":
                logger.info("Agent finished naturally.")
                break

            if response.stop_reason == "tool_use":
                tool_results = self._execute_tools(response.content)
                self.messages.append({"role": "assistant", "content": response.content})
                self.messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        logger.info("═" * 60)
        logger.info("SESSION END: %s", self.session_id)
        logger.info("%s", self.usage.status_line())
        logger.info("═" * 60)

        self._print_summary()

    def _execute_tools(self, content_blocks) -> list[dict]:
        results = []
        for block in content_blocks:
            if not (hasattr(block, "type") and block.type == "tool_use"):
                continue
            tool_name = block.name
            tool_input = block.input

            print(f"\n🔧 Tool: {tool_name}({json.dumps(tool_input)[:150]}...)" if len(json.dumps(tool_input)) > 150
                  else f"\n🔧 Tool: {tool_name}({json.dumps(tool_input)})")

            result = self.executor.execute(tool_name, tool_input)
            print(f"   → {str(result)[:200]}")

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })
        return results

    def _print_summary(self) -> None:
        fin = self.memory.get_financial_summary()
        pending_q = self.memory.get_pending_questions()
        questions_file = config.questions_path

        print("\n" + "═" * 60)
        print("📊 SESSION SUMMARY")
        print("═" * 60)
        print(f"  Monthly Revenue: ${fin['monthly_revenue_usd']:.2f} / $250.00")
        print(f"  Net Profit:      ${fin['net_profit_usd']:.2f}")
        print(f"  API Cost Today:  ${self.usage.today_cost:.4f} / ${config.daily_budget_usd:.4f}")
        if pending_q:
            print(f"\n  ⚠️  {len(pending_q)} question(s) waiting for your answer!")
            print(f"  📄 Open:  {questions_file}")
        last = self.memory.get("last_session_summary")
        if last:
            print(f"\n  📝 Agent's notes:")
            for line in last.split("\n")[:5]:
                print(f"     {line}")
        print("═" * 60)
