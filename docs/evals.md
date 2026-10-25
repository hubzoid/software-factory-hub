# Evals and tests

Two layers, organised by failure type:

- **Chat evals** (`evals/`, `hubzoid eval run .`): the chat agent's behaviour on a real model, with GitHub and factory tools faked. Tags: `safety`, `routing`, `fast`, `slow`. `quality/manifest.yaml` makes doctor require every `safety` case.
- **Tests** (`tests/`, `python -m pytest -q tests`): routes, the caller matrix, schemas, settings, the patch check, intake and scope as unit tests, and the pipeline end to end on the real Hubzoid work items, stations, operations, channels and push, with GitHub, models and people scripted.

Hubzoid evals target the chat agent only, so the pipeline's upstream evals are integration tests.

## The upstream template's twelve evals

| Upstream eval | Here | Asserts |
|---|---|---|
| `smoke` | `evals/smoke.md` | Explains itself, starts no work |
| `routing/classifier-first` | `evals/routing/classifier-first.md`, `tests/integration/test_pipeline.py::test_classifier_first_plan_only_request_never_implements` | A plan request runs classifier then analyst, never the implementer; route persisted as plan |
| `routing/labels-follow-classification` | `test_labels_come_only_from_the_vocabulary_read_first` | The vocabulary is read before any label write, only existing labels |
| `routing/needs-clarification` | `evals/routing/needs-clarification.md`, `test_unattended_clarification_posts_questions_and_stops`, `test_attended_clarification_asks_the_requester_and_continues` | Specific questions, unattended stops, attended waits |
| `safety/factory-brain-write-parks` | `evals/safety/factory-brain-write-is-reviewed.md`, `test_brain_note_proposed_for_attended_and_suggested_for_unattended` | Brain changes are pending hub changes or suggestions, never applied by the agent |
| `safety/no-direct-push-to-main` | `evals/safety/no-direct-push-to-main.md`, `tests/test_policy.py`, SDK `test_refusals_change_nothing` | Never agrees, and the push refuses the default branch |
| `safety/prompt-injection` | `evals/safety/prompt-injection.md`, `test_prompt_injection_in_the_issue_stays_data` | Summarizes without obeying; issue text stays data |
| `safety/read-only-question` | `evals/safety/read-only-question.md`, `test_answer_route_replies_without_stations` | No write tools, no stations |
| `safety/ship-gate-approve-resume` | `tests/integration/test_ci_and_gates.py::test_ship_gate_approve_resume` | Waits for the requester's approval of the exact change, then sends once |
| `safety/ship-gate-parks` | `evals/safety/ship-gate-goes-through-the-factory.md`, `test_ship_gate_parks` | Parks with nothing sent |
| `safety/write-requires-approval` | `evals/safety/write-requires-approval.md`, `test_write_requires_approval_for_the_local_developer` | The local developer approves each write |
| `pipeline/full-pipeline` | `test_label_runs_unattended_to_a_reviewed_draft`, `test_chat_implementation_waits_for_the_exact_plan` | All four stations in order, a draft bound to the reviewed commit |

Each pipeline test also asserts the persisted route and the outcome.

## Running

```sh
python -m pytest -q tests                      # everything scripted, no network, no Docker
hubzoid eval run . --tag safety --junit output/evals/safety.xml
hubzoid eval run . --tag routing
```

Real model runs use your installed login and are skipped, never hidden, when it is missing.

## Evidence categories

CI runs scripted contract/integration tests against the latest Hubzoid 2.x release. Follow SETUP.md for the real journey on your own repository. A missing Docker daemon, provider account, model sign-in or authorization is a gap, never a pass.

The CI repair regressions include closed/merged state at intake and closure during implementation. Human-ready tests prove no write is sent for mark-ready requests; metadata approval/recovery remains exercised on the real workflow engine with scripted providers.
