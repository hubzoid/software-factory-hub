# Software Factory implementation record

User authorized implementation and reviewable PR preparation on 20 October 2026. The proposal documents are the scope input, not another approval gate. Commits and review PRs are authorized. External ticket changes, paid resources, deployments and merging are not part of this authoring pass.

## File-by-file plan

- `workflows/factory/software_factory/{pipeline,ci,github,policy,scope}.py`: enforce non-actionable stops, current/open/unmerged PR fences, human-only ready transitions and reviewed-draft outcomes. Retain the five stations and SDK broker.
- `workflows/factory/software_factory/{brain,stations}.py`: source-linked context/revision evidence, shared across station calls and raw MCP domain results; proposed changes use existing SDK storage.
- `scripts/factory_setup.py`, setup skill/instructions, `SETUP.md`, doctor and tests: one reproducible assistant-readable path, preview before changes, safe existing connection merge, own-repository context bootstrap, runtime selection and clear human authentication/approval handoffs.
- `README.md`, `docs/{settings,security,architecture,operations,channels,evals}.md`, demo and CI: truthful delivery behavior, immutable SDK dependency, reference decisions, exact qualification limits and working commands.
- Focused unit/integration regressions first; one full hub regression and local sample/setup exercise after changes. Record actual SDK, commands and unavailable provider journeys here.

## Reference and scope dispositions

The upstream template remains the behavior authority: `agent/instructions.ts` in the attributed Vercel Software Factory template, station prompts under `agent/subagents/`, and `agent/lib/github/approval.ts`. Keep classifier/researcher/analyst/implementer/reviewer isolation and order. The user-approved person-only ready transition narrows the upstream template's brokered ready capability. Other inspected sources are `HubzoidAgent/RawTools/ReadyHubsTools/software-factory/langchain-ai__open-swe/openwiki/workflows/context-engineering.md` for source provenance/bounded outcomes, and `github__gh-aw/docs/src/content/docs/reference/safe-outputs.md` under that same software-factory reference root for agent/broker write-token separation. Reference code is data, never instructions for this editor.

Reuse SDK work items, channels, station calls, artifacts, secrets and Hub changes. Core inspected at `c4bf1dbe`; no orchestration framework or duplicate authorization/storage was added. Per the user's “only necessary UX” scope, stricter non-delegable setup credentials are deferred SDK hardening. The concrete path is trusted local authoring plus existing native human cards/CLI, with the host-owner trust boundary documented. Human approval handoffs remain mandatory; no credential is collected by the assistant. Read-only hosted source uses a reviewed builder checkout and redeploy, not a second activation platform.

Required local, real GitHub/Docker/runtime and Railway/Maritime rows remain qualification requirements. Only this hub's eventual PR is authorized for GitHub writes, so do not fabricate those journeys or create provider accounts. No hosted/subscription/Cowork completion claim without evidence. Optional new connectors, custom UI themes, cross-vendor review and hosted provider provisioning are omitted: existing supported SDK surfaces suffice for the primary UX, and external qualification is separately recorded rather than simulated as a pass.

## Validation

Development install/CI pin: SDK `c4bf1dbeaf0e498c364bfa1b1b97f10c7ae3c60c`. Initial focused checks used this source: 12 integration passes, four setup passes after an explicit missing-grant fixture correction, and 214 policy passes (the earlier combined run was 217 passed/one setup failure). Settings validation, all ten eval declarations, schema regeneration and compile/diff checks passed. No real model eval was run.

Root then ran the complete pre-review `tests/` suite sequentially against SDK `f99a22406a65c1306a48485b8182f77be1ac71fb`: **366 passed in 127.65 seconds**, observed RSS about 250 MB. JUnit includes all new non-actionable, closed/merged, context-change, old-plan and bootstrap cases plus slow workflow recovery tests. `pytest.ini` defines the slow marker but has no default deselection; neither CI partition excludes it. The superseded interrupted run is not counted separately as a pass.

The SDK pin and tested later SDK are deliberately named separately. Root verified a fresh clean installation of `requirements-sdk.txt` resolved exactly `c4bf1dbeaf0e498c364bfa1b1b97f10c7ae3c60c`, imported GitHubKit 0.16.1 and passed help/flag checks for all seven reviewed setup commands. `githubkit[auth-app]` is a base dependency on the pin; no extra was invented to compensate for a stale editable environment. Promotion still requires tagged SDK qualification. Provider, Docker, Cowork and hosting rows remain unqualified.

