"""The availability gate — stage 2 of the resolution pipeline.

Pure Python, no GenLayer imports. Answers "could I actually see this page?"
before any LLM call, per docs/ARCHITECTURE.md section 4. Detection is
deterministic and rule-based, on purpose: an LLM-judged gate would itself be
non-deterministic, defeating the point of gating before the model.

Rule order matters and is fixed: status code, then throttle markers, then
bot-wall markers, then paywall markers + length floor, then empty-evidence
floor, then question-overlap. First match wins.
"""

from __future__ import annotations

import re

from lib.normalize._html import strip_to_text

VERDICT_READABLE = "READABLE"
VERDICT_UNAVAILABLE = "UNAVAILABLE"

REASON_RATE_LIMIT = "RATE_LIMIT"
REASON_TRANSIENT = "TRANSIENT"
REASON_EXTERNAL = "EXTERNAL"
REASON_BOT_WALL = "BOT_WALL"
REASON_PAYWALL = "PAYWALL"
REASON_EMPTY = "EMPTY"
REASON_NO_OVERLAP = "NO_OVERLAP"

MIN_EVIDENCE_CHARS = 40
PAYWALL_LENGTH_FLOOR = 600

_BOT_WALL_MARKERS = (
    "just a moment",
    "enable javascript",
    "access denied",
    "attention required",
    "checking your browser",
    "verify you are human",
    "please enable cookies",
    "unusual traffic",
)

_PAYWALL_MARKERS = (
    "subscribe to continue",
    "subscribe now to read",
    "this article is for subscribers",
    "you have reached your article limit",
    "become a subscriber",
    "sign in to continue reading",
    "to continue reading this article",
)

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "this",
        "that",
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "does",
        "did",
        "do",
        "has",
        "have",
        "had",
        "for",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "it",
        "than",
        "more",
    }
)
_WORD_RE = re.compile(r"[a-z0-9]{4,}")


def _question_keywords(question: str) -> set[str]:
    words = _WORD_RE.findall(question.lower())
    return {w for w in words if w not in _STOPWORDS}


def check(status_code: int, body: str, question: str) -> tuple[str, str]:
    """Returns (verdict, reason). reason is "" when verdict is READABLE."""
    if status_code == 429:
        return (VERDICT_UNAVAILABLE, REASON_RATE_LIMIT)
    if status_code >= 500:
        return (VERDICT_UNAVAILABLE, REASON_TRANSIENT)
    if status_code >= 400:
        return (VERDICT_UNAVAILABLE, REASON_EXTERNAL)

    text = strip_to_text(body or "")
    lowered = text.lower()

    for marker in _BOT_WALL_MARKERS:
        if marker in lowered:
            return (VERDICT_UNAVAILABLE, REASON_BOT_WALL)

    if len(text) < PAYWALL_LENGTH_FLOOR:
        for marker in _PAYWALL_MARKERS:
            if marker in lowered:
                return (VERDICT_UNAVAILABLE, REASON_PAYWALL)

    if len(text) < MIN_EVIDENCE_CHARS:
        return (VERDICT_UNAVAILABLE, REASON_EMPTY)

    keywords = _question_keywords(question or "")
    if keywords and not any(k in lowered for k in keywords):
        return (VERDICT_UNAVAILABLE, REASON_NO_OVERLAP)

    return (VERDICT_READABLE, "")
