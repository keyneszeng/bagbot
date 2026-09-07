# Security Policy

## Supported versions

BagBot is in active development.  Only the latest commit on `main` receives security
fixes.  Older tags are not patched.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | ✅                 |
| older   | ❌                 |

## Reporting a vulnerability

Please **do not** file a public issue for security bugs.

Send a private report to one of:

- GitHub: open a [private security advisory](https://github.com/keyneszeng/bagbot/security/advisories/new) on this repo
- X DM: [@keyneszeng](https://x.com/keyneszeng)
- Email: `orbiodotso at proton.me` (PGP preferred but optional)

Please include:

1. A short description of the bug and its impact
2. Steps to reproduce, ideally a proof-of-concept
3. The commit / tag you reproduced against
4. Anything else relevant (logs, screenshots)

I aim to acknowledge new reports within **48 hours** and to ship a fix or mitigation
within **7 days**, depending on severity.

## Threat model

BagBot sits between you and Orbio's MCP.  The highest-impact threats are:

| Threat | Mitigation |
| --- | --- |
| `ORBIO_MCP_TOKEN` leak (env file, log, screenshot) | Token kept out of git via `.gitignore`; secrets redacted from logs; rotate the token on the Orbio dashboard if leaked |
| An agent on the key overspends | `top_up_key` policy + per-key $200 cap + burn-rate-based auto-rotate |
| A compromised dependency (supply chain) | `pip install --require-hashes` recommended for production; pinned versions in `requirements.txt`; review `git diff` before `pip install` |
| macOS launchd plist readable by other users | Plist contains no secrets (token is loaded from `~/.config/bagbot-pass` or env at runtime) |
| A bug in the policy engine causes a bad rotate/delete | All decisions go through `bagbot.policy.decide`, a pure function covered by unit tests; rotate / delete events are emitted to all notifiers so a human can intervene |
| Unauthenticated dashboard mutations (claim/rotate/topup) | Mutation endpoints require `DASHBOARD_TOKEN` (Bearer or `X-Dashboard-Token`). Empty token → endpoints return 403 (read-only). Default bind is `127.0.0.1` |
| OpenRouter key secrets stored in SQLite | Secrets never returned by dashboard APIs; DB file should live on an encrypted volume / restricted permissions (`chmod 600`). Full at-rest encryption is planned |

## Out of scope

- Bugs in Orbio or OpenRouter themselves
- Bugs in your LLM agent that uses the OpenRouter key
- Issues with third-party notifier services (Feishu, WeChat Work, your SMTP host)

## Acknowledgements

Thanks to everyone who reports responsibly.  Reporters are credited in
`docs/SECURITY_HALL_OF_FAME.md` (with their permission) when a fix ships.
