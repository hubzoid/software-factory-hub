# Operations: running, backup, restore, upgrades and costs

## Running

- Laptop: `hubzoid run . --port 8701 --bridge-port 8702` with `HUBZOID_SCHEDULES=1` in `.env`. Without it, work items never run.
- Hosted: follow Hubzoid's Railway or Maritime guide (SDK `docs/deploy/`), with a GitHub App (not a personal token), `HUBZOID_PUBLIC_URL` set for webhooks, and a separate sandbox service when the host has no Docker. Record the exact supported runtime authentication for the qualified host row. A local login alone does not establish hosted/shared operation; see docs/qualification.md.
- Pause new work with `FACTORY_INTAKE_ENABLED: false` (Setup in the Console, or `hub.settings.yaml`). Like every hub setting it applies when the hub restarts. Waiting decisions, recovery and cancellation continue. To stop GitHub events at once without a restart, pause the channel: Channels in the Console, or `hubzoid channels pause . github --expected-revision N`.

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

1. Pause new intake. List both running and waiting work (`hubzoid work-items list . --workflow factory --json`), then inspect each waiting item with `hubzoid work-items show . ITEM --json`.
2. **Before upgrading from an older Factory**, inspect waiting/approved `github.updatePullRequest` operations. If their arguments contain any `draft` field (especially `draft: false` from an old mark-ready request), the requester rejects the operation through the native decision surface, or an authorized manager cancels the entire item with `hubzoid work-items cancel . ITEM`. Recheck that it is cancelled/rejected and will not resume. Do not approve, restart or redrive those legacy mark-ready operations on either version. A person changes draft status in GitHub instead. If a write is ambiguous, reconcile its actual GitHub state before proceeding.
3. Drain or explicitly resolve other running/waiting work. Pull the new hub version, run `hubzoid hub configure . --check` and `hubzoid hub doctor .`.
4. Restart and resume intake only after checking the new revision and operation backlog. The upgrade is not a migration of old approvals into the new policy.

Work belongs to the code that started it. Work interrupted or waiting across a code change stops as `needs_input` (`definition_changed`) instead of continuing on new code. Check what changed, then `hubzoid work-items restart . ITEM --reason "..."` continues after the last saved stage. A station call pins its definition: a changed station file makes a new call, never a different old one. Uncertain operations must be decided first. Nothing migrates on its own, approved plans are never rebased, and uncertain writes are never re-run.

## Upgrading Hubzoid

Pin the Hubzoid version you tested. On each Hubzoid release, run the test suite and the evals against it before upgrading (`.github/workflows/ci.yml` uses the immutable requirements-sdk.txt pin).

## Costs

- Model use: one agent turn per station call on your installed Claude Code or Codex login, plus short routing calls (scope, labels, research need, brain note). A plain implement request is about five agent turns, each revision adds two (implementer and reviewer).
- Reuse supported runtime authentication; no silent paid API fallback or second vendor requirement. Budgets and limits are opt-in (Hubzoid `budgets.yaml`).
- Sandboxes: Docker containers with 2 CPUs and 2 GiB each by default (`sandboxes/factory.yaml`), at most four at once (`sandbox.yaml`).

## Read-only source and rollback

The SDK refuses in-place Hub proposals/activation on read-only source mounts. Prepare and review the source diff in the builder checkout, then redeploy that reviewed revision. Do not add a second mutable knowledge store. Keep source revision, SDK commit, databases, artifacts and external-operation receipts together in backup records. After restore, reconcile GitHub branch/PR state and uncertain operations before new writes. Restoring local data cannot undo a published branch or PR.

Pause intake before an upgrade; keep old records readable, and resume only with a compatible source/SDK revision. A changed approved rule returns `context_changed` instead of silently continuing. New configuration fields remain optional for existing Hubs; these helpers do not require a new Git layout.

Revisions preserve a human's existing PR draft/ready status; the factory never toggles it. `review_ready` on revision work describes the factory's exact-commit review result, not a claim that a previously readied PR became a draft again. Inspect the linked GitHub PR for its current lifecycle state.
