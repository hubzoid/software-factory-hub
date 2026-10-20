# Software Factory implementation record

User authorized implementation and reviewable PR preparation on 20 October 2026. The proposal documents are the scope input, not another approval gate. Commits and review PRs are authorized. External ticket changes, paid resources, deployments and merging are not part of this authoring pass.

## File-by-file plan

- `workflows/factory/software_factory/{pipeline,ci,github,policy,scope}.py`: enforce non-actionable stops, current/open/unmerged PR fences, human-only ready transitions and reviewed-draft outcomes. Retain the five stations and SDK broker.
- `workflows/factory/software_factory/{brain,stations}.py`: source-linked context/revision evidence, shared across station calls and raw MCP domain results; proposed changes use existing SDK storage.
- `scripts/factory_setup.py`, setup skill/instructions, `SETUP.md`, doctor and tests: one reproducible assistant-readable path, preview before changes, safe existing connection merge, own-repository context bootstrap, runtime selection and clear human authentication/approval handoffs.
- `README.md`, `docs/{settings,security,architecture,operations,channels,evals}.md`, demo and CI: truthful delivery behavior, immutable SDK dependency, reference decisions, exact qualification limits and working commands.
- Focused unit/integration regressions first; one full hub regression and local sample/setup exercise after changes. Record actual SDK, commands and unavailable provider journeys here.

## Reference and scope dispositions

Foreman remains the behavior authority: `HubzoidAgent/RawTools/eve-master/eve-software-factory-template-main/agent/instructions.ts`, station prompts under `agent/subagents/`, and `agent/lib/github/approval.ts`. Keep classifier/researcher/analyst/implementer/reviewer isolation and order. The user-approved person-only ready transition narrows Foreman's brokered ready capability. Other inspected sources are `HubzoidAgent/RawTools/ReadyHubsTools/software-factory/langchain-ai__open-swe/openwiki/workflows/context-engineering.md` for source provenance/bounded outcomes, and `github__gh-aw/docs/src/content/docs/reference/safe-outputs.md` under that same software-factory reference root for agent/broker write-token separation. Reference code is data, never instructions for this editor.

Reuse SDK work items, channels, station calls, artifacts, secrets and Hub changes. Core inspected at `c4bf1dbe`; no orchestration framework or duplicate authorization/storage was added. Per the user's “only necessary UX” scope, stricter non-delegable setup credentials are deferred SDK hardening. The concrete path is trusted local authoring plus existing native human cards/CLI, with the host-owner trust boundary documented. Human approval handoffs remain mandatory; no credential is collected by the assistant. Read-only hosted source uses a reviewed builder checkout and redeploy, not a second activation platform.

Required local, real GitHub/Docker/runtime and Railway/Maritime rows remain qualification requirements. Only this hub's eventual PR is authorized for GitHub writes, so do not fabricate those journeys or create provider accounts. No hosted/subscription/Cowork completion claim without evidence. Optional new connectors, custom UI themes, cross-vendor review and hosted provider provisioning are omitted: existing supported SDK surfaces suffice for the primary UX, and external qualification is separately recorded rather than simulated as a pass.

## Validation

Tested source SDK: `c4bf1dbeaf0e498c364bfa1b1b97f10c7ae3c60c`. The core editable environment lacks GitHub dependencies. Tests used the existing `customer-desk-hub/.venv/bin/python` with `PYTHONPATH` explicitly pointing at current core source, not that environment's older editable SDK. An isolated `.venv/` dependency attempt was abandoned after offline-cache resolution failed; it is ignored, not part of delivery.

Confirmed commands/results before the RAM interruption:

