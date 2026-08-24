# Veritas — Roadmap

**Goal:** ship a shared, schema-constrained web-fact oracle on GenLayer that other
contracts depend on by address, and package it so it lands as a high-value
contribution across multiple GenLayer Points builder categories.

**Design reference:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Task-level detail:** [BUILD-PLAN.md](./BUILD-PLAN.md)
**Points packaging:** [SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md)

---

## Sequencing principle

The build order is **deterministic core first, consensus last**. Everything that can
be a pure Python function with a unit test gets written and proven before a single
line touches the GenVM. This is deliberate:

- The schema kernel and the normalizer are roughly 70% of the actual intellectual
  content of Veritas, and both are testable in milliseconds with zero network, zero
  LLM, and zero validators.
- Consensus bugs are the slowest thing in the world to debug. Every bug killed in a
  pure function is a bug never chased through a validator round.
- If the deterministic core is solid, the contract layer becomes thin glue.

Phases 1 and 2 therefore produce a **library that is useful and demonstrable on its
own** — which is also, not coincidentally, a separately submittable "developer tool"
contribution.

---

## Phase 0 — Foundations

**Outcome:** a repo that lints, tests, and deploys, before any real code exists.

| Item | Detail |
|---|---|
| Repo + license | Public GitHub, MIT or Apache-2.0. Public and login-free is a hard requirement for Points evidence. |
| Runner pin | Every contract file starts with a **pinned** `Depends` runner hash. Never `py-genlayer:test` or `:latest` — all GenLayer networks reject aliases. |
| Tooling | `genlayer-cli` installed, `genvm-lint` wired into a make target and CI. |
| Test harness | `pytest` for the pure-Python lib; GenLayer direct-mode tests for contract logic. |
| CI | GitHub Actions: lint + pure-Python tests + direct-mode tests on every push. |
| Testnet wallet | Funded, and the deploy path proven end to end with a hello-world contract. |

**Exit criterion:** a trivial contract deploys to testnet and a green CI badge is on
the README. Nothing else starts until this is true.

**Why first:** the most common way these projects die is discovering on day 8 that
the deploy path does not work.

---

## Phase 1 — The schema kernel

**Outcome:** `lib/schema/` — a pure-Python module with no GenLayer imports.

Responsibilities:

1. **Parse** a schema declaration string into a schema object.
   `BOOL`, `ENUM:a,b,c`, `BAND:min:max:step`, `DATE_DAY`, `INT:min:max`
2. **Canonicalize** it — sort enum options, normalize spacing and case — so two
   callers writing the same schema differently still hash to the same cache key.
3. **Enumerate legal values** for prompt injection.
4. **Project** an arbitrary model output string onto the schema, or fail explicitly:
   - enum: case-insensitive exact match, no fuzzy matching
   - band: parse number, clamp to range, integer-divide into a band index
   - date: strict ISO parse, day granularity
   - bool: a fixed accepted-token table, nothing else
5. **Reject** everything else as `SCHEMA_VIOLATION`. No nearest-neighbour guessing.

**Exit criterion:** table-driven test suite covering every schema type, every
projection success path, and — the important half — every projection *failure* path.
Target: projection is total and never raises an unhandled exception.

**Why this is the highest-leverage phase:** the schema kernel is what makes consensus
possible at all. It is also the piece a reviewer can read in five minutes and
immediately understand the point of the project.

---

## Phase 2 — The normalizer and availability gate

**Outcome:** `lib/normalize/` — also pure Python, also no GenLayer imports.

Two components:

**`availability.py`** — deterministic rules answering "could I actually see this
page?" from `(status_code, raw_body)`. Returns a verdict plus a reason code. Runs
before any LLM call.

**`normalize.py`** — deterministic text surgery: strip volatile DOM, collapse
whitespace, redact relative and sub-day timestamps, quantize free-standing numbers,
window-truncate around question keywords.

**Test method:** a corpus of real saved pages in `tests/fixtures/` — a 429 response,
a bot-check interstitial, a paywalled article, an empty SPA shell, a status page, a
flight tracker, a GitHub PR page. Each fixture asserts a verdict.

