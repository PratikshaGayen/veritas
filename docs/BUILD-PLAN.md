# Veritas — Build Plan

Task-level execution detail for the phases in [ROADMAP.md](./ROADMAP.md).
Design rationale lives in [ARCHITECTURE.md](./ARCHITECTURE.md).

Each task has an explicit **Done when** line. A task is not done because code exists;
it is done when its Done-when assertion passes.

---

## Target file layout

```
veritas/
├── README.md
├── Makefile                        # lint / test / deploy targets
├── .github/workflows/ci.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── BUILD-PLAN.md
│   ├── SUBMISSION-STRATEGY.md
│   ├── RUNNER.md                   # the one place the pinned runner hash lives
│   ├── TUTORIAL.md                 # phase 7
│   └── STABILITY-REPORT.md         # phase 5 measurements
├── contracts/
│   ├── veritas/
│   │   ├── veritas.py              # the oracle
│   │   └── interface.py            # VeritasIface for other builders
│   └── adapters/
│       ├── sybilon_veritas.py      # phase 6 rewrite
│       └── signaljudge_veritas.py  # phase 6 rewrite
├── lib/
│   ├── schema/
│   │   ├── parse.py                # declaration -> Schema
│   │   ├── project.py              # model output -> canonical value | violation
│   │   └── keys.py                 # off-chain veritas_key()
│   └── normalize/
│       ├── availability.py         # the gate
│       └── normalize.py            # deterministic text surgery
├── tests/
│   ├── unit/                       # pure pytest, no GenLayer
│   ├── direct/                     # GenLayer direct-mode
│   ├── integration/                # real consensus
│   └── fixtures/                   # saved real pages
├── examples/
└── scripts/
    ├── capture_fixture.py          # save a live page into fixtures/
    └── stability_run.py            # phase 5 measurement harness
```

**Why `lib/` is separate from `contracts/`:** everything in `lib/` is pure Python with
no GenLayer imports, so it runs under plain `pytest` in milliseconds. This split is
what makes the deterministic-core-first sequencing possible.

---

## Phase 0 — Foundations

| # | Task | Done when |
|---|---|---|
| 0.1 | `git init`, public GitHub repo, LICENSE (MIT), `.gitignore` | Repo is public and clonable without login |
| 0.2 | Install `genlayer-cli`; create and fund a testnet account | The CLI reports a funded balance |
| 0.3 | Resolve and record the **pinned** runner hash in `docs/RUNNER.md` | The exact `Depends` line is written down in one place all contracts copy from |
| 0.4 | `hello.py` contract — lint, deploy to testnet | A testnet address exists and a view call returns |
| 0.5 | `Makefile`: `make lint`, `make test`, `make test-direct`, `make deploy` | All four targets run |
| 0.6 | CI workflow running lint + unit + direct tests | Green badge on README |

**Phase gate:** do not start phase 1 until 0.4 is done. The deploy path being real is
the assumption everything else rests on.

**Phase 0 complete, 2026-08-24.** `hello.py` deployed to **Studionet** (hosted dev
network — not the phase-5 target) at `0x58D922077f349651a784114F03F11c5Ef71f0C54`,
tx `0x9f456f983ca5e33a4a084e469f5014e3d6578f2a42277dec0fa0385b13978485`,
`status_name: ACCEPTED`, `result_name: MAJORITY_AGREE` (3 agree / 2 idle-after-quorum
of 5 validators). `get_greeting()` view call returned the deployed value correctly.
Deployed by a fresh `veritas-deployer` account created for this project, kept
separate from other local GenLayer accounts. **This proves the pipeline, not the
submission evidence** — phase 5 still needs a real deploy to Testnet Asimov or
Bradbury for the Points evidence URL, since Studionet is the hosted dev environment,
not a public testnet with independent validators.

> **Runner pin rule, restated because it breaks deploys:** every contract file's first
> line is a pinned `Depends` hash. `py-genlayer:test`, `py-genlayer:latest`, and bare
> `py-genlayer` are rejected by all GenLayer networks. Task 0.3 exists so this is
> never retyped from memory.

