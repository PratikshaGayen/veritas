"""Phase 5 task 5.7 — the actual measurement, run under gltest (it needs
gltest's pytest-plugin-injected config context; get_contract_factory()
cannot run outside that context — confirmed: a standalone `python
scripts/stability_run.py` invocation failed with
`AttributeError: 'NoneType' object has no attribute 'exists'` because the
contracts-dir config is only populated by the plugin's pytest_configure
hook).

Run directly with:
    gltest tests/integration/test_stability.py -v -s

Or via the wrapper (same command, plus report parsing):
    python scripts/stability_run.py --runs 20

Controlled by the STABILITY_RUNS env var so scripts/stability_run.py can
drive it without editing this file.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

URL = "https://www.githubstatus.com/"
QUESTION = "According to this page, are all systems currently operational?"
SCHEMA = "ENUM:operational,degraded,outage"


@pytest.mark.slow
def test_volatile_page_stability_measurement():
    n_runs = int(os.environ.get("STABILITY_RUNS", "20"))

    factory = get_contract_factory("Veritas")
    contract = factory.deploy(args=[])
    key = contract.compute_key(args=[URL, QUESTION, SCHEMA]).call()

    results = []
    for i in range(n_runs):
        try:
            tx_receipt = contract.request_fact(args=[URL, QUESTION, SCHEMA]).transact()
            succeeded = tx_execution_succeeded(tx_receipt)
        except Exception as e:  # pragma: no cover - real network run
            succeeded = False
            print(f"run {i + 1} raised: {e}")

        fact = contract.get_fact(args=[key, 0]).call()
        row = {
            "run": i + 1,
            "consensus_succeeded": succeeded,
            "status": fact.get("status"),
            "answer": fact.get("answer"),
        }
        results.append(row)
        print(f"run {i + 1}/{n_runs}: succeeded={succeeded} status={fact.get('status')} answer={fact.get('answer')!r}")

        if i < n_runs - 1:
            try:
                contract.refresh(args=[key]).transact()
            except Exception as e:  # pragma: no cover - real network run
                print(f"  refresh failed: {e}")

    n_success = sum(1 for r in results if r["consensus_succeeded"])
    rate = n_success / len(results) if results else 0.0

    out_path = REPO_ROOT / "docs" / "STABILITY-REPORT.md"
    _write_report(out_path, n_success, len(results), rate, results)
    print(f"\n{n_success}/{len(results)} consensus rounds succeeded ({rate:.1%})")

    # A crash mid-run is a real failure; a low-but-measured rate is not —
    # the whole point is to publish the honest number, not gate on it.
    assert results, "no runs completed at all"


def _write_report(out_path: Path, n_success: int, n_total: int, rate: float, results: list) -> None:
    failures = [r for r in results if not r["consensus_succeeded"]]
    lines = [
        "# Consensus Stability Report",
        "",
        "Measured, not estimated — see tests/integration/test_stability.py. Published",
        "as-is, including failures, per docs/SUBMISSION-STRATEGY.md's honesty requirement.",
        "",
        f"**Measured:** {datetime.now(timezone.utc).isoformat()}",
        f"**Target:** `{URL}`",
        f"**Question:** {QUESTION!r}",
        f"**Schema:** `{SCHEMA}`",
        "**Network:** studio.genlayer.com (real leader + validators, real web/LLM calls)",
        "",
        f"## Result: {n_success}/{n_total} ({rate:.1%})",
        "",
    ]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for f in failures:
            lines.append(f"- run {f['run']}: status={f['status']!r} answer={f['answer']!r}")
        lines.append("")
    lines.append("## Raw data")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(results, indent=2))
    lines.append("```")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
