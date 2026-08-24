"""Phase 3 direct-mode tests for the Veritas contract.

Direct mode runs the leader function only — validator logic is NOT
exercised (confirmed via the genlayer-dev:direct-tests skill and by
inspection: run_nondet_unsafe's validator_fn is never invoked by
direct_deploy's call path). These tests therefore cover: storage/views,
TTL boundaries, idempotency, the deterministic [EXPECTED] error path, the
[LLM_ERROR] path (leader_fn raising), and every status the leader-side
pipeline can produce (OK / UNAVAILABLE / SCHEMA_VIOLATION). Whether the
VALIDATOR actually agrees or disagrees on a given leader result is a
phase-5 integration-test concern, not something this file can prove.
"""

import json
from datetime import datetime, timezone

READABLE_BODY = "This page confirms the current status is up. " * 5
UP_ANSWER = json.dumps({"answer": "up", "evidence_span": "status is up"})


def _iso(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# 3.1 — storage and constructor
# ---------------------------------------------------------------------------


def test_deploy_and_initial_stats(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    assert contract.stats() == {
        "total_resolves": 0,
        "total_unavailable": 0,
        "total_facts": 0,
    }


# ---------------------------------------------------------------------------
# 3.2 — views: PENDING for unknown key, TTL boundaries
# ---------------------------------------------------------------------------


def test_get_fact_on_unknown_key_is_pending(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    key = contract.compute_key("https://example.test/x", "Is it up?", "BOOL")
    fact = contract.get_fact(key, 3600)
    assert fact["status"] == "PENDING"
    assert fact["is_fresh"] is False


def test_ttl_boundary_exactly_at_max_age_is_fresh(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fetched_at = contract.get_fact(key, 3600)["fetched_at"]

    direct_vm.warp(_iso(fetched_at + 100))
    assert contract.get_fact(key, 100)["is_fresh"] is True


def test_ttl_boundary_one_second_under_is_fresh(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fetched_at = contract.get_fact(key, 3600)["fetched_at"]

    direct_vm.warp(_iso(fetched_at + 99))
    assert contract.get_fact(key, 100)["is_fresh"] is True


def test_ttl_boundary_one_second_over_is_stale(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fetched_at = contract.get_fact(key, 3600)["fetched_at"]

    direct_vm.warp(_iso(fetched_at + 101))
    assert contract.get_fact(key, 100)["is_fresh"] is False


def test_has_fresh_matches_get_fact_is_fresh(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fetched_at = contract.get_fact(key, 3600)["fetched_at"]

    assert contract.has_fresh(key, 3600) is True

    # max_age=0 at the same instant is still "fresh" (now - fetched_at == 0
    # <= 0) — staleness only appears once time actually moves forward.
    direct_vm.warp(_iso(fetched_at + 1))
    assert contract.has_fresh(key, 0) is False


# ---------------------------------------------------------------------------
# 3.3 — request_fact idempotency
# ---------------------------------------------------------------------------


def test_request_fact_is_idempotent_when_fresh(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")

    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fact = contract.get_fact(key, 3600)
    assert fact["resolve_count"] == 1
    assert contract.stats()["total_resolves"] == 1


def test_refresh_bypasses_freshness_and_reresolves(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    assert contract.get_fact(key, 3600)["resolve_count"] == 1

    contract.refresh(key)
    assert contract.get_fact(key, 3600)["resolve_count"] == 2
    assert contract.stats()["total_resolves"] == 2


def test_refresh_unknown_key_raises_expected(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("[EXPECTED]"):
        contract.refresh("0" * 64)


# ---------------------------------------------------------------------------
# 3.5 — error taxonomy
# ---------------------------------------------------------------------------


def test_unknown_schema_raises_expected_before_any_fetch(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    # No mock_web registered — if the pipeline tried to fetch, it would
    # either hit a real network call or fail loudly, neither of which
    # should happen: schema parsing must fail before the nondet block.
    with direct_vm.expect_revert("[EXPECTED]"):
        contract.request_fact("https://example.test/x", "irrelevant", "NOT_A_SCHEMA")


def test_malformed_llm_json_raises_llm_error(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    # A JSON array, not an object — response_format="json" guarantees valid
    # JSON, not that it's a dict.
    direct_vm.mock_llm(r".*", json.dumps(["not", "a", "dict"]))

    with direct_vm.expect_revert("[LLM_ERROR]"):
        contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")


# ---------------------------------------------------------------------------
# Every leader-side status the pipeline can produce
# ---------------------------------------------------------------------------


def test_rate_limited_status_becomes_unavailable(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 429, "body": ""})

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fact = contract.get_fact(key, 3600)
    assert fact["status"] == "UNAVAILABLE"
    assert fact["answer"] == ""
    assert contract.stats()["total_unavailable"] == 1


def test_bot_wall_body_becomes_unavailable(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(
        r".*",
        {"status": 200, "body": "Just a moment... checking your browser before continuing."},
    )

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    assert contract.get_fact(key, 3600)["status"] == "UNAVAILABLE"


def test_llm_out_of_schema_answer_becomes_schema_violation(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    # "sideways" is not a legal ENUM option.
    direct_vm.mock_llm(r".*", json.dumps({"answer": "sideways", "evidence_span": ""}))

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    fact = contract.get_fact(key, 3600)
    assert fact["status"] == "SCHEMA_VIOLATION"
    assert fact["answer"] == ""


def test_llm_unavailable_token_is_respected(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", json.dumps({"answer": "UNAVAILABLE", "evidence_span": ""}))

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    key = contract.compute_key("https://example.test/status", "What is the status?", "ENUM:up,down")
    assert contract.get_fact(key, 3600)["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Content-addressing sanity: different questions/schemas get independent facts
# ---------------------------------------------------------------------------


def test_different_questions_get_independent_facts(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice
    direct_vm.mock_web(r".*", {"status": 200, "body": READABLE_BODY})
    direct_vm.mock_llm(r".*", UP_ANSWER)

    contract.request_fact("https://example.test/status", "What is the status?", "ENUM:up,down")
    contract.request_fact("https://example.test/status", "Is everything fine?", "ENUM:up,down")

    assert contract.stats()["total_facts"] == 2
    assert contract.stats()["total_resolves"] == 2
