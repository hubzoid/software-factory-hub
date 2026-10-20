<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/hubzoid/hubzoid/72ac7bf1610c8a335b9b3ac3b536de8fdb6770f1/assets/mark-dark.svg">
    <img alt="Hubzoid" src="https://raw.githubusercontent.com/hubzoid/hubzoid/72ac7bf1610c8a335b9b3ac3b536de8fdb6770f1/assets/mark-light.svg" width="200">
  </picture>
</p>

<h1 align="center">Software Factory</h1>
<h3 align="center">AI agents on each stage of the development loop. People on the judgment calls.</h3>
<p align="center">Assign a task. Approve the plan. Review the draft pull request.</p>
<p align="center">
  <a href="https://youtu.be/gOlEus5hQzs">Watch the video</a> ·
  <a href="SETUP.md">Setup guide</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/security.md">Security</a> ·
  <a href="https://github.com/hubzoid/hubzoid">Hubzoid</a>
</p>
<p align="center">
  <a href="https://github.com/hubzoid/hubzoid"><img src="https://img.shields.io/badge/Built%20on-Hubzoid-B5471F" alt="Built on Hubzoid"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-0B0B0C" alt="Apache License 2.0"></a>
</p>

**The Software Factory is a ready-to-use Hubzoid hub that turns engineering
requests into reviewed draft pull requests.** It classifies the work, researches
outside facts when needed, plans in a real checkout of your repository, builds
in an isolated sandbox, and has an independent reviewer check the exact commit.
A person reviews the draft, marks it ready and merges.

<p align="center">
  <a href="https://youtu.be/gOlEus5hQzs"><img alt="Watch: from tickets to reviewed pull request" src="https://img.youtube.com/vi/gOlEus5hQzs/maxresdefault.jpg" width="640"></a>
</p>

## How it works for you

| You do | The factory does |
|---|---|
| Assign a task in Linear, or ask in Slack or the web chat | Plans the work and posts it back. You approve the exact plan in Hubzoid's **Waiting for you**. Then it builds, reviews and opens a draft pull request. |
| Add the `factory` label to a GitHub issue | Runs on its own: classifies, plans, builds, reviews and opens a draft pull request, posting progress on the issue. Label events arrive through a GitHub App webhook. |
| Mention it on an issue (`@your-app plan this`) | Answers, triages, plans or implements, depending on what you asked. |
| Ask from Claude, ChatGPT or Codex over MCP | The same work as chat, with the plan waiting for your approval. |
| Let CI fail on a factory branch | Diagnoses and repairs it, at most twice per branch, on the same pull request. |
| Open a pull request | Posts one orientation comment for reviewers: what it does and a table of the changed files. |

Using another tracker? Ask in chat, and the factory pulls the issue in through
that tracker's MCP server.

## Get your first useful result

You need Python 3.12, Git, a running Docker engine, and Claude Code or Codex
signed in on this machine. No API key.

```bash
git clone https://github.com/hubzoid/software-factory-hub software-factory
cd software-factory
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-sdk.txt
cp .env.example .env
```

Keep the folder name `software-factory`: it is the hub's name, and the channel
files use it. Set `MODEL=claude-local` or `MODEL=codex-local` in `.env`. Point the factory at
a scratch repository and connect GitHub ([SETUP.md](SETUP.md), steps 2 and 3),
then start it:

```bash
hubzoid hub doctor .
hubzoid run . --port 8701 --bridge-port 8702
```

In the web chat, ask, or start the same request with manual GitHub intake
(see [SETUP.md](SETUP.md)):

> Implement the fix for issue #1. Show me the plan first.

The labelled sample in [`fixtures/`](fixtures/) has a planted rounding bug and a
failing regression test. Approve the exact plan in **Waiting for you**, and you
get a reviewed draft pull request with the reviewer's result for each
acceptance criterion. To see only a plan, ask *"Plan a fix for issue #1. Stop
after the plan."* [Full setup →](SETUP.md)

<details>
<summary>Prefer to set up with Claude Code or Codex?</summary>

Paste this from the cloned folder:

