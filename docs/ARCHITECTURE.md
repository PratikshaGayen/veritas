# Veritas — Architecture

> A shared, schema-constrained web-fact oracle for GenLayer.
> One contract, deployed once, that every other Intelligent Contract calls to turn
> a webpage into a consensus-stable fact.

---

## 1. The problem, stated precisely

GenLayer removes the **trusted** oracle. It does not remove the **evidence
normalization** problem.

When a contract calls `gl.nondet.web.render(url)` inside a non-deterministic block,
the leader and every validator issue *independent* HTTP requests. They get:

| Divergence source | Example |
|---|---|
| Rotating content | ads, "trending now" rails, A/B buckets |
| Clock drift | "updated 4 minutes ago" becomes "5 minutes ago" |
| Rate limiting | validator #3 gets `429`, leader got `200` |
| Mid-consensus edits | the page changed between leader and validator fetch |
| Downstream non-determinism | free-text LLM answers never match byte-for-byte |

Every builder currently patches this by hand, inside their own contract, and every
patch has the same holes. The worst hole is the last one:

> **A rate-limited or paywalled page gets fed to the LLM anyway, and the LLM invents
> a confident answer.** Nothing in the pipeline says "I could not see the page."
> Downstream contracts settle on a hallucination.

Veritas is the shared layer that fixes this once.

---

## 2. The core trick: answers must have a shape

Free-form answers never reach consensus. So the contract **refuses to return free
text**. Every request declares a schema up front, and the schema is the entire
reason consensus becomes tractable — it shrinks the comparison surface from
"two paragraphs of English" to "two elements of a small discrete set."

| Schema | Declaration | Example question | Consensus value |
|---|---|---|---|
| `BOOL` | `BOOL` | "Is flight AI302 delayed >3h?" | `true` |
| `ENUM` | `ENUM:degraded,down,up` | "What is the status page state?" | `degraded` |
| `BAND` | `BAND:0:1000:50` | "What is the BTC funding rate (bps)?" | band `7` |
| `DATE_DAY` | `DATE_DAY` | "When did this PR merge?" | `2026-08-19` |
| `INT_RANGE` | `INT:0:100` | "How many open P0 issues?" | `12` |

Plus one set of statuses that are **not** schema values and apply to every request:

| Status | Meaning |
|---|---|
| `OK` | The page was readable and the answer projects cleanly onto the schema |
| `UNAVAILABLE` | The page could not be read: 4xx/5xx, 429, paywall, bot-wall, empty |
| `SCHEMA_VIOLATION` | The page was readable but no legal schema value could be derived |
| `PENDING` | Requested, not yet resolved |

`UNAVAILABLE` is the whole point. **Veritas returns "I could not see it" instead of
a confident lie**, so downstream contracts can wait instead of settling wrong.

### The tolerance lives in the schema, not the validator