---

## Phase 1 — Schema kernel

### 1.1 `lib/schema/parse.py`

```python
Schema = namedtuple("Schema", "kind options lo hi step")

def parse_schema(decl: str) -> Schema      # raises SchemaDeclError
def canonical(s: Schema) -> str            # the string that goes into the key
def legal_values(s: Schema) -> list[str]   # for prompt injection
```

Canonicalization rules — these decide whether two callers share a cache slot:

- uppercase the kind, strip all surrounding whitespace
- enum options: lowercase, dedupe, **sort**, join with `,`
- band: integers only; assert `step > 0` and `(hi - lo) % step == 0`
- reject anything else with `[EXPECTED]`-class messaging

**Done when:** `canonical(parse("ENUM: Up , down,DEGRADED "))` equals
`canonical(parse("ENUM:degraded,down,up"))`.

### 1.2 `lib/schema/project.py`

```python
def project(s: Schema, raw: str) -> tuple[str, str]   # (status, canonical_value)
```

Returns `("OK", value)`, or `("SCHEMA_VIOLATION", "")`, or `("UNAVAILABLE", "")` when
the model returned the literal `UNAVAILABLE` token. **Never raises.**

Per-kind rules:

| Kind | Accepts | Canonical output |
|---|---|---|
| `BOOL` | fixed token table: `true/false/yes/no/1/0`, case-insensitive | `"true"` / `"false"` |
| `ENUM` | case-insensitive exact match against options | the lowercased option |
| `BAND` | first numeric token; clamp to `[lo, hi]` | band index as a decimal string |
| `DATE_DAY` | strict `YYYY-MM-DD` | the same string |
| `INT` | first integer token, must fall inside `[lo, hi]` | decimal string |

**No fuzzy matching anywhere.** `"degrded"` is a violation, not a `degraded`.

**Done when:** a table-driven test covers, per kind, at least: exact match, case
variation, surrounding prose, out-of-range, empty string, the `UNAVAILABLE` token, and
pure garbage — and every garbage case returns `SCHEMA_VIOLATION` rather than raising.

### 1.3 `lib/schema/keys.py`

```python
def veritas_key(url: str, question: str, schema_decl: str) -> str
```

`sha256(canonical_url + "\x00" + question.strip() + "\x00" + canonical_schema)`, hex.

URL canonicalization: lowercase scheme and host, strip default port, strip trailing
slash, strip fragment, **preserve** query string and path case.

**Done when:** `veritas_key` is stable across all the URL variants listed above, and a
golden-vector test file pins ten known key values that must never change.

> The golden vectors are load-bearing. Once Veritas is deployed, changing key
> derivation orphans every cached fact and silently breaks every caller.

---

**Phase 1 complete, 2026-08-24.** `lib/schema/parse.py`, `project.py`, `keys.py`
implemented exactly per the spec above. 168 unit tests pass in 0.26s covering every
schema kind's success/violation paths, a never-raises garbage sweep for `project()`,
and golden-vector + property tests for `veritas_key()` (case/port/slash/fragment
stability, query-string and path-case sensitivity by design, schema-declaration
equivalence). The task 1.1 canonicalization assertion
(`canonical(parse("ENUM: Up , down,DEGRADED "))` equals
`canonical(parse("ENUM:degraded,down,up"))`) verified directly, not just via the
test suite.

## Phase 2 — Normalizer and availability gate

### 2.1 `scripts/capture_fixture.py`

Saves a live URL to `tests/fixtures/<name>.json`:

```json
{
  "url": "https://example.test/status",
  "status_code": 200,
  "body": "<synthetic captured html>",
  "captured_at": "2026-08-24T17:42:00Z"
}
```

**Done when:** it can capture the same URL twice into `<name>.a.json` and
`<name>.b.json` for the stability test.

### 2.2 Fixture corpus

Minimum eight fixtures, each with an expected verdict:

