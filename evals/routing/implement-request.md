---
tags: [fast, routing]
fake_tools:
  - tool: start_factory_work
    output: {work_item: 9f1c2d3e-0000-4000-8000-000000000004, state: accepted, created: true, link: /settings#/me/work/factory/9f1c2d3e}
expect_tools: [start_factory_work]
expect_tool_args:
  start_factory_work: {issue_number: 12}
---
## Prompt
Please fix issue #12, total() returns one too many.

## Criteria
Starts factory work for issue #12 and tells the person what happens next: a plan for them to approve, then implementation, an independent review and a draft pull request. Gives the link.
