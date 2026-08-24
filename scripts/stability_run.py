"""Phase 5 task 5.7 — measure real consensus stability on a volatile page.

Thin wrapper around tests/integration/test_stability.py, which does the
actual work. gltest's get_contract_factory() needs pytest-plugin-injected
config state (contracts_dir, network client, etc.) that only exists inside
a gltest/pytest run — confirmed: calling it from a bare `python` script
failed with `AttributeError: 'NoneType' object has no attribute 'exists'`.
So this wrapper just sets STABILITY_RUNS and shells out to `gltest`.

Usage:
    python scripts/stability_run.py --runs 20
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    env = os.environ.copy()
    env["STABILITY_RUNS"] = str(args.runs)

    result = subprocess.run(
        [
            "gltest",
            "tests/integration/test_stability.py",
            "-v",
            "-s",
            "-m",
            "slow",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
