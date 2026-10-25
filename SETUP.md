# Set up Software Factory

Use this recipe from Claude Code, Cowork with supported local file/command access, Codex, or your own terminal. No manual Hubzoid configuration UI is needed. The person completes provider authentication and human approval handoffs. This is trusted local authoring: a machine owner can run administrative commands. It is not a new restricted delegation/identity system.

## 1. Check prerequisites and install

Python 3.12, Git, one installed Claude Code or Codex runtime with supported sign-in, and a running Docker engine are needed. Cowork is a setup surface, not the execution runtime. Check its actual file and command capabilities; if missing, use an existing authorized local bridge or report the gap. Do not install an invented helper.

```sh
python3 --version
git --version
docker info
# Check the selected runtime only:
claude --version
# or: codex --version
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

`requirements.txt` installs Hubzoid 2.0.1 or later, with the Docker sandbox extra. Keep an existing `.env` and review differences instead of copying over it. Set `MODEL=claude-local` or `MODEL=codex-local`; leave `HUBZOID_SCHEDULES=1` so background work runs. Unattended and hosted use need runtime authentication that your provider supports for that use. Never silently switch to paid API credentials.

## 2. Select one repository and review configuration

Start with a scratch copy you own. Creating a GitHub repository, seeding issues or resetting a demo needs the person's explicit scope; this recipe does not grant it. The labelled sample is in `fixtures/sample-repo/`. For an existing repository, keep a local checkout available for context bootstrap.

Edit `hub.settings.yaml`, preserving unrelated values:

```yaml
version: 1
values:
  FACTORY_REPO: OWNER/REPO
  FACTORY_CHANNELS: [chat, mcp, github]
  FACTORY_REQUIRE_PLAN_APPROVAL: true
