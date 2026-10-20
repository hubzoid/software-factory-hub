# Live-run stand-ins (proof and demo only)

`factory_live.py` and `sitecustomize.py` let the Software Factory run end to end in a real browser on a machine with no container runtime and no GitHub account. They are test assets, never part of the hub.

- `FACTORY_LIVE_SANDBOX=standin`: the analyst, implementer and reviewer return scripted results, labelled as stand-ins in everything they produce. The "implementer" commits the fixture's known fix in a host clone made by test code: no model and no agent command runs on the host. Doctor reports the stand-in as a labelled warning. The classifier and researcher, the chat agent, routing, approvals, the Console and the push stay real.
- `FACTORY_LIVE_GITHUB=fake`: a file-backed GitHub stand-in (issues, comments, labels, pull requests, check runs, repository reads) and a local bare repository that the factory really pushes to.

## Run it

You need the SDK revision pinned in `requirements-sdk.txt` (on `PYTHONPATH` or installed), a Claude Code or Codex login, and a copy of a Hubzoid test hub whose `.env` sets `MODEL=claude-local`.

```sh
cp -R HubzoidTestHub/test-hub ready-hubs/software-factory-local
tests/live/setup.sh ready-hubs/software-factory-local /tmp/factory-local
. /tmp/factory-local/env.sh
cd ready-hubs/software-factory-local && hubzoid run . --port 8701 --bridge-port 8702
```

Open http://127.0.0.1:8701 once, then link the stand-in GitHub account (setup.sh prints the exact command), and drive it:

```sh
python tests/live/deliver.py --hub-id software-factory-local --state /tmp/factory-local label 1    # unattended label run to a draft PR
python tests/live/deliver.py --hub-id software-factory-local --state /tmp/factory-local ci 105     # a red check on that PR
```

Chat ("Please fix issue #2"), Waiting for you, Work items and Setup work as on any hub. A real run needs a container runtime (Docker today, hosted sandboxes later), a GitHub App or token, and none of this.
