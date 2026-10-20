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

## Authoring environment, 20 October 2026

- Hub baseline: `666c337e`; implementation branch: `codex/claude-led-reviewed-prs`.
- Development install and CI pin SDK `c4bf1dbeaf0e498c364bfa1b1b97f10c7ae3c60c`; initial focused checks used this source. A fresh clean installation of `requirements-sdk.txt` succeeded at that exact resolved commit, imported GitHubKit 0.16.1 and verified all seven reviewed setup CLI help surfaces/flags. The final pre-review 366-case regression used SDK `f99a22406a65c1306a48485b8182f77be1ac71fb`. These are distinct evidence records; promotion still requires a qualified SDK tag containing dependencies.
- Tests reused an existing dependency environment with `PYTHONPATH` explicitly selecting the intended SDK source. See `IMPLEMENTATION.md` for commands/results. `githubkit[auth-app]` is a base dependency of the pinned SDK; the `sandbox` extra supplies Docker. A stale local environment missing a dependency does not establish a broken package declaration.
- Docker CLI is installed, but `docker info` fails because no daemon socket is available. No host-shell fallback was used. Real model-in-sandbox work is consequently unverified.
- GitHub fixture writes use a local bare repository and scripted REST responses; model/station/human results are labelled doubles. Only this hub's eventual review PR is authorized for GitHub writes in this task, so no scratch GitHub issue/PR was created for qualification.
- No Railway/Maritime account, container, paid resource or customer system was provisioned. Cowork capabilities and hosted/subscription authentication were not exercised. No such compatibility is claimed.

## Local real journey checklist

Follow SETUP.md after authorizing a scratch repository. Capture cold install, connection, bootstrap and task timing separately. Use the current supported runtime authentication. Complete plan-only, correction/repeat, attended implementation/approval, independent review, exact-head draft, human-ready handoff, restart and denial checks. For App/event operation also test label, stale/red CI, closed/merged PRs and duplicate delivery. Never replace a missing journey with the scripted `tests/live` demo.
