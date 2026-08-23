---
tags: [fast, routing]
fake_tools:
  - tool: start_factory_work
    output: {work_item: 9f1c2d3e-0000-4000-8000-000000000003, state: accepted, created: true, link: /settings#/me/work/factory/9f1c2d3e}
expect_tools: [start_factory_work]
expect_tool_args:
  start_factory_work: {route: plan}
---
## Prompt
Password reset emails sometimes arrive twice (issue #3). Classify it and plan a fix, but stop after the analysis. Don't implement anything.

## Criteria
Starts factory work for issue #3 limited to a plan (route plan), and says the factory will classify and plan without implementing.
