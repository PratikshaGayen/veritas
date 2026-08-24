"""Deterministic text surgery — stage 2b of the resolution pipeline.

Pure Python, no GenLayer imports. Kills the divergence sources between
leader and validator fetches (docs/ARCHITECTURE.md section 1) before the
text reaches the model: rotating ads already dropped by strip_to_text,
relative/sub-day clocks redacted, large volatile numbers quantized, then
windowed around the question's keywords.

The test that matters for this module is test_normalization_is_stable
in tests/unit/test_normalize.py: the same URL fetched twice, minutes apart,
must normalize to identical bytes.
"""

from __future__ import annotations

import re

from lib.normalize._html import strip_to_text

MAX_EVIDENCE_CHARS = 4000
_WINDOW_RADIUS = MAX_EVIDENCE_CHARS // 2

_REL_TIME_RE = re.compile(
    r"\b("
    r"just now"
    r"|a (?:second|minute|hour|day|week|month|year) ago"
    r"|\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago"
    r"|(?:yesterday|today|tomorrow)"
    r")\b",
    re.IGNORECASE,
)

# Sub-day timestamps: "14:32", "14:32:07", "2:32 PM", ISO datetime with a T.
_SUBDAY_TIME_RE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?\b"
    r"|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)

# Negative lookahead protects a YYYY-MM-DD year from being "quantized" into
# a different year — dates are meaningful, day-granularity data (see
# _project_date_day / DATE_DAY schemas) and must survive this pass intact.
_NUMBER_RE = re.compile(r"\d[\d,]{2,}(?!-\d{2}-\d{2})")

_WORD_RE = re.compile(r"[a-zA-Z0-9]{4,}")
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "this",
        "that",
        "what",
        "when",
        "where",
        "which",
        "does",
        "did",
        "has",
        "have",
        "for",
        "and",
        "than",
        "more",
    }
)


def _redact_times(text: str) -> str:
    text = _REL_TIME_RE.sub("[REL_TIME]", text)
    text = _SUBDAY_TIME_RE.sub("[TIME]", text)
    return text


def _quantize_number(match: re.Match) -> str:
    raw = match.group(0).replace(",", "")
    try:
        n = int(raw)
    except ValueError:
        return match.group(0)
    if n < 1000:
        # Small numbers are usually the meaningful data (prices, percentages,
        # counts of things a question asks about) — leave them alone. Large
        # numbers are the volatile ones (follower counts, view counts).
        return match.group(0)
    digits = len(str(n))
    sig_figs = 2
    factor = 10 ** (digits - sig_figs)
    quantized = round(n / factor) * factor
    return str(quantized)


def _quantize_numbers(text: str) -> str:
    return _NUMBER_RE.sub(_quantize_number, text)


def _question_keywords(question: str) -> list[str]:
    words = _WORD_RE.findall((question or "").lower())
    seen = []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.append(w)
    return seen


def _window(text: str, question: str) -> str:
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text

    lowered = text.lower()
    anchor = None
    for kw in _question_keywords(question):
        idx = lowered.find(kw)
        if idx != -1:
            anchor = idx
            break

    if anchor is None:
        return text[:MAX_EVIDENCE_CHARS]

    start = max(0, anchor - _WINDOW_RADIUS)
    end = min(len(text), start + MAX_EVIDENCE_CHARS)
    start = max(0, end - MAX_EVIDENCE_CHARS)
    return text[start:end]


def normalize(body: str, question: str) -> str:
    """Deterministic pipeline: strip -> redact times -> quantize numbers ->
    collapse whitespace -> window-truncate around the question's keywords.
    Same input (body, question) always produces the same output.
    """
    text = strip_to_text(body or "")
    text = _redact_times(text)
    text = _quantize_numbers(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _window(text, question or "")
    return text