**The differentiating test:** capture the *same* URL twice, minutes apart, and assert
`normalize(a) == normalize(b)`. That single test is the entire value proposition of
Veritas, expressed as an assertion.

**Exit criterion:** every fixture classifies correctly, and the stability test passes
on at least three volatile real-world pages.

---

## Phase 3 — The core contract

**Outcome:** `contracts/veritas/veritas.py` — the deployable oracle.

Build order inside the phase:

1. Storage layout and the `Fact` dataclass — class-level annotations, `u256`
   scalars, `str` enums, append-only field ordering.
2. `compute_key` — content-addressed, matching the off-chain helper byte for byte.
3. `get_fact(key, max_age)` / `has_fresh` / `stats` — pure view methods, no
   non-determinism, safe for synchronous cross-contract reads.
4. `request_fact` — idempotent write. Fresh slot means no-op. A hard requirement, not
   an optimization, because `emit(on='accepted')` can deliver more than once across
   appeal rounds.
5. The non-deterministic resolution block — `gl.vm.run_nondet_unsafe` with a custom
   validator that independently re-runs the whole pipeline and compares
   `(status, value)` only.
6. The error taxonomy — `[EXPECTED]` / `[EXTERNAL]` / `[TRANSIENT]` / `[LLM_ERROR]`
   prefixes plus the canonical validator error handler.

**Exit criterion:** `genvm-lint check` clean; direct-mode tests cover idempotency,
TTL boundaries, every status transition, and every error class.

**Explicit non-goal:** validator behaviour is *not* exercised by direct-mode tests.
Do not mistake green direct-mode tests for working consensus.

---

## Phase 4 — The dependency surface

**Outcome:** the thing that makes Veritas *reusable* rather than merely *deployed*.

| Artifact | Purpose |
|---|---|
| `contracts/veritas/interface.py` | A `@gl.contract_interface` typed `VeritasIface` other builders import — type checking and autocomplete against the oracle. |
| `lib/schema/keys.py` | Off-chain `veritas_key(url, question, schema)` helper. Must produce byte-identical keys to the on-chain `compute_key`. |
| `examples/` | Three copy-paste caller patterns: read-only consumer, request-then-settle, refresh-on-stale. |
| Cross-key parity test | Asserts off-chain and on-chain key derivation agree. If these diverge, every caller silently misses the cache. |

**Exit criterion:** a second contract, written from scratch against only the published
interface and examples, successfully reads a fact without reading the Veritas source.

**Why this phase matters most for scoring:** "reusable" is a rubric word. A deployed
contract scores once; a deployed contract *with a documented dependency surface* is
infrastructure.

---

## Phase 5 — Integration, consensus, testnet

**Outcome:** proof it survives real validators, not just direct mode.

- Integration tests against a real GenLayer environment covering: consensus on a
  stable page, consensus on a *volatile* page (the real test), `UNAVAILABLE` on a
  429/paywall, `[LLM_ERROR]` forcing validator rotation, and idempotent duplicate
  `emit` delivery.
- Deploy Veritas to the public testnet. Record the address and explorer link — the
  primary evidence URL for the "deployed contract" submission.
- Deploy the example consumer alongside it and prove a live cross-contract read.
- Run the volatile-page fact 20+ times and record the consensus success rate. **Put
  the number in the README, even if it is not 100%.** A measured number with an
  honest failure analysis is more credible than a claim.

**Exit criterion:** live testnet address, a published consensus-stability
measurement, and a reproducible integration test suite.

---

## Phase 6 — The proof: adapter rewrites

**Outcome:** the argument that makes the whole submission land.

Take two existing web-reading contracts — **Sybilon** and **SignalJudge** — and
rewrite their fetch-and-ask blocks to call Veritas instead.

For each, publish:

| Metric | What it shows |
|---|---|
| Lines removed | The duplication Veritas absorbs |
| The shared bug | The specific hallucination-on-unavailable case both contracts had |
| Before/after diff | Concrete and reviewable, not a claim |
| Consensus stability delta | Measured, same page, before and after |

