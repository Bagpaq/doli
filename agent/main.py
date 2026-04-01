"""Entry point and scheduler for the autonomous revenue agent."""

import logging
import sys
from datetime import datetime

from .config import config


def setup_logging() -> None:
    config.ensure_dirs()
    handlers = [
        logging.FileHandler(config.log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def run_once() -> None:
    """Run a single agent session."""
    from .agent import AgentSession
    session = AgentSession()
    session.run()


def run_scheduled(run_at: str = "09:00") -> None:
    """Run the agent daily at a specified time using the `schedule` library."""
    try:
        import schedule
        import time
    except ImportError:
        print("Install 'schedule' to use scheduled mode: pip install schedule")
        sys.exit(1)

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Scheduled mode: agent will run daily at %s", run_at)
    print(f"\n🕐 Agent scheduled to run daily at {run_at}")
    print("   Press Ctrl+C to stop.\n")

    schedule.every().day.at(run_at).do(run_once)

    # Run immediately on first start
    run_once()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Autonomous Revenue Agent — runs daily to generate $250/month"
    )
    parser.add_argument(
        "--schedule",
        metavar="HH:MM",
        help="Run daily at this time (e.g. 09:00). Requires `schedule` package.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        help="Override the daily budget in USD (default: 8%% of weekly budget)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current status and exit",
    )

    args = parser.parse_args()

    setup_logging()

    if args.budget:
        config.weekly_budget_usd = args.budget / 0.08  # Reverse-compute weekly from daily
        print(f"Daily budget set to ${args.budget:.2f}")

    if args.status:
        _print_status()
        return

    if not config.anthropic_api_key:
        print("❌ ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    if args.schedule:
        run_scheduled(args.schedule)
    else:
        run_once()


def _print_status() -> None:
    """Print current agent status without running a session."""
    from .memory import Memory
    from .usage_tracker import UsageTracker

    config.ensure_dirs()
    memory = Memory(config.db_path)
    usage = UsageTracker(memory, config.daily_budget_usd)

    fin = memory.get_financial_summary()
    pending = memory.get_pending_questions()
    strategies = memory.get_strategies()
    last = memory.get("last_session_summary") or "No sessions yet."

    print("\n" + "═" * 60)
    print("📈 AUTONOMOUS REVENUE AGENT — STATUS")
    print("═" * 60)
    print(f"  Goal:            $250.00/month")
    print(f"  Monthly Revenue: ${fin['monthly_revenue_usd']:.2f}")
    print(f"  Net Profit:      ${fin['net_profit_usd']:.2f}")
    print(f"  Total Expenses:  ${fin['total_expenses_usd']:.2f}")
    print(f"\n  Daily Budget:    ${config.daily_budget_usd:.4f}")
    print(f"  Used Today:      ${usage.today_cost:.4f}")
    print(f"  Remaining:       ${usage.budget_remaining:.4f}")
    if pending:
        print(f"\n  ⚠️  {len(pending)} unanswered question(s) in {config.questions_path}")
    if strategies:
        print(f"\n  Strategies ({len(strategies)}):")
        for s in strategies:
            print(f"    [{s['status']}] {s['title']}")
    print(f"\n  Last session:\n    {last[:200]}")
    print("═" * 60)
