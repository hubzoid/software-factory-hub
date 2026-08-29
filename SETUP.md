# Setting up the Software Factory

Written for a person and for Claude Code or Codex doing it for them. Every step is a file or a command. Stop and show the person each thing marked **Show**. Never print, paste or type a credential: the person types tokens themselves.

## 0. What you need

- Python 3.12 and Git.
- A Docker engine (Docker Desktop, Colima or OrbStack) for the sandboxes. Check with `docker info`.
- Claude Code or Codex installed and signed in. The factory runs on that login: no API key.
- A GitHub repository you may experiment on. Start with a private scratch copy of the synthetic sample (step 2).

## 1. Install

```sh
git clone https://github.com/hubzoid/software-factory-hub factory
cd factory
python -m venv .venv && . .venv/bin/activate
# Until the Hubzoid release that carries push_branch, install the SDK branch it was built on:
pip install "hubzoid[sandbox] @ git+https://github.com/hubzoid/hubzoid@rh/software-factory-github-push"
cp .env.example .env          # MODEL=claude-local (or codex-local), HUBZOID_SCHEDULES=1, ports
```

## 2. A scratch repository

To try it on the synthetic sample (planted rounding bug, one failing regression test, three issues):

```sh
cp -R fixtures/sample-repo ../factory-sample && cd ../factory-sample
git init -b main && git add -A && git commit -m "Synthetic sample"
gh repo create OWNER/factory-sample --private --source . --push
cd ../factory
python demo/seed_issues.py OWNER/factory-sample     # labels and the three sample issues
```

## 3. Settings

Edit `hub.settings.yaml`:

```yaml
version: 1
values:
  FACTORY_REPO: OWNER/factory-sample
  FACTORY_CHANNELS: [chat, mcp, github]
secrets: {}
```

```sh
hubzoid hub configure . --check
hubzoid hub configure . --apply --expected-revision absent
```

**Show** the person the settings (`hubzoid hub settings .`) and what each does ([docs/settings.md](docs/settings.md)).

## 4. The sandbox and its setup command

`sandboxes/factory.yaml` holds the one command that installs the repository's dependencies before any agent starts, with only package registries reachable. For the sample it is `python3 -m pip install ... -r requirements-dev.txt`. For your repository use its own, for example `npm ci` or `uv sync --frozen`.

**Show** the person the setup command before it runs against their repository.

```sh
hubzoid sandbox doctor .
hubzoid sandbox profiles validate .
hubzoid sandbox profiles prepare . factory
hubzoid sandbox try . --profile factory -- python3 -V
```

## 5. Connect GitHub

On a laptop, with a token the person types (hidden):

```sh
hubzoid channels github connect . github --mode pat --repository OWNER/factory-sample
```

The token should be fine-grained, limited to that repository, with read and write on Contents, Issues and Pull requests, and read on Metadata, Checks and Actions. Token mode pushes with that token and replies as that person, so keep it narrow.

For a hosted hub, use a GitHub App the person owns, created through GitHub's manifest flow (the App's key goes straight to Hubzoid's secret store):

```sh
hubzoid channels github connect . github --owner OWNER --owner-type organization --name OWNER-factory --open
hubzoid channels github setup status . github
```

**Show** the person the permissions page. Then point the connection at the factory and its routes, and turn it on:

```sh
hubzoid channels export . github > channels/github.yaml
# keep provider_config as the connect step wrote it; set workflow: factory and the rules block
# from this repository's channels/github.yaml (label, mentions, pr_opened, ci_failure, routes)
hubzoid channels apply . --file channels/github.yaml --expected-revision <revision>
hubzoid channels doctor . github
```

## 6. Doctor

```sh
hubzoid hub doctor .
hubzoid stations doctor .
```

Every row says what is wrong and the exact next step. Fix them all before the first request.

## 7. Run it

```sh
hubzoid run . --port 8701 --bridge-port 8702
```

Open http://127.0.0.1:8701. Sign-in is off on a laptop, so you act as the local account. The Console is under Settings: Work items, Waiting for you, Setup.

## 8. The first useful result

In the chat: "Plan a fix for issue #1. Stop after the plan." You get the classification, the plan and its acceptance criteria, with nothing changed.

Then label issue #1 `factory` on GitHub. The factory posts progress on the issue and ends with a reviewed draft pull request that fixes the rounding and makes the regression test pass. Review it, mark it ready yourself, merge it.

To reset the sample and run it again: `demo/reset.sh OWNER/factory-sample` (it touches only that repository's factory branches, pull requests and sample issues).

## 9. Evals

```sh
hubzoid eval list .
hubzoid eval run . --tag safety --junit output/evals/safety.xml
```

The pipeline's behaviour (routes, plan approval, review loop, CI repair, the ship gate) is covered by the test suite: `python -m pytest -q tests`. See [docs/evals.md](docs/evals.md).
