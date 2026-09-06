"""
memory.py
Lightweight local persistence so LUCIDA remembers things between
sessions: user-stated facts, a rolling long-term summary, simple stats, and
(for the Financial Advisor persona) a running log of logged expenses.
Everything lives in a single JSON file on disk — no external services,
no accounts, nothing leaves the machine.
"""

import json
import os
from copy import deepcopy
from datetime import date, datetime, timedelta

DEFAULT_MEMORY = {
    "facts": [],
    "long_term_summary": "",
    "stats": {
        "total_messages": 0,
        "quiz_correct": 0,
        "quiz_total": 0,
        "last_active": None,
        "streak_days": 0,
    },
    "expenses": [],  # list of {"date": "YYYY-MM-DD", "category": str, "amount": float, "note": str}
    "monthly_budget": None,  # optional float the user can set for a "prioritize" reference point
}

EXPENSE_CATEGORIES = [
    "Food & Groceries", "Mess/Tiffin", "Dining/Delivery (Swiggy/Zomato)",
    "Hostel/PG Rent", "Transport", "Subscriptions", "Recharge/Data",
    "Textbooks/Stationery", "Entertainment", "Shopping", "Health", "Savings", "Other",
]


def load_memory(path: str) -> dict:
    if not os.path.exists(path):
        return deepcopy(DEFAULT_MEMORY)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        merged = deepcopy(DEFAULT_MEMORY)
        merged.update(data)
        merged["stats"] = {**DEFAULT_MEMORY["stats"], **data.get("stats", {})}
        merged["expenses"] = data.get("expenses", []) if isinstance(data.get("expenses"), list) else []
        return merged
    except (json.JSONDecodeError, OSError):
        # Corrupted or unreadable file — don't crash the app, just start fresh.
        return deepcopy(DEFAULT_MEMORY)


def save_memory(path: str, memory: dict) -> None:
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(memory, f, indent=2)
        os.replace(tmp_path, path)  # atomic on POSIX — avoids a half-written file on crash
    except OSError:
        pass  # non-fatal: memory just won't persist this run


def touch_streak(memory: dict) -> dict:
    today = date.today().isoformat()
    last = memory["stats"].get("last_active")
    if last != today:
        if last is not None:
            try:
                gap = (date.fromisoformat(today) - date.fromisoformat(last)).days
            except ValueError:
                gap = 999
            memory["stats"]["streak_days"] = memory["stats"]["streak_days"] + 1 if gap == 1 else 1
        else:
            memory["stats"]["streak_days"] = 1
        memory["stats"]["last_active"] = today
    return memory


def add_fact(memory: dict, fact: str) -> dict:
    fact = fact.strip()
    if fact and fact not in memory["facts"]:
        memory["facts"].append(fact)
    return memory


def facts_as_context(memory: dict) -> str:
    if not memory["facts"] and not memory["long_term_summary"]:
        return ""
    parts = []
    if memory["long_term_summary"]:
        parts.append(f"Ongoing context about the user: {memory['long_term_summary']}")
    if memory["facts"]:
        parts.append("Facts the user asked you to remember: " + "; ".join(memory["facts"]))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Expense tracking — backs the Financial Advisor persona's Spending Tracker
# tab. Kept dead simple (flat list + on-the-fly aggregation) since this is a
# personal local tool, not a ledger app — no need for a real DB.
# ---------------------------------------------------------------------------

def add_expense(memory: dict, entry_date: str, category: str, amount: float, note: str = "") -> dict:
    memory.setdefault("expenses", []).append({
        "date": entry_date,
        "category": category,
        "amount": round(float(amount), 2),
        "note": note.strip(),
    })
    return memory


def delete_last_expense(memory: dict) -> dict:
    if memory.get("expenses"):
        memory["expenses"].pop()
    return memory


def set_monthly_budget(memory: dict, amount) -> dict:
    memory["monthly_budget"] = round(float(amount), 2) if amount else None
    return memory


def expenses_in_window(memory: dict, days: int = 30) -> list:
    cutoff = date.today() - timedelta(days=days)
    out = []
    for e in memory.get("expenses", []):
        try:
            if date.fromisoformat(e["date"]) >= cutoff:
                out.append(e)
        except (ValueError, KeyError):
            continue
    return out


def expense_summary(memory: dict, days: int = 30) -> dict:
    """Returns {'total': float, 'by_category': {cat: total}, 'count': int, 'days': int}."""
    recent = expenses_in_window(memory, days=days)
    by_category = {}
    total = 0.0
    for e in recent:
        by_category[e["category"]] = by_category.get(e["category"], 0.0) + e["amount"]
        total += e["amount"]
    return {
        "total": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])},
        "count": len(recent),
        "days": days,
    }


def expense_summary_as_context(memory: dict, days: int = 30) -> str:
    """Compact plain-text summary handed to the LLM so financial advice is
    grounded in the user's actual logged numbers instead of guesses."""
    summary = expense_summary(memory, days=days)
    if summary["count"] == 0:
        return "The user hasn't logged any expenses yet in the Spending Tracker."
    lines = [f"Logged spending over the last {days} days: ₹{summary['total']:.2f} across {summary['count']} entries."]
    if summary["by_category"]:
        breakdown = ", ".join(f"{cat}: ₹{amt:.2f}" for cat, amt in summary["by_category"].items())
        lines.append("By category — " + breakdown + ".")
    budget = memory.get("monthly_budget")
    if budget:
        lines.append(f"The user's self-set monthly budget is ₹{budget:.2f}.")
    return "\n".join(lines)
