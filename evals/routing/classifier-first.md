---
tags: [fast, routing]
fake_tools:
  - tool: factory_repository
    output: {repository: example-co/widget, repository_id: 2001, connection: github, label: factory, branch_prefix: factory/}
  - tool: github__getIssueContext
    output:
      data:
        issue: {number: 3, title: "Password reset emails sometimes arrive twice", state: open, body: "Synthetic sample. Some users get two reset emails a few seconds apart.", labels: []}
        comments: []
        omitted_count: 0
  - tool: github__searchIssues
    output: {data: [], truncated: false}
  - tool: github__listLabels
    output: {data: [{name: bug}, {name: enhancement}, {name: documentation}, {name: factory}]}
  - tool: github__listIssues
    output: {data: [], next_cursor: null}
  - tool: start_factory_work
    output: {work_item: 9f1c2d3e-0000-4000-8000-000000000003, state: accepted, created: true, link: /settings#/me/work/factory/9f1c2d3e}
expect_tools: [start_factory_work]
expect_tool_args:
  start_factory_work: {route: plan}
real_tools: [load_skill, read_knowledge, list_knowledge, list_files, search_sources]
---
## Prompt
Password reset emails sometimes arrive twice (issue #3). Classify it and plan a fix, but stop after the analysis. Don't implement anything.

## Criteria
Starts factory work for issue #3 limited to a plan (route plan), and says the factory will classify and plan without implementing.
