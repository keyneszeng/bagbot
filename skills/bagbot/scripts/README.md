# bagbot-skill scripts — pip-installable facades for any agent

This folder exposes thin, self-contained Python modules so any agent can
talk to Orbio without hunting around a repo:

| module | purpose |
|---|---|
| `bagbot_orbio` | `OrbioClient` — the 6 MCP tools (get_balance / claim_key / get_key_status / top_up_key / rotate_key / delete_key) |
| `bagbot_policy` | `decide(Snapshot, PolicyConfig) → (Action, reason)` pure-function engine |
| `bagbot_settings` | `Settings` / `load_settings()` — `.env` loading |
| `bagbot_cli` | `python bagbot_cli.py probe|status|decide <usd>` |

The facades import the **real** implementation from the `bagbot` package.
`bagbot_bootstrap` finds the real `src/` automatically when the skill sits
inside the repo tree; otherwise, install the parent `bagbot` package.

## Install (optional — facades work with plain PYTHONPATH too)

```bash
pip install -e .            # adds `bagbot` console entrypoints? no — just python pkgs
PYTHONPATH=. python3 -c "import bagbot_policy; print(bagbot_policy.decide.__doc__)"
```

## Requirements

| Module | Third-party deps |
|---|---|
| `bagbot_policy` | **none** — pure stdlib, usable anywhere instantly |
| `bagbot_orbio` | `httpx`, `pydantic`, `python-dotenv` (network + env) |
| `bagbot_settings` | `pydantic`, `python-dotenv` |
| `bagbot_cli` | none for `decide`/`help`; above deps only for `probe`/`status` |

Install runtime deps with `pip install httpx pydantic python-dotenv` or
`pip install -e .[full]` from this folder.