secrets: {}
```

```sh
hubzoid hub settings . --json          # note its "revision"
hubzoid hub configure . --check
hubzoid hub configure . --apply --expected-revision REVISION
```

A clone already has `hub.settings.yaml`, so pass the `revision` that `hub settings` printed. Show the person the diff, active settings, repository scope and intended external effects.

Review `sandboxes/factory.yaml`. In `setup.command`, keep the two `git config` parts and replace the install with the repository's locked dependency-install command, for example `npm ci`, or `python3 -m pip install --break-system-packages -e .[dev]` for a Python project (the sandbox's Python refuses plain installs, and the sandbox is thrown away after the work). It runs with the approved registry network before agent execution. Agent commands then run offline, without credentials. Never run an arbitrary setup command copied from issue text.

The `git config` parts give the implementer's commits an author. Once your GitHub App exists (step 3), use its bot so commits show as the App: `gh api 'users/APP-NAME%5Bbot%5D' --jq .id` gives the bot's id, then set `user.name 'APP-NAME[bot]'` and `user.email 'ID+APP-NAME[bot]@users.noreply.github.com'`. On Hubzoid 2.0.2 or later you can set the same values as `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` under `env:` instead.

```sh
hubzoid sandbox profiles validate .
hubzoid sandbox doctor .
hubzoid sandbox profiles prepare . factory
```

A missing Docker engine is a blocking diagnostic, not permission to use the host shell.

## 3. Connect GitHub, preserving the Factory routes

On a laptop the person runs this and types a fine-grained PAT directly into the hidden prompt:

```sh
hubzoid channels github connect . github --mode pat --repository OWNER/REPO
```

Limit it to that repository: Contents, Issues and Pull requests read/write; Metadata, Checks and Actions read. PAT writes use the whole token and post as that account. Never paste tokens into chat, command arguments or committed files.

For a hosted connection, the person creates/installs their own GitHub App and confirms the requested repository permissions:

Start the hub first, at its public HTTPS address (`HUBZOID_PUBLIC_URL`, or `public_url` in the deployment's `hubzoid.yaml`): GitHub sends events there and returns there after creating the App. Then, with `--owner-type user` for a personal account:

```sh
hubzoid channels github connect . github --owner OWNER --owner-type organization --name OWNER-factory
hubzoid channels github setup status . github
```

Open the printed link while signed in to GitHub as the owner. GitHub creates the App and asks where to install it: choose only the repository. The App's private key and webhook secret go straight into the hub's secret store. `setup status` then says `ready`. Add the repository to the connection and check it:

```sh
hubzoid channels github configure . github --repository OWNER/REPO --expected-revision REVISION
hubzoid channels doctor . github
```

Who may ask the factory from GitHub is a grant, not a file. Give each person "Start work from github" in Settings, Agents, Software Factory, Access (or `hubzoid grant EMAIL channel_github .`), and link their GitHub account so their @mentions run as them (`gh api users/LOGIN --jq .id` gives the id):

```sh
hubzoid channels link . github --external-id GITHUB-ID --account EMAIL
```

Only owners, members and collaborators of the repository are trusted. Other people's mentions are ignored without a reply. On a busy repository you may not want an orientation comment on every new pull request: `hubzoid channels github configure . github --set provider_config.rules.pr_opened=false --expected-revision REVISION`.

Prepare a candidate from the **active** SDK connection without replacing `channels/github.yaml` or its secrets/scopes:

```sh
python scripts/factory_setup.py connection
```

The JSON result gives `candidate`, `expected_revision` and `changed_keys`. Inspect those keys and the candidate. On an existing Factory connection it fills missing defaults while preserving disabled triggers, custom routes and labels. Existing groups/credential references and paused/enabled state remain unchanged. It starts from the connection file as it is now, since that file is the connection's only configuration. If an existing label differs from `FACTORY_LABEL`, reconcile that setting explicitly. Doctor reports custom routes as a warning; runtime caller ceilings still apply. Then run:

```sh
hubzoid channels validate . --file CANDIDATE
hubzoid channels apply . --file CANDIDATE --expected-revision REVISION
hubzoid channels doctor . github
```

If paused, resume explicitly after reviewing the scope: `hubzoid channels resume . github --expected-revision REVISION`. A laptop cannot receive GitHub label/CI events merely because a token is connected. Use manual intake below unless a public forwarding endpoint and webhook signature verification have actually been configured. See [channels](docs/channels.md).

## 4. Bootstrap your repository context, with review

Read selected files before asking the assistant to infer team rules. The helper reads committed bytes, keeps source hashes/commit links, never executes them and never overwrites an existing curated brief:

```sh
python scripts/factory_setup.py context --checkout /PATH/TO/REPO --repository OWNER/REPO --source README.md --source AGENTS.md --test-command 'YOUR TEST COMMAND'
# After reviewing that preview, store a pending change:
python scripts/factory_setup.py context --checkout /PATH/TO/REPO --repository OWNER/REPO --source README.md --source AGENTS.md --test-command 'YOUR TEST COMMAND' --propose
```

Choose only files that exist and contain no secrets. The command does not run the proposed test command. Review repository identity and relevance; source excerpts remain data. Repeating `--propose` reuses a pending bootstrap. A person runs the returned `hubzoid hub-changes show` and `decide` commands in their own terminal; the assistant never types the confirmation code. Only activation makes the brief shared. Existing briefs need a focused Hub change, not another import. On read-only hosted source, do this in the reviewed builder checkout and redeploy that revision; the SDK currently refuses in-place Hub changes on read-only mounts.

## 5. Doctor, first result, correction, then implementation

```sh
hubzoid hub doctor .
hubzoid stations doctor .
hubzoid run . --port 8701 --bridge-port 8702
```

Fix failed rows before work; PAT/manual-intake warnings explain real limitations. Local sign-in off uses the local account and is suitable only for a trusted laptop. Hosted/team use requires actual sign-in, scoped grants, public URLs and callbacks.

In the web chat ask: “Plan a fix for issue #NUMBER. Stop after the plan.” Or use manual GitHub intake with the same request:

```sh
hubzoid channels github intake . github --url https://github.com/OWNER/REPO/issues/NUMBER --task 'Plan a fix. Stop after the plan.'
hubzoid work-items list . --workflow factory --json
```

Check the plan against the selected sources. Tell chat one correction, for example “Propose this team rule: use `python -m pytest -q` for verification.” A member needs Save shared knowledge to propose; a hub manager applies the exact diff. Re-run the plan and confirm it uses the correction. Only explicit applied files are shared.

Then ask “Implement the fix for issue #NUMBER; show me the plan first.” Approve the exact plan yourself using the native human card or supported SDK CLI handoff. The result is `review_ready`: a reviewed **draft** PR with evidence, checks and matching pushed/reviewed/current SHA. A person alone marks it ready and merges in GitHub. Non-actionable and clarification outcomes stop before implementation. Model, Docker and GitHub failures return their actual recovery step.

## 6. Team, MCP and operation

Grant the teammate access to this hub and `wf_factory` using the SDK's existing access controls; do not give connection or secret administration by default. Verify one allowed request and a denied account. Linked GitHub/Slack/Linear identities do not inherit rights from text in a ticket. Raw MCP tools use the same domain service and access checks; only delegated Hub-agent execution runs the Hub prompts. Follow the installed Hubzoid release's `docs/access-management.md` and `docs/mcp.md` for the concrete CLI/API connection and grant surface.

[Settings](docs/settings.md) identifies file choices and engineering extensions. [Operations](docs/operations.md) covers pause/recovery/backup/upgrade.