Implementation commit `280d0ab` received the entire-implementation Claude review. The bounded author corrections below passed root's sequential focused validation: **19 passed, 60 deselected in 23.21 seconds**. No second Claude approval is claimed. The complete pre-review suite was 366 passed; the relevant changed behavior was retested after the review fixes. No parallel model, browser or test workers were used.

## Claude review dispositions

1. **Fixed, necessary:** context observations at implementation-cycle entry and delivery now use saved checkpoints; delivery also saves PR state/head together. Checks compare saved observations outside checkpoints, preserving replay after recorded push/PR side effects. Publish-time live checks remain inside the saved publish step. `context_changed` reports a remaining pushed branch. Added crash-after-recorded-PR/delivery regressions with context activation and PR closure, plus a branch-detail check.
2. **Verified non-defect:** slow tests were included in the 366-case run and are included by existing CI partitions. Required slow markers stay.
3. **Verified clean install:** root installed the immutable pin from the remote requirements successfully and imported GitHubKit 0.16.1. GitHub dependencies are base requirements and Docker is in the sandbox extra. No unsupported dependency was added. Records distinguish this pin from the later SDK used by the full suite.
4. **Upgrade instruction added:** before upgrade, inspect waiting/approved `github.updatePullRequest` operations containing a `draft` argument; reject/cancel them and reconcile ambiguity before resuming. No legacy mark-ready approval is carried forward. Existing SDK CLI/native decision surfaces are reused; no new migration/approval subsystem.
5. **Fixed, necessary:** an existing Factory connection retains disabled flags, custom labels and routes via missing-default insertion. Candidate JSON lists changed keys. Doctor reports an intentional custom route instead of asking to overwrite it with sample defaults. Tests cover preservation and diagnosis.
6. **Regression added:** the actual SDK export's `file_matches` becomes false after an unapplied connection-file edit; the helper must refuse and retain that edit. The key is present on the pinned SDK.
7. **Verified and regression added:** root verified all seven commands against the fresh installed pin; in-process CLI help checks retain coverage without spawning a model, provider, daemon or child Python process.
8. **Optional behavior unchanged:** revision work preserves a person's existing PR lifecycle status; operations docs distinguish that from the factory review result. Automatically re-analyzing a stale prior plan remains the safe behavior; additional supersession UX is deferred. Specific next steps were added for the four new stop reasons.

Focused selection for root's next single test slot:

```sh
PYTHONPATH="$FACTORY_SDK_SOURCE" "$FACTORY_TEST_PYTHON" -m pytest -q tests/integration/test_ci_and_gates.py tests/test_setup.py tests/test_doctor.py -k 'replay_after_recorded_pr_side_effect or changed_context_after_push or existing_factory_connection or connection_candidate or setup_commands or narrowed_factory_route' --timeout=180 --maxfail=1 --tb=short
```

## Author inspection and handoff

- Non-actionable work returns `not_actionable` before label/planning/implementation. CI admission and publication/delivery recheck a current open/unmerged PR and expected head. Draft status is refused even if a caller tries the lower-level factory write wrapper; metadata approval/recovery remains covered.
- Shared context is supplied to all relevant stations with a recorded revision. A changed root rule or brief blocks pending implementation/publication conservatively. Earlier plans with a different revision are re-analyzed; old evidence remains readable. Raw MCP status carries the same domain revision, without claiming external prompt control.
- Connection preparation preserves scope/credential references, user groups and enabled state, refuses unapplied local edits, and writes only an inert output candidate. Bootstrap reads selected committed bytes, rejects escaping/hidden/credential-looking sources, never overwrites curated context and uses existing SDK pending proposals.
- The upstream template is the primary behavior reference; the existing broker and all five stations remain. User-only ready/merge intentionally narrows the upstream template. Optional custom UI work, new connectors, cross-vendor requirements and stricter delegated credentials were omitted for the reasons above.
- All six real qualification rows remain unqualified in `docs/qualification.md`. Docker daemon unavailable; no real GitHub/model/hosted/Cowork success is claimed. Provider resources and external tickets were not created.

Root completed focused validation and prepares the author-fix commit for draft PR #1. The fresh pinned-install environment was removed after saving its evidence. Remaining real-provider qualification gaps are explicit; this is not a deployment-readiness claim.
