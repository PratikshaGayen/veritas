# Tooling Friction Log

Real defects hit while building against the GenLayer toolchain, kept from day one of
phase 0 per [SUBMISSION-STRATEGY.md](./SUBMISSION-STRATEGY.md) artifact #6. File the
real ones as issues while the reproduction is fresh; link the issue URL here once
filed.

| Date | Tool | Symptom | Repro | Status |
|---|---|---|---|---|
| 2026-08-24 | `genvm-linter` v0.3.0-rc7 | `genvm-lint check` on `py-genlayer:1zr6nqk...` (the hash the linter itself suggests as "newer available") fails with `Failed to load SDK: No module named 'genlayer.py'`, even after `genvm-lint setup --contract` fetches the matching SDK. The older pinned hash `1jb45aa8y...` lints and validates cleanly. | `genvm-lint check contracts/hello.py` after editing the `Depends` header to the suggested newer hash | Not yet filed |
| 2026-08-24 | `genlayer-test` 0.29.2 | `direct_deploy(...)` fails every call on native Windows Python with `PermissionError: [WinError 32]`. `gltest/direct/loader.py`'s `_inject_message_to_fd0` does `os.dup2(fd, 0)` then `os.unlink(path)` on the same still-open fd — legal on POSIX, not on Windows. `tests/unit` (pure Python) is unaffected; `ubuntu-latest` CI is unaffected. | `pytest tests/direct` from a native Windows shell (not WSL) | Not yet filed |
| 2026-08-24 | `genlayer-test` 0.29.2 (direct mode, WSL/Linux) | `direct_deploy(...)` fails on first use with `urllib.error.HTTPError: HTTP Error 404` while downloading the GenVM SDK. `gltest/direct/sdk_loader.py`'s `download_artifacts()` hardcodes the asset filename `genvm-universal.tar.xz`, but the actual GitHub release (checked via the API for `v0.3.0-rc7`) ships no such asset — only `genvm-linux-amd64(-executor).tar.xz`, `genvm-linux-arm64(-executor).tar.xz`, `genvm-macos-arm64(-executor).tar.xz`, and `genvm-runners-all.tar.xz`. Workaround used this session: copy `genvm-linter`'s own cache file (`~/.cache/genvm-linter/genvm-universal-<version>.tar.xz`, which — confusingly — genvm-linter names the same way despite fetching from a different source) into `~/.cache/gltest-direct/genvm-universal-<version>.tar.xz` to bypass the broken downloader entirely. | `pytest tests/direct` on a machine with no pre-existing `~/.cache/gltest-direct/` bundle | Not yet filed |
| 2026-08-24 | GenLayer docs, "Handling HTTP Errors" example (`developers/intelligent-contracts/features/web-access`) | The docs show `response.status_code` for the object returned by `gl.nondet.web.request(...)`. The actual installed SDK (`genlayer/gl/nondet/web.py`, confirmed by reading the source directly) defines `Response` as `@dataclass class Response: status: int; headers: dict; body: bytes \| None` — the field is `.status`, not `.status_code`. Using `.status_code` doesn't raise where you'd notice it (it's easy to wrap in a broad `except Exception`, as this project's first draft did) — it silently produces an `AttributeError` that gets swallowed, and every fetch looks like a network failure. | Any contract written against the documented `.status_code` field name, run under direct mode with `mock_web` | Not yet filed |

## Filing checklist

- [ ] Minimal reproduction (contract file + exact command)
- [ ] Expected vs. actual behaviour
- [ ] Environment (OS, tool version, Python version)
- [ ] Link back to this row once filed
