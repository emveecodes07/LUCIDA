"""
memory.py
Lightweight local persistence so the Desk Buddy remembers things between
sessions: user-stated facts, a rolling long-term summary, and simple stats.
Everything lives in a single JSON file on disk — no external services,
no accounts, nothing leaves the machine.
"""

import json
import os
from copy import deepcopy
from datetime import date

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
}


def load_memory(path: str) -> dict:
    if not os.path.exists(path):
        return deepcopy(DEFAULT_MEMORY)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        merged = deepcopy(DEFAULT_MEMORY)
        merged.update(data)
        merged["stats"] = {**DEFAULT_MEMORY["stats"], **data.get("stats", {})}
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
