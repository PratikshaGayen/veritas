# Phase 6 — the availability-gate lesson, applied honestly

The original pitch's premise was: "rewrite two of your own contracts to call
Veritas, show the diff, show the line count drop." Reading the real code of both
candidate contracts — `Sybilon/contract/eligibility_judge.py` and
`signaljudge-ui/contract/signal_judge.py`, both real, deployed, working contracts
on this machine (paths local to the author's development environment, not part of
this repository) — that premise does not hold, and this document says so rather
than papering over it.

## Why the literal retrofit doesn't apply

Veritas exists for one specific shape of problem: an **unstructured** web page
(prose, a status dashboard, an article) whose content requires **subjective LLM
interpretation** to answer a question, and where a degraded fetch (429, paywall,
bot-wall) must resolve to an explicit `UNAVAILABLE` rather than feed the LLM
something it will hallucinate an answer from. See
[ARCHITECTURE.md](./ARCHITECTURE.md) section 1.

Neither contract does this:

| Contract | External source | What it fetches | LLM's role |
|---|---|---|---|
| Sybilon `eligibility_judge.py` | GitHub REST API (`api.github.com/users/{handle}`, `.../gists/{id}`) | Structured JSON: `created_at`, `public_repos`, `bio`, gist file contents | Scores pre-extracted, banded features against a rubric — never sees raw HTML |
| SignalJudge `signal_judge.py` | Binance klines REST API | Structured JSON: OHLC candle arrays | Judges a trader's prediction against pre-computed price-action facts — never extracts data itself |

Both authors deliberately kept the LLM away from raw web content and gave it only
deterministic, pre-parsed facts to reason about. That is a different, and in some
ways more conservative, design than Veritas's — it sidesteps the entire class of
bug Veritas exists to fix, because there is no unstructured-page-to-LLM step for
a degraded fetch to corrupt.

**Correcting the pitch:** "GenLayer doesn't need oracles" is about the trusted-oracle
problem. Sybilon and SignalJudge already solved their own version of the
evidence-normalization problem for structured APIs, independently, before Veritas
existed. Veritas's contribution is specific to the *unstructured* case neither of
them has.

## The lesson that does transfer

Veritas's real principle isn't "call this specific contract" — it's **detect a
degraded fetch deterministically and turn it into an explicit signal, never let it
silently become a wrong answer or a hard failure of an otherwise-working
transaction.** Both contracts have a real, concrete gap here, found by reading the
actual code, not by assumption.

### Gap 1 — Sybilon: a GitHub rate limit reverts unrelated work

`eligibility_judge.py`, inside `judge()`'s `leader_fn`:

```python
gh = gl.nondet.web.get("https://api.github.com/users/" + _handle)
if gh.status == 200:
    prof = json.loads((gh.body or b"").decode("utf-8"))
    social_exists = True
    age_band = _account_age_band(prof.get("created_at", ""))
    repos_band = _band_repos(int(prof.get("public_repos", 0) or 0))
    has_bio = bool(str(prof.get("bio") or "").strip())
elif gh.status == 404:
    social_exists = False   # a signal, not an error
elif gh.status >= 500:
    raise gl.vm.UserError(f"{ERROR_TRANSIENT} github {gh.status}")
elif gh.status >= 400 and gh.status != 404:
    raise gl.vm.UserError(f"{ERROR_EXTERNAL} github {gh.status}")
```

`judge()` also fetches the wallet's on-chain transaction count and balance via RPC
**before** this GitHub call, and those succeed independently. A GitHub `429`
(rate-limited — not remotely rare against the unauthenticated REST API a busy
campaign would hammer) falls into the `>= 400 and != 404` branch and raises
`[EXTERNAL]`, which reverts the **entire** `judge()` call — throwing away the
already-fetched on-chain data and costing the caller real gas, for a condition that
is transient in practice, not the deterministic client error `[EXTERNAL]` implies.

**The fix — reuse the existing sentinel pattern already in the file**, applying
exactly Veritas's rule: identity evidence is supplementary context for the rubric,
not load-bearing, so a degraded fetch for it should degrade the *feature*, not
abort the *judgment*.

