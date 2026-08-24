# Veritas — Submission Strategy

How this project converts into GenLayer Points contributions, and why it is
structured the way it is.

> **Verify before filing.** Programme details change — categories, point ranges, and
> the global multiplier are all set by stewards and adjusted over time. Confirm the
> current category list and requirements on the Points portal before submitting.
> This document is the plan, not the rulebook.

---

## The strategy in one line

**One project, structured so that six legitimately separate artifacts fall out of
it** — each with its own public evidence URL, each mapping to a different builder
contribution category.

This is not gaming the system. It is the natural shape of infrastructure work: a
shared contract genuinely *is* a deployed contract, *and* a developer tool, *and* a
teaching artifact. The structural decision that makes this possible is keeping `lib/`
free of GenLayer imports (see [BUILD-PLAN.md](./BUILD-PLAN.md)), so the schema kernel
stands on its own as a reusable library instead of being buried inside a contract file.

---

## What is known about the programme

From the GenLayer Foundation Points documentation:

| Aspect | What it says |
|---|---|
| Tracks | Validators, Builders, Community/Stewards |
| Builder categories | Deployed contracts, GitHub repositories, blog posts, tutorials and documentation, developer tools, tooling bug reports, community education |
| Scoring | Each type has a min–max point range; **stewards set the value during review based on impact and quality**; a global multiplier applies |
| Steward criteria | Evidence quality and completeness, adherence to the contribution type's requirements, work impact and quality, date accuracy and context |
| Evidence rule | Verifiable, **login-free** URLs. Private repositories cannot be evaluated. |
| Submission flow | Choose type → completion date → description (max 1,000 chars) → evidence URLs → submit for steward review |
| Possible outcome | "More Information Needed" — requires edits and resubmission |

Two things follow directly.

**First: points are a judgement call, not a formula.** Stewards score on impact and
quality within a range. So the goal is not to maximise submission count — it is to
make each submission obviously high-impact to a human reviewer with limited time.

**Second: the 1,000-character description is the real bottleneck.** Everything else is
a link. The description is where a steward decides whether this is a weekend dApp or
ecosystem infrastructure. Draft each one deliberately; do not improvise it in the form.

---

## Mapping: artifact to category

| # | Artifact | Category | Evidence URL |
|---|---|---|---|
| 1 | Veritas oracle live on testnet | Deployed contract | Explorer link to the contract address |
| 2 | The repository | GitHub repository | Public repo URL |
| 3 | `lib/schema` + `lib/normalize` + `interface.py` | Developer tool | Repo subpath / package link |
| 4 | "Making your web-reading contract consensus-stable" | Tutorial / documentation | Published docs URL |
| 5 | "GenLayer doesn't need oracles — half right" | Blog post | Public post URL |
| 6 | Any real GenVM / CLI / docs defect found while building | Tooling bug report | Issue link |

**On #6 — do not skip this.** Building against a young runtime surfaces real defects:
undocumented API shapes, linter false positives, doc pages that contradict the runner.
Keep a running `docs/FRICTION.md` from day one of phase 0 and file the real ones as
issues. They are separately submittable, cost almost nothing extra, and are genuinely
useful to the ecosystem. The one caught while researching this plan — tooling and docs
disagreeing on the exact web-access API shape — is precisely the type.

---

## Writing the descriptions

The 1,000-character limit is tight. A structure that works:

```
[1 sentence]  What it is.
[1 sentence]  The specific problem in the ecosystem it fixes.
[2 sentences] What is technically novel — the mechanism, not the adjective.
[1 sentence]  Evidence of impact: a measured number or a concrete reuse.
[1 sentence]  What is reusable by others, and how they call it.
```

### Draft — #1, deployed contract

> Veritas is a shared web-fact oracle: contracts pass a URL, a question, and a
> **schema**, and get back a consensus-stable discrete value. GenLayer removes the
> trusted oracle but not the evidence-normalization problem — validators fetching the
> same page independently get different bytes, and today a rate-limited or paywalled
> page is fed to the LLM anyway, which then invents a confident answer. Veritas
> refuses free-text answers (every request declares BOOL / ENUM / BAND / DATE), runs a
> deterministic availability gate before the LLM, and returns UNAVAILABLE instead of a
> guess. Answers are cached under a content-addressed key, so the first caller pays and
> the whole ecosystem reads free. Consensus stability on a volatile page:
> **[MEASURED]%** over N runs. Callable cross-contract via a published typed interface.

