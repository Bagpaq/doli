"""Persistent SQLite memory for the agent."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class Memory:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key   TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS daily_usage (
                    date          TEXT PRIMARY KEY,
                    input_tokens  INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd      REAL    DEFAULT 0.0,
                    sessions      INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS revenue (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT,
                    amount_usd  REAL,
                    source      TEXT,
                    description TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS expenses (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT,
                    amount_usd  REAL,
                    description TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS action_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    action     TEXT,
                    result     TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS user_questions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    question    TEXT,
                    context     TEXT,
                    answer      TEXT,
                    status      TEXT DEFAULT 'pending',
                    created_at  TEXT DEFAULT (datetime('now')),
                    answered_at TEXT
                );

                CREATE TABLE IF NOT EXISTS strategies (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT,
                    description TEXT,
                    status      TEXT DEFAULT 'researching',
                    revenue_usd REAL DEFAULT 0.0,
                    notes       TEXT,
                    created_at  TEXT DEFAULT (datetime('now')),
                    updated_at  TEXT DEFAULT (datetime('now'))
                );
            """)

    # ── Key-Value Store ──────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set(self, key: str, value: Any) -> None:
        text = json.dumps(value) if not isinstance(value, str) else value
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, text),
            )

    def get_json(self, key: str) -> Any:
        raw = self.get(key)
        return json.loads(raw) if raw else None

    # ── Revenue & Expenses ───────────────────────────────────────────────────

    def add_revenue(self, amount_usd: float, source: str, description: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO revenue (date, amount_usd, source, description) VALUES (date('now'), ?, ?, ?)",
                (amount_usd, source, description),
            )
            return cur.lastrowid

    def add_expense(self, amount_usd: float, description: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO expenses (date, amount_usd, description) VALUES (date('now'), ?, ?)",
                (amount_usd, description),
            )
            return cur.lastrowid

    def get_financial_summary(self) -> dict:
        with self._connect() as conn:
            total_revenue = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM revenue").fetchone()[0]
            total_expenses = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM expenses").fetchone()[0]

            # This month
            monthly_revenue = conn.execute(
                "SELECT COALESCE(SUM(amount_usd), 0) FROM revenue WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
            ).fetchone()[0]

            # By source
            sources = conn.execute(
                "SELECT source, SUM(amount_usd) as total FROM revenue GROUP BY source ORDER BY total DESC"
            ).fetchall()

            return {
                "total_revenue_usd": round(total_revenue, 2),
                "total_expenses_usd": round(total_expenses, 2),
                "net_profit_usd": round(total_revenue - total_expenses, 2),
                "monthly_revenue_usd": round(monthly_revenue, 2),
                "revenue_by_source": [{"source": r["source"], "total": round(r["total"], 2)} for r in sources],
            }

    # ── Action Log ───────────────────────────────────────────────────────────

    def log_action(self, session_id: str, action: str, result: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO action_log (session_id, action, result) VALUES (?, ?, ?)",
                (session_id, action, result),
            )

    def get_recent_actions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM action_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── User Q&A ─────────────────────────────────────────────────────────────

    def add_question(self, question: str, context: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO user_questions (question, context) VALUES (?, ?)",
                (question, context),
            )
            return cur.lastrowid

    def get_pending_questions(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_questions WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def answer_question(self, question_id: int, answer: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE user_questions SET answer = ?, status = 'answered', answered_at = datetime('now') WHERE id = ?",
                (answer, question_id),
            )

    def get_all_questions(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_questions ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Strategies ───────────────────────────────────────────────────────────

    def add_strategy(self, title: str, description: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO strategies (title, description) VALUES (?, ?)",
                (title, description),
            )
            return cur.lastrowid

    def update_strategy(self, strategy_id: int, **kwargs) -> None:
        allowed = {"title", "description", "status", "revenue_usd", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [strategy_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE strategies SET {sets}, updated_at = datetime('now') WHERE id = ?",
                values,
            )

    def get_strategies(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM strategies ORDER BY status, created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Usage ────────────────────────────────────────────────────────────────

    def get_today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def get_daily_usage(self, date: Optional[str] = None) -> dict:
        date = date or self.get_today_str()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_usage WHERE date = ?", (date,)
            ).fetchone()
            if row:
                return dict(row)
            return {"date": date, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "sessions": 0}

    def add_usage(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        today = self.get_today_str()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage (date, input_tokens, output_tokens, cost_usd, sessions)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    input_tokens  = input_tokens  + excluded.input_tokens,
                    output_tokens = output_tokens + excluded.output_tokens,
                    cost_usd      = cost_usd      + excluded.cost_usd,
                    sessions      = sessions      + 1
                """,
                (today, input_tokens, output_tokens, cost_usd),
            )

    def get_week_cost(self) -> float:
        """Return the total cost for the current week (Mon–Sun)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM daily_usage
                WHERE date >= date('now', 'weekday 1', '-7 days')
                """
            ).fetchone()
            return round(row[0], 4)