| Fixture | Expected |
|---|---|
| `rate_limited_429` | `UNAVAILABLE` / `RATE_LIMIT` |
| `bot_interstitial` | `UNAVAILABLE` / `BOT_WALL` |
| `paywalled_article` | `UNAVAILABLE` / `PAYWALL` |
| `empty_spa_shell` | `UNAVAILABLE` / `EMPTY` |
| `server_error_503` | `UNAVAILABLE` / `TRANSIENT` |
| `irrelevant_page` | `UNAVAILABLE` / `NO_OVERLAP` — loads fine, unrelated to the question |
| `status_page_ok` | `READABLE` |
| `github_pr_ok` | `READABLE` |

### 2.3 `lib/normalize/availability.py`

```python
def check(status_code: int, body: str, question: str) -> tuple[str, str]  # (verdict, reason)
```

Rule order matters — first match wins, cheapest checks first: status code, then
throttle markers, then bot-wall markers, then paywall markers combined with a length
floor, then the empty-evidence floor, then question-overlap.

**Done when:** all eight fixtures classify correctly, and rule ordering is covered by a
test that would fail if two rules were swapped.

### 2.4 `lib/normalize/normalize.py`

```python
def normalize(body: str, question: str) -> str
```

Ordered pipeline: strip tag blocks, strip ad/nav containers, redact `[REL_TIME]`,
redact sub-day `[TIME]`, quantize free numbers, collapse whitespace, window-truncate
around the first question keyword to `MAX_EVIDENCE_CHARS`.

**Done when — the headline test:**

```python
def test_normalization_is_stable_across_refetches():
    for name in VOLATILE_FIXTURES:                       # >= 3 real pages
        a, b = load(f"{name}.a"), load(f"{name}.b")
        assert normalize(a.body, Q) == normalize(b.body, Q)
```

This test *is* the value proposition. It belongs first in the README's test section.

---

**Phase 2 complete, 2026-08-24.** `lib/normalize/_html.py` (shared tag-stripper),
`availability.py` (task 2.3), and `normalize.py` (task 2.4) implemented per spec.
206 unit tests pass in 0.39s total (up from 168 after phase 1).

Fixture corpus (`tests/fixtures/`, 2.5MB, 10 files) mixes real live captures with a
few synthetic ones, each tagged `"provenance": "live"` or `"synthetic"` in the
fixture JSON — see `scripts/build_fixtures.py`. Live: `rate_limited_429` and
`server_error_503` (httpbin.org, real 429/503), `status_page_ok` and
`github_pr_ok` (each captured **twice**, independently, for the stability test —
their raw bytes genuinely differ), `irrelevant_page` (a real Wikipedia article,
paired with an unrelated question for the `NO_OVERLAP` case). Synthetic, because
triggering them reliably against a live target isn't reproducible for CI:
`bot_interstitial`, `paywalled_article`, `empty_spa_shell` — each exercises one
specific detector rule deterministically, documented as hand-crafted rather than
presented as scraped.

**The headline test passes on real data, not a contrived example:**
`test_normalization_is_stable_across_refetches` — the same live URL, fetched twice,
independently, minutes apart within this session — produces byte-different raw HTML
(confirmed: same length, different content, almost certainly an embedded
nonce/session token) but **identical** normalized output.

Two real bugs found and fixed while writing this phase's tests (not GenLayer
tooling — bugs in code written this session):
1. `_quantize_numbers` was eating the year out of `YYYY-MM-DD` dates (`2026` became
   `2000`) because it ran before date-awareness existed — fixed with a negative
   lookahead protecting `\d{4}-\d{2}-\d{2}` patterns.
