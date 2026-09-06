"""
emotion_detector.py
Real-time affect detection for LUCIDA using a fine-tuned DistilRoBERTa
emotion classifier: `j-hartmann/emotion-english-distilroberta-base`
(7-way: anger, disgust, fear, joy, neutral, sadness, surprise).

Runs fully locally via `transformers` — the first call downloads and caches
the model from Hugging Face, every call after that is offline. If
`transformers`/`torch` aren't installed, this module degrades to a small
keyword heuristic so the rest of the app never breaks.

This mirrors the optional-dependency + graceful-fallback pattern used across
the project: every capability sits behind a try/except feature flag, and a
single dramatic message never instantly flips the whole app into crisis
mode — a short rolling window has to actually trend that way first.
"""

from __future__ import annotations

import logging
import os
import warnings

# Quiet the very noisy (but harmless) startup logging from TensorFlow/
# transformers/absl that this model pulls in — none of it is an error, it's
# just verbose-by-default library chatter. Must be set BEFORE `transformers`
# (which pulls in tf_keras/tensorflow) is imported below.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")       # 0=all .. 3=errors only
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("tensorflow").setLevel(logging.ERROR)

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, List, Optional

MODEL_NAME = "j-hartmann/emotion-english-distilroberta-base"
PRIMARY_EMOTIONS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]

EMOTION_EMOJI = {
    "anger": "😠", "disgust": "🤢", "fear": "😨", "joy": "🙂",
    "neutral": "😐", "sadness": "😔", "surprise": "😮",
}

# How heavily each emotion pushes the composite "stress" score up or down.
_STRESS_WEIGHTS = {"anger": 1.0, "fear": 1.0, "sadness": 0.8, "disgust": 0.5}
_CALMING_WEIGHTS = {"joy": 1.0, "neutral": 0.3, "surprise": 0.1}

try:
    from transformers import pipeline
    _HAS_TRANSFORMERS = True
except Exception:
    _HAS_TRANSFORMERS = False
    pipeline = None  # type: ignore

# Tiny lexicon used only if transformers/torch aren't installed at all.
_FALLBACK_LEXICON = {
    "anger": ["furious", "pissed", "angry", "hate this", "rage", "screw this"],
    "fear": ["anxious", "scared", "terrified", "panic", "worried", "afraid"],
    "sadness": ["sad", "hopeless", "exhausted", "crying", "burnt out", "burned out", "drained"],
    "disgust": ["disgusted", "gross", "sick of this"],
    "joy": ["happy", "great", "excited", "awesome", "relieved", "proud", "good news"],
    "surprise": ["shocked", "wow", "unexpected", "no way"],
}


@dataclass
class EmotionReading:
    idx: int
    ts: str
    text_preview: str
    scores: Dict[str, float]
    dominant: str
    stress_score: float  # 0.0 (calm) .. 1.0 (high distress)


class EmotionEngine:
    """Loads the classifier once and reuses it; keeps a rolling stress trend."""

    def __init__(self, window: int = 5):
        self._clf = None
        self._load_error: Optional[str] = None
        self.history: Deque[EmotionReading] = deque(maxlen=200)
        self.window = window
        self._msg_count = 0

        if _HAS_TRANSFORMERS:
            try:
                self._clf = pipeline("text-classification", model=MODEL_NAME, top_k=None)
            except Exception as e:
                self._clf = None
                self._load_error = (
                    f"Couldn't load the DistilRoBERTa emotion model ({e}). "
                    "Using a keyword fallback instead — check your internet connection "
                    "for the first-time model download, then restart."
                )
        else:
            self._load_error = (
                "`transformers`/`torch` aren't installed — using a lightweight keyword "
                "fallback. Run `pip install transformers torch` for the real model."
            )

    @property
    def is_model_backed(self) -> bool:
        return self._clf is not None

    @property
    def status_message(self) -> Optional[str]:
        return self._load_error

    def _classify_raw(self, text: str) -> Dict[str, float]:
        if self._clf is not None:
            try:
                raw = self._clf(text[:512])[0]  # [{"label": "...", "score": ...}, ...]
                return {r["label"].lower(): float(r["score"]) for r in raw}
            except Exception:
                pass  # any runtime hiccup falls through to the heuristic below
        return self._fallback_classify(text)

    @staticmethod
    def _fallback_classify(text: str) -> Dict[str, float]:
        text_l = text.lower()
        scores = {e: 0.0 for e in PRIMARY_EMOTIONS}
        hits = 0
        for emotion, words in _FALLBACK_LEXICON.items():
            for w in words:
                if w in text_l:
                    scores[emotion] += 1.0
                    hits += 1
        if hits == 0:
            scores["neutral"] = 1.0
        else:
            scores = {k: v / hits for k, v in scores.items()}
        return scores

    @staticmethod
    def _stress_score(scores: Dict[str, float]) -> float:
        raw = sum(scores.get(e, 0.0) * w for e, w in _STRESS_WEIGHTS.items())
        calm = sum(scores.get(e, 0.0) * w for e, w in _CALMING_WEIGHTS.items())
        return max(0.0, min(1.0, raw - 0.3 * calm))

    def analyze(self, text: str) -> EmotionReading:
        scores = self._classify_raw(text)
        dominant = max(scores, key=scores.get) if scores else "neutral"
        reading = EmotionReading(
            idx=self._msg_count,
            ts=datetime.now().strftime("%H:%M:%S"),
            text_preview=(text[:60] + "…") if len(text) > 60 else text,
            scores=scores,
            dominant=dominant,
            stress_score=self._stress_score(scores),
        )
        self.history.append(reading)
        self._msg_count += 1
        return reading

    def rolling_stress(self) -> float:
        """Average stress over the recent window — smooths out one-off blips."""
        recent = list(self.history)[-self.window:]
        return sum(r.stress_score for r in recent) / len(recent) if recent else 0.0

    def should_escalate(self, threshold: float = 0.55, min_readings: int = 2) -> bool:
        recent = list(self.history)[-self.window:]
        if len(recent) < min_readings:
            return False
        return self.rolling_stress() >= threshold

    def trend_series(self) -> List[float]:
        return [r.stress_score for r in self.history]

    def latest(self) -> Optional[EmotionReading]:
        return self.history[-1] if self.history else None
