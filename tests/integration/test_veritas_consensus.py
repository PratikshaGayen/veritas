"""Phase 5 tasks 5.1-5.4 — real consensus integration tests against
studio.genlayer.com (real leader + validators, real web fetches, real
LLM calls, gasless — no funding required).

Kept deliberately lean: studio.genlayer.com is rate-limited (60 req/min,
1000 req/hr per IP, see genlayer-dev:integration-tests skill) and every
test here costs a real deploy plus one or more real consensus rounds.
"""

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy_veritas():
    factory = get_contract_factory("Veritas")
    return factory.deploy(args=[])


def test_stable_page_reaches_consensus():
    """5.1 — a static, unambiguous page settles cleanly."""
    contract = _deploy_veritas()

    url = "https://en.wikipedia.org/wiki/HTTP"
    question = "Does this page describe the HTTP protocol used on the web?"
    schema = "BOOL"

    tx_receipt = contract.request_fact(args=[url, question, schema]).transact()
    assert tx_execution_succeeded(tx_receipt)

    key = contract.compute_key(args=[url, question, schema]).call()
    fact = contract.get_fact(args=[key, 3600]).call()

    assert fact["status"] == "OK", fact
    assert fact["answer"] == "true", fact


def test_volatile_page_reaches_consensus():
    """5.2 — the real proof: a live status page whose raw bytes almost
    certainly differ between the leader's and each validator's independent
    fetch (session/nonce tokens, timestamps — confirmed genuinely volatile
    in phase 2's fixture capture), yet the pipeline still reaches
    consensus because normalize() collapses the volatility before the
    LLM ever sees it.
    """
    contract = _deploy_veritas()

    url = "https://www.githubstatus.com/"
    question = "According to this page, are all systems currently operational?"
    schema = "ENUM:operational,degraded,outage"

    tx_receipt = contract.request_fact(args=[url, question, schema]).transact()
    assert tx_execution_succeeded(tx_receipt)

    key = contract.compute_key(args=[url, question, schema]).call()
    fact = contract.get_fact(args=[key, 3600]).call()

    # The point being proven is CONSENSUS was reached (tx_execution_succeeded
    # already confirms that — an undetermined tx would fail this assert).
    # The specific status/answer is real-world data, asserted loosely.
    assert fact["status"] in ("OK", "SCHEMA_VIOLATION"), fact


def test_rate_limited_page_becomes_unavailable():
    """5.3 — a real 429 response resolves to UNAVAILABLE, not a guess."""
    contract = _deploy_veritas()

    url = "https://httpbin.org/status/429"
    question = "Is the service reporting healthy status?"
    schema = "BOOL"

    tx_receipt = contract.request_fact(args=[url, question, schema]).transact()
    assert tx_execution_succeeded(tx_receipt)

    key = contract.compute_key(args=[url, question, schema]).call()
    fact = contract.get_fact(args=[key, 3600]).call()

    assert fact["status"] == "UNAVAILABLE", fact
    assert fact["answer"] == "", fact


def test_duplicate_request_fact_is_idempotent():
    """5.4 — calling request_fact again on an already-fresh fact is a
    no-op (proxy for the appeal-round duplicate-delivery guarantee — the
    contract-level idempotency check is identical regardless of what
    triggers the repeat call).
    """
    contract = _deploy_veritas()

    url = "https://en.wikipedia.org/wiki/HTTP"
    question = "Does this page describe the HTTP protocol used on the web?"
    schema = "BOOL"

    tx1 = contract.request_fact(args=[url, question, schema]).transact()
    assert tx_execution_succeeded(tx1)

    key = contract.compute_key(args=[url, question, schema]).call()
    resolve_count_after_first = contract.get_fact(args=[key, 3600]).call()["resolve_count"]
    assert resolve_count_after_first == 1

    tx2 = contract.request_fact(args=[url, question, schema]).transact()
    assert tx_execution_succeeded(tx2)

    resolve_count_after_second = contract.get_fact(args=[key, 3600]).call()["resolve_count"]
    assert resolve_count_after_second == 1, "request_fact must be a no-op when already fresh"
