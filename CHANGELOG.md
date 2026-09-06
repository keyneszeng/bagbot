# Changelog

All notable changes to **BagBot** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] — 2026-09-06

### 🐛 Bug fixes

- **CLI no longer dumps traceback on common errors** (`src/bagbot/cli.py`)
  `python -m bagbot.cli probe` with no token, with a bad token, or with a
  network error now prints a single-line error message + hint and exits with
  a proper code (2 for missing config, 1 for runtime errors). The full
  Python traceback is reserved for genuinely unexpected errors and shows
  only the last 5 lines.

### 🛠 Tooling

- **Installable as a package** via `pip install -e .` (no need to `cd` to
  `src/` first). `pyproject.toml` defines the entry points and metadata.
- **MyPy type checking** added to CI (`mypy --strict` config in
  `pyproject.toml`).
- **Ruff linting** added to CI with bugbear + security + pyupgrade rule set.
- **CI matrix** now tests on Python 3.10, 3.11, AND 3.12.
- **Nightly mutation testing** via `.github/workflows/mutation.yml` —
  results uploaded as an artifact; soft warning if score drops below 50%.

### 📊 Test coverage

- 80 → **83** tests passing
- Added 3 CLI error-handling tests (`tests/test_cli_errors.py`)

## [0.1.1] — 2026-09-06

### 🐛 Bug fixes (found by mutation testing)

- **Daemon ALERT branch was unreachable** (`src/bagbot/daemon.py`)
  The `_execute()` method had a `if current is None: return` guard that fired
  before the ALERT branch. ALERT actions are emitted by the policy when there
  is **no** current key and the balance is below threshold — exactly the
  scenario the guard rejected. Moved the ALERT branch above the guard.
  *Symptom*: users never received the "balance too low" notification.

- **Dashboard `topup` endpoint had inverted logic** (`src/bagbot/dashboard.py`)
  `if cur is not None: raise HTTPException(400, ...)` — the condition was
  inverted, so the endpoint rejected every top-up that had a current key.
  Flipped to `if cur is None: raise HTTPException(400, ...)`.
  *Symptom*: manual top-up button in the dashboard always returned 400.

- **`KeyStatus` was missing `used_fraction` property** (`src/bagbot/orbio_mcp.py`)
  The daemon's `tick()` method read `status.used_fraction` but the property
  only existed on `Key`. Every tick would raise `AttributeError` if a key
  existed. Added the property to `KeyStatus` as well.

- **Probe command would leak secrets to stdout** (`src/bagbot/cli.py`)
  `print(json.dumps(st.raw))` printed raw MCP responses; if a field named
  `secret`/`token`/`authorization`/etc. was in the response, it would land
  in shell history and CI logs. Added a `_redact()` helper that masks
  sensitive fields by name before printing. Probe now only prints the
  `key_id` and `headroom_usd` of issued keys, never the `secret`.

### ✅ Tests

- Test suite grew from **8** to **80** unit/integration tests across 8 modules.
- **Mutation score** for `policy.py` improved from 26.7% to 92.9%.
- **Mutation score** for `daemon.py` improved to 94.1%.
- **Mutation score** for `orbio_mcp.py` improved to ~65%.
- All surviving mutations are now noise (dataclass defaults, log lines) or
  are explicitly documented as "minor improvement opportunity" rather than
  real bugs.

### 🛠 Tooling

- Added `scripts/mutation_test.py` — a 600-line crash-safe AST-based mutation
  tester. Uses `git stash -- <paths>` for atomic snapshots so a SIGKILL
  mid-run leaves the working tree untouched. Refuses to run if there are
  pre-existing uncommitted changes to target files.
- Added `pyproject.toml` with ruff and mypy configuration.
- Added `.github/workflows/ci.yml` (lint + test) and
  `.github/workflows/mutation.yml` (nightly mutation testing).
- Added `CODEOWNERS` (auto-review requests to `@keyneszeng`).
- Added `SECURITY.md` (vulnerability reporting policy + threat model).
- Added issue templates (`bug_report.md`, `feature_request.md`) and a
  PR template.

### 📚 Documentation

- Chinese user guide (`docs/guide.zh-CN.md`, 283 lines).
- Build Week pre-filled application text (`docs/BUILD_WEEK.md`).
- This changelog.
- Bilingual README with badges, screenshots, and install steps.

## [0.1.0] — 2026-09-06

### 🎉 Initial release

Built in 7 days for [Orbio Build Week](https://orbio.so/build).

Features:

- 6-tool Orbio MCP client (claim, get_balance, get_key_status, top_up_key,
  rotate_key, delete_key) with exponential-backoff retry and 429 awareness.
- 7×24 daemon that monitors balance, decides via a pure-function policy
  engine, and executes auto-claim / auto-topup / auto-rotate (by age and
  burn rate) / auto-delete.
- 4 notifier adapters (Feishu, WeChat Work, generic Webhook, SMTP email)
  with Chinese-first templates.
- FastAPI dashboard (Chinese UI, dark theme, 24h balance trend chart,
  event log, manual claim/rotate/topup buttons).
- One-command macOS launchd + Linux systemd install scripts.
- MIT licensed.
