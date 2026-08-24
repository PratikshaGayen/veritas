"""Phase 1 task 1.2 — projecting model output onto a declared schema.

project() must NEVER raise. Every test in this file asserts that, including
the garbage-input sweep at the bottom.
"""

import pytest

from lib.schema.parse import parse_schema
from lib.schema.project import (
    STATUS_OK,
    STATUS_SCHEMA_VIOLATION,
    STATUS_UNAVAILABLE,
    project,
)

BOOL = parse_schema("BOOL")
ENUM = parse_schema("ENUM:up,down,degraded")
BAND = parse_schema("BAND:0:1000:50")  # 20 bands: 0..19
INT = parse_schema("INT:0:100")
DATE = parse_schema("DATE_DAY")


# ---------------------------------------------------------------------------
# UNAVAILABLE token — universal across every schema kind, checked first
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("schema", [BOOL, ENUM, BAND, INT, DATE])
@pytest.mark.parametrize("raw", ["UNAVAILABLE", "unavailable", "  Unavailable  "])
def test_unavailable_token_is_universal(schema, raw):
    assert project(schema, raw) == (STATUS_UNAVAILABLE, "")


# ---------------------------------------------------------------------------
# BOOL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", "true"),
        ("True", "true"),
        ("TRUE", "true"),
        ("yes", "true"),
        ("1", "true"),
        ("The answer is true.", "true"),
        ("false", "false"),
        ("False", "false"),
        ("no", "false"),
        ("0", "false"),
        ("I believe this is false based on the evidence.", "false"),
    ],
)
def test_bool_success_paths(raw, expected):
    assert project(BOOL, raw) == (STATUS_OK, expected)


@pytest.mark.parametrize("raw", ["", "   ", "maybe", "definitely not sure", "TBD"])
def test_bool_violation_paths(raw):
    assert project(BOOL, raw) == (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# ENUM — no fuzzy matching, ever
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("degraded", "degraded"),
        ("Degraded", "degraded"),
        ("DEGRADED", "degraded"),
        ("The status page currently reads degraded.", "degraded"),
        ("up", "up"),
    ],
)
def test_enum_success_paths(raw, expected):
    assert project(ENUM, raw) == (STATUS_OK, expected)


def test_enum_typo_never_matches_similar_option():
    assert project(ENUM, "degrded") == (STATUS_SCHEMA_VIOLATION, "")
    assert project(ENUM, "dgraded") == (STATUS_SCHEMA_VIOLATION, "")


@pytest.mark.parametrize("raw", ["", "sideways", "not listed anywhere"])
def test_enum_violation_paths(raw):
    assert project(ENUM, raw) == (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# BAND — clamped to range, never a violation for out-of-range numbers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_band",
    [
        ("0", "0"),
        ("49", "0"),
        ("50", "1"),
        ("999", "19"),
        ("The funding rate is 7 bps.", "0"),  # first number is 7 -> band 0
        ("-500", "0"),  # clamped below lo
        ("5000", "19"),  # clamped above hi, lands in last band
        ("1000", "19"),  # exactly at hi, must not overflow to a nonexistent band
    ],
)
def test_band_success_and_clamping(raw, expected_band):
    assert project(BAND, raw) == (STATUS_OK, expected_band)


@pytest.mark.parametrize("raw", ["", "no numbers here", "N/A"])
def test_band_violation_paths(raw):
    assert project(BAND, raw) == (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# INT — out-of-range IS a violation (no clamping, unlike BAND)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", "0"),
        ("100", "100"),
        ("42", "42"),
        ("There are 12 open issues.", "12"),
    ],
)
def test_int_success_paths(raw, expected):
    assert project(INT, raw) == (STATUS_OK, expected)


@pytest.mark.parametrize("raw", ["-1", "101", "1000", "", "no digits at all"])
def test_int_violation_paths(raw):
    assert project(INT, raw) == (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# DATE_DAY — strict ISO, day granularity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-19", "2026-08-19"),
        ("The PR merged on 2026-08-19 at noon.", "2026-08-19"),
    ],
)
def test_date_success_paths(raw, expected):
    assert project(DATE, raw) == (STATUS_OK, expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "08/19/2026",  # wrong format, never accepted
        "yesterday",
        "2026-13-40",  # not a real date
        "2026-02-30",  # not a real date (Feb has 28/29 days)
    ],
)
def test_date_violation_paths(raw):
    assert project(DATE, raw) == (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# project() must never raise, for any schema x any garbage input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("schema", [BOOL, ENUM, BAND, INT, DATE])
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "\n\t",
        "a" * 10000,
        "'; DROP TABLE facts; --",
        "<script>alert(1)</script>",
        None,
        123,
        3.14,
    ],
)
def test_project_never_raises(schema, raw):
    status, value = project(schema, raw)  # type: ignore[arg-type]
    assert status in (STATUS_OK, STATUS_SCHEMA_VIOLATION, STATUS_UNAVAILABLE)
    assert isinstance(value, str)