```text
Set up the Software Factory hub from this folder for my scratch repository
OWNER/REPO. Read SETUP.md and follow it. Show me the settings, the GitHub
permissions and the setup command before running anything against the
repository. Connect GitHub with a token I type myself, run doctor, then show me
a plan-only request. After I approve a plan, implement it as a draft pull
request. Do not merge anything.
```

The [builder skill](skills/setup-software-factory/SKILL.md) holds the same steps
for your coding assistant.

</details>

## Under the hood

```
request -> scope -> ground -> classify -> label -> [research] -> analyze -> [plan approval]
        -> implement (offline sandbox, commits only) -> patch check -> push to a factory branch
        -> independent review of that exact commit -> [revise, at most twice] -> draft pull request
```

- **Plan.** The analyst works from a real checkout of your repository and writes
  a plan with acceptance criteria.
- **Build.** The implementer works in its own sandbox, with no network and no
  credentials, and runs your repository's own checks. Workflow code checks the
  exported patch and pushes it to a factory branch. The agent never holds a
  GitHub token.
- **Review.** A separate reviewer, in a fresh checkout of the pushed commit,
  judges the change against every acceptance criterion. The draft opens only
  when the branch, the pushed commit and the reviewed commit are the same.
- **Durable.** Every request is one work item. A restart resumes it from its
  last saved step, and nothing runs or posts twice. Every run ends in an answer,
  a plan, a reviewed draft or a stated stop reason with the next step.

## Make it yours

1. **Your repository.** Set `FACTORY_REPO` in `hub.settings.yaml`, run
   `hubzoid hub configure . --check`, then connect GitHub for that repository.
2. **Your setup command.** Put it in `sandboxes/factory.yaml` (`setup.command`),
   for example `npm ci` or `uv sync --frozen`. It runs before the agent starts,
   with only package registries reachable.
3. **Your team's rules.** Bootstrap a source-linked brief from selected committed
   files with `python scripts/factory_setup.py context --checkout PATH
   --repository OWNER/REPO --source FILE --test-command 'CMD'`
   ([SETUP.md](SETUP.md), step 4). Then tell the chat agent
   *"Remember for the team: run the tests with `pnpm test --runInBand`."* It
   proposes the exact edit to `knowledge/factory-brain/<owner>-<repo>.md`, a hub
   manager applies it, and every station sees it on the next run.
4. **How each stage works.** Each station is a page of instructions in
   `agents/<station>/AGENTS.md`: classifier, researcher, analyst, implementer
   and reviewer. For a cross-vendor review, set `engine: codex-local` in
   `agents/reviewer/AGENTS.md`.

## Safety

- No merge tool, no push to the default or a protected branch, no repository
  administration. A person marks a draft ready and merges in GitHub.
- Writes go only to `FACTORY_REPO`. Unattended work writes only on the issue or
  pull request it came from.
- Attended implementation waits for the requester to approve the exact plan.
  The person who asked decides. An administrator cannot approve for them.
- Issue text, comments, repository files and web pages are data, never
  instructions. Hidden HTML comments and invisible characters are removed from
  issue and chat text before a model reads it.

Each station is one agent turn, so an implement request is about five agent
turns plus small routing calls, more with research or revisions. Budgets are
opt-in in Hubzoid. [Security details →](docs/security.md)

## The folder

```
AGENTS.md                      the chat agent: answers questions, hands work to the factory
agents/<station>/AGENTS.md     classifier, researcher, analyst, implementer, reviewer
agents/<station>/schemas/      each station's closed result schema
skills/                        writing-quality, triaging-issues, github-linear-bridging, setup
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
```

## Go further

| Next step | Guide |
|---|---|
| Install, connect GitHub and get a first result | [Setup](SETUP.md) |
| Every setting and its check | [Settings](docs/settings.md) |
| Connect GitHub, Linear and Slack | [Channels](docs/channels.md) |
| How routes, stations and publishing fit together | [Architecture](docs/architecture.md) |
| Run it, back it up and upgrade it | [Operations](docs/operations.md) |
| Fix a failed station, intake or webhook | [Troubleshooting](docs/troubleshooting.md) |
| Behaviour checks | [Evals](docs/evals.md) |

The Software Factory is **Apache-2.0**. Built on [Hubzoid](https://github.com/hubzoid/hubzoid).
Need it running for your team? [Build with us](https://hubzoid.com/enterprise).
