# Troubleshooting

Every stop says why and what to do next, on the issue or in `factory_status`. The codes:

| Code | What happened | What to do |
|---|---|---|
| `needs_clarification` | The classifier could not tell what to build | Answer the questions, then ask again or re-add the label |
| `implementation_not_pushed` | The implementer could not finish (`committed: false`) | Read its limitations, refine the issue, ask again |
| `review_rejected` | The reviewer rejected the approach | Read the findings, adjust the issue, ask again. The pushed branch stays for a person |
| `review_unresolved` | Still changes requested after `FACTORY_REVIEW_CYCLES` revisions | A person takes it from the pushed branch |
| `reviewed_sha_mismatch` | The review did not cover the exact pushed commit | Ask again. No pull request was opened |
| `patch_refused` | The change touched CI workflows, git metadata or a symbolic link, was too large, or looked like it carried a credential | Nothing was pushed. Narrow the request |
| `plan_rejected`, `plan_changes_requested` | The requester rejected the plan, or its revisions ran out | Ask again with what should change |
| `branch_exists`, `branch_owned_elsewhere` | The branch is not the factory's for this work | Nothing was overwritten. Check who created it |
| `stale_head`, `head_changed` | Someone pushed to the factory's branch | Automated work stops. A person takes over |
| `not_factory_branch` | Red CI on a branch the factory did not push | Nothing to do: only the factory's own branches are repaired |
| `ci_attempts_exhausted` | `FACTORY_CI_ATTEMPTS` repairs did not turn the checks green | A person takes over |
| `fork_pull_request` | A pull request from a fork | Forks never get automated work |
| `push_rejected` | GitHub refused the push (a rule on the branch) | Check branch rules for the factory's prefix |
| `policy_denied` | The action is not allowed for this kind of request (for example a pull request from an unlinked mention) | Link your GitHub account in Hubzoid, or use the label |
| `approval_denied` | The person who asked said no | Nothing was sent |
| `repository_unavailable` | `FACTORY_REPO` is not in the GitHub connection, or a write targeted another repository | Fix the setting or the App installation |
| `intake_paused` | `FACTORY_INTAKE_ENABLED` is false | Turn it back on |
| `stopped_by_requester` | The requester wrote "stop" | Nothing more runs |

Codes from Hubzoid itself:

| Code | What to do |
|---|---|
| `sandbox_unavailable`, `docker_unavailable` | Start Docker, then `hubzoid sandbox doctor .`. Hubzoid never falls back to the host shell |
| `setup_failed` | Read the output tail, fix `setup.command` in `sandboxes/factory.yaml` or the lockfile |
| `image_unavailable` | `hubzoid sandbox profiles prepare . factory` |
| `sandbox_lost` | The sandbox disappeared. Retry the station call to start a fresh one |
| `retry_exhausted` | A station failed twice. Check the call with `hubzoid stations calls show`, fix the cause, restart the work |
| `definition_changed` | Code changed while the work waited. Check, then `hubzoid work-items restart` |
| `pr_update_requires_approval` | Set `github.pr_update: approve` in `work-items.yaml` |
| Ambiguous operation | A write may or may not have happened. The requester decides done, retry or abandon in Work items. An empty search is not proof. An interrupted pull request creation settles itself by finding the pull request for its branch |
| Ambiguous operation in unattended work | Label and CI work has no person to decide. A manager cancels it (`hubzoid work-items cancel . ITEM`) and checks GitHub. Nothing is resent on its own |
| `review_evidence_invalid` | The reviewer left changed files, so its checks don't prove the published commit. Ask again |
| `pull_request_unconfirmed` | An uncertain creation was settled as done, but no pull request for the reviewed commit exists. Open it from the branch or ask again |
| `pat_remote_forbidden` | Token mode is for a laptop. Use a GitHub App for a hosted hub |
| `signature_invalid` | The webhook secret does not match the App's |

Doctor (`hubzoid hub doctor .`) checks settings, the GitHub connection and its routes, the stations and their schemas, the sandbox and Docker, the write modes, the channels, the runtime and the brain, and gives the fix for each.
