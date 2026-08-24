"""Phase 2 task 2.4 — deterministic text surgery.

test_normalization_is_stable_across_refetches is the headline test: it IS
the value proposition of Veritas, expressed as an assertion
(docs/BUILD-PLAN.md phase 2, docs/ARCHITECTURE.md section 1). It runs
against two independently-fetched captures of the same real, live URLs
(tests/fixtures/status_page_ok.{a,b}.json, github_pr_ok.{a,b}.json), whose
raw bytes genuinely differ (verified — same length, different content,
almost certainly a rotating nonce or session token), yet normalize()
collapses both to byte-identical output.
"""

import pytest

from lib.normalize.normalize import MAX_EVIDENCE_CHARS, normalize
from tests.unit._fixtures import load

VOLATILE_FIXTURES = [
    ("status_page_ok", "What is the current status of GitHub services?"),
    ("github_pr_ok", "What is this pull request about?"),
]


def test_normalization_is_stable_across_refetches():
    for name, question in VOLATILE_FIXTURES:
        a = load(f"{name}.a")
        b = load(f"{name}.b")
        assert a["body"] != b["body"], (
            f"{name}: fixture pair must genuinely differ in raw bytes, "
            "otherwise this test proves nothing"
        )
        na = normalize(a["body"], question)
        nb = normalize(b["body"], question)
        assert na == nb


# ---------------------------------------------------------------------------
# Individual pipeline stages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_substr",
    [
        ("Posted 5 minutes ago", "[REL_TIME]"),
        ("Updated just now", "[REL_TIME]"),
        ("Last seen 2 hours ago", "[REL_TIME]"),
        ("Filed yesterday", "[REL_TIME]"),
    ],
)
def test_relative_times_redacted(raw, expected_substr):
    assert expected_substr in normalize(raw, "")


@pytest.mark.parametrize(
    "raw",
    [
        "The meeting is at 14:32.",
        "Posted at 2:32 PM today",
        "2026-08-19T14:32:07Z",
    ],
)
def test_subday_times_redacted(raw):
    assert "[TIME]" in normalize(raw, "")


def test_plain_dates_are_not_redacted():
    # Day-granularity dates are meaningful data (e.g. for DATE_DAY schemas)
    # and are explicitly NOT sub-day precision — must survive normalization.
    out = normalize("The PR merged on 2026-08-19.", "")
    assert "2026-08-19" in out
    assert "[TIME]" not in out


def test_large_numbers_quantized():
    out = normalize("This post has 15234 likes.", "")
    assert "15234" not in out
    # quantized to 2 sig figs: 15234 -> 15000
    assert "15000" in out


def test_small_numbers_not_quantized():
    # Small numbers are usually the meaningful data a question asks about
    # (prices, percentages) — must survive untouched.
    out = normalize("The price is 42 dollars.", "")
    assert "42" in out


def test_script_and_style_and_nav_stripped():
    html = (
        "<html><head><style>.x{color:red}</style></head>"
        "<body><nav>Home | About</nav>"
        "<script>trackPageview();</script>"
        "<p>The actual article content is here.</p>"
        "<footer>Copyright 2026</footer></body></html>"
    )
    out = normalize(html, "")
    assert "actual article content" in out
    assert "trackPageview" not in out
    assert "color:red" not in out
    assert "Home" not in out
    assert "Copyright" not in out


def test_whitespace_collapsed():
    out = normalize("<p>too    much\n\n\nwhitespace</p>", "")
    assert "  " not in out


def test_window_truncation_centers_on_question_keyword():
    filler = "x " * 3000  # far exceeds MAX_EVIDENCE_CHARS
    html = f"<p>{filler} the answer is degraded right here {filler}</p>"
    out = normalize(html, "What is the status? degraded")
    assert len(out) <= MAX_EVIDENCE_CHARS
    assert "degraded" in out


def test_window_truncation_falls_back_to_start_when_no_keyword_found():
    filler = "x " * 3000
    out = normalize(f"<p>START {filler}</p>", "nothing matches here at all")
    assert len(out) <= MAX_EVIDENCE_CHARS
    assert out.startswith("START")


def test_short_text_not_truncated():
    out = normalize("<p>Short text.</p>", "irrelevant")
    assert out == "Short text."


# ---------------------------------------------------------------------------
# normalize() must never raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,question",
    [
        ("", ""),
        (None, None),
        ("<div><span>unclosed", "question"),
        ("<<<>>>", ""),
    ],
)
def test_normalize_never_raises(body, question):
    out = normalize(body, question)
    assert isinstance(out, str)


def test_normalize_never_raises_on_very_large_input():
    # Kept separate from the parametrized sweep above: using a 1MB literal
    # as a parametrize value blows Windows' ~32KB environment-variable limit
    # via pytest's PYTEST_CURRENT_TEST id (confirmed by actually running it).
    out = normalize("a" * 1_000_000, "x")
    assert isinstance(out, str)
