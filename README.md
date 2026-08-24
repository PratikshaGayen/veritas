# Veritas

**A shared, schema-constrained web-fact oracle for GenLayer.**
One contract, deployed once, that every other Intelligent Contract calls to turn a
webpage into a consensus-stable fact.

> **Status: planning.** The design and build plan are complete; implementation starts
> at phase 0. Nothing is deployed yet. Placeholders marked `[TBD]` get filled from real
> measurements, never estimated.

---

## The misread this corrects

Everyone in the ecosystem says *"GenLayer doesn't need oracles."* Half right.

GenLayer removes the **trusted** oracle — you no longer need anyone's word for it. It
does not remove the **evidence normalization** problem. Three validators fetch the same
URL and get three different pages. Ads rotated. A timestamp ticked. Validator #3 got a
`429`. The page updated mid-consensus.

So every builder writes their own fragile fetch-and-ask block, and ships the same bug.
The worst version of that bug:

> A rate-limited or paywalled page gets fed to the LLM anyway, and the LLM invents a
> confident answer. Nothing says *"I could not see the page."* The contract settles on
> a hallucination.

Nobody has built the shared layer. That is what this is.

---

## The core trick: answers must have a shape

Free-form answers never reach consensus. So Veritas **refuses to return free text**.
Every request declares a schema up front, and that is the whole reason it works:

```python
BOOL                             # "Is flight AI302 delayed?"        -> True
ENUM:up,down,degraded            # "What's the status page state?"   -> "degraded"
BAND:0:1000:50                   # "What's the BTC funding rate?"    -> band 7
DATE_DAY                         # "When did this PR merge?"         -> 2026-08-19
```

Plus one status that matters as much as the rest:

```
UNAVAILABLE                      # page 429'd / paywalled / bot-walled / empty
```

Today, a rate-limited page gets fed to the LLM anyway and it invents an answer.
**Veritas detects the failure and returns `UNAVAILABLE` instead of a confident lie** —
so downstream contracts can wait rather than pay out wrong.

### The tolerance lives in the schema, not the validator

A hand-rolled contract puts the fuzz in the validator ("agree if within 10%"). Veritas
puts it in the **declared schema**, before the question is ever asked. `BAND:0:1000:50`
is the caller stating on the record what precision their business logic actually needs.
The validator then compares **exactly**, on the band index.

The tolerance becomes auditable on-chain, and the validator stays un-gameable.

---

## The shape

```python
# The key is content-addressed, so you compute it yourself - no return value needed.
KEY = veritas_key(
    url="https://flightaware.com/live/flight/AI302",
    question="Is this flight delayed more than 3 hours?",
    schema="BOOL",
)

v = gl.get_contract_at(VERITAS_ADDR)
fact = v.view().get_fact(KEY, u256(3600))     # any contract, later, for free

if fact["status"] == "PENDING" or not fact["is_fresh"]:
    v.emit(on="finalized").request_fact(URL, QUESTION, "BOOL")
    return                                     # come back after resolution

if fact["status"] != "OK":
    return                                     # UNAVAILABLE - wait, don't pay out

self._settle(fact["answer"] == "true")
```

**Cached with a TTL and a content fingerprint.** The first contract to ask a question
pays for it; the whole ecosystem reads it free. That is the compounding part.

**Cross-contract callable.** Other contracts don't copy-paste your code — they depend
on your address. An actual on-chain dependency, not a gist.

**Normalized before the LLM ever sees it.** Volatile DOM stripped, numbers banded,
clocks quantized, availability checked *first*.

---

## How it works

```
url -> [1] fetch -> [2] AVAILABILITY GATE -> [2b] normalize -> [3] LLM -> [4] project
                          |                                                    |
                          v                                                    v
                    UNAVAILABLE                                        SCHEMA_VIOLATION
                   (LLM never runs)                                    (never guesses)
```

