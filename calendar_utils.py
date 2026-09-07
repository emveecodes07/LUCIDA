"""
calendar_utils.py
Pure, framework-agnostic helpers backing LUCIDA's Calendar tab. The event
data itself lives in memory.py (same JSON file as everything else — so
events are "active memory" that persists across restarts and persona
switches). This module owns two things:

1. A cheap, zero-model-call heuristic that flags when a chat message
   mentions a day/date in a way worth pinning — same pattern as
   personas.suggest_alternate_persona(): pure keyword/regex matching, no
   LLM call, so it's effectively free to run on every message and never
   adds latency or interferes with the persona's actual reply.
2. A best-effort date guess from that message, used only to pre-fill the
   pin form — the user can always correct it before saving.

Deliberately conservative: `mentions_date()` alone would fire on almost any
casual "see you tomorrow", so the pop-up is gated on `is_pin_worthy()`,
which additionally requires a word that suggests something worth
remembering (exam, due, deadline, appointment, etc.). This keeps the nudge
useful instead of naggy, exactly like the existing persona-suggestion nudge
only fires on real keyword hits.
"""

import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
]

_DATE_PATTERNS = [
    r"\btomorrow\b", r"\btonight\b", r"\btoday\b",
    r"\bnext week\b", r"\bthis (?:weekend|week)\b",
    r"\b(?:" + "|".join(WEEKDAYS) + r")\b",
    r"\b(?:" + "|".join(MONTHS) + r")\s+\d{1,2}(?:st|nd|rd|th)?\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:" + "|".join(MONTHS) + r")\b",
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    r"\b\d{1,2}(?:st|nd|rd|th)\b",
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)

# Words that make a date-mention worth flagging as pin-worthy — filters out
# plain small talk that just happens to contain "today"/"tomorrow".
_PIN_WORTHY_HINTS = [
    "exam", "test", "quiz", "due", "deadline", "assignment", "submission",
    "submit", "interview", "presentation", "viva", "meeting", "appointment",
    "fee", "fees", "reminder", "remind me", "don't forget", "dont forget",
    "birthday", "event", "registration", "last date",
]


def mentions_date(text: str) -> bool:
    """True if the text contains anything that reads like a day/date."""
    if not text:
        return False
    return bool(_DATE_RE.search(text))


def is_pin_worthy(text: str) -> bool:
    """Mentions a date/day AND sounds like something worth remembering —
    the gate the app uses to decide whether to show the pin pop-up."""
    if not mentions_date(text):
        return False
    text_l = text.lower()
    return any(h in text_l for h in _PIN_WORTHY_HINTS)


def guess_date(text: str, today: date = None) -> str:
    """Best-effort ISO date guess from the message, only used to pre-fill
    the pin form. Falls back to today if nothing concrete is found."""
    today = today or date.today()
    text_l = text.lower()
    if "tomorrow" in text_l:
        return (today + timedelta(days=1)).isoformat()
    if "today" in text_l or "tonight" in text_l:
        return today.isoformat()
    for i, wd in enumerate(WEEKDAYS):
        if wd in text_l:
            days_ahead = (i - today.weekday()) % 7
            days_ahead = days_ahead or 7  # saying "monday" ON a Monday means next Monday
            return (today + timedelta(days=days_ahead)).isoformat()
    ordinal = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", text_l)
    if ordinal:
        day_num = int(ordinal.group(1))
        if 1 <= day_num <= 31:
            year, month = today.year, today.month
            try:
                candidate = date(year, month, day_num)
            except ValueError:
                candidate = None
            if candidate and candidate < today:
                # Already passed this month — assume they mean next month.
                month = month + 1 if month < 12 else 1
                year = year if month != 1 else year + 1
                try:
                    candidate = date(year, month, day_num)
                except ValueError:
                    candidate = None
            if candidate:
                return candidate.isoformat()
    return today.isoformat()
