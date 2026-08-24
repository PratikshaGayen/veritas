# Tooling Friction Log

Real defects hit while building against the GenLayer toolchain, kept from day one of
phase 0 per [SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md) artifact #6. File the
real ones as issues while the reproduction is fresh; link the issue URL here once
filed.

| Date | Tool | Symptom | Repro | Status |
|---|---|---|---|---|
| 2026-08-24 | `genvm-linter` v0.3.0-rc7 | `genvm-lint check` on `py-genlayer:1zr6nqk...` (the hash the linter itself suggests as "newer available") fails with `Failed to load SDK: No module named 'genlayer.py'`, even after `genvm-lint setup --contract` fetches the matching SDK. The older pinned hash `1jb45aa8y...` lints and validates cleanly. | `genvm-lint check contracts/hello.py` after editing the `Depends` header to the suggested newer hash | Not yet filed |
| 2026-08-24 | `genlayer-test` 0.29.2 | `direct_deploy(...)` fails every call on native Windows Python with `PermissionError: [WinError 32]`. `gltest/direct/loader.py`'s `_inject_message_to_fd0` does `os.dup2(fd, 0)` then `os.unlink(path)` on the same still-open fd — legal on POSIX, not on Windows. `tests/unit` (pure Python) is unaffected; `ubuntu-latest` CI is unaffected. | `pytest tests/direct` from a native Windows shell (not WSL) | Not yet filed |

## Filing checklist

- [ ] Minimal reproduction (contract file + exact command)
- [ ] Expected vs. actual behaviour
- [ ] Environment (OS, tool version, Python version)
- [ ] Link back to this row once filed
