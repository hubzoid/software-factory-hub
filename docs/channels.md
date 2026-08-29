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
| API | `POST /portal/api/hubs/{hub}/work-items` with `{workflow: "factory", key, route, input: {request, subject}}` | the route asked for, within the caller's ceiling | The authenticated caller |

## GitHub

Two ways to connect (SDK `docs/channels/github.md`):

- **Your own GitHub App** for a hosted hub. Created through GitHub's manifest flow, owned by your account or organization, with metadata read, contents write, issues write, pull requests write, checks read and actions read. Each call uses a token narrowed to one repository and the permissions that call needs. Webhooks are verified with SHA-256 HMAC.
- **A personal token** for a laptop. Replies use your account and pushes use the whole token, so use a fine-grained token limited to the scratch repository. Webhooks are not verified in this mode: use manual intake (`hubzoid channels github intake . github --url <issue> --task "..."`) or a forwarding tool.

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

The orientation comment has one owner. If GitZoid reviews pull requests in the same repository, turn `pr_opened` off in one of them.

## Slack and Linear

Copy `channels/slack.yaml.example` or `channels/linear.yaml.example` to `.yaml`, apply it, connect it (SDK `docs/channels/slack.md`, `docs/channels/linear.md`), link each person's account (`hubzoid channels link`), set `FACTORY_SLACK_CONNECTION` or `FACTORY_LINEAR_CONNECTION` and add the channel to `FACTORY_CHANNELS`. Progress and the wrap-up go back to the thread or the agent session. Unattended work never reads or writes Linear.

## Follow-ups and stopping

A follow-up from the person who asked, in the same thread or chat, reaches the next station as their instruction. "stop" stops the work at the next step. Anyone else waits their turn. Cancel from the Console (Work items) or `hubzoid work-items cancel . ITEM`.

## Other trackers

ClickUp, Jira and others: connect their MCP server in Settings, then ask in chat ("pull ClickUp task 86xyz into a factory request"). The chat agent reads the task and starts factory work as you.