```python
elif gh.status in (404, 429):
    social_exists = False
    identity_unavailable = (gh.status == 429)   # NEW: explicit, not silent
elif gh.status >= 500:
    raise gl.vm.UserError(f"{ERROR_TRANSIENT} github {gh.status}")
elif gh.status >= 400:
    raise gl.vm.UserError(f"{ERROR_EXTERNAL} github {gh.status}")
```

`identity_unavailable` would be threaded into `features` and the `RUBRIC` prompt
(a one-line addition: `"identity_data_unavailable: {identity_unavailable}   # GitHub
was rate-limited; do not penalize the absence of identity signals this round"`), so
the LLM — and every validator identically, since the flag is derived deterministically
from the real HTTP status — is told explicitly that identity couldn't be checked,
rather than silently treating a rate-limit the same as "no identity, ever." That
is the same distinction Veritas draws between `UNAVAILABLE` and a schema violation:
"I could not check" is not the same fact as "the answer is no."

### Gap 2 — SignalJudge: a malformed Binance response is an unhandled crash

`signal_judge.py` already has a graceful-degradation *pattern* — an empty candle
list becomes the sentinel `"0|0"` in `_verified_anchor` or `{"error":
"NO_CANDLE_DATA"}` in `get_judgment` — but only for the case where Binance returns
valid JSON that happens to be an empty list. Neither function guards the
`json.loads()` call itself:

```python
def fetch_anchor() -> str:
    raw = gl.nondet.web.render(url, mode="text")
    candles = json.loads(raw)          # <- no try/except
    if not isinstance(candles, list) or not candles:
        return "0|0"
    return f"{int(candles[-1][0]) // 1000}|{candles[-1][1]}"
```

If Binance is rate-limited or degraded and returns an HTML error page (or any
non-JSON body) instead of `[]`, `json.loads` raises `json.JSONDecodeError` —
an unclassified Python exception, not a `gl.vm.UserError` with an
`[EXPECTED]`/`[TRANSIENT]`/`[EXTERNAL]` prefix, undermining the deliberate error
taxonomy the rest of the file uses (see `signal_judge.py` lines 9-13, matching
Veritas's own `ERROR_EXPECTED`/`ERROR_TRANSIENT` constants).

**The fix — the same reused-sentinel pattern**, this time closing the actual gap
instead of introducing a new concept:

```python
def fetch_anchor() -> str:
    raw = gl.nondet.web.render(url, mode="text")
    try:
        candles = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "0|0"                    # same sentinel already used for "unknown symbol"
    if not isinstance(candles, list) or not candles:
        return "0|0"
    return f"{int(candles[-1][0]) // 1000}|{candles[-1][1]}"
```

```python
raw_klines = gl.nondet.web.render(klines_url, mode="text")
try:
    candles = json.loads(raw_klines)
except (json.JSONDecodeError, TypeError):
    return json.dumps({"error": "NO_CANDLE_DATA"})   # already handled downstream
if not isinstance(candles, list) or not candles:
    return json.dumps({"error": "NO_CANDLE_DATA"})
```

Both patches reuse sentinels the contract's own author already established
elsewhere in the same file — this is not introducing Veritas's vocabulary into a
foreign codebase, it is extending an existing, working pattern to cover a case it
was one `try/except` short of covering.

## What this document is, and isn't

This is a **reviewable case study written inside Veritas's own repository**. The
patches above are proposed, quoted, and explained — they have **not** been applied
to `Sybilon/contract/eligibility_judge.py` or `signaljudge-ui/contract/signal_judge.py`.
SignalJudge in particular escrows real staked GEN; a change to its error-handling
path is not something to apply without deliberate review and a decision about
redeployment, separate from this session's work on Veritas.

## Submission framing

The honest version of the "bug-parity" story: not *"here are two contracts that
had my exact bug and I fixed it with my exact fix,"* but *"here is a general
principle — deterministic detection before trust, explicit unavailability over a
silent wrong answer or an unrelated hard failure — validated by finding it applies,
in a different but recognizable shape, to two independently-written contracts that
never used Veritas at all."* That is a more defensible and more interesting claim
than a forced retrofit would have been.
