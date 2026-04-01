"""Configuration for the autonomous revenue agent."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WORKSPACE_DIR = DATA_DIR / "workspace"


@dataclass
class Config:
    # Anthropic API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = "claude-opus-4-6"

    # Budget: agent is limited to 8% of the weekly budget per day
    weekly_budget_usd: float = float(os.getenv("WEEKLY_BUDGET_USD", "10.0"))
    daily_limit_pct: float = 0.08  # 8% of weekly budget per day

    # Goal
    goal_monthly_usd: float = 250.0
    initial_investment_usd: float = float(os.getenv("INITIAL_INVESTMENT_USD", "100.0"))

    # Paths
    data_dir: Path = DATA_DIR
    workspace_dir: Path = WORKSPACE_DIR
    db_path: Path = DATA_DIR / "agent.db"
    log_path: Path = DATA_DIR / "agent.log"
    questions_path: Path = DATA_DIR / "QUESTIONS_FOR_YOU.md"

    @property
    def daily_budget_usd(self) -> float:
        return self.weekly_budget_usd * self.daily_limit_pct

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(exist_ok=True)
        self.workspace_dir.mkdir(exist_ok=True)


config = Config()