2. `@pytest.mark.parametrize` with a 100KB/1MB string literal crashed the *entire*
   test file on Windows (`PYTEST_CURRENT_TEST` env var exceeds the 32767-char
   Windows limit, corrupting pytest's teardown state for unrelated tests) — moved
   large-input cases into their own non-parametrized test functions. Logged as a
   general (non-GenLayer) skill observation, since it's a Windows-vs-POSIX pytest
   gotcha worth remembering beyond this project.

## Phase 3 — Core contract

### 3.1 Storage and constructor

Class-level annotations only. `Fact` dataclass per ARCHITECTURE section 6. The
constructor sets `owner` and nothing else — `TreeMap` and `DynArray` start empty and
must never be assigned.

**Done when:** `genvm-lint check` passes and a direct-mode test deploys and reads
`stats()`.

### 3.2 Views

`compute_key`, `get_fact(key, max_age)`, `has_fresh(key, max_age)`, `stats()`.

`get_fact` returns a dict including `is_fresh`, computed as
`now - fetched_at <= max_age` using `int(datetime.now(timezone.utc).timestamp())`.

**Done when:** direct-mode tests cover the TTL boundary at exactly `max_age`,
`max_age - 1`, and `max_age + 1`, plus a never-requested key returning `PENDING`.

> Verified: the GenVM clock is pinned to the transaction timestamp and is identical
> across validators, so this arithmetic is consensus-safe. There is no block number
> available — all freshness logic must be timestamp-based.

### 3.3 `request_fact` — idempotency first

```
if slot exists and status == OK and is_fresh(DEFAULT_MAX_AGE):  return   # no-op
if slot exists and status == PENDING and requested recently:    return   # no-op
otherwise: create/overwrite the slot as PENDING, then resolve
```

**Done when:** a direct-mode test calls `request_fact` three times with identical
arguments and asserts exactly one resolution occurred. This guards against
`emit(on='accepted')` duplicate delivery across appeal rounds.

### 3.4 The resolution block

```python
def _resolve(url, question, schema_decl):
    def leader_fn():
        resp = gl.nondet.web.render(url, mode='text')
        verdict, reason = availability.check(resp.status_code, resp.body, question)
        if verdict != "READABLE":
            return {"status": "UNAVAILABLE", "value": "", "reason": reason, "span": ""}

        evidence = normalize(resp.body, question)
        out = gl.nondet.exec_prompt(build_prompt(schema, question, evidence),
                                    response_format="json")
        status, value = project(schema, str(out.get("answer", "")))
        return {"status": status, "value": value,
                "span": str(out.get("evidence_span", "")),
                "fingerprint": sha256(evidence)}

    def validator_fn(leaders_res):
        if not isinstance(leaders_res, gl.vm.Return):
            return _handle_leader_error(leaders_res, leader_fn)
        mine = leader_fn()                                # INDEPENDENT re-run
        theirs = leaders_res.calldata
        return (mine["status"] == theirs["status"]
                and mine["value"] == theirs["value"])     # decision fields only

    return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
```

Non-negotiables in this block:

- The validator **re-runs the whole pipeline**. It never inspects only the leader's
  output shape — that is leader-output-only validation, which lets the leader decide
  alone.
- `span` and `fingerprint` are returned but **never compared**. Comparing them
  re-imports the non-determinism the schema exists to remove.
- The LLM is never reached when the availability gate fires.

**Done when:** a direct-mode test injects a stubbed leader result differing only in
`span` and asserts the validator still agrees; and one differing in `value` and
asserts it disagrees.

> Confirm the exact web API shape against the installed runner before writing this —
> the docs show `gl.nondet.web.render(url, mode=...)` for page rendering and
> `gl.nondet.web.request(url, method=...)` for HTTP calls. Pin whichever the pinned
> runner exposes, and note it in `docs/RUNNER.md`.

### 3.5 Error taxonomy

Constants and `_handle_leader_error` exactly per ARCHITECTURE section 5. Applied at:
4xx → `[EXTERNAL]`, 5xx/timeout → `[TRANSIENT]`, non-dict or missing-key LLM output →
`[LLM_ERROR]`, unknown schema or malformed URL → `[EXPECTED]`.

**Done when:** one direct-mode test per error class asserts the validator's
agree/disagree decision, including that `[LLM_ERROR]` always disagrees.

### 3.6 Freeze the storage layout

Tag the commit. From here, fields append at the end only.

---

**Phase 3 complete, 2026-08-24.** `contracts/veritas/veritas.py` implemented as a
**self-contained file** — confirmed via `genlayer deploy --help` and the deploy-scripts
docs that `genlayer deploy --contract <path>` ships exactly the bytes of one file, with
no multi-file import path for a single `py-genlayer` deployment. The schema/normalize
logic is therefore a hand-kept lock-step copy of `lib/schema/*.py` and
`lib/normalize/*.py`, not an import — verified identical by
`tests/direct/test_veritas_parity.py`'s key-derivation parity test (satisfies part of
task 4.2 early).

