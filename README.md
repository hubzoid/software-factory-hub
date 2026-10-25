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
  <a href="#quick-start">Quick start</a> ·
  <a href="SETUP.md">Setup guide</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="https://github.com/hubzoid/hubzoid">Hubzoid</a>
</p>
<p align="center">
  <a href="https://github.com/hubzoid/hubzoid"><img src="https://img.shields.io/badge/Built%20on-Hubzoid-B5471F" alt="Built on Hubzoid"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-0B0B0C" alt="Apache License 2.0"></a>
  <a href="https://github.com/hubzoid/hubzoid/discussions"><img src="https://img.shields.io/badge/Community-Discussions-0B0B0C?logo=github" alt="GitHub Discussions"></a>
</p>

**The Software Factory is a ready-to-use Hubzoid hub that turns engineering requests into reviewed draft pull requests.** It classifies the work, plans in a real checkout of your repository, builds in an isolated sandbox, and has an independent reviewer check the exact commit. A person approves the plan, reviews the draft, marks it ready and merges.

<p align="center">
  <a href="https://youtu.be/gOlEus5hQzs"><img alt="Watch: from tickets to reviewed pull request" src="https://img.youtube.com/vi/gOlEus5hQzs/maxresdefault.jpg" width="640"></a>
</p>

## How it works

- **Classifier** triages the request: type, priority, complexity, and whether it is actionable. When it is not, the factory asks the requester instead of building the wrong thing.
- **Analyst** writes a plan with acceptance criteria, working from a real checkout of your repository. Attended requests wait here for the requester to approve the exact plan.
- **Implementer** carries out the plan in its own Docker sandbox, with no network and no credentials, and runs your repository's own checks. Workflow code checks the patch and pushes it to a factory branch. The agent never holds a GitHub token.
- **Reviewer** judges the pushed commit in a fresh checkout against every acceptance criterion, with evidence for each verdict. At most two revisions. The draft pull request opens only when the branch, the pushed commit and the reviewed commit are the same.
- **Factory brain.** Durable facts about your repository in `knowledge/factory-brain/`, which every station reads and only reviewed hub changes update.

Every request is one work item. A restart resumes it from its last saved step, and nothing runs or posts twice. Every run ends in an answer, a plan, a reviewed draft or a stated stop reason with the next step. [Architecture](docs/architecture.md)

## Quick start

You need Python 3.12, Git, a running Docker engine, and Claude Code or Codex signed in on this machine. No API key. For the first run you also need a scratch GitHub repository you own.

Paste this into Claude Code or Codex from the cloned folder:

```text
Set up the Software Factory hub from this folder for my scratch repository
OWNER/REPO. Read SETUP.md and follow it. Show me the settings, the GitHub
permissions and the setup command before running anything against the
repository. Connect GitHub with a token I type myself, run doctor, then show me
a plan-only request. After I approve a plan, implement it as a draft pull
request. Do not merge anything.
```

Or by hand:

