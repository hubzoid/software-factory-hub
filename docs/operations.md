# Operations: running, backup, restore, upgrades and costs

## Running

- Laptop: `hubzoid run . --port 8701 --bridge-port 8702` with `HUBZOID_SCHEDULES=1` in `.env`. Without it, work items never run.
- Hosted: follow Hubzoid's Railway or Maritime guide (SDK `docs/deploy/`), with a GitHub App (not a personal token), `HUBZOID_PUBLIC_URL` set for webhooks, and a separate sandbox service when the host has no Docker. A Claude subscription token or a Codex login works for unattended runs.
- Pause new work with `FACTORY_INTAKE_ENABLED: false` (waiting decisions and recovery continue), or pause one channel with `hubzoid channels pause . github --expected-revision N`.

## Watching

| Where | What |
|---|---|
| Console, Work items | State, saved stages, station calls and their attempts, operations, exact content waiting for approval, cancel and restart |
| Waiting for you | Plans and questions for the person who asked |
| `hubzoid work-items list . --workflow factory` | The same from a terminal, `--json` for scripts |
| `hubzoid stations calls list . --work-item ITEM` | Each station call, its definition digest and result |
| `hubzoid sandbox list .` | Live sandboxes, never their files |
| The issue or pull request | Progress notes and the wrap-up |

## Backup and restore

`hubzoid backup` copies the operational database (work items, operations, station calls, handoffs, the factory's records), the workflow database and the hub folder together, holding new runs while it copies. Restore both together (SDK `docs/BACKUP.md`). Restored delivery and operation keys still deduplicate, so a restored hub never re-sends a recorded write. Branches and pull requests live on GitHub and are not part of the backup.

## Upgrading the hub

1. Wait until no factory work is running or waiting (`hubzoid work-items list . --workflow factory --state running`), or let it finish.
2. Pull the new hub version, run `hubzoid hub configure . --check` and `hubzoid hub doctor .`.
3. Restart.

Work belongs to the code that started it. Work interrupted or waiting across a code change stops as `needs_input` (`definition_changed`) instead of continuing on new code. Check what changed, then `hubzoid work-items restart . ITEM --reason "..."` continues after the last saved stage. A station call pins its definition: a changed station file makes a new call, never a different old one. Uncertain operations must be decided first. Nothing migrates on its own, approved plans are never rebased, and uncertain writes are never re-run.

## Upgrading Hubzoid

Pin the Hubzoid version you tested. On each Hubzoid release, run the test suite and the evals against it before upgrading (`.github/workflows/ci.yml` does this on the SDK branch the hub is built on).

## Costs

- Model use: one agent turn per station call on your installed Claude Code or Codex login, plus short routing calls (scope, labels, research need, brain note). A plain implement request is about five agent turns, each revision adds two (implementer and reviewer).
- No API key or second vendor by default. Budgets and limits are opt-in (Hubzoid `budgets.yaml`).
- Sandboxes: Docker containers with 2 CPUs and 2 GiB each by default (`sandboxes/factory.yaml`), at most four at once (`sandbox.yaml`).