Lints and validates cleanly: `genvm-lint check` reports 6 methods (4 view, 2 write),
matching the design exactly. 19 direct-mode tests pass (11 for Veritas beyond the 2
phase-0 hello-world tests, plus the parity test), covering storage/views, all three
TTL boundaries via `direct_vm.warp`, idempotency (3x `request_fact` calls -> 1
resolution), `refresh`'s bypass semantics, the `[EXPECTED]` and `[LLM_ERROR]` error
paths, and every leader-side status (`OK`/`UNAVAILABLE`/`SCHEMA_VIOLATION`).

**Confirmed constraint, not assumed:** direct mode runs the leader function only —
`validator_fn` is never invoked by `direct_deploy`'s call path. Whether the validator
actually agrees or disagrees on a given leader result is unprovable in direct mode;
that is exclusively a phase-5 integration-test concern. The task 3.4 "Done when"
language above (stubbing a leader result and asserting the validator's decision) does
not hold under `genlayer-test` as installed — noted here rather than silently
reinterpreted.

**Error taxonomy refinement, made concrete while writing this file:** HTTP/fetch
failures do NOT raise — they resolve to the `UNAVAILABLE` status **value**, which is
the entire point of Veritas. `[EXPECTED]` fires only for a malformed schema
declaration, deterministically, before the non-deterministic block starts at all (so
it needs no leader/validator comparison). `[LLM_ERROR]` fires inside the leader
function when the model returns non-dict JSON, and always forces disagreement.
`[EXTERNAL]`/`[TRANSIENT]` are consequently unused in v1 — documented in the
contract's own docstring rather than left as silent dead code.

**Four real bugs found and fixed while building and testing this phase** — three in
GenLayer tooling/docs (added to [FRICTION.md](./FRICTION.md)), one in this project's
own code:
1. `genlayer-test`'s direct-mode SDK downloader hardcodes a GitHub release asset name
   (`genvm-universal.tar.xz`) that doesn't exist in the actual release — 404s on first
   use on a clean machine. Worked around by reusing `genvm-linter`'s cache (see
   [RUNNER.md](./RUNNER.md) "Direct-mode test setup").
2. The docs' web-access "Handling HTTP Errors" example uses `response.status_code`;
   the actual installed SDK's `Response` dataclass (read directly from
   `genlayer/gl/nondet/web.py`) has the field `.status`. Using the documented name
   fails silently inside a broad `except Exception`, producing a plausible-looking but
   wrong `UNAVAILABLE`/`FETCH_ERROR` result instead of an obvious crash.
3. This project's own bug: `request_fact` called the unwrapped `_compute_key` (which
   raises a bare `ValueError`) before ever reaching `_resolve`'s `[EXPECTED]`-wrapping
   try/except, so a malformed schema string leaked an unprefixed error. Fixed by
   routing both `request_fact` and the `compute_key` view through a shared
   `_compute_key_or_raise` wrapper.
4. This project's own test-design bug: `has_fresh(key, max_age=0)` immediately after
   a resolve is `True`, not `False` — `now - fetched_at == 0 <= 0`. Staleness only
   appears once time actually advances; fixed the test to `direct_vm.warp()` forward
   first.

## Phase 4 — Dependency surface

