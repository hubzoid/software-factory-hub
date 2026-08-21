"""The factory's seven routes, as Hubzoid work-item routes (HUB-6 section 6).

A route is a ceiling: the stages a work item may run and the external actions
it may take. A run can narrow its route, never widen it. Intake picks the
ceiling from the trigger. A person's request (chat, a mention, Slack, Linear)
arrives under ``request``, the union of every attended route, and the
tool-less scope step narrows it to exactly one route before anything else
runs. The label arrives under ``implement``, red CI under ``revise`` and a new
pull request under ``summarize``.
"""
from __future__ import annotations

from hubzoid.work_items import Route

#: Channel replies (progress, questions, the wrap-up) on the work's own thread.
REPLY = "channel.reply"
#: GitHub writes through the SDK's recorded operations (comments, labels,
#: issue state, the draft pull request).
GITHUB = "github.write"
#: Publishing a checked patch to a factory branch (the SDK's push_branch).
PUSH = "github.push"
#: Changing a pull request, including marking it ready. Waits for the
#: requester's approval of the exact change (work-items.yaml).
PR_UPDATE = "github.pr_update"

#: Stage names, in pipeline order. They appear in the work item's saved stages.
SCOPE, GROUND, CLASSIFY, LABEL, RESEARCH, ANALYZE = "scope", "ground", "classify", "label", "research", "analyze"
PLAN_REVIEW, IMPLEMENT, PUBLISH, REVIEW, DELIVER = "plan_review", "implement", "publish", "review", "deliver"
ANSWER, SUMMARIZE, ACT, CI_CHECK = "answer", "summarize", "act", "ci_check"

TERMINAL_STAGE = {
    "answer": ANSWER,
    "triage": LABEL,
    "plan": ANALYZE,
    "implement": DELIVER,
    "revise": DELIVER,
    "summarize": SUMMARIZE,
    "act": ACT,
}

_SPEC: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "answer": ((SCOPE, GROUND, ANSWER), (REPLY,)),
    "triage": ((SCOPE, GROUND, CLASSIFY, LABEL, DELIVER), (REPLY, GITHUB)),
    "plan": ((SCOPE, GROUND, CLASSIFY, LABEL, RESEARCH, ANALYZE, DELIVER), (REPLY, GITHUB)),
    "implement": ((SCOPE, GROUND, CLASSIFY, LABEL, RESEARCH, ANALYZE, PLAN_REVIEW, IMPLEMENT, PUBLISH, REVIEW,
                   DELIVER), (REPLY, GITHUB, PUSH)),
    "revise": ((SCOPE, CI_CHECK, GROUND, IMPLEMENT, PUBLISH, REVIEW, DELIVER), (REPLY, GITHUB, PUSH)),
    "summarize": ((SCOPE, SUMMARIZE), (REPLY,)),
    "act": ((SCOPE, ACT, DELIVER), (REPLY, GITHUB, PR_UPDATE)),
}

#: Routes a person's request may narrow to. `summarize` is unattended only.
ATTENDED = ("answer", "triage", "plan", "implement", "revise", "act")


def _union(names) -> tuple[tuple[str, ...], tuple[str, ...]]:
    stages: list[str] = []
    actions: list[str] = []
    for name in names:
        for s in _SPEC[name][0]:
            if s not in stages:
                stages.append(s)
        for a in _SPEC[name][1]:
            if a not in actions:
                actions.append(a)
    return tuple(stages), tuple(actions)


#: The declaration for @workflow(work_items=...). `request` comes first, so a
#: channel that names no route (Slack, Linear) lands on it.
ROUTES: dict[str, Route] = {"request": Route(stages=_union(ATTENDED)[0], actions=_union(ATTENDED)[1])}
ROUTES.update({name: Route(stages=stages, actions=actions) for name, (stages, actions) in _SPEC.items()})

ALL = tuple(ROUTES)


def stages(route: str) -> tuple[str, ...]:
    return tuple(ROUTES[route].stages or ())


def actions(route: str) -> tuple[str, ...]:
    return tuple(ROUTES[route].actions or ())


def narrower(ceiling: str, route: str) -> bool:
    """Whether `route` fits inside `ceiling` (the only direction a run moves)."""
    c, r = ROUTES[ceiling], ROUTES[route]
    return set(r.stages or ()) <= set(c.stages or ()) and set(r.actions or ()) <= set(c.actions or ())
