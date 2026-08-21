# Attribution

The Software Factory is a Hubzoid port of eve's Software Factory template ("Foreman", MIT, Copyright (c) 2026 Vercel, Inc.). Foreman is the authority for stations and behaviour (founder decisions B023 and B027). The MIT licence is in `LICENSES/MIT-foreman.txt`.

## Files ported from Foreman

| This hub | Foreman source | How |
|---|---|---|
| `agents/classifier/AGENTS.md` | `agent/subagents/classifier/instructions.md` | Text kept, data-not-instructions rule added |
| `agents/researcher/AGENTS.md` | `agent/subagents/researcher/instructions.md` | Text kept, tools renamed (`web_search`, `http_get`, `save_handoff`) |
| `agents/analyst/AGENTS.md` | `agent/subagents/analyst/instructions.md` | Text kept, artifacts are handoffs, offline sandbox noted |
| `agents/implementer/AGENTS.md` | `agent/subagents/implementer/instructions.md` | The implementer commits and never pushes: the workflow publishes (gh-aw) |
| `agents/reviewer/AGENTS.md` | `agent/subagents/reviewer/instructions.md` | Reviews the exact pushed commit and reports `reviewed_sha` |
| `workflows/factory/software_factory/schemas.py` and `agents/*/schemas/result.json` | `agent/lib/stations/schemas.ts` | Every field kept. `artifact_id` is `handoff_id`. The implementer reports `committed` and `head_commit` instead of `pushed`. The reviewer adds `reviewed_sha` |
| `workflows/factory/software_factory/policy.py` | `agent/lib/github/approval.ts`, `agent/extensions/github.ts` | The policies as data, with HUB-6's named fixes |
| `workflows/factory/software_factory/pipeline.py`, `AGENTS.md` | `agent/instructions.ts` | The orchestrator's rules as durable workflow code |
| `workflows/factory/software_factory/ci.py` | `agent/channels/github.ts` (`CI_FIX_TASK`, `onCheckSuite`) | Ownership proved by the ledger and the SDK's push record, not the branch prefix |
| `workflows/factory/software_factory/brain.py` | `agent/lib/factory-brain.ts`, `agent/tools/update_factory_brain.ts` | A hub file changed through reviewed hub changes |
| `skills/writing-quality/` | `agent/skills/writing-quality/` | Copied, `name:` added |
| `skills/triaging-issues/` | `agent/skills/triaging-issues/` | Copied, one sentence adapted |
| `skills/github-linear-bridging/` | `agent/skills/github-linear-bridging/` | Copied, preferences are the person's own notes |
| `evals/` and `tests/integration/test_foreman_evals.py` | `evals/*.eval.ts` | The twelve evals ported (see `docs/evals.md`) |

## Patterns from other references (no code copied)

- LangChain open-swe (MIT): requester follow-ups read at each stage boundary (`openswe/middleware/check_message_queue.py`), CI repair caps counted per work and never reset by the factory's own pushes (`openswe/baby_sit.py`), every run ends in a pull request or a stated failure (`openswe/completion.py`).
- github/gh-aw (MIT): the agent holds no write token and deterministic code applies the patch and opens the draft (`actions/setup/js/create_pull_request.cjs`), patch size and file caps, protected files with a request-review default (`manifest_file_helpers.cjs`).