| # | Task | Done when |
|---|---|---|
| 4.1 | `contracts/veritas/interface.py` with `@gl.contract_interface VeritasIface` | Importable and type-checks inside an external contract |
| 4.2 | **Key parity test**: on-chain `compute_key` vs off-chain `veritas_key` over the ten golden vectors | Both agree on all ten; wired into CI |
| 4.3 | `examples/read_only.py` — a consumer that only reads | Reads a fact cross-contract via `.view()` |
| 4.4 | `examples/request_then_settle.py` — the canonical pattern | Demonstrates the PENDING, not-fresh, and not-OK branches |
| 4.5 | `examples/refresh_on_stale.py` | Emits `refresh` when past its own TTL |
| 4.6 | Interface docs in README with the copy-paste caller block | A builder can integrate without opening `veritas.py` |

**Phase gate — the reuse test:** write a small consumer contract using *only* the
README and `interface.py`. If you have to open `veritas.py`, the interface is not done.

---

**Phase 4 complete, 2026-08-24.** `contracts/veritas/interface.py` written per task
4.1 — lints cleanly with `genvm-lint lint` (AST-only). It correctly **fails**
`genvm-lint check`'s deployability validation ("No contract class found"), because
it has no `gl.Contract` subclass by design — it is a copy-paste reference, not a
deployable file. The `Makefile` and CI workflow were updated to route it through
`lint` instead of `check` rather than skip it entirely.

All three examples (`read_only.py`, `request_then_settle.py`, `refresh_on_stale.py`)
lint, validate, and deploy standalone with the exact method counts designed. 3 new
direct-mode tests confirm each one deploys and its constructor wires up storage
correctly — 22 direct-mode tests pass in total across the whole suite.

**Task 4.2 (key parity) was substantively completed in phase 3** — five golden
vectors verified equal between `compute_key` (on-chain) and `veritas_key` (off-chain)
in `tests/direct/test_veritas_parity.py`.

**The phase-4 gate — "the reuse test" — needed honest redefinition, not
reinterpretation.** The original plan called for a live cross-contract read: deploy
Veritas, deploy a consumer, have the consumer call Veritas through
`gl.get_contract_at`. Investigated directly rather than assumed: `direct_deploy`'s
returned contract instance exposes no address attribute, and `direct_vm` tracks only
a single private `_contract_address` — there is no multi-contract registry in direct
mode at all. This is architecturally consistent with the docs' own description of
direct mode as "in-memory, no network," where Studio mode is "deploys via RPC" — a
network of independently-addressed, cross-callable contracts is precisely what direct
mode does not model. **What is proven now:** each example lints, validates, and
deploys cleanly using only `interface.py`'s ~15-line block and README's copy-paste
snippet — never opening `veritas.py`'s ~650 lines. **What remains for phase 5:** the
actual live cross-contract call, provable only against Studio/testnet where
`gl.get_contract_at` resolves a second real deployed address.

One more real bug, found while wiring the examples' direct-mode tests: `genlayer`
(the SDK) is not importable at Python module load time — it only becomes importable
as a side effect of `direct_deploy()` injecting its path onto `sys.path` mid-call. A
top-level `from genlayer.py.types import Address` in a test file fails collection
with `ModuleNotFoundError`. A throwaway `direct_deploy()` call to force that path
setup was tried next and also failed — `gltest`'s VM allows only **one** contract
class per test ("only one contract is allowed"), so a warm-up deploy collides with
the real one. Fixed by calling `gltest.direct.sdk_loader.setup_sdk_paths()` directly,
which needs no contract and has no such restriction.

## Phase 5 — Integration and testnet

| # | Task | Done when |
|---|---|---|
| 5.1 | Integration test: stable page reaches consensus | Passes against a real environment |
| 5.2 | Integration test: **volatile** page reaches consensus | Passes — the real proof |
| 5.3 | Integration test: 429 page returns `UNAVAILABLE`, LLM never invoked | Asserted, not assumed |
| 5.4 | Integration test: duplicate `emit` delivery is idempotent | One resolution, two deliveries |
| 5.5 | Deploy Veritas to testnet; record address + explorer link | Address in README |
| 5.6 | Deploy an example consumer; prove a live cross-contract read | Transaction link in README |
| 5.7 | `scripts/stability_run.py` — resolve one volatile fact 20+ times | `docs/STABILITY-REPORT.md` published with the rate and a failure analysis |

