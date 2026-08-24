"""One-off script used to build tests/fixtures/*.json for phase 2.

Not part of the test suite itself — run manually when the corpus needs
regenerating. Reads a raw capture (path given on the command line) and
writes the fixture JSON format:
{"url", "status_code", "body", "captured_at", "provenance"}

"provenance" is either "live" (an actual HTTP fetch, unmodified) or
"synthetic" (hand-crafted to exercise a specific detector rule
deterministically, documented as such rather than presented as scraped).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def write_fixture(name: str, url: str, status_code: int, body: str, provenance: str):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url,
        "status_code": status_code,
        "body": body,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
    }
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {path} ({len(body)} chars, provenance={provenance})")


if __name__ == "__main__":
    # name url status_code body_file provenance
    name, url, status_code, body_file, provenance = sys.argv[1:6]
    body = Path(body_file).read_text(encoding="utf-8", errors="replace")
    write_fixture(name, url, int(status_code), body, provenance)
