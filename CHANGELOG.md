# Changelog

All notable changes to **BagBot** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 🐛 Bug fixes (found by full-stack integration testing)

- **`bagbot dashboard` crashed on startup** (`src/bagbot/dashboard.py`,
  `src/bagbot/cli.py`)
  `run_dashboard()` called `uvicorn.run()`, which tries to create its own
  event loop — raising "Cannot run the event loop while another loop is
  running" because `cmd_dashboard` was already inside `asyncio.run()`.
  Rewritten as an async coroutine that builds a `uvicorn.Server` and awaits
  `serve()` on the existing loop. Verified by real HTTP requests:
  `GET /` → 200, unauthenticated mutations → 403 (read-only) or 401
  (wrong token), correct token → passes through to MCP.

- **`bagbot` console script was missing** (`pyproject.toml`)
  The project claimed `pip install -e .` provides a `bagbot` command, but
  `[project.scripts]` was never declared. Added
  `bagbot = "bagbot.cli:main"`; verified the entry point serves
  `status`/`probe`/`once`/`run`/`dashboard` after a fresh editable install.

- **`BagBot.__init__` raised when `ORBIO_MCP_TOKEN` was unset**
  (`src/bagbot/daemon.py`)
  Constructing the object without a token raised `ValueError` immediately,
  blocking tests, demos and introspection. Token-less construction now
  defers client creation (`self.mcp is None`) and `require_mcp()` raises a
  clear `OrbioMCPError` only when a network call is actually attempted.

### 🛠 Tooling

- **`make install` no longer hardcodes `python3.10`** (Makefile,
  `scripts/detect_python.sh`) — auto-detects the newest Python ≥ 3.10 in
  PATH and prints actionable guidance when none is found.
- **`make demo` target** runs `scripts/demo_e2e.py` (zero-config 5-tick
  end-to-end demo); errors clearly when the venv does not exist yet.

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

## [0.1.3] — 2026-09-07

### 🔒 Security fix (from upstream branch `fix/dashboard-auth-and-portable-tests`)

- **Dashboard mutation endpoints now require authentication** (`src/bagbot/dashboard.py`)
  POST `/api/claim`, `/api/rotate`, `/api/topup` were previously **unauthenticated**:
  anyone who could reach the dashboard (default: `127.0.0.1:8765`) could claim or rotate
  your OpenRouter keys. Now protected by `DASHBOARD_TOKEN`:

  - **Empty token** (default) → mutations are **disabled** (403). Dashboard is read-only.
  - **Set token in `.env`** → mutations require `Authorization: Bearer <token>` OR
    `X-Dashboard-Token: <token>` header.
  - **Wrong/missing token** with a configured expected token → 401.

  Recommended: bind to `127.0.0.1` (default). If you bind to `0.0.0.0`, **you MUST
  set a strong `DASHBOARD_TOKEN`**.

- **Frontend stores token in localStorage** (`dashboard/static/app.js`)
  `getDashboardToken()` reads from `localStorage` and prompts once if missing.
  Applied to all 3 manual actions (claim/rotate/topup). Also fixed response parsing
  to be safe when JSON is empty (e.g. 502 errors).

- **Dashboard responses never include the secret** (`src/bagbot/dashboard.py`)
  Claim endpoint returns only `{key_id, headroom_usd}` — never the `sk-or-v1-…` secret.

- **Documented threat model** (`SECURITY.md`)
  Two new rows: "Unauthenticated dashboard mutations" + "OpenRouter key secrets
  stored in SQLite" (recommendation: `chmod 600` the DB; full at-rest encryption planned).

### 🛠 Test improvements

- **CLI error tests are now portable** (`tests/test_cli_errors.py`)
  No more hard-coded `/Users/mac/Desktop/deepseek/bagbot` path. Uses
  `Path(__file__).resolve().parents[1]` to find the project root at test time.

- **Added 13 mutation-resistant auth tests** (`tests/test_dashboard_auth.py`)
  Each test targets a specific decision point in the new auth logic. Designed
  to be KILLED by `scripts/mutation_test.py`.

### 📊 Test stats

- Tests: 84 → **97** (+13 auth, all mutation-resistant)
- Mutation score: **dashboard.py 100%** (was N/A — new code)
- ruff: clean
- mypy: clean