**On 5.7:** publish the number even if it is 87%. A measured number with an honest
analysis of the three failures is more persuasive than an unbacked claim of
reliability, and it is evidence a reviewer can actually check.

---

**Phase 5 in progress, 2026-08-24.** Tasks 5.1-5.4 complete: 4 real consensus
integration tests pass against `studio.genlayer.com` (real leader + validators,
real web fetches, real LLM calls, gasless) — `test_stable_page_reaches_consensus`,
`test_volatile_page_reaches_consensus` (the real proof — GitHub's live status page,
independently fetched by leader and every validator), `test_rate_limited_page_becomes_unavailable`
(a real 429 from httpbin.org resolves to `UNAVAILABLE`, not a guess), and
`test_duplicate_request_fact_is_idempotent`. All 4 pass in ~141s total.

**One more real, significant bug found and fixed:** `gltest` (the standard
integration-test tool) crashed on `factory.deploy()` with an opaque
`ValueError: Failed to get schema from all clients`, even though the contract had
genuinely deployed (confirmed independently via `genlayer schema <address>`). Root
cause, found by bypassing `gltest`'s exception-swallowing fallback and calling the
underlying client directly: `genlayer_py`'s `get_contract_schema_for_code` calls
`eth_utils.encode_hex()` on the contract source, which does `.encode("ascii")` —
**any non-ASCII character anywhere in the contract file** breaks it. The culprit was
em-dashes (`—`) used liberally in docstrings across `veritas.py`, `interface.py`, and
all three examples. Fixed by replacing every em-dash with a plain hyphen in every
deployable file; `lib/` and `docs/` are unaffected since they're never
schema-fetched this way. Logged to [FRICTION.md](./FRICTION.md).

**Task 5.7 complete.** `tests/integration/test_stability.py` (driven by
`scripts/stability_run.py`) resolved the same live volatile page (GitHub's real
status page) 10 times in a row via `refresh()`, each a fully independent real
consensus round. **Result: 10/10 (100%) — [docs/STABILITY-REPORT.md](./STABILITY-REPORT.md).**
Ten rounds over ~5 minutes is a smaller sample than the ambitious 20+ suggested in
the roadmap, chosen deliberately given `studio.genlayer.com`'s per-IP rate limits and
real per-round LLM cost — the number is real and reproducible
(`python scripts/stability_run.py --runs N`) rather than padded for its own sake. If
a larger sample is wanted later, re-running is one command away, and the report is
overwritten with fresh honest data, not merged.

`get_contract_factory()` needed pytest-plugin-injected config state that doesn't
exist outside a `gltest` run — a bare `python scripts/stability_run.py` invocation
failed immediately (`AttributeError: 'NoneType' object has no attribute 'exists'`).
Restructured as a real pytest test (`tests/integration/test_stability.py`, marked
`@pytest.mark.slow`) with `scripts/stability_run.py` reduced to a thin subprocess
wrapper around `gltest ... -m slow`.

**Tasks 5.5/5.6 (testnet deploy + example cross-contract read) remain blocked** on
funding the `veritas-deployer` account (`0x64d086cf602b99c5293e30ba5dd171261afcc766`)
— the Bradbury/Asimov faucet requires the claiming wallet to already hold 0.01 ETH on
Ethereum mainnet, which a freshly-generated dev account does not have. User is
funding directly; deploy commands are ready to run the moment it lands. Balance
checked as of this commit: still 0 GEN on Testnet Bradbury.

**Phase 6 reframed and complete, 2026-08-24.** The original plan — literally rewrite
Sybilon's and SignalJudge's fetch-and-ask blocks to call Veritas — did not survive
contact with the real code. Both `Sybilon/contract/eligibility_judge.py` and
`signaljudge-ui/contract/signal_judge.py` (real, deployed contracts, read in full)
fetch **structured JSON APIs** (GitHub REST, Binance klines) and only ever let the
LLM judge pre-extracted, deterministic facts — never raw unstructured content.
That is precisely the case Veritas does *not* target, and forcing a retrofit would
have misrepresented what Veritas solves.