Fill `[MEASURED]` from `docs/STABILITY-REPORT.md`. **Do not submit with a placeholder,
and do not round it up.**

### Draft — #3, developer tool

> A standalone, GenLayer-import-free Python library for making web evidence
> consensus-safe: a schema kernel (parse, canonicalize, project model output onto a
> closed value set, or fail explicitly) plus a deterministic normalizer and
> availability gate (strips volatile DOM, redacts relative clocks, quantizes numbers,
> detects 429 / paywall / bot-wall / empty). Usable inside any Intelligent Contract,
> not only Veritas. Ships with a fixture corpus of real captured pages and the test
> that matters: the same URL fetched twice, minutes apart, normalizes to identical
> bytes.

---

## Sequencing the submissions

Submit as each artifact becomes real, not all at once at the end.

| When | Submit | Why then |
|---|---|---|
| End of phase 2 | #3, developer tool | The library is genuinely done and standalone — it does not need the contract to be valuable |
| End of phase 5 | #1 deployed contract, #2 repository | The address and the measured stability number both exist |
| During phases 0–6 | #6 bug reports, as found | File while the reproduction is fresh |
| End of phase 7 | #4 tutorial, #5 blog post | Both depend on having real results to cite |

**Rationale:** submissions carry a completion date and stewards check date accuracy.
Submitting a finished artifact when it is finished is both more accurate and more
credible than a retroactive batch that all claims the same date.

---

## The single highest-leverage decision

**Phase 6 — the adapter rewrites — is what turns this from a good submission into a
strong one.**

A steward reviewing "I built an oracle contract" has to take the usefulness on faith.
A steward reviewing this:

> *"Here are N of my own deployed contracts. Here is the one bug they all shared: when
> the page 429s, the LLM invents an answer and the contract settles on it. Here is the
> shared fix. Here are two of them retrofitted — `-[X] lines` each, and consensus
> stability on the same volatile page went from [before]% to [after]%."*

...does not have to take anything on faith. The evidence is a diff and two numbers.

That is the difference between a contract submission and an infrastructure submission,
and it is why phase 6 gets its own phase instead of being folded into the demo.

---

## Pre-submission checklist

Run this before filing anything.

- [ ] Repo is **public** and clones without login — private repos cannot be evaluated
- [ ] LICENSE file present
- [ ] CI badge is green and the workflow actually runs the tests
- [ ] README opens with what it does and who calls it, not with installation steps
- [ ] Testnet contract address is in the README, with an explorer link
- [ ] `docs/STABILITY-REPORT.md` has real measured numbers, honestly reported
- [ ] Every contract file's line 1 is a **pinned** runner hash — no `test`, no `latest`
- [ ] The limitations section exists and is honest
- [ ] Demo video is public and login-free
- [ ] Every evidence URL opens in a private browser window with no account
- [ ] Each description is under 1,000 characters and contains at least one number
- [ ] Completion dates are accurate per artifact, not backfilled

---

## What would sink this

Worth naming so it can be avoided.

| Failure | Why it sinks the submission |
|---|---|
| Claiming reliability without measuring it | The one claim a steward can and will check |
| A private or login-walled repo | Explicitly unevaluable |
| Unpinned runner alias in a contract | Anyone who tries to deploy it fails immediately, and it signals the contract was never really deployed |
| No caller other than the author | "Reusable" becomes an adjective instead of a demonstration — phase 4's reuse gate exists to prevent this |
| Six submissions of the same thing reworded | Stewards score on impact; padding reads as padding and damages the credible submissions next to it |
| Hiding the limitations | An unstated limitation a reviewer finds themselves costs more than a stated one |

---

## Beyond points: the grants track

The Foundation also runs a grants programme, weighted: technical feasibility 30%,
ecosystem impact 30%, team track record 20%, long-term viability 20%. Grantees are
expected to open-source the code, report progress, and present at a community
showcase.

Veritas fits the "Core Infrastructure & Developer Tools" category, and the phase 6
evidence maps directly onto the ecosystem-impact weighting. **Do not pursue this
first.** Ship the contribution, gather the measured numbers and any external callers,
then approach grants with results rather than a proposal. An application backed by a
live testnet address, a published stability measurement, and two retrofitted contracts
is a substantially different application from one backed by a plan.
