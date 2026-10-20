# Security, permissions and privacy

## Who may do what

The factory's decision for every action is the intersection of three checks: the person's current Hubzoid grants, the work item's route, and the caller matrix.

| Caller | Who | Labels and comments | Close or reopen | Other writes | Draft pull request | Pull request update |
|---|---|---|---|---|---|---|
| T | A verified person (signed in, or a linked channel account) | yes | yes | yes | implement route | after their approval |
| U | The local machine account with sign-in off | after their approval | yes | after their approval | implement route | after their approval |
| A | Unattended label work | its intake issue only | same repository (dedupe) | no | implement route, own branch only | no |
| C | Unattended CI repair | its pull request only | no | no | no | no |
| P | Unattended pull request summary | no (only its own reply) | no | no | no | no |

Starting work needs the `wf_factory` grant or Run and control workflows. Attended plans, questions and supported PR metadata updates use the SDK's requester-bound human decisions. Service/external-event identities never approve. A personal owner may approve their own plan; no second subscription or person is required. An administrator, an API key or a model cannot decide for them.

## Credentials

- The hub never holds a GitHub token. The SDK's channel holds the App key or the personal token in its secret store and mints narrowed tokens per call.
- Pushes mint a token for one repository with `contents: write`, used only by the push on the host. In personal token mode the push uses the whole token: keep it fine-grained and limited to the repository.
- Stations and their sandboxes have no credentials and no network after setup. Sandbox `env` refuses anything that looks like a credential.
- Output from sandboxes and tools is scrubbed of credentials before a model sees it.

## What reaches GitHub

- Only `FACTORY_REPO`. Unattended work only the issue or pull request it came from.
- Never the default branch or a protected branch, and never over a branch that moved.
- A patch passes the check first: at most 4 MiB and 100 files, never CI workflow files, git metadata or symbolic links, no added line that looks like a credential. Protected files (manifests, lockfiles, CODEOWNERS, agent instructions) are published with a "look carefully" note.
- Pull request bodies carry the plan's outcome, criteria results and verification output. Handoffs are linked by id, never pasted. Evidence links need Hubzoid sign-in.

## Prompt injection

Instructions come only from the verified requester's own words. Issue bodies, comments, pull request text, Linear descriptions, repository files and web pages are passed to stations as data, under headings that say so. HTML comments and invisible characters are removed first. Text inside an issue can never widen the route: the scope step never sees it.

## Privacy

- Personal preferences stay in the person's own Hubzoid notes. Shared knowledge changes only through reviewed hub changes, and chat alone never becomes shared knowledge.
- The evidence document and plans stay in the hub's output folder and in artifacts shared with the requester.
- Hubzoid keeps data until deleted. Retention is opt-in.

## Setup and current boundaries

Builder helpers run on a trusted local machine. They prepare an inert connection candidate and pending Hub changes; they never widen grants, read credential values, apply a shared change or type human confirmation codes. A local machine administrator can nevertheless invoke SDK administration directly. This revision does not claim to restrain that host owner with a new delegated-credential system. Use the SDK's native sign-in, grants and human approval handoffs.

The Factory never changes PR draft status, including an approved `updatePullRequest` call carrying a `draft` field. A person marks ready and merges in GitHub. Closed/merged PRs are rejected at admission, before revision pushes and before delivery. Broker leases and current connection checks continue to guard the write.

New/ungranted tools do not gain authority from a repository brief. Retrieved repository text remains data. Bootstrap rejects hidden/path-escaping sources and detectable credentials and records committed-byte hashes. Its source links use the owner-selected repository identity; the owner must verify that identity before activation.