This is the design principle that separates Veritas from a hand-rolled fetch block.
A hand-rolled contract puts the fuzz in the validator ("agree if the two numbers are
within 10%"). Veritas puts the fuzz in the **declared schema**, before the question
is ever asked. `BAND(0, 1000, step=50)` is not a validator tolerance — it is the
caller stating, on the record, what precision their business logic actually needs.
The validator then does an **exact** comparison on the projected band index.

Consequences:

- The tolerance is auditable on-chain, in the request, by anyone.
- The validator stays trivially simple and hard to game.
- Two callers needing different precision declare different schemas and get
  different — correctly separate — cache slots.

---

## 3. The constraint that shapes the API

> Verified against the GenLayer docs, August 2026.

Intelligent Contract to Intelligent Contract interaction has exactly two forms:

```python
other = gl.get_contract_at(addr)
value = other.view().get_fact(key)           # SYNCHRONOUS, read-only, returns a value
other.emit(on='accepted').request_fact(...)  # ASYNCHRONOUS, write, returns NOTHING
```

Resolving a fact requires web access plus an LLM call, which requires a
non-deterministic block, which requires a **write**. Writes between contracts are
`emit()` — fire-and-forget. **A calling contract can never receive a `fact_id` back
from `request_fact`.**

This is not a limitation to work around. It is the constraint that forces the
correct design.

### Content-addressed fact keys

```
fact_key = sha256( canonical_url || 0x00 || question || 0x00 || canonical_schema )
```

The key is derivable by anyone, off-chain and on-chain, **before the transaction
lands**. The caller computes the key itself, emits the request, and reads the slot
later. No return value needed.

Three properties fall out for free:

1. **The cache is content-addressed.** Two contracts that independently ask the same
   question of the same URL with the same schema land on the *same slot*. The first
   one pays; everyone else reads free. This is the compounding property.
2. **`request_fact` is naturally idempotent.** Required, because `emit(on='accepted')`
   can be delivered more than once across appeal rounds. If the slot is already
   fresh, the call is a no-op.
3. **TTL is a read-side parameter, not part of the key.** A caller needing 5-minute
   freshness and a caller tolerating 24-hour staleness share one slot; each decides
   independently whether what is stored is fresh enough.

```python
answer, status, fetched_at, is_fresh = veritas.view().get_fact(key, max_age=3600)
```

> If TTL were baked into the key, the cache would fragment by caller preference and
> the shared-cache property — the entire economic argument for Veritas — would
> collapse. This is the single most important design decision in the project.

---

## 4. The resolution pipeline

Every resolution runs the same four stages. Stages 1, 2 and 4 are **deterministic**;
only stage 3 touches an LLM.

```
                 +---------------------------------------------+
   url --------->| 1. FETCH      gl.nondet.web.render(mode=text)|
                 +----------------------+----------------------+
                                        | raw text + status_code
                 +----------------------v----------------------+
                 | 2. AVAILABILITY GATE      (deterministic)   |
                 |    4xx/5xx? 429? bot-wall? paywall? empty?  |--> UNAVAILABLE
                 +----------------------+----------------------+    (LLM never runs)
                                        | readable
                 +----------------------v----------------------+
                 | 2b. NORMALIZE             (deterministic)   |
                 |    strip volatile DOM, collapse whitespace, |
                 |    quantize numbers, redact relative clocks |
                 +----------------------+----------------------+
                                        | normalized_evidence
                 +----------------------v----------------------+
                 | 3. SCHEMA-CONSTRAINED PROMPT       (LLM)    |
                 |    legal outputs enumerated in the prompt   |
                 |    response_format="json"                   |
                 +----------------------+----------------------+
                                        | raw LLM json
                 +----------------------v----------------------+
                 | 4. PROJECTION             (deterministic)   |
                 |    clamp to band / match enum / parse date  |--> SCHEMA_VIOLATION
                 +----------------------+----------------------+    (never guesses)
                                        |
                                   (value, OK)
```

### Stage 2 — the availability gate (the headline feature)

Runs **before** the LLM and short-circuits it. Detection is deterministic and
rule-based, never LLM-judged:

| Signal | Rule |
|---|---|
| HTTP status | `>= 400` yields `UNAVAILABLE` — 4xx tagged `[EXTERNAL]`, 5xx tagged `[TRANSIENT]` |
| Rate limit | status `429`, or body matches known throttle markers |
| Bot wall | body matches `Just a moment`, `Enable JavaScript`, `Access Denied`, `Attention Required` |
| Paywall | body matches subscriber-wall markers **and** body is under the length floor |
| Empty | normalized evidence shorter than `MIN_EVIDENCE_CHARS` |
| Irrelevant | zero token overlap between the question's content words and the evidence |

The last rule is the subtle one: a page that loaded fine but contains nothing
related to the question is *also* a case where an LLM will invent an answer.

### Stage 2b — normalization

Deterministic text surgery applied identically by leader and every validator. It
kills the divergence sources from section 1 before they can reach the model:

- drop `script`, `style`, `nav`, `footer`, `aside`, and ad containers
- collapse all whitespace runs to a single space
- redact relative-time strings (`4 minutes ago`, `just now`) to `[REL_TIME]`
- redact absolute timestamps finer than day granularity to `[TIME]`
- quantize free-standing numbers to a significant-figure budget
- truncate to `MAX_EVIDENCE_CHARS`, windowed on the first question-keyword match

### Stage 3 — the prompt

The schema is injected as an explicit closed set. The model is told, in the prompt,
that `UNAVAILABLE` is a legal and expected answer:

```
You are answering ONE question from the EVIDENCE below.
Legal answers, and nothing else:  ["up", "down", "degraded"]
If the evidence does not contain enough information, answer exactly: UNAVAILABLE
Do not guess. Do not explain outside the JSON.
Return: {"answer": <one legal value>, "evidence_span": "<verbatim quote>"}
```

`evidence_span` is required, and is **not** part of the consensus comparison. It is
stored as an audit trail so a human can see *why* the contract believed the answer.

### Stage 4 — projection

Deterministic coercion of the model's string onto the schema: case-insensitive enum
match, band index by integer division, ISO date parse. **If projection fails the
result is `SCHEMA_VIOLATION` — never a nearest-neighbour guess.**

---

## 5. Consensus model

A custom validator via `gl.vm.run_nondet_unsafe`, not a convenience wrapper.

```
leader_fn()     -> runs the full pipeline, returns {status, value, fingerprint, span}
validator_fn()  -> INDEPENDENTLY re-runs the full pipeline, then compares:
                       leader.status == validator.status
                   AND leader.value  == validator.value    # exact, on the projection
```

**Explicitly excluded from the comparison:** `evidence_span`, `fingerprint`, raw LLM
text, page byte length, fetch latency. These are advisory metadata. Including any of
them would re-import exactly the non-determinism the schema exists to eliminate.

This is genuine comparative validation — the validator produces its own independent
answer and compares the decision field. It is *not* a schema-shape check on the
leader's output, which would let the leader decide alone.

### Error taxonomy

Failure paths need consensus too. Every raised error carries a prefix that tells the
validator how to compare it:

| Prefix | Class | Validator rule |
|---|---|---|
| `[EXPECTED]` | business logic (unknown schema, malformed URL) | exact message match required |
| `[EXTERNAL]` | deterministic external failure (4xx) | exact message match required |
| `[TRANSIENT]` | non-deterministic (5xx, timeout, 429) | agree if **both** sides are transient |
| `[LLM_ERROR]` | model misbehaviour (non-JSON, missing key) | **always disagree**, forcing rotation |

Agreeing on broken LLM output would lock bad state into a cache the whole ecosystem
reads. `[LLM_ERROR]` must never reach consensus.

---

## 6. Storage

```python
@allow_storage
@dataclass
class Fact:
    url: str
    question: str
    schema: str            # canonical schema string
    status: str            # OK | UNAVAILABLE | SCHEMA_VIOLATION | PENDING
    answer: str            # canonical projected value; "" unless status == OK
    fetched_at: u256       # unix seconds, from the deterministic tx clock
    fingerprint: str       # sha256 of normalized evidence - ADVISORY ONLY
    evidence_span: str     # verbatim quote - ADVISORY ONLY
    resolve_count: u256
    last_error: str
    requester: Address


class Veritas(gl.Contract):
    facts: TreeMap[str, Fact]        # fact_key -> Fact
    fact_keys: DynArray[str]         # enumeration for indexers
    total_resolves: u256             # O(1) stats
    total_unavailable: u256
    owner: Address
```

Rules locked in from the GenLayer storage model:

- Storage fields are **class-level annotations**, never `__init__` assignments.
- Scalars use `u256`; enum-like values are stored as `str`, never `Enum` objects.
- New fields append at the **end** only — layout is positional, and this contract is
  meant to be long-lived and shared.
- `total_*` counters are maintained inline to avoid O(n) scans under the compute limit.

### Time

Verified: the GenVM clock is **deterministic and pinned to the transaction
timestamp** — `datetime.now(timezone.utc)` and `time.time()` return the same value on
every validator. TTL arithmetic is therefore safe in a deterministic block. There is
**no block number and no block hash**, so all freshness logic is timestamp-based.

---

## 7. Public interface

```python
@gl.contract_interface
class VeritasIface:
    class View:
        def get_fact(self, key: str, max_age: u256) -> dict: ...
        def compute_key(self, url: str, question: str, schema: str) -> str: ...
        def has_fresh(self, key: str, max_age: u256) -> bool: ...
        def stats(self) -> dict: ...

    class Write:
        def request_fact(self, url: str, question: str, schema: str) -> None: ...
        def refresh(self, key: str) -> None: ...
```

Caller pattern:

```python
KEY = veritas_key(URL, QUESTION, "BOOL")     # computed off-chain, a compile-time constant

@gl.public.write
def settle(self):
    v = gl.get_contract_at(VERITAS_ADDR)
    fact = v.view().get_fact(KEY, u256(3600))

    if fact["status"] == "PENDING" or not fact["is_fresh"]:
        v.emit(on="finalized").request_fact(URL, QUESTION, "BOOL")
        return                                # come back after resolution

    if fact["status"] != "OK":
        return                                # UNAVAILABLE - wait, do not pay out

    self._pay_out(fact["answer"] == "true")
```

Note the shape: **the wait-do-not-guess branch is now impossible to forget**, because
`status` is a required field of the return value rather than something a builder has
to remember to check.

---

## 8. Known limitations (stated up front)

1. **Band boundary straddle.** If the true value sits exactly on a band edge, leader
   and validator can land in adjacent bands and fail consensus. Mitigation is
   caller-side: choose a step coarser than the observed jitter. Documented with
   guidance rather than papered over with validator fuzz.
2. **Single-fetch evidence.** Veritas reads one URL per fact. Multi-source
   corroboration is deliberately out of scope for v1 and belongs in a layer above.
3. **Refresh is caller-driven.** There is no scheduler; a fact goes stale until
   someone pays to refresh it. Correct for a shared public good — refresh cost falls
   on whoever needs freshness.
4. **JS-heavy pages.** Text-mode rendering handles most cases; SPA-only content may
   register as `UNAVAILABLE`. Correctly so, but it is still a coverage gap.
5. **`emit(on='accepted')` duplicate delivery.** Handled by idempotency, but callers
   choosing `on='accepted'` must understand the appeal-rotation semantics.

---

## 9. Why this belongs on GenLayer

Checked against the "when to use GenLayer" boundary:

- **GenLayer owns:** the state transition from *"a URL and a question"* to *"a
  consensus-agreed discrete value, or an explicit admission of unavailability"* —
  including the validator comparison rule and the shared cache other contracts settle
  against.
- **Frontend/backend owns:** key-computation helpers, indexing, cache dashboards,
  non-authoritative previews.
- **External sources own:** raw page bytes, treated as untrusted and independently
  re-fetched by every validator.

This is not GenLayer-as-an-AI-backend. The judgment being made — *"does this page
support this claim, and can I even see this page?"* — is exactly the subjective,
evidence-based call that multiple validators must verify independently, and its
output directly gates settlement in every contract that depends on it.
