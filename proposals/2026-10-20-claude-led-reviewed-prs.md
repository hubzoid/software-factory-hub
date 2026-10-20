# Software Factory: Claude-led setup to reviewed draft pull requests

**Draft for user approval. No implementation authorized by this document.**

Proposed destination: `proposals/2026-10-20-claude-led-reviewed-prs.md`.
This proposal and the [common contract](2026-10-20-ready-hubs-common-contract.md) need approval before implementation. Independent subagent review informs user approval. Complete scope determines readiness before dates.

## Problem

A builder should bring a request, issue or ticket and receive a reviewed draft PR grounded in repository and team rules. The pipeline exists; setup and production evidence do not establish that journey.

At baseline `666c337e`, `SETUP.md` requires manual configuration and a moving SDK branch. Its laptop PAT path tells someone to label an issue without providing webhook delivery. Exporting the GitHub connection can overwrite the supplied route template. `ci.py` reads PR state without excluding closed or merged PRs, and the pipeline does not enforce classifier `actionable=False`. These source findings need reproduced regression cases before changes are claimed as fixes.

The reported 348 passing tests use synthetic dependencies. `tests/live/README.md` explicitly describes GitHub and sandbox stand-ins. Neither establishes real model, Docker, GitHub, authentication or deployment readiness. The current CI “real” job prints instructions; it is not qualification.

## Why now

Software Factory is an approved ready-made hub. B023 and B027 retain the upstream template's stations and behavior; B042 names LangChain open-swe as the second reference and gh-aw for the write-token boundary. B037 requires useful operation with one installed Claude or Codex runtime. B038 requires thin adapters around SDK capabilities, and B042 forbids a fourth repository or package.

The need is a repeatable path through existing components: shared context, file configuration, customization, visible first value, proven actions, assistant-led setup and explicit tool access.

## What should happen

### Builder: set up, personalize, prove

The builder asks Claude Code, Cowork or Codex to set up this hub. The assistant reads instructions, checks prerequisites, selects one runtime, explains costs and inspects a user-selected scratch repository. It configures files and runs supported commands without manual Hubzoid UI work. Cowork is a required setup target. Any needed helper must be an existing supported component; otherwise return for a scope decision. Human-readable instructions cover the same path.

The assistant presents the repository, tools, dependency setup command, network profile and proposed changes. Its delegated setup identity may prepare files and activate already authorized connector definitions. It cannot mint or widen grants, read/administer secret values, activate shared revisions or approve business actions. Protected acts require the SDK's authenticated human confirmation through a separate non-delegated principal session, bound to principal, action/resource, exact digest and time. Setup/runtime credentials cannot produce it; absent separation is a must-have SDK dependency. The person completes GitHub sign-in, installation and credential entry directly. The assistant verifies status without seeing secrets. External consent and identity linking remain human handoffs.

Initial context bootstrap reads selected repository instructions, architecture, manifests, test commands and ownership rules. It proposes a small source-linked repository brief in `knowledge/factory-brain/`, including repository identity, source commits and unverified assumptions. The builder approves the exact diff before it becomes shared. Explicit Hub rules govern behavior; fetched issues, code and documents remain untrusted task data. Setup conversation is not automatically saved.

The first result is a useful plan with acceptance criteria and no code changes. A correction from chat or MCP requests an SDK proposed-change operation. The SDK stores the proposal and source evidence in its data root; an authorized human approves its exact diff, then activation uses the qualified builder/update workspace, including for read-only source mounts. Chat tools never write outside `<hub>/output/<session>/`. Missing SDK support is a named must-have before implementation. The next run must reflect the activated correction. A scratch bug then completes the whole pipeline. Laptop PAT intake uses a manual command until verified forwarding exists; labeling alone is never advertised as delivery.

### Member: request work and understand the result

A permitted member asks in the Hubzoid web app, an existing assistant over MCP, GitHub, or an enabled existing Slack/Linear channel. Other ticket systems use their existing MCP interface to supply a request; this proposal adds no helpdesk product or second chat app. Verified account links and grants determine authority across surfaces.

Questions receive grounded answers. Triage and plan requests stop at their route ceiling. Change requests run classifier, optional researcher, analyst, implementer and independent reviewer. Non-actionable work stops; missing facts produce bounded questions. Attended implementation waits for exact-plan approval. A verified internal human holding the action/resource approval grant approves; an external sender or service/event identity never approves. A personal owner may self-approve; no two-person rule is introduced. Authorized label intake may run unattended to an inert draft PR under its configured policy; clarification stops rather than inventing consent.

Depth matches the task: include relevant repository context and checks, research only outside facts, and stop when scope is unsafe or unresolved. Preserve configurable review and CI attempt bounds, clear exhaustion outcomes and opt-in spending limits. Same-vendor review uses a fresh reviewer context on the exact pushed commit; a second subscription is unnecessary.

