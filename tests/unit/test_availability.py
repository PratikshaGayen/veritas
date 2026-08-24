"""Phase 2 task 2.3 — the availability gate, against the fixture corpus.

Every expected verdict below was computed by actually running check()
against the fixture (see the session log / scripts/build_fixtures.py),
not asserted blind.
"""

import pytest

from lib.normalize.availability import (
    REASON_BOT_WALL,
    REASON_EMPTY,
    REASON_NO_OVERLAP,
    REASON_PAYWALL,
    REASON_RATE_LIMIT,
    REASON_TRANSIENT,
    VERDICT_READABLE,
    VERDICT_UNAVAILABLE,
    check,
)
from tests.unit._fixtures import load


@pytest.mark.parametrize(
    "fixture_name,question,expected_verdict,expected_reason",
    [
        ("rate_limited_429", "Is the API up?", VERDICT_UNAVAILABLE, REASON_RATE_LIMIT),
        ("server_error_503", "Is the API up?", VERDICT_UNAVAILABLE, REASON_TRANSIENT),
        ("bot_interstitial", "Is this page accessible?", VERDICT_UNAVAILABLE, REASON_BOT_WALL),
        (
            "paywalled_article",
            "What happened to markets on Monday?",
            VERDICT_UNAVAILABLE,
            REASON_PAYWALL,
        ),
        (
            "empty_spa_shell",
            "What is shown on the dashboard?",
            VERDICT_UNAVAILABLE,
            REASON_EMPTY,
        ),
    ],
)
def test_synthetic_and_status_fixtures_classify_correctly(
    fixture_name, question, expected_verdict, expected_reason
):
    f = load(fixture_name)
    verdict, reason = check(f["status_code"], f["body"], question)
    assert verdict == expected_verdict
    assert reason == expected_reason


def test_status_page_is_readable():
    f = load("status_page_ok.a")
    verdict, reason = check(
        f["status_code"], f["body"], "What is the current status of GitHub services?"
    )
    assert verdict == VERDICT_READABLE
    assert reason == ""


def test_github_pr_is_readable():
    f = load("github_pr_ok.a")
    verdict, reason = check(f["status_code"], f["body"], "What is this pull request about?")
    assert verdict == VERDICT_READABLE
    assert reason == ""


def test_irrelevant_page_is_no_overlap():
    # A real Wikipedia article on photosynthesis, asked an unrelated question.
    # Loads fine (200, plenty of text) but shares no content words with the
    # question — this is the "loaded fine but the LLM would still have to
    # invent an answer" case from docs/ARCHITECTURE.md section 4.
    f = load("irrelevant_page")
    verdict, reason = check(f["status_code"], f["body"], "Is the customer refund approved?")
    assert verdict == VERDICT_UNAVAILABLE
    assert reason == REASON_NO_OVERLAP


# ---------------------------------------------------------------------------
# Rule order: status code first, then bot-wall, then paywall+length,
# then empty, then overlap. A fixture engineered to trip two rules must
# report the earlier one.
# ---------------------------------------------------------------------------


def test_rule_order_status_code_beats_everything():
    # Body contains a bot-wall marker, but a 429 status must win.
    verdict, reason = check(429, "Just a moment while we check your browser.", "irrelevant")
    assert (verdict, reason) == (VERDICT_UNAVAILABLE, REASON_RATE_LIMIT)


def test_rule_order_bot_wall_beats_paywall():
    body = (
        "Just a moment... checking your browser. "
        "Subscribe to continue reading this exclusive content. " * 3
    )
    verdict, reason = check(200, body, "irrelevant")
    assert (verdict, reason) == (VERDICT_UNAVAILABLE, REASON_BOT_WALL)


def test_rule_order_paywall_beats_empty():
    # Short body (under the paywall floor) that also happens to be under the
    # empty floor — paywall marker present, must report PAYWALL not EMPTY,
    # since the paywall check runs first.
    body = "Subscribe to continue."
    assert len(body) < 40  # sanity: this would also trip the EMPTY floor
    verdict, reason = check(200, body, "irrelevant")
    assert (verdict, reason) == (VERDICT_UNAVAILABLE, REASON_PAYWALL)


def test_rule_order_empty_beats_no_overlap():
    # Nothing to overlap against because there's nothing there at all.
    verdict, reason = check(200, "<div></div>", "What is the weather today?")
    assert (verdict, reason) == (VERDICT_UNAVAILABLE, REASON_EMPTY)


# ---------------------------------------------------------------------------
# check() must never raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_code,body,question",
    [
        (200, "", ""),
        (200, None, "question"),
        (200, "text", None),
        (0, "", ""),
    ],
)
def test_check_never_raises(status_code, body, question):
    verdict, reason = check(status_code, body, question)
    assert verdict in (VERDICT_READABLE, VERDICT_UNAVAILABLE)
    assert isinstance(reason, str)


def test_check_never_raises_on_very_large_input():
    # Kept separate: a 100KB literal as a parametrize value blows Windows'
    # ~32KB environment-variable limit via pytest's PYTEST_CURRENT_TEST id
    # (confirmed by actually running it — see test_normalize.py's identical
    # fix for the same underlying issue).
    verdict, reason = check(599, "a" * 100000, "x" * 1000)
    assert verdict in (VERDICT_READABLE, VERDICT_UNAVAILABLE)
    assert isinstance(reason, str)