```bash
git clone https://github.com/hubzoid/software-factory-hub software-factory
cd software-factory
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Keep the folder name `software-factory`: it is the hub's name, and the channel files use it. `.env` uses Claude Code (`MODEL=claude-local`). For Codex, set `MODEL=codex-local`.

Point the factory at your scratch repository and connect GitHub ([SETUP.md](SETUP.md), steps 2 and 3). The labelled sample in [`fixtures/`](fixtures/) seeds it with a planted rounding bug and a failing regression test. Then check and start:

```bash
hubzoid hub doctor .
hubzoid run . --port 8701 --bridge-port 8702
```

In the web chat at **http://127.0.0.1:8701**, ask:

> Plan a fix for issue #1. Stop after the plan.

You get a plan with acceptance criteria, built from a real checkout. Then ask *"Implement the fix for issue #1. Show me the plan first."*, approve the exact plan in your **Inbox**, and you get a reviewed draft pull request with the reviewer's result for each acceptance criterion.

<!-- Screenshot: the Inbox plan approval card, or the draft pull request with the reviewer's per-criterion verdicts. -->

The [builder skill](skills/setup-software-factory/SKILL.md) holds the same steps for your coding assistant. [Full setup](SETUP.md)

## Integrations

| Works with | What the factory does |
|---|---|
| GitHub | Label an issue `factory` and it runs on its own, posting progress on the issue. Mention it (`@your-app plan this`) to ask, triage, plan or implement. It repairs failing CI on its own branches, at most twice, and posts one orientation comment on each new pull request. |
| Linear | Assign it a task. The plan comes back for you to approve in your Hubzoid **Inbox**. |
| The web chat and Slack | Ask for work or its status. Plans wait for your approval in the **Inbox**. |
| Claude Code, ChatGPT and Codex, over MCP | The same requests from your own assistant, with the plan waiting for your approval. |
| Another tracker | Ask in chat, and the factory pulls the issue in through that tracker's MCP server. |

Label and mention intake need a GitHub App. Chat and MCP intake can start with a token you type yourself. [Channels](docs/channels.md) · [SETUP.md](SETUP.md), step 3

## Make it yours

The files you will edit, and what each one changes:

```text
software-factory/
├── AGENTS.md                        the chat agent: answers questions, hands work to the factory
├── agents/
│   ├── classifier/AGENTS.md         how requests are triaged
│   ├── analyst/AGENTS.md            how plans are written
│   ├── implementer/AGENTS.md        how the sandbox build runs
│   └── reviewer/AGENTS.md           how the review judges a commit. Set engine: codex-local for a cross-vendor review
├── knowledge/factory-brain/         durable facts about each repository, one file per owner-repo
├── hub.settings.yaml                FACTORY_REPO, channels, whether plans need approval
├── sandboxes/factory.yaml           the Docker sandbox and its reviewed setup command
└── channels/                        the GitHub, Linear and Slack connections
```

Each station is one page of instructions. Edit it in your checkout and review the change like any commit.

To point it at your own repository, set `FACTORY_REPO` in `hub.settings.yaml` and replace the install in `sandboxes/factory.yaml` with your repository's locked install, such as `npm ci` or `uv sync --frozen`. Then bootstrap a source-linked brief from committed files you choose:

```bash
python scripts/factory_setup.py context --checkout PATH --repository OWNER/REPO --source FILE --test-command 'CMD'
```

Review the preview, then store it as a pending hub change for a hub manager to apply. Start with plan-only requests, and move to implementation once the plans read right. [SETUP.md](SETUP.md), steps 2 and 4

To save a team rule from chat, tell the factory *"Remember for the team: run the tests with `pnpm test --runInBand`."* It proposes the exact edit to `knowledge/factory-brain/<owner>-<repo>.md`, a hub manager applies it, and every station sees it on the next run. A correction in chat is not shared until that edit is applied. [Settings](docs/settings.md)

## Safety

- **No merge, no push to a protected branch, no repository administration.** A person marks a draft ready and merges in GitHub. Writes go only to `FACTORY_REPO`, and unattended work writes only on the issue or pull request it came from.
- **The person who asked decides.** Attended implementation waits for the requester to approve the exact plan. An administrator cannot approve for them.
- **Inputs are data, never instructions.** Issue text, comments, repository files and web pages are read as data. Hidden HTML comments and invisible characters are removed before a model reads them.

An implement request is about five agent turns plus small routing calls, more with research or revisions. Budgets are opt-in in Hubzoid. [Security details](docs/security.md)

## Host it for your team

The factory runs on a server the same way any Hubzoid hub does: one image built from this repository, one durable folder at `/data`, sign-in on, and one public address. Three things are specific to the factory:

- **A Docker engine the hub can reach**, for the sandbox.
- **`HUBZOID_SCHEDULES=1`**, so work items run in the background. It is set in `.env.example`.
- **`HUBZOID_PUBLIC_URL`**, your hub's HTTPS address, which the GitHub App webhook posts to.

Grant teammates access to the hub and to `wf_factory`. Linked GitHub, Slack and Linear identities get no rights from text in a ticket. [Operations](docs/operations.md) covers pause, recovery, backup and upgrade. [Hubzoid deployment](https://github.com/hubzoid/hubzoid/blob/main/docs/deploy/README.md) lists the hosting options and which are verified.

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

Questions go to [GitHub Discussions](https://github.com/hubzoid/hubzoid/discussions). Bugs in the factory go to [this repository's issues](https://github.com/hubzoid/software-factory-hub/issues).

The Software Factory is **Apache-2.0**. Built on [Hubzoid](https://github.com/hubzoid/hubzoid). Need it running for your team? [Build with us](https://hubzoid.com/build-with-us).
