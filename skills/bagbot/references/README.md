# References

Pointer docs for the bagbot skill. Full files live in the main repo; the
entries below link to them so any agent can fetch the complete guide on
demand.

| Reference | Repo path | Why |
|---|---|---|
| Main README | [`../../README.md`](../../README.md) | Project overview, badges, structure |
| Chinese user guide | [`../../docs/guide.zh-CN.md`](../../docs/guide.zh-CN.md) | 283-line zero-to-running tutorial (中文) |
| Build Week notes | [`../../docs/BUILD_WEEK.md`](../../docs/BUILD_WEEK.md) | Competition context / submission text |
| Tweet drafts | [`../../docs/TWEETS.md`](../../docs/TWEETS.md) | Promotion copy |
| Changelog | [`../../CHANGELOG.md`](../../CHANGELOG.md) | Version history |
| Security | [`../../SECURITY.md`](../../SECURITY.md) | Vulnerability reporting / threat model |
| Python package | [`../../pyproject.toml`](../../pyproject.toml) | Main package metadata |

When an agent needs *operational detail* (exact MCP payload shape, policy
thresholds, notifier formats), read the corresponding module in
[`../../src/bagbot/`](../../src/bagbot/):
`orbio_mcp.py`, `policy.py`, `config.py`, `daemon.py`, `notifier.py`,
`dashboard.py`, `state.py`.
