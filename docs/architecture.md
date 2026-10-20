# Architecture

The factory is a Hubzoid hub: Markdown agents and skills, one durable work-item workflow, and a small amount of Python for the parts that must be deterministic. It adds no SDK module, route or database table of its own.

## Pieces

| Piece | Where | Built on |
|---|---|---|
| Chat agent | `AGENTS.md`, `tools_local/factory.py` | Hubzoid chat, MCP, the GitHub read tools |
| Five stations | `agents/<station>/` | SDK stations: isolated agent, exact tools, closed schema, one retry, one crash recovery |
| Pipeline | `workflows/factory/software_factory/pipeline.py` | SDK work items: saved stages, route ceilings, follow-up inbox, recorded operations |
| Routes and policy | `routes.py`, `policy.py` | Data, tested directly |
| Publishing | `publish.py`, `scan.py` | SDK sandbox export plus the SDK GitHub channel's `push_branch` |
| CI repair | `ci.py` | The factory's ledger plus the SDK's record of each push |
| Plans and approvals | `pipeline.py` | SDK plan review (`hub.review_plan`), questions (`hub.ask`), approve-mode operations |
| Evidence | `evidence.py` | Hub output folder, handoffs, artifacts |
| Brain | `brain.py`, `knowledge/factory-brain/` | SDK hub changes (reviewed, versioned, one git commit each) |

## One work item

```
scope        tool-less model call on the requester's own words, then narrow the route
ground       read the issue or pull request, comments, labels, candidate duplicates, the brain (saved)
classify     classifier station (text only)
label        the fewest labels from the repository's own vocabulary
research     researcher station, only when the item turns on an outside fact
analyze      analyst station in a sandbox checkout of the default branch
plan_review  attended work waits for the requester to approve the exact plan
implement    implementer station in a sandbox checkout, commits only, offline
publish      scan the exported patch, check branch ownership, push through the SDK (saved)
review       reviewer station in a fresh checkout of the pushed commit
deliver      check branch head = pushed = reviewed, open the draft, evidence, wrap-up
```

Revisions loop implement, publish and review with a new station revision each time. A stop at any point posts the reason and what remains.

The terminal outcome is `review_ready`, which remains a draft. Draft status and merge are human-only. Each run records its approved context digest; a changed root rule or repository brief blocks subsequent implementation/publication until a fresh plan.

## Trust boundary

- Stations never hold a GitHub credential. Their sandboxes are offline after the reviewed setup command.
- The SDK clones repositories on the host with the host's Git access and copies them in without it.
- `publish_branch` is workflow code. It reads the patch the SDK exported, binds the push to its SHA-256, checks it, and calls the SDK's `push_branch`, which mints a one-repository `contents: write` token for that push only.
- GitHub writes are SDK operations: recorded before they are sent, never repeated on their own, refused outside a work item.
- Every write also passes the factory's caller matrix and is limited to `FACTORY_REPO`.

## Durability

All GitHub reads happen inside saved stages, model calls are saved steps, writes are recorded operations, and the factory's own records (progress, the branch ledger) are written idempotently. A restart, redrive or continuation replays the same path: no station runs twice, nothing is pushed or posted twice. An interrupted push is settled by reading the branch, because the commit id is deterministic.

## State

| State | Where |
|---|---|
| Work items, stages, operations, station calls, handoffs | Hubzoid's operational database |
| Progress record per work item | `hub.shared_state` key `factory_v1:item:<id>` |
| Branch ledger (owner, last pushed commit, pull request, CI attempts) | `hub.shared_state` key `factory_v1:branch:<repo id>:<branch>` |
| Plans and evidence | `output/factory/<work item>/` and published artifacts |
| Factory brain | `knowledge/factory-brain/*.md` in the hub's git history |
| The factory's result | the work item's result, under `factory_v1` |

## Reference decisions

The upstream template remains primary: `agent/instructions.ts`, `agent/subagents/*` and `agent/lib/github/approval.ts` in the attributed Vercel Software Factory source. Keep its station order, fresh reviewer, bounded revisions, selected research, task-origin writes and narrow curated brain. The approved human-only ready transition deliberately narrows the upstream template's brokered ready operation. LangChain open-swe's source-context preparation informs saved repository provenance and a definite PR/answer/plan/stop outcome. GitHub gh-aw's safe-output separation reinforces the existing credential-free agent and host-held broker. No reference instructions execute as editor commands. See ATTRIBUTION.md.