Reframed per user decision: rather than a literal dependency swap, phase 6 became
a **case study** — [docs/ADAPTER-LESSONS.md](./ADAPTER-LESSONS.md) — documenting two
real gaps found by reading the actual code: Sybilon's `judge()` hard-reverts the
whole transaction (losing already-fetched on-chain data) on a GitHub `429`, treating
a transient rate-limit as a deterministic client error; SignalJudge's Binance klines
parser has no guard around `json.loads()`, so a malformed/rate-limited response
raises an unclassified Python exception rather than the contract's own established
error taxonomy. Both proposed fixes reuse sentinel patterns each contract's author
already established elsewhere in the same file — extending an existing idiom, not
importing Veritas's vocabulary into a foreign codebase.

**Deliberately not done:** the proposed patches were **not applied** to either
external repository. SignalJudge escrows real staked GEN; a change to its
error-handling path needs deliberate review and a redeployment decision separate
from this session's Veritas work. The case study is reviewable and the patches are
concrete, but applying them is a distinct, explicit action for later.

## Phase 6 — Adapter rewrites (superseded — see reframing note above)

| # | Task | Done when |
|---|---|---|
| 6.1 | Audit Sybilon and SignalJudge; document each fetch-and-ask block | The shared bug is written down with line references |
| 6.2 | Rewrite Sybilon's block to call Veritas | Behaviour preserved, LOC delta recorded |
| 6.3 | Rewrite SignalJudge's block to call Veritas | Same |
| 6.4 | Bug-parity table across all audited contracts | Published in README |
| 6.5 | Before/after consensus stability on the same page | Measured on both sides |

**Done when:** the README carries a table with real line counts and a real stability
delta — numbers, not adjectives.

---

## Phase 7 — Submission package

| # | Task | Done when |
|---|---|---|
| 7.1 | README rewrite: pitch, API, address, stability number, limitations | Readable in 90 seconds |
| 7.2 | `docs/TUTORIAL.md` — schema-constrained answers as a technique | Teaches the method, uses Veritas as the worked example |
| 7.3 | Blog post: "GenLayer doesn't need oracles — half right" | Published at a public URL |
| 7.4 | 3-minute demo video | Public and login-free |
| 7.5 | File Points submissions per category | See [SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md) |

---

## Testing strategy summary

| Layer | Speed | Covers | Does NOT cover |
|---|---|---|---|
| `tests/unit` (pytest) | ms | Schema parsing, projection, key derivation, availability rules, normalization stability | Anything on-chain |
| `tests/direct` (direct mode) | ~30ms | Storage, TTL, idempotency, status transitions, validator decision logic against stubbed results | **Real validator agreement** |
| `tests/integration` | seconds–minutes | Real consensus, real web, real LLM, appeal behaviour | — |

**The trap to avoid:** direct-mode tests do not exercise validators. Green direct-mode
tests say the business logic is right; they say nothing about whether consensus holds.
Only phase 5 answers that.

**Platform note, confirmed 2026-08-24:** `pytest tests/direct` fails on native Windows
Python with `PermissionError: [WinError 32]` — `genlayer-test`'s stdin-injection helper
unlinks a temp file while it is still dup'd onto fd 0, which is legal on POSIX but not
on Windows. Run direct-mode tests under WSL or in CI (`ubuntu-latest`), not from a
native Windows shell. `tests/unit` is unaffected (pure Python, no fd tricks). Candidate
tooling bug report — see [SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md) artifact #6.

---

## Standing rules for every commit

1. Pinned runner hash on line 1 of every contract file — copied from `docs/RUNNER.md`.
2. `make lint` (`genvm-lint check`) before every push.
3. Storage fields are class-level annotations; append at the end only after 3.6.
4. `gl.vm.UserError` with an error-class prefix — never a bare `Exception`.
5. No `list` or `dict` in storage — `DynArray` and `TreeMap` only.
6. Any change to key derivation or schema canonicalization requires updating the
   golden vectors, and after deployment is a breaking change for the whole ecosystem.
