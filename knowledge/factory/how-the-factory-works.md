---
name: how-the-factory-works
description: The factory's routes, stations, gates and stop reasons, for answering questions about what the factory will do with a request.
keywords: [factory, routes, stations, plan approval, draft pull request, ci repair, label]
---
# How the factory works

Every request becomes one durable work item on one route. The route is chosen first, before any station or write, and can only narrow.

| Route | Stations | What it may change |
|---|---|---|
| answer | none | a reply only |
| triage | classifier | labels from the repository's own vocabulary, a comment |
| plan | classifier, researcher when needed, analyst | triage changes, plus a shared plan |
| implement | classifier, researcher when needed, analyst, implementer, reviewer | triage changes, a factory branch, one draft pull request |
| revise | implementer, reviewer | the factory's own branch on an existing pull request |
| summarize | none | one orientation comment on a new pull request |
| act | none | one supported action, such as editing PR metadata after exact approval |

How work arrives: the `factory` label (unattended, straight to a draft pull request), a mention by an owner, member or collaborator, a new pull request (one orientation comment, not a review), red CI on a factory branch (at most two repairs), the web chat, a personal assistant over MCP, Slack, Linear and the API.

Gates:

- Attended implementation waits for the requester to approve the exact plan. The owner can turn that off with FACTORY_REQUIRE_PLAN_APPROVAL.
- The implementer works offline in a sandbox with no credentials and only commits. The factory checks the exported patch (size, paths it never changes such as CI workflows, protected files, credentials) and pushes it to its own branch through the SDK, never to the default branch.
- An independent reviewer reviews the exact pushed commit in a fresh checkout. Approve needs every acceptance criterion to pass. Request changes sends it back to the implementer, at most twice. Reject stops.
- The draft pull request is opened only when the remote branch, the pushed commit and the reviewed commit are the same. The terminal state is review_ready, still a draft. A person alone marks it ready in GitHub. Merging is always a person's job.

Stop reasons are stated plainly with the next step: needs_clarification, implementation_not_pushed, review_rejected, review_unresolved, patch_refused, plan_rejected, stale_head, head_changed, not_factory_branch, ci_attempts_exhausted and others. A pushed branch from a stopped run stays on GitHub and is never labelled approved.
