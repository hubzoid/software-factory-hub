# Settings reference

Settings are declared in `settings.yaml` and set in `hub.settings.yaml`. Check with `hubzoid hub configure . --check`, apply with `hubzoid hub configure . --apply --expected-revision <n>`, and see effective values with `hubzoid hub settings .`. The same settings are in the Console under Agents, the agent, Setup, and in the API at `/api/hubs/{hub_id}/settings`. A change applies after the hub restarts. Work in progress keeps the definition it started with.

| Setting | Type and default | What it does |
|---|---|---|
| `FACTORY_REPO` | string, required | The repository, in one of two forms. `owner/name`: a GitHub repository, which must be one of the GitHub connection's repositories. A folder path starting with `/` or `~/`: local repository mode, with no GitHub. The folder must be the top folder of a Git repository outside the hub, with at least one commit on a branch; its current branch is the base, and each result is a reviewed branch in that folder (plans and changes only, no issues or pull requests). The factory never switches repositories on its own. |
| `FACTORY_LABEL` | string, `factory` | The issue label that hands an issue to the factory. With verified webhook delivery, adding it starts unattended work ending in a reviewed draft. Laptop PAT mode uses manual intake until forwarding is configured. Keep it equal to `rules.label` in `channels/github.yaml`. |
| `FACTORY_BRANCH_PREFIX` | string, `factory/` | Prefix of every branch the factory creates (`factory/12-bug-fix-total-1a2b3c`). A prefix is never proof of ownership: CI repairs need the factory's own record of the push. |
| `FACTORY_BOT_NAME` | string, empty | The name people mention on GitHub. Empty uses the GitHub App's own name. Token mode needs it. |
| `FACTORY_GITHUB_CONNECTION` | string, `github` | The GitHub channel connection id (`channels/<id>.yaml`). |
| `FACTORY_LINEAR_CONNECTION` | string, empty | The Linear connection id, needed when `linear` is in `FACTORY_CHANNELS`. |
| `FACTORY_SLACK_CONNECTION` | string, empty | The Slack connection id, needed when `slack` is in `FACTORY_CHANNELS`. |
| `FACTORY_CHANNELS` | list, `[chat, mcp, github]` | Where people may ask: any of `chat`, `mcp`, `github`, `linear`, `slack`. Each enabled channel must pass doctor. Other trackers are not built in: a chat request can pull an issue in through that tracker's MCP server. |
| `FACTORY_INTAKE_ENABLED` | boolean, `true` | False stops new work after the hub restarts. Waiting decisions, recovery and cancellation keep working. To stop GitHub events at once, pause the channel instead. |
| `FACTORY_REQUIRE_PLAN_APPROVAL` | boolean, `true` | Attended implementation waits for the requester to approve the exact plan. Unattended label work never waits on a person. |
| `FACTORY_REVIEW_CYCLES` | integer 0 to 2, `2` | Revisions allowed after the reviewer requests changes. At the cap the work stops as `review_unresolved` with the pushed branch left for a person. |
| `FACTORY_CI_ATTEMPTS` | integer 0 to 2, `2` | CI repair attempts per factory branch, counted once per failing head and kept across restarts. |
| `FACTORY_BUILDS` | `auto`, `docker` or `local`, `auto` | Where the analyst, implementer and reviewer work. `auto` uses Docker when it is running, else builds locally. `docker` always uses Docker. `local` always builds locally, without Docker (macOS for now): a clone in a work folder in the system's temporary folder, with every command confined by macOS's sandbox to that folder, offline, with a clean environment and no access to your home folder. On Linux and Windows, use Docker. Each work item decides once and keeps its choice. |
| `FACTORY_SANDBOX_PROFILE` | string, `factory` | The Docker sandbox profile (`sandboxes/<id>.yaml`) for the analyst, implementer and reviewer. Its reviewed `setup.command` installs the repository's dependencies before the agent starts. The agent then works offline. |
| `FACTORY_LOCAL_SETUP` | string, empty | For local builds: the command that installs the repository's dependencies in each new work folder, before the agent starts. It runs in the repository folder, reaches only the package registries in the Docker profile's setup allowlist (`sandboxes/factory.yaml`), and may write only the work folder. Put Python dependencies in `"$FACTORY_ENV"`, a virtual environment outside the repository that is first on `PATH` afterwards. The sample uses `python3 -m venv "$FACTORY_ENV" && "$FACTORY_ENV/bin/python" -m pip install --quiet -r requirements-dev.txt`. |

## Not settings, on purpose

These are fixed policy, not options: no merge tool, no push to the default or a protected branch, no unattended waiting on a person, one writer per branch (a second change started on a branch while another is running stops without pushing, because every push is leased to the head the factory last pushed), replies only on the work's own thread, decisions only by the person who asked, a draft pull request bound to the reviewed commit, the factory brain at most 40,000 characters, handoffs at most 200,000 characters, titles at most 200.

## Where other choices live

- **Engines and models** are per station, in `agents/<station>/AGENTS.md` (`engine:` and `model:`). By default every station uses the hub's runtime (`MODEL` in `.env`, `claude-local` or `codex-local`) and the reviewer shares the implementer's vendor. To make the review cross-vendor, set `engine: codex-local` in `agents/reviewer/AGENTS.md`.
- **The setup command** lives in the sandbox profile, `sandboxes/factory.yaml`, which is the reviewed file Hubzoid binds before any sandbox starts. For local builds it is `FACTORY_LOCAL_SETUP`. A model can never change either.
- **Pull request updates** are the write mode `github.pr_update: approve` in `work-items.yaml`.
- **Who may ask** is Hubzoid access: the `wf_factory` workflow grant (or Run and control workflows), the `channel_<connection>` grant for each channel (for example `channel_github`), and account links for Slack, Linear and GitHub mentions.

## File settings, identity state and extensions

Instructions, station/model choices, curated rules, tool policies, role bundles, connector definitions and supported appearance files are source configuration. Account identity, account links, individual grants, approvals and secret values remain in the SDK store. Console/CLI/API changes use the SDK's existing revision/operation mechanisms, never an independent writable copy. The setup helper neither creates grants nor activates shared knowledge. Local authoring trusts the machine owner; non-delegable setup credentials are deferred SDK hardening.

Use the existing web app's supported branding/theme/layout settings. New arbitrary layouts, harnesses, authorization semantics or connectors require engineering; no hub setting pretends to implement them. Claude-only and Codex-only stations use identical domain tool contracts; a cross-vendor reviewer is optional. Raw MCP clients receive domain results/evidence, while their own prompts stay under their control.

A curated-context revision is recorded with work and evidence. If approved root rules or the repository brief changes while a plan waits or runs, the factory conservatively stops with `context_changed`; request a fresh plan. It does not infer semantic equivalence of instructions or reuse old approval. Existing SDK operation/grant checks still apply at dispatch.