The member sees stage, waiting reason, plan, evidence, changed files, checks and the next human action. The terminal state `review_ready` means a draft PR with reviewed SHA = pushed SHA = current branch head. The factory never changes draft status. A person alone marks the PR ready for review and merges in GitHub.

### Administrator: control access and operation

The administrator sees effective settings and their authority, validates grants, connects systems, pauses intake, revokes tools, and inspects failures, usage and recovery. Instructions, rules, model/harness/station definitions, tool/action policies, role bundles, connector definitions and appearance are file-authoritative. Identities, account links, member assignments, secret values and approvals are runtime-authoritative SDK state. Console/CLI/API edits produce a reviewed file revision or operate scoped SDK state; no setting has two writable truths. Every exposed control works and persists.

## Authority, tools and artifacts

Every surface uses shared domain-service semantics, scope checks, revision identifiers and evidence. Hub instructions and skills apply where Hubzoid runs the agent: chat, workflows and MCP tools delegating to the Hub agent. Raw MCP tools do not force an external client's generation to follow Hub prompts. Fixed fixtures must return matching allow/deny and rule/evidence identifiers across surfaces; live reads record their evidence snapshot and policy revision rather than promise identical results.

Existing work retains its recorded definition and evidence. Immediately before dispatch, recheck current grants and context/rule revision and recompute the action digest. Lost authority blocks dispatch. A changed approved digest voids approval and requires a fresh preview/approval; an identical digest records both revisions. Unattended actions still require current policy and grants. GitHub owns source and PRs; Hub files own approved rules; SDK state owns execution/approvals; sandbox checkouts are disposable.

Plans and evidence live in scoped Hub output and authenticated artifacts, linked to work item, repository, plan digest and commit. Chat and MCP expose the same authorized artifact identifiers; possession of a link grants no access. External comments contain only an intentionally publishable summary. Private evidence and unrelated members' files never leak into a PR body. Personal notes remain personal; unattended learning produces suggestions, not shared edits.

| Action | Member/requester | Builder or administrator | Unattended workflow |
|---|---|---|---|
| Read repository/context/artifacts | Explicit repository, tool and artifact grants | Same checks; manage grants separately | Only bound repository and task context |
| Start/inspect/cancel work | Granted routes and owned/visible work | Explicit workflow-management grant | Approved event route only |
| Approve plan or consequential action | Verified internal human with action/resource approval grant, exact digest | Same checks; personal owner may self-approve | Service/external event identity cannot approve |
| Save shared rules/settings | Propose with grant | Approve/apply with distinct grant | Suggest only |
| Push branch/open draft PR | Brokered factory operation only | Same publication rules | Own recorded branch and source thread |
| Comment/label/close issue | Named tool and action policy | No blanket connector authority | Caller matrix and origin restrictions |
| Configure secrets/connections | No default grant | Explicit administration grant | No secret access |
| Mark PR ready/merge/default-branch push/administer repo | Human GitHub operation | Human GitHub operation | Never |

Authorization intersects identity, group, repository, tool, route and action at execution time. Members receive no powerful or paid tools by default. New MCP tools require explicit classification and grants. Keep existing `off`/`draft`/`approve` action semantics where applicable; installing a connector never enables all its writes. Plan approval, shared-rule approval and external-action approval are separate records.

## Scope and non-goals

Reuse all stations, work items, operation broker, branch ledger, sandbox exports, channels and review gates. Implementers receive no GitHub credentials. The broker verifies patch digest, branch ownership, expected head and allowed files before publication. CI repair must recheck an open, unmerged PR, current failing head and remaining attempt count immediately before publishing. No host-shell fallback, merges, default-branch writes or automatic release deployment.

Keep GitHub App credentials in the SDK secret store; mint narrowly scoped tokens per operation. The laptop PAT exception uses one repository and disclosed permissions. Operator `.env` sources remain locked where the SDK defines them. Credentials never enter Hub files, logs, model prompts, sandbox environments or Git history. Validate both connection failure and revocation recovery.

Settings cover repository, channels, routing, concurrency, review depth, action modes, sandbox setup and optional limits. Agent files choose model/runtime, harness instructions, skills and knowledge. Supported theme/layout files customize the one Hubzoid web app. New connector adapters, authorization behavior, unsupported UI extensions or runtime capabilities require reviewed engineering, not misleading settings switches. Preserve equivalent tool schemas and behavior across Claude and Codex; runtime construction stays in SDK adapters.

| Work area | Proposed responsibility |
|---|---|
| `SETUP.md`, `docs/`, `doctor/`, manifests | Assistant-led setup, bootstrap, diagnostics and accurate claims |
| `agents/`, `skills/`, `knowledge/`, settings | Context, station contracts and supported customization |
| `workflows/factory/software_factory/`, `tools_local/` | Route enforcement, context/evidence, CI admission and broker integration |
| `channels/`, sandbox profiles, tests/evals/demo | Connection-safe configuration, real journeys and labelled fixtures |
| Hubzoid SDK | Only missing generic must-haves: delegated identity/human-confirmation separation, proposed-change storage and activation, scoped grants, or demonstrated artifact/connection/station/broker/settings gaps |