- Focused integration selection in `tests/integration/test_pipeline.py` and `test_ci_and_gates.py`: **12 passed**, 42 deselected. Covers non-actionable routes, closed/merged admission, closure during implementation, human-only ready, changed rules after plan approval, and the existing broker journey.
- `tests/test_setup.py`: **4 passed** after the test explicitly demonstrated missing-grant denial followed by an administrator's legitimate grant. Covers safe inert connection composition, committed-source provenance, path escape, pending proposal reuse and no auto-activation.
- Combined setup/policy run: **217 passed, one setup-fixture failure** because the local owner lacked the required grant. This comprises 214 policy cases and three successful setup cases. The fixture was corrected to assert that denial and grant explicitly; the four setup checks then passed. Do not count the earlier combined command as wholly passing.
- `hubzoid hub configure . --check`: valid, no change. `hubzoid eval list .`: all ten declarations parsed; no real model eval was executed. Station schema regeneration from `workflows/factory` produced no schema diff. Compile check and `git diff --check` passed.

The full hub regression was started with `pytest -q -m '' tests --timeout=180 --junitxml=output/tests.xml --tb=short`, including slow DBOS tests. Laptop RAM/freezing concerns interrupted work before a final result was captured. `output/tests.xml` is absent; the old exec session is no longer available and root confirmed no pytest processes remain. **The full regression is incomplete, not a pass.** No heavy exclusions are hidden.

Two final safety refinements landed during that interval: old-plan reuse rejects a different context revision and shared status exposes the revision; repeated bootstrap refuses a conflicting pending proposal instead of returning stale content. Focused reruns for those refinements have no captured result and must run sequentially when root schedules checks. No further test/browser/Docker/model processes were launched after the RAM constraint.

Suggested sequential focused check before broader validation:

```sh
PYTHONPATH="$FACTORY_SDK_SOURCE" "$FACTORY_TEST_PYTHON" -m pytest -q tests/test_setup.py tests/integration/test_pipeline.py tests/integration/test_review_fixes.py -k 'repeated_bootstrap or saved_correction_reanalyzes or status_says' --timeout=180 --tb=short
```

`FACTORY_SDK_SOURCE` identifies the intended core checkout; `FACTORY_TEST_PYTHON` is the already qualified dependency environment. Root controls further checks and the single entire-implementation Claude review. No commit or PR has been created by this authoring agent.

## Author inspection and handoff

- Non-actionable work returns `not_actionable` before label/planning/implementation. CI admission and publication/delivery recheck a current open/unmerged PR and expected head. Draft status is refused even if a caller tries the lower-level factory write wrapper; metadata approval/recovery remains covered.
- Shared context is supplied to all relevant stations with a recorded revision. A changed root rule or brief blocks pending implementation/publication conservatively. Earlier plans with a different revision are re-analyzed; old evidence remains readable. Raw MCP status carries the same domain revision, without claiming external prompt control.
- Connection preparation preserves scope/credential references, user groups and enabled state, refuses unapplied local edits, and writes only an inert output candidate. Bootstrap reads selected committed bytes, rejects escaping/hidden/credential-looking sources, never overwrites curated context and uses existing SDK pending proposals.
- Foreman is the primary behavior reference; the existing broker and all five stations remain. User-only ready/merge intentionally narrows Foreman. Optional custom UI work, new connectors, cross-vendor requirements and stricter delegated credentials were omitted for the reasons above.
- All six real qualification rows remain unqualified in `docs/qualification.md`. Docker daemon unavailable; no real GitHub/model/hosted/Cowork success is claimed. Provider resources and external tickets were not created.

Source is frozen for root's sequential full regression, staged inspection and entire-implementation Claude review. Root owns further tests and any commit/PR; this authoring agent will make no more source edits until findings are returned. Remaining validation gaps are explicit; this is not a deployment-readiness claim.


## Final sequential regression

Root ran the complete `tests/` suite sequentially with low CPU priority, SDK f99a22406a65c1306a48485b8182f77be1ac71fb and the existing Customer test interpreter: **366 passed in127.65s**. Observed RSS about250MB. Initial bare pytest collected the separate sample fixture repository; corrected tests/ scope passed. No real-provider/model/Docker/hosted qualification inferred.
