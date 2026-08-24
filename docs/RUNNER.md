# Pinned Runner Versions

This is the single source of truth for the `Depends` header every contract file in
this repo must start with. Copy from here — never retype from memory, and never use
`py-genlayer:test` or `py-genlayer:latest` (both are local-development-only aliases
and are rejected by every GenLayer network).

**Resolved:** 2026-08-24, via the locally cached `genvm-linter` runner manifest
(`genvm-lint download --list` → `v0.3.0-rc7`, cross-checked against
`~/.cache/genvm-linter/genvm-universal-v0.3.0-rc7.tar.xz.index.json`) and proven by
actually running `genvm-lint check` against `contracts/hello.py`.

**Known issue, tested 2026-08-24:** the linter reports a newer runner is available
(`1zr6nqk597d97kg0dyxg0shhrykx5v02zjgnyrajapy4wlqvfvwh`), but pinning it and running
`genvm-lint check` fails SDK validation with `Failed to load SDK: No module named
'genlayer.py'`, even after `genvm-lint setup --contract` fetches the matching SDK.
This reproduces locally and looks like a linter/SDK packaging bug, not a contract
error — candidate for a tooling bug report (see
[SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md) artifact #6). **Pinned below is
the hash that both lints and validates cleanly.** Re-check this before phase 5 —
the newer hash may be fixed by then, or a further-newer one may exist.

## Single-file Python contracts (default — use this for Veritas)

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

## Multi-file Python contract packages

```python
# { "Depends": "py-genlayer-multi:06zyvrlivjga0d5jlpdbprksc0pa6jmllxvp8s20hq1l512vh5yk" }
```

## Contracts using embeddings / semantic search

```python
# {
#   "Seq": [
#     { "Depends": "py-lib-genlayer-embeddings:0bmbm3cyfwxsyh454z53vxqjf47wz2q7smcqp1q4g4a6k2kidnyk" },
#     { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
```

Veritas does not use embeddings; this is here only in case an adapter or example needs
it later.

## Verification command

```bash
genvm-lint download --list
```

## Windows note

`genvm-lint`'s human-readable output uses Unicode checkmarks that crash under the
default `cp1252` Windows console encoding (`UnicodeEncodeError` on `✓`). Force
UTF-8 output:

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 genvm-lint check contract.py
```

The `Makefile`'s `lint` target sets this automatically.

Any hash used in this repo must appear under the `py-genlayer` (or relevant) key in
that manifest for the currently cached version.

## Pre-push checklist

- [ ] Every `.py` file under `contracts/` has the pinned hash above as its first line
- [ ] `grep -rn 'py-genlayer:test\|py-genlayer:latest' contracts/` returns nothing
- [ ] `genvm-lint check <file>` passes for every changed contract file