Then write the bug-parity table: *"here are N of my own contracts and here is the one
bug they all shared."*

**Why this is worth a whole phase:** a seventh dApp is a seventh dApp. "I found a bug
class in the ecosystem, built the shared fix, and retrofitted my own code to prove
it" is a fundamentally different and stronger story — and it is the difference
between a contract submission and an infrastructure submission.

---

## Phase 7 — Submission package

**Outcome:** every artifact needed for multiple Points submissions, each with a
public, login-free evidence URL.

- **README** — the pitch, the API, the testnet address, the measured stability
  number, and the limitations section. Written for someone who has 90 seconds.
- **Tutorial** — "Making your web-reading GenLayer contract consensus-stable."
  Teaches schema-constrained answers as a *technique*, using Veritas as the worked
  example. The highest-value educational artifact.
- **Blog post** — the thesis piece: *"GenLayer doesn't need oracles — half right."*
  Argues the trusted-oracle vs. evidence-normalization distinction.
- **Demo video** — 3 minutes: volatile page fails consensus without Veritas, succeeds
  with it, then the rate-limited page returning `UNAVAILABLE` instead of a lie.
- **Points submissions** — filed per category with the right evidence URL each.

**Exit criterion:** every submission filed with its evidence link. See
[SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md).

---

## Phase timeline

Indicative, assuming focused solo work. Phases 1–2 compress if the fixture corpus is
gathered early; phase 5 reliably takes longer than planned because real consensus is
slow to iterate against.

| Phase | Focus | Est. |
|---|---|---|
| 0 | Foundations, deploy path proven | 0.5 day |
| 1 | Schema kernel | 1 day |
| 2 | Normalizer + availability gate | 1.5 days |
| 3 | Core contract | 2 days |
| 4 | Dependency surface | 1 day |
| 5 | Integration + testnet | 1.5 days |
| 6 | Adapter rewrites | 1 day |
| 7 | Submission package | 1.5 days |
| | **Total** | **~10 days** |

---

## Scope boundaries

**In scope for v1:** single-URL facts, the five schema types, the availability gate,
the shared content-addressed cache, caller-driven refresh, the typed cross-contract
interface.

**Explicitly out of scope for v1** — and saying so in the README is a strength, not a
weakness:

- Multi-source corroboration or cross-referencing between URLs
- Payment, staking, or fee mechanics for cache usage
- Automatic scheduled refresh
- A dispute or appeal layer over stored facts
- Freeform or long-text answers, in any form, ever — a permanent boundary, not a v1
  limitation

**The permanent boundary is the product.** The moment Veritas returns free text it
stops being able to reach consensus and becomes the thing it was built to replace.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Off-chain and on-chain key derivation drift | Silent total cache miss — the worst failure mode, because nothing errors | Parity test in CI, phase 4, non-negotiable |
| Band boundary straddle breaks consensus | Intermittent, hard-to-reproduce failures | Documented guidance on step sizing; measure and publish the rate |
| Normalizer over-strips and removes the answer | `SCHEMA_VIOLATION` on good pages | Fixture corpus asserts expected answers, not just verdicts |
| Testnet deploy path breaks late | Blocks phase 5 entirely | Proven in phase 0 with hello-world, not discovered in phase 5 |
| Storage layout change after deploy | Breaks the deployed shared contract for every caller | Append-only field discipline from day one; layout frozen at end of phase 3 |
| Scope creep into a "fact marketplace" | Nothing ships | Boundaries above are written down; revisit only after submission |

---

## Definition of done for the project

1. Veritas is deployed to GenLayer testnet at a public address.
2. A second contract reads a fact from it cross-contract, live.
3. Consensus stability on a volatile page is **measured and published**.
4. Two pre-existing contracts are retrofitted, with the diff public.
5. Repo is public, CI is green, and the docs explain the technique — not just the API.
6. Contributions are filed across every category the work legitimately covers.
