"""Project an arbitrary model-output string onto a declared Schema.

Pure Python, no GenLayer imports. This is the deterministic "stage 4" of the
resolution pipeline (docs/ARCHITECTURE.md section 4): the model's raw text
either projects cleanly onto the schema, or it doesn't — there is no fuzzy
matching, no nearest-neighbour guessing. project() never raises; every input
maps to a (status, value) pair.
"""

from __future__ import annotations

import re
from datetime import date

from lib.schema.parse import Schema

STATUS_OK = "OK"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_SCHEMA_VIOLATION = "SCHEMA_VIOLATION"

_VIOLATION = (STATUS_SCHEMA_VIOLATION, "")

_BOOL_TRUE = {"true", "yes", "1"}
_BOOL_FALSE = {"false", "no", "0"}
_BOOL_TOKEN_RE = re.compile(r"\b(true|false|yes|no|1|0)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def project(schema: Schema, raw: str) -> tuple[str, str]:
    """Returns (status, canonical_value). Never raises."""
    if raw is None:
        return _VIOLATION
    if not isinstance(raw, str):
        raw = str(raw)

    stripped = raw.strip()
    if stripped.upper() == "UNAVAILABLE":
        return (STATUS_UNAVAILABLE, "")

    if not stripped:
        return _VIOLATION

    if schema.kind == "BOOL":
        return _project_bool(stripped)
    if schema.kind == "ENUM":
        return _project_enum(schema, stripped)
    if schema.kind == "BAND":
        return _project_band(schema, stripped)
    if schema.kind == "INT":
        return _project_int(schema, stripped)
    if schema.kind == "DATE_DAY":
        return _project_date_day(stripped)

    return _VIOLATION


def _project_bool(raw: str) -> tuple[str, str]:
    m = _BOOL_TOKEN_RE.search(raw)
    if not m:
        return _VIOLATION
    token = m.group(1).lower()
    if token in _BOOL_TRUE:
        return (STATUS_OK, "true")
    if token in _BOOL_FALSE:
        return (STATUS_OK, "false")
    return _VIOLATION  # pragma: no cover — unreachable given the regex alternation


def _project_enum(schema: Schema, raw: str) -> tuple[str, str]:
    lowered = raw.lower()
    if lowered in schema.options:
        return (STATUS_OK, lowered)
    for option in schema.options:
        if re.search(rf"\b{re.escape(option)}\b", lowered):
            return (STATUS_OK, option)
    return _VIOLATION


def _project_band(schema: Schema, raw: str) -> tuple[str, str]:
    m = _NUMBER_RE.search(raw)
    if not m:
        return _VIOLATION
    try:
        value = float(m.group(0))
    except ValueError:
        return _VIOLATION  # pragma: no cover — regex guarantees a parseable float
    clamped = min(max(value, schema.lo), schema.hi)
    band_index = int(clamped - schema.lo) // schema.step
    max_index = (schema.hi - schema.lo) // schema.step - 1
    band_index = min(band_index, max_index)
    return (STATUS_OK, str(band_index))


def _project_int(schema: Schema, raw: str) -> tuple[str, str]:
    m = _INT_RE.search(raw)
    if not m:
        return _VIOLATION
    try:
        value = int(m.group(0))
    except ValueError:
        return _VIOLATION  # pragma: no cover — regex guarantees a parseable int
    if value < schema.lo or value > schema.hi:
        return _VIOLATION
    return (STATUS_OK, str(value))


def _project_date_day(raw: str) -> tuple[str, str]:
    m = _DATE_RE.search(raw)
    if not m:
        return _VIOLATION
    candidate = m.group(0)
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return _VIOLATION
    return (STATUS_OK, parsed.isoformat())
