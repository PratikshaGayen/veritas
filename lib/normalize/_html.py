"""Shared, minimal HTML-to-text stripping.

Regex-based on purpose: this project does not depend on an HTML parser
library, and the goal is not general-purpose HTML robustness — it is
deterministic, identical output for leader and every validator (see
docs/ARCHITECTURE.md section 4, stage 2b). A regex-based stripper is
adequate for that and keeps lib/ dependency-free.
"""

from __future__ import annotations

import html
import re

_DROP_BLOCK_RE = re.compile(
    r"<(script|style|nav|footer|aside)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_to_text(raw_html: str) -> str:
    """Remove volatile/non-content blocks and tags, unescape entities,
    collapse whitespace. Does NOT redact timestamps or quantize numbers —
    that is normalize.normalize()'s job. This is the shared substrate both
    availability.check() and normalize.normalize() build on.
    """
    if not raw_html:
        return ""
    text = _DROP_BLOCK_RE.sub(" ", raw_html)
    text = _COMMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text
