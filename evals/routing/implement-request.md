---
tags: [fast, routing]
fake_tools:
  - tool: factory_repository
    output: {repository: example-co/widget, repository_id: 2001, connection: github, label: factory, branch_prefix: factory/}
  - tool: github__getIssueContext
    output:
      data:
        issue: {number: 12, title: "total() returns one too many", state: open, body: "Synthetic sample. total([1, 2]) returns 4.", labels: []}
        comments: []
        omitted_count: 0
  - tool: github__searchIssues
    output: {data: [], truncated: false}
  - tool: github__listLabels
    output: {data: [{name: bug}, {name: enhancement}, {name: documentation}, {name: factory}]}
  - tool: github__listIssues
    output: {data: [], next_cursor: null}
  - tool: start_factory_work
    output: {work_item: 9f1c2d3e-0000-4000-8000-000000000004, state: accepted, created: true, link: /settings#/me/work/factory/9f1c2d3e}
expect_tools: [start_factory_work]
expect_tool_args:
  start_factory_work: {issue_number: 12}
real_tools: [load_skill, read_knowledge, list_knowledge, list_files, search_sources]
---
## Prompt
Please fix issue #12, total() returns one too many.

## Criteria
Starts factory work for issue #12 and tells the person what happens next: a plan for them to approve, then implementation, an independent review and a draft pull request. Gives the link.
