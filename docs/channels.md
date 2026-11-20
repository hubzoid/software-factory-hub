# Where requests come from

Every channel starts the same durable `factory` work item. The trigger decides the route ceiling, and the scope step narrows it. Who asked, and whether the work runs unattended, come from what Hubzoid verified, never from message text.

| Channel | Trigger | Route ceiling | Who it acts as |
|---|---|---|---|
| GitHub label | The configured label added by someone with triage permission or more (checked live) | implement | The factory's workflow account, unattended. Writes only on that issue, plus one draft pull request for its own branch |
| GitHub mention | `@app` in a new comment by an owner, member or collaborator | request (answer, triage, plan, implement, revise, act) | The linked Hubzoid person. A collaborator without a linked account runs unattended and may answer, triage or plan, not open a pull request |
| GitHub red CI | A failed check suite on a pull request | revise | Unattended, only on a branch the factory pushed itself, at most `FACTORY_CI_ATTEMPTS` per branch |
| GitHub new pull request | Opened by a person, not a bot | summarize | Unattended, one orientation comment and nothing else |
| Web chat | `start_factory_work` from the chat agent | request | The signed-in person |
| MCP (Claude, ChatGPT, Codex) | The same tool over Hubzoid's MCP server | request | The signed-in person |
| Slack | A message in a thread the connection watches | request | The linked person, in `allowed_groups` |
| Linear | An agent session on an issue | request | The linked person |
| ClickUp | A task moved to the trigger status (or given the trigger tag), in an allowed list | request | The linked person who moved it |
| API | `POST /portal/api/hubs/{hub}/work-items` with `{workflow: "factory", key, route, input: {request, subject}}` | the route asked for, within the caller's ceiling | The authenticated caller |

## GitHub

Two ways to connect (SDK `docs/channels/github.md`):

- **Your own GitHub App** for a hosted hub. Created through GitHub's manifest flow, owned by your account or organization, with metadata read, contents write, issues write, pull requests write, checks read and actions read. Each call uses a token narrowed to one repository and the permissions that call needs. Webhooks are verified with SHA-256 HMAC.
- **A personal token** for a laptop. Replies use your account and pushes use the whole token, so use a fine-grained token limited to the scratch repository. A laptop has no public address, so GitHub cannot deliver webhooks to it: use manual intake (`hubzoid channels github intake . github --url <issue> --task "..."`), or a forwarding tool with `webhook_secret_ref` set, in which case each delivery is verified with SHA-256 HMAC as in App mode.

`channels/github.yaml` must start the factory and set the routes:

```yaml
workflow: factory
run_as: workflow
provider_config:
  rules:
    mentions: true
    label: factory
    pr_opened: true
    ci_failure: true
    routes: {mention: request, review_mention: request, label: implement, pull_request: summarize, ci_failure: revise}
```

With the optional `status_failures` rule for `engineering-desk/review`, Engineering Desk's failed merge gate on a factory pull request is repaired like red CI, in its own rounds (SETUP.md, step 7).

The orientation comment has one owner. If GitZoid reviews pull requests in the same repository, turn `pr_opened` off in one of them.

## Slack and Linear

Copy `channels/slack.yaml.example` or `channels/linear.yaml.example` to `.yaml`, apply it, connect it (SDK `docs/channels/slack.md`, `docs/channels/linear.md`), link each person's account (`hubzoid channels link`), set `FACTORY_SLACK_CONNECTION` or `FACTORY_LINEAR_CONNECTION` and add the channel to `FACTORY_CHANNELS`. Progress and the wrap-up go back to the thread or the agent session. Unattended work never reads or writes Linear.

## ClickUp

ClickUp is built for teams whose requests start with people who are not engineers. A task moved to the trigger status (for example "ready for agent") starts factory work as the person who moved it. The task's name and description reach the stations as data, never as instructions. When the factory needs decisions it asks up to three plain-language questions as a task comment, with suggested answers, and moves the task to `statuses.question`. That person's next comment ("1 a, 2 b", or their own words) answers them and the work continues. The plan is attached to the task as a file (`FACTORY_PLAN_FORMAT`: Markdown by default, or HTML) and the task moves to `statuses.approval`. With `approve_in_task: true` in the channel file, that person replies `approve`, `change:` followed by what to change, or `reject`; otherwise, or as well, they approve in their Hubzoid Inbox, which the comment links to. Filter the board by the question and approval statuses to see everything waiting on people. The draft pull request is linked on the task (and the task in the pull request), its branch is named `factory/CU-<task id>-…`, and the task moves to `statuses.result`.

Copy `channels/clickup.yaml.example` to `channels/clickup.yaml`, put in your workspace and list ids, apply it, store the token, run `hubzoid channels clickup setup . clickup`, link each person (`hubzoid channels clickup members . clickup` lists their ClickUp ids), set `FACTORY_CLICKUP_CONNECTION: clickup` and add `clickup` to `FACTORY_CHANNELS`. The SDK page `docs/channels/clickup.md` covers the token, the webhooks and the statuses. With the connection set, a chat request can also name a task ("fix https://app.clickup.com/t/86abc"): the factory reads it through the same connection. Moving the task after the pull request merges is left to people or ClickUp's own GitHub integration.

With several repositories (`FACTORY_REPOS`), give each task one tag equal to its repository's short name (`api`) or `owner/name`. A task with none, or with two, gets the question "Which repository?" as a task comment, and the person's reply (the repository's name) continues it. ClickUp sends the factory a task's first 20 tags.

## Follow-ups and stopping

A follow-up from the person who asked, in the same thread or chat, reaches the next station as their instruction. "stop" stops the work at the next step. Anyone else waits their turn. Cancel from the Console (Work items) or `hubzoid work-items cancel . ITEM`.

## Other trackers

Trackers other than Linear and ClickUp are not built in. If a tracker has an MCP server, connect it in Settings, then ask in chat ("pull task 86xyz into a factory request"). The chat agent reads the task with that server's tools and starts factory work as you.
