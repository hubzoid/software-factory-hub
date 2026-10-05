---
tags: [fast, routing]
fake_tools:
  - tool: factory_repository
    output: {repository: example-co/widget, repository_id: 2001, connection: github, label: factory, branch_prefix: factory/}
  - tool: ask_question
    output: {answer: "The password reset emails, they arrive twice."}
  - tool: github__searchIssues
    output: {data: [], truncated: false}
  - tool: github__listLabels
    output: {data: [{name: bug}, {name: enhancement}, {name: documentation}, {name: factory}]}
  - tool: github__listIssues
    output: {data: [], next_cursor: null}
  - tool: start_factory_work
    output: {work_item: 9f1c2d3e-0000-4000-8000-000000000005, state: accepted, created: true, link: /settings#/me/work/factory/9f1c2d3e}
real_tools: [load_skill, read_knowledge, list_knowledge, list_files, search_sources]
---
## Prompt
fix the emails

## Criteria
Either asks one or two specific clarifying questions (which emails, what is wrong, where), or hands it to the factory, which will ask. Does not invent details about what "the emails" are.