Required SDK baseline is `14e1a59b`. Testing pins an immutable reviewed commit; promoted installation ships against a qualified tagged SDK release. SDK gaps get separate must-have PRs for human review and merge. Prefer native runtime approval, sessions and delegation; no new framework, package, repository, global memory system or UI mode. Product code stays Apache-2.0; retain the upstream MIT attribution.

## Required qualification coverage

Each required row uses real GitHub, Docker sandbox and runtime journeys, with chat/workflow/MCP checks. All rows must pass; order of execution is not a release cut. Hosted rows also pass the common hosting acceptance, including separate sandbox operation, callbacks, teammate access, persistence, scheduler, restore and upgrades.

| Row | Host | Execution runtime | Required setup/authoring | Provider |
|---|---|---|---|---|
| L-C | Local | Claude only | Claude Code and Cowork, each exercised | GitHub PAT, manual intake |
| L-X | Local | Codex only | Codex authoring | GitHub PAT, manual intake |
| R-C | Railway | Claude only | Claude Code | GitHub App, verified events |
| R-X | Railway | Codex only | Codex authoring | GitHub App, verified events |
| M-C | Maritime | Claude only | Cowork | GitHub App, verified events |
| M-X | Maritime | Codex only | Codex authoring | GitHub App, verified events |

Other matrix cells receive synthetic contract coverage, with no supported-combination claim. Qualify the existing supported-runtime authentication first and record the actual method for each row. Local first use may use installed sign-in without API spend. Subscription-based unattended, hosted or teammate-shared use is claimed only with evidence for that exact combination. No unapproved paid fallback or qualification spending is authorized here.

## Migration, rollback and risks

No existing deployment migrates automatically. Back up the Hub, operational/workflow databases and artifact references together; record revisions and GitHub side effects. Pause intake, drain or explicitly resolve waiting work, and dry-run configuration merges without overwriting customer routes. Upgrade with doctor checks. Changed definitions stop for review, never reinterpret old approval. Roll back compatible code/configuration together; reconcile ambiguous external writes before retry. Restoring data cannot undo a published PR.

Primary risks are prompt injection, stale repository context, overbroad credentials, duplicate delivery, changed branch heads, dependency setup executing hostile code, private evidence publication and false readiness claims. Existing broker checks and sandbox isolation are retained; regression and real-user evidence must cover their boundaries. Provider hosting, runtime authentication and network restrictions must be qualified as a specific combination before promotion; Railway or Maritime support is not implied by local success.

## Open questions and proposed decisions

Approval is requested for the whole scope, authority/approval model, reviewed corrections, six-row qualification table and human-only ready/merge boundary. Confirm Cowork's existing supported helper if needed and inventory the actual theme/layout controls. Record unresolved SDK or authentication gaps and return for a scope decision if the required outcome is infeasible. No dates, partial release cuts or paid qualification actions are authorized by this draft.

## Definition of done

- A fresh builder completes qualified Claude-led setup without manual Hubzoid settings, authenticates directly, sees a useful real-repository plan, saves a reviewed correction and observes it on the next run.
- Fixed-fixture chat, workflow and MCP checks match allow/deny, rule and evidence identifiers; live reads record snapshots. Delegated agent execution applies Hub prompts; raw MCP does not claim client compliance. A permitted teammate completes work; denied or revoked grants block artifacts, tools and pending writes.
- Every required qualification row produces a `review_ready` draft PR with reproducible checks, context and exact-commit evidence. Only a person marks it ready and merges. Plan-only, non-actionable and clarification routes perform no implementation.
- Focused regressions reproduce and resolve PAT delivery guidance, closed/merged CI repair, non-actionable classification, route-template overwrite and immutable SDK installation. Restart, duplicate events, stale approvals/heads, reviewer modifications, ambiguous writes and exhausted attempts produce correct recovery or stops.
- One broader regression run follows focused checks. Real journeys record versions, permissions, costs, results, failures and limitations for each promoted runtime/provider combination. Stand-ins, skipped tests, timeouts and absent credentials are reported separately and never counted as real passes.
- Tests prove setup credentials cannot widen grants, administer secrets, activate shared revisions or approve actions. Verified internal action-scoped humans can approve, including personal-owner self-approval; external senders and services cannot.
- Pending-plan tests recompute the action digest under current rules: changed digests require fresh approval, identical digests record both revisions, and lost authority always blocks. Read-only source activation and rollback preserve one authoritative revision.
- Railway and Maritime each pass common hosting acceptance for both required runtime rows, with exact authentication methods, versions and limitations recorded.
- Settings, access controls, theme/layout behavior, diagnostics, backup/restore and rollback work through actual user journeys. No dummy controls or unqualified compatibility claims remain in the promoted path.
