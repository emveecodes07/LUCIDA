"""
document_utils.py
Parses uploaded course material (pdf, pptx, docx) and builds prompts that turn
it into a full local "study pack": a revision summary, a plain-language
overview, section pointers, key terms, flashcards, and a short quiz.

Speed note: the study pack is built from ONE model call instead of several.
Every extra call re-sends and re-processes the full source text, which is the
expensive part — a single combined JSON response cuts that cost roughly in
half-to-a-third versus separate summary/quiz/flashcard calls, with no loss of
depth in any individual section.
"""

import hashlib
import json

from pypdf import PdfReader
from pptx import Presentation
from docx import Document

MAX_CHARS = 8000  # keeps prompts within a safe context window for small local models


def extract_text(file) -> str:
    ext = file.name.split(".")[-1].lower()
    text = ""
    try:
        if ext == "pdf":
            reader = PdfReader(file)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        elif ext in ("ppt", "pptx"):
            prs = Presentation(file)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
        elif ext in ("doc", "docx"):
            doc = Document(file)
            for p in doc.paragraphs:
                text += p.text + "\n"
        else:
            raise ValueError(f"Unsupported file type: .{ext}")
    except Exception as e:
        raise ValueError(f"Couldn't read this {ext.upper()} file: {e}")

    text = text.strip()
    if not text:
        raise ValueError("No extractable text found — is this a scanned/image-only file?")
    return text[:MAX_CHARS]


def file_fingerprint(file) -> str:
    """Cheap hash so we skip regenerating a study pack for a file we've already processed."""
    file.seek(0)
    digest = hashlib.md5(file.read()).hexdigest()
    file.seek(0)
    return digest


def _strip_json_fences(raw: str) -> str:
    cleaned = raw.strip()
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Combined study pack: summary + overview + section pointers + keywords +
# flashcards + quiz, all from a single model call.
# ---------------------------------------------------------------------------

def build_study_pack_prompt(text: str, n_quiz: int = 4, n_flashcards: int = 8) -> str:
    return (
        "You are building a complete study pack from the material below. Base every field "
        "ONLY on the material — never invent facts that aren't in it.\n\n"
        "Respond with ONLY a raw JSON object, no markdown fences, no prose outside the JSON, "
        "matching EXACTLY this shape:\n"
        "{\n"
        '  "overview": "2-3 sentence plain-language overview of what this material covers and why it matters",\n'
        '  "summary": ["4-6 high-yield bullets — concepts, definitions, facts likely to be tested, no filler"],\n'
        '  "section_pointers": ["one line per major section/topic: name — what to focus on when reviewing it"],\n'
        f'  "keywords": ["{max(8, 1)}-14 major keywords or named concepts, most important first"],\n'
        f'  "flashcards": [{{"front": "question or term", "back": "concise answer"}}] — exactly {n_flashcards} cards,\n'
        f'  "quiz": [{{"q": "question text", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "answer": "A"}}] — exactly {n_quiz} questions\n'
        "}\n\nMATERIAL:\n" + text
    )


def parse_study_pack_json(raw: str) -> dict:
    """Robustly parses the study pack JSON, defaulting any missing/malformed field to empty."""
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}

    def _str(v):
        return v if isinstance(v, str) else ""

    def _list_of_str(v):
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    def _flashcards(v):
        if not isinstance(v, list):
            return []
        return [c for c in v if isinstance(c, dict) and "front" in c and "back" in c]

    def _quiz(v):
        if not isinstance(v, list):
            return []
        return [q for q in v if isinstance(q, dict) and "q" in q and "options" in q and "answer" in q]

    return {
        "overview": _str(data.get("overview")),
        "summary": _list_of_str(data.get("summary")),
        "section_pointers": _list_of_str(data.get("section_pointers")),
        "keywords": _list_of_str(data.get("keywords")),
        "flashcards": _flashcards(data.get("flashcards")),
        "quiz": _quiz(data.get("quiz")),
    }


# ---------------------------------------------------------------------------
# Generic (no-upload) quiz — built from a topic the user types in, using the
# model's own knowledge rather than an uploaded file.
# ---------------------------------------------------------------------------

def build_generic_quiz_prompt(topic: str, n_questions: int = 4) -> str:
    return (
        f"Generate exactly {n_questions} multiple-choice quiz questions to help someone study "
        f'the topic: "{topic}". Use your own general knowledge — no source material is provided. '
        "Respond with ONLY a raw JSON array, no markdown, no prose, matching exactly this shape: "
        '[{"q": "question text", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "answer": "A"}]'
    )


def parse_quiz_json(raw: str) -> list:
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list) and all(
            isinstance(q, dict) and "q" in q and "options" in q and "answer" in q for q in data
        ):
            return data
    except json.JSONDecodeError:
        pass
    return []
