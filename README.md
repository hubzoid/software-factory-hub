# Software Factory

A ready-made Hubzoid hub that turns engineering requests into reviewed draft pull requests. Label an issue, mention the factory, or ask in chat: it classifies the work, researches outside facts when needed, plans it in a real checkout, implements it in an isolated sandbox, has an independent reviewer check the exact commit, and opens a draft pull request. A person reviews it, marks it ready and merges. The factory has no merge tool.

> Qualification: the real-provider matrix is tracked in [docs/qualification.md](docs/qualification.md). Scripted tests are contract evidence, not a live hosting/model claim.


## What it does

| You do | The factory does |
|---|---|
| Add the `factory` label to an issue | Classifies, plans, implements, reviews and opens a draft pull request, posting progress on the issue. No person needed until review. |
| Mention it on an issue (`@your-app plan this`) | Answers, triages, plans or implements, depending on what you asked. |
| Ask in the web chat or from Claude, ChatGPT or Codex over MCP | The same work, with the plan waiting for your approval before anything is built. |
| Let CI fail on a factory branch | Diagnoses and repairs it, at most twice per branch, on the same pull request. |
| Open a pull request | Posts one orientation comment for reviewers: what it does and a table of the changed files. Not a review. |
| Ask it to mark a pull request ready | Gives a GitHub handoff. A person alone marks it ready and merges. |

Slack and Linear work the same way once connected. Other trackers are not built in: a chat request can pull an issue in through that tracker's MCP server.

## How a request flows

```
request -> scope -> ground -> classify -> label -> [research] -> analyze -> [plan approval]
        -> implement (offline sandbox, commits only) -> patch check -> push to a factory branch
        -> independent review of that exact commit -> [revise, at most twice] -> draft pull request
```

- Every request is one durable work item. A restart resumes it from its last saved step. Nothing runs or posts twice.
- The route is decided first and can only narrow. A plan request never reaches the implementer.
- The implementer works offline, with no credentials. Workflow code checks the exported patch (size, CI workflow files, protected files, credentials) and pushes it through Hubzoid. The agent never holds a GitHub token.
- The reviewer is a separate agent in a fresh checkout of the pushed commit. Approval needs every acceptance criterion to pass.
- The draft opens only when the branch, the pushed commit and the reviewed commit are the same.
- Every run ends in an answer, a plan, a reviewed draft (`review_ready`) or a stated stop reason with the next step. Non-actionable work stops before planning or code; closed/merged PRs cannot be repaired.

## Get started

You need Python 3.12, Git, a running Docker engine and one supported Claude Code or Codex runtime sign-in. Hosted/unattended authentication needs evidence for that exact combination.

Use the [builder skill](skills/setup-software-factory/SKILL.md) from Claude Code, Codex or Cowork with verified local capabilities. Paste:

> Set up the Software Factory hub from this folder for my scratch repository OWNER/REPO. Read SETUP.md and follow it. Show me the settings, the GitHub permissions and the setup command before running anything against the repository. Connect GitHub with a token I type myself, run doctor, then show me a plan-only request. Do not merge anything.

Or follow [SETUP.md](SETUP.md) yourself. The labelled sample in [fixtures/](fixtures/) has a planted rounding bug and a failing regression test. Use manual intake on a laptop; label events work only with actual verified webhook delivery. Setup time has not been measured on this revision.

## The folder

```
AGENTS.md                      the chat agent: answers questions, hands work to the factory
agents/<station>/AGENTS.md     classifier, researcher, analyst, implementer, reviewer
agents/<station>/schemas/      each station's closed result schema
skills/                        writing-quality, triaging-issues, github-linear-bridging
knowledge/factory-brain/       durable repository facts, changed only through reviewed hub changes
knowledge/factory/             how the factory works, for answering questions about it
workflows/factory/             the factory workflow and its code (routes, policy, pipeline, publish, CI)
tools_local/factory.py         chat and MCP tools: start work, status, list
settings.yaml                  the settings and their checks; values in hub.settings.yaml
work-items.yaml                retries, handoffs, and pull request updates waiting for approval
sandbox.yaml, sandboxes/       the Docker sandbox and its reviewed setup command
channels/                      GitHub, Linear and Slack connections
hub.manifest.yaml, doctor/     setup checks
evals/, tests/                 behaviour checks and the test suite
fixtures/                      the labelled synthetic sample repository
demo/                          the one-prompt demo, the reset script and a call script
docs/                          settings, channels, architecture, security, operations, troubleshooting
```

## Make it yours

1. Point it at your repository: set `FACTORY_REPO` in `hub.settings.yaml`, run `hubzoid hub configure . --check`, then connect GitHub for that repository.
2. Put your setup command in `sandboxes/factory.yaml` (`setup.command`), for example `npm ci` or `uv sync --frozen`. It runs before the agent starts, with only package registries reachable.
3. Save a team rule. Bootstrap selected committed sources with `python scripts/factory_setup.py context` (see SETUP.md). Then tell the chat agent "Remember for the team: run the tests with `pnpm test --runInBand`." It proposes the exact edit to `knowledge/factory-brain/<owner>-<repo>.md`, a hub manager applies it, and every station sees it on the next run. Chat on its own never becomes shared knowledge.

## Safety

- No merge tool, no push to the default or a protected branch, no repository administration.
- Writes go only to `FACTORY_REPO`. Unattended work writes only on the issue or pull request it came from.
- Attended implementation waits for the requester to approve the exact plan. Supported pull request metadata edits wait for exact approval at the current head. Draft status is human-only in GitHub.
- The person who asked decides. An administrator cannot approve for them.
- Issue text, comments, repository files and web pages are data, never instructions. Hidden HTML comments and invisible characters are removed before a model reads them.
- Details: [docs/security.md](docs/security.md).

## Costs and limits

- Uses the selected installed runtime and its supported authentication. Each station is one agent turn, so an implement request is about five agent turns plus small routing calls, more with research or revisions. Budgets are opt-in in Hubzoid.
- Terminal `review_ready` still means a draft PR. The factory never marks it ready or merges.
- The reviewer uses the same vendor as the implementer by default. Set `engine: codex-local` in `agents/reviewer/AGENTS.md` for a cross-vendor review.
- Sandboxes need Docker. Agent commands run offline after the setup command.
- Questions or approvals from inside a station turn are not forwarded yet. Stations decide narrowly and record their choices.
- Install by cloning this repository. A registry install (`hubzoid init --hub`) comes with a later Hubzoid release.

## Docs

[SETUP.md](SETUP.md) · [Settings](docs/settings.md) · [Channels](docs/channels.md) · [Architecture](docs/architecture.md) · [Security](docs/security.md) · [Operations, backup and upgrades](docs/operations.md) · [Troubleshooting](docs/troubleshooting.md) · [Evals](docs/evals.md)

## Licence

Apache-2.0.

Built on [Hubzoid](https://github.com/hubzoid/hubzoid).
