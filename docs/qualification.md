# Qualification record

The hub is being prepared for review. The table below is the required covering matrix, not a list of proven support claims. A synthetic pass does not qualify a real provider. Complete rows need a runtime/provider record with versions, authoring capabilities, authentication method, permissions, source revision, plan/correction evidence, reviewed/pushed/head SHA, checks, costs, observed limits and recovery results.

| Row | Host | Sole runtime | Setup surface | Provider journey | Current evidence |
|---|---|---|---|---|---|
| L-C | Local | Claude | Claude Code and Cowork independently | GitHub PAT/manual intake, real Docker | Not qualified |
| L-X | Local | Codex | Codex authoring | GitHub PAT/manual intake, real Docker | Not qualified |
| R-C | Railway | Claude | Claude Code | GitHub App/events, qualified sandbox | Not qualified |
| R-X | Railway | Codex | Codex authoring | GitHub App/events, qualified sandbox | Not qualified |
| M-C | Maritime | Claude | Cowork | GitHub App/events, qualified sandbox | Not qualified |
| M-X | Maritime | Codex | Codex authoring | GitHub App/events, qualified sandbox | Not qualified |

Every row includes chat, durable workflow and MCP checks, context bootstrap and a saved correction, scoped teammate access/denial, revocation, failures and restart. Hosted rows also need public URLs and sign-in/MCP callbacks, data-root persistence, scheduler behavior, sleep/wake, backup/restore and upgrades. A blocked row remains a visible qualification gap. Other combinations may receive synthetic contract coverage but are not advertised as supported.

## Evidence so far

- 20 October 2026, authoring: the full suite passed with scripted model, station, GitHub and human doubles and a local bare repository. That proves the pipeline's logic, not any provider row.
- 22 to 23 October 2026, a hosted run on a Hubzoid 2.0.1 deployment (Linux VM, Docker sandbox, one Claude subscription runtime) connected to a real GitHub repository through a GitHub App. Proven: the mention gets the eyes reaction, the work is accepted and classified, the plan is posted on the issue and approved in the Inbox, and the implementer starts in a real sandbox. Found and fixed on the way: the sandbox had no commit identity, the default image refuses plain `pip install`, the chat link pointed at a hub path that does not exist, and `allowed_groups` on the GitHub connection did not decide who may start work (the `channel_github` grant does).
- Linear and Slack have recorded-payload integration tests, not live runs. Railway, Maritime (the second hosting provider Hubzoid documents, next to Railway), Codex and Cowork rows have not been run.

## Local real journey checklist

Follow SETUP.md after authorizing a scratch repository. Capture cold install, connection, bootstrap and task timing separately. Use the current supported runtime authentication. Complete plan-only, correction/repeat, attended implementation/approval, independent review, exact-head draft, human-ready handoff, restart and denial checks. For App/event operation also test label, stale/red CI, closed/merged PRs and duplicate delivery. Never replace a missing journey with the scripted `tests/live` demo.