Stages 1, 2 and 4 are **deterministic**. Only stage 3 touches a model. The validator
independently re-runs the entire pipeline and compares **only** `(status, value)` —
never the free text, never the fingerprint, never the evidence quote.

Full design: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

---

## Why the API looks like this

Because of a real GenLayer constraint, not a preference.

IC-to-IC writes are `emit()` — asynchronous and fire-and-forget. **A calling contract
can never receive a `fact_id` back from `request_fact`.** So the key is derived from
the content itself:

```
fact_key = sha256(canonical_url || question || canonical_schema)
```

Anyone can compute it, off-chain or on-chain, before the transaction lands. Three
things fall out for free: the cache is content-addressed (shared across all callers),
`request_fact` is naturally idempotent (required, because `emit(on='accepted')` can be
delivered twice across appeal rounds), and **TTL stays a read-side parameter** so
callers with different freshness needs still share one cache slot.

---

## Project documents

| Document | What's in it |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Schema system, resolution pipeline, consensus model, storage layout, limitations |
| [ROADMAP.md](docs/ROADMAP.md) | Eight phases, exit criteria, scope boundaries, risk register |
| [BUILD-PLAN.md](docs/BUILD-PLAN.md) | File-level tasks with Done-when assertions, testing strategy |
| [SUBMISSION-STRATEGY.md](docs/SUBMISSION-STRATEGY.md) | How this maps to GenLayer Points contribution categories |

---

## Build order

Deterministic core first, consensus last. Everything that can be a pure Python function
with a unit test is written and proven before a line touches the GenVM.

| Phase | | Est. |
|---|---|---|
| 0 | Foundations — repo, lint, CI, **deploy path proven** | 0.5d |
| 1 | Schema kernel (pure Python) | 1d |
| 2 | Normalizer + availability gate (pure Python) | 1.5d |
| 3 | Core contract + equivalence principle | 2d |
| 4 | Typed interface, key parity, examples | 1d |
| 5 | Integration tests + testnet deploy + stability measurement | 1.5d |
| 6 | Retrofit two existing contracts, publish the diff | 1d |
| 7 | Tutorial, blog post, demo, submissions | 1.5d |

`lib/` never imports GenLayer, so phases 1–2 run under plain `pytest` in milliseconds —
and ship as a standalone library in their own right.

---

## The test that is the point

```python
def test_normalization_is_stable_across_refetches():
    for name in VOLATILE_FIXTURES:            # real pages, captured twice
        a, b = load(f"{name}.a"), load(f"{name}.b")
        assert normalize(a.body, Q) == normalize(b.body, Q)
```

Same URL, fetched minutes apart, normalizes to identical bytes. That assertion is the
entire value proposition.

---

## Status

| | |
|---|---|
| Testnet address | `[TBD — phase 5]` |
| Consensus stability, volatile page | `[TBD — measured in phase 5, published as-is]` |
| Contracts retrofitted | `[TBD — phase 6]` |
| Lines removed by retrofit | `[TBD — phase 6]` |

**These get real numbers or they stay empty.** A measured 87% with an honest analysis
of the three failures is worth more than an unbacked claim of reliability.

---

## Known limitations

Stated up front, deliberately.

1. **Band boundary straddle.** A true value sitting exactly on a band edge can put
   leader and validator in adjacent bands. Mitigation is caller-side: pick a step
   coarser than the observed jitter.
2. **Single-fetch evidence.** One URL per fact. Multi-source corroboration is out of
   scope for v1 and belongs in a layer above.
3. **Refresh is caller-driven.** No scheduler — a fact goes stale until someone pays to
   refresh it. Correct for a shared public good.
4. **JS-heavy pages** may register as `UNAVAILABLE`. Correctly, but it is a coverage gap.
5. **Free-text answers are never coming.** Not a v1 limitation — a permanent boundary.
   The moment Veritas returns prose it stops being able to reach consensus and becomes
   the thing it was built to replace.

---

## License

MIT.
