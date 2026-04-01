"""Tool implementations for the autonomous revenue agent."""

import json
import logging
import re
import textwrap
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text."""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html)
    except ImportError:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)


def _truncate(text: str, max_chars: int = 8000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[...truncated, {len(text) - max_chars} chars omitted]"


# ── Tool Definitions (JSON schema for Claude) ─────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for information using DuckDuckGo. "
            "Returns a list of results with titles, URLs, and snippets. "
            "Use this to research opportunities, competitors, platforms, and strategies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 8, max 15)",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch the content of a web page and return it as text. "
            "Use this to read articles, documentation, pricing pages, or any URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file in the agent workspace. "
            "Use this to create blog posts, templates, product descriptions, README files, "
            "scripts, or any other content you need to produce."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to the workspace (e.g. 'blog_post.md', 'strategy.txt')",
                },
                "content": {"type": "string", "description": "The file content"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the agent workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to the workspace",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in the agent workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subdirectory": {
                    "type": "string",
                    "description": "Optional subdirectory to list (default: root of workspace)",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    {
        "name": "remember",
        "description": (
            "Store a piece of information persistently across sessions. "
            "Use this to save strategies, contacts, login credentials (non-sensitive), "
            "plans, learnings, or any data you need to remember for future sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "A descriptive key (e.g. 'primary_strategy', 'fiverr_gig_url')",
                },
                "value": {
                    "type": "string",
                    "description": "The value to store",
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "recall",
        "description": "Retrieve a previously stored memory by key.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "The key to look up"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question that requires their input, decision, or approval. "
            "Use this when you need: permission to spend money, account credentials, "
            "approval for a strategy, or information only the user knows. "
            "The question will be written to a file the user can read and answer. "
            "You will receive the answer in the next session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "context": {
                    "type": "string",
                    "description": "Background context explaining WHY you're asking (helps the user give a good answer)",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of suggested options/choices",
                },
            },
            "required": ["question", "context"],
        },
    },
    {
        "name": "get_user_answers",
        "description": (
            "Check if the user has answered any of your pending questions. "
            "Returns a list of answered questions with their responses. "
            "Always call this at the start of each session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "record_revenue",
        "description": (
            "Record income earned. Call this whenever money comes in. "
            "This tracks progress toward the $250/month goal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_usd": {"type": "number", "description": "Amount earned in USD"},
                "source": {
                    "type": "string",
                    "description": "Source of the revenue (e.g. 'Fiverr', 'affiliate', 'product sale')",
                },
                "description": {"type": "string", "description": "Brief description of the income"},
            },
            "required": ["amount_usd", "source", "description"],
        },
    },
    {
        "name": "record_expense",
        "description": (
            "Record money spent. Call this whenever the user spends money on your behalf."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_usd": {"type": "number", "description": "Amount spent in USD"},
                "description": {"type": "string", "description": "What was purchased and why"},
            },
            "required": ["amount_usd", "description"],
        },
    },
    {
        "name": "get_financial_summary",
        "description": "Get the current financial status: revenue, expenses, profit, and monthly progress.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "save_strategy",
        "description": (
            "Save a business strategy to track and develop. "
            "Use this to document strategies you're researching or executing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short strategy name"},
                "description": {
                    "type": "string",
                    "description": "Detailed description: what it is, how it works, potential revenue",
                },
            },
            "required": ["title", "description"],
        },
    },
    {
        "name": "get_strategies",
        "description": "List all strategies you've saved (researching, active, completed, abandoned).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "log_progress",
        "description": (
            "Log what you accomplished in this session. "
            "Write a summary of actions taken, results observed, and next steps. "
            "This creates a record you can review in future sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished and what comes next",
                },
            },
            "required": ["summary"],
        },
    },
]


# ── Tool Executor ─────────────────────────────────────────────────────────────

class ToolExecutor:
    def __init__(self, memory, workspace_dir: Path, session_id: str) -> None:
        self.memory = memory
        self.workspace_dir = workspace_dir
        self.session_id = session_id
        self._questions_path = memory.db_path.parent / "QUESTIONS_FOR_YOU.md"

    def execute(self, tool_name: str, tool_input: dict) -> str:
        try:
            method = getattr(self, f"_tool_{tool_name}", None)
            if method is None:
                return f"Error: unknown tool '{tool_name}'"
            result = method(**tool_input)
            self.memory.log_action(self.session_id, f"{tool_name}({json.dumps(tool_input)[:200]})", str(result)[:500])
            return result
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return f"Error executing {tool_name}: {exc}"

    # ── Web Tools ─────────────────────────────────────────────────────────────

    def _tool_web_search(self, query: str, max_results: int = 8) -> str:
        max_results = min(int(max_results), 15)
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return "Search unavailable: install 'ddgs' package."
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)
            if not results:
                return "No results found."
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r.get('title', 'No title')}**")
                lines.append(f"   URL: {r.get('href', '')}")
                lines.append(f"   {r.get('body', '')[:300]}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Search error: {e}. The agent can still proceed using web_fetch with known URLs."

    def _tool_web_fetch(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type:
                text = _html_to_text(resp.text)
            else:
                text = resp.text
            return _truncate(text.strip())
        except requests.RequestException as e:
            return f"Fetch error: {e}"

    # ── File Tools ────────────────────────────────────────────────────────────

    def _safe_path(self, filename: str) -> Path:
        """Resolve filename to a safe path inside the workspace."""
        # Strip leading slashes/dots to prevent path traversal
        clean = re.sub(r"^[./\\]+", "", filename)
        path = (self.workspace_dir / clean).resolve()
        if not str(path).startswith(str(self.workspace_dir.resolve())):
            raise ValueError(f"Path traversal denied: {filename}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _tool_write_file(self, filename: str, content: str) -> str:
        path = self._safe_path(filename)
        path.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to workspace/{filename}"

    def _tool_read_file(self, filename: str) -> str:
        path = self._safe_path(filename)
        if not path.exists():
            return f"File not found: {filename}"
        return _truncate(path.read_text(encoding="utf-8"))

    def _tool_list_files(self, subdirectory: str = "") -> str:
        base = self.workspace_dir
        if subdirectory:
            base = (base / subdirectory).resolve()
        if not base.exists():
            return "Directory not found."
        files = sorted(base.rglob("*"))
        if not files:
            return "Workspace is empty."
        lines = []
        for f in files:
            rel = f.relative_to(self.workspace_dir)
            size = f.stat().st_size if f.is_file() else 0
            kind = "file" if f.is_file() else "dir"
            lines.append(f"  {kind}: {rel}  ({size:,} bytes)" if kind == "file" else f"  {kind}: {rel}/")
        return "\n".join(lines)

    # ── Memory Tools ──────────────────────────────────────────────────────────

    def _tool_remember(self, key: str, value: str) -> str:
        self.memory.set(key, value)
        return f"Stored: {key}"

    def _tool_recall(self, key: str) -> str:
        value = self.memory.get(key)
        return value if value is not None else f"No memory found for key '{key}'"

    # ── User Communication ────────────────────────────────────────────────────

    def _tool_ask_user(self, question: str, context: str, options: list[str] | None = None) -> str:
        qid = self.memory.add_question(question, context)
        self._regenerate_questions_file()
        msg = f"Question #{qid} saved. The user will be notified in QUESTIONS_FOR_YOU.md"
        if options:
            msg += f"\nOptions provided: {', '.join(options)}"
        return msg

    def _tool_get_user_answers(self) -> str:
        questions = self.memory.get_all_questions()
        answered = [q for q in questions if q["status"] == "answered"]
        pending = [q for q in questions if q["status"] == "pending"]

        # Check QUESTIONS_FOR_YOU.md for inline answers
        self._parse_inline_answers()

        # Re-fetch after parsing
        questions = self.memory.get_all_questions()
        answered = [q for q in questions if q["status"] == "answered"]
        pending = [q for q in questions if q["status"] == "pending"]

        lines = []
        if answered:
            lines.append(f"## Answered Questions ({len(answered)}):")
            for q in answered[-5:]:  # Show last 5
                lines.append(f"\n**Q#{q['id']}**: {q['question']}")
                lines.append(f"**Answer**: {q['answer']}")
        if pending:
            lines.append(f"\n## Pending Questions ({len(pending)}) — Awaiting user response:")
            for q in pending:
                lines.append(f"  - Q#{q['id']}: {q['question'][:100]}")
        if not answered and not pending:
            lines.append("No questions on record.")

        return "\n".join(lines) if lines else "No answered questions yet."

    def _parse_inline_answers(self) -> None:
        """Parse QUESTIONS_FOR_YOU.md for answers written by the user."""
        if not self._questions_path.exists():
            return
        content = self._questions_path.read_text(encoding="utf-8")

        # Find blocks like: **Your Answer**: some text
        pattern = r"### Question #(\d+).*?>\s*\*\*Your Answer\*\*:\s*(.+?)(?=\n###|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)
        for qid_str, answer_text in matches:
            qid = int(qid_str)
            answer = answer_text.strip()
            # Only record non-empty, non-placeholder answers
            if answer and answer.lower() not in ("type your answer here", ""):
                questions = self.memory.get_all_questions()
                for q in questions:
                    if q["id"] == qid and q["status"] == "pending":
                        self.memory.answer_question(qid, answer)
                        logger.info("Parsed answer for Q#%d from questions file", qid)

    def _regenerate_questions_file(self) -> None:
        """Regenerate the human-readable questions file."""
        questions = self.memory.get_all_questions()
        lines = [
            "# Questions From Your Revenue Agent",
            "",
            "> **How to answer**: Find the question below and replace *\"Type your answer here\"* with your response.",
            "> Save the file. The agent will read your answer in the next session.",
            "",
            "---",
            "",
        ]
        if not questions:
            lines.append("*No questions yet.*")
        else:
            for q in sorted(questions, key=lambda x: x["id"]):
                status_emoji = "✅" if q["status"] == "answered" else "⏳"
                lines.append(f"### Question #{q['id']} {status_emoji} [{q['status'].upper()}]")
                lines.append(f"*Asked on: {q['created_at'][:10]}*")
                lines.append("")
                lines.append(f"**Context**: {q['context']}")
                lines.append("")
                lines.append(f"**Question**: {q['question']}")
                lines.append("")
                if q["status"] == "answered":
                    lines.append(f"> ~~**Your Answer**~~ (received): {q['answer']}")
                else:
                    lines.append("> **Your Answer**: Type your answer here")
                lines.append("")
                lines.append("---")
                lines.append("")
        self._questions_path.write_text("\n".join(lines), encoding="utf-8")

    # ── Financial Tools ───────────────────────────────────────────────────────

    def _tool_record_revenue(self, amount_usd: float, source: str, description: str) -> str:
        rid = self.memory.add_revenue(float(amount_usd), source, description)
        summary = self.memory.get_financial_summary()
        return (
            f"Revenue recorded: ${amount_usd:.2f} from {source}\n"
            f"Monthly total: ${summary['monthly_revenue_usd']:.2f} / $250.00 goal "
            f"({summary['monthly_revenue_usd'] / 250 * 100:.1f}%)"
        )

    def _tool_record_expense(self, amount_usd: float, description: str) -> str:
        self.memory.add_expense(float(amount_usd), description)
        return f"Expense recorded: ${amount_usd:.2f} — {description}"

    def _tool_get_financial_summary(self) -> str:
        s = self.memory.get_financial_summary()
        pct = min(100, s["monthly_revenue_usd"] / 250 * 100)
        lines = [
            "## Financial Summary",
            f"- Monthly Revenue: ${s['monthly_revenue_usd']:.2f} / $250.00 ({pct:.1f}% of goal)",
            f"- Total Revenue: ${s['total_revenue_usd']:.2f}",
            f"- Total Expenses: ${s['total_expenses_usd']:.2f}",
            f"- Net Profit: ${s['net_profit_usd']:.2f}",
        ]
        if s["revenue_by_source"]:
            lines.append("- Revenue Sources:")
            for src in s["revenue_by_source"]:
                lines.append(f"    - {src['source']}: ${src['total']:.2f}")
        return "\n".join(lines)

    # ── Strategy Tools ────────────────────────────────────────────────────────

    def _tool_save_strategy(self, title: str, description: str) -> str:
        sid = self.memory.add_strategy(title, description)
        return f"Strategy #{sid} saved: {title}"

    def _tool_get_strategies(self) -> str:
        strategies = self.memory.get_strategies()
        if not strategies:
            return "No strategies saved yet."
        lines = []
        for s in strategies:
            lines.append(f"**#{s['id']} — {s['title']}** [{s['status']}]")
            lines.append(f"  Revenue: ${s['revenue_usd']:.2f}")
            lines.append(f"  {s['description'][:200]}")
            if s["notes"]:
                lines.append(f"  Notes: {s['notes'][:100]}")
            lines.append("")
        return "\n".join(lines)

    def _tool_log_progress(self, summary: str) -> str:
        self.memory.log_action(self.session_id, "session_summary", summary)
        self.memory.set("last_session_summary", summary)
        self.memory.set("last_session_date", self.memory.get_today_str())
        return "Progress logged."
