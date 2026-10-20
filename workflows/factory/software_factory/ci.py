"""Admission for the revise route: red CI and requested changes on a factory
pull request.

Foreman's CI loop (``agent/channels/github.ts:102-125, 201-221``, MIT,
Vercel) trusts the branch prefix and counts its own comments, judged by the
model. HUB-6 names both as weaknesses. Here a repair needs, freshly checked:

* a pull request in the configured repository, not from a fork;
* a branch the factory pushed itself (its ledger and the SDK's record of the
  push), with the failing head equal to the pull request's current head and
  to the factory's last push;
* checks still failing at that head;
* an attempt left, counted once per failing head in the ledger, capped at
  ``FACTORY_CI_ATTEMPTS`` and surviving restarts. A slot names the work
  that took it, so that work may run again after a manager restarts it,
  while other work for the same head stays a duplicate.

The attempt comment is posted before the repair starts, so a run that dies
mid-repair still counts. Stale or duplicate events stop quietly.
"""
from __future__ import annotations

from hubzoid import hub

from . import github, progress, publish, routes
from .errors import FactoryStop


class Quiet(FactoryStop):
    """Nothing to do and nothing to say (green checks, a stale head, a duplicate)."""


ATTEMPT = "factory_v1:ci:{rid}:{branch}:{n}"


def slots(repository_id: int, branch: str, cap: int) -> list[dict]:
    """The repair attempts already used on this branch, in order: the failing
    head and the work item that took the slot. Each attempt is its own
    write-once key, so no other writer's update of the branch ledger can
    erase one, and a new head never resets the count."""
    out = []
    for n in range(1, cap + 2):
        value = hub.shared_state.get(ATTEMPT.format(rid=repository_id, branch=branch, n=n))
        if not value:
            break
        out.append(value if isinstance(value, dict) else {"head": value, "item": None})
    return out


def attempts(repository_id: int, branch: str, cap: int) -> list[str]:
    """The failing heads that already used a repair attempt on this branch."""
    return [s["head"] for s in slots(repository_id, branch, cap)]


def reserve(repository_id: int, branch: str, head: str, cap: int) -> int | None:
    """This failing head's attempt number, reserving the next slot once.
    None when the cap is used up. CI work on one pull request runs one at a
    time (one active work item per thread), so slots are not contended."""
    used = attempts(repository_id, branch, cap)
    if head in used:
        return used.index(head) + 1
    if len(used) >= cap:
        return None
    hub.shared_state[ATTEMPT.format(rid=repository_id, branch=branch, n=len(used) + 1)] = {
        "head": head, "item": hub.work_item.id}
    return len(used) + 1


def _prior(owner_item: str) -> dict:
    """The classification and plan of the work that created the branch, with
    its analysis handoff copied into this work item."""
    from hubzoid.work_items import store as wi_store
    from hubzoid.workflows import context

    from .pipeline import carry_handoff

    item = wi_store.get_item(context._ctx().hub_dir, owner_item) if owner_item else None
    result = (((item or {}).get("result_json") or {}).get("result") or {}).get("factory_v1") or {}
    analysis = dict(result["analysis"]) if result.get("analysis") else None
    if analysis:
        analysis["handoff_id"] = carry_handoff(owner_item, analysis.get("handoff_id"))
    return {"classification": result.get("classification"), "analysis": analysis}


def _fallback(branch: str) -> dict:
    return {
        "classification": {"type": "bug", "priority": "high", "complexity": "small", "affected_area": "CI",
                           "actionable": True, "needs_clarification": False, "questions": [],
                           "summary": f"Make the failing checks on {branch} pass."},
        "analysis": {"problem_statement": f"The checks fail on the factory branch {branch}.",
                     "approach": "Diagnose the failing checks from their logs and make the smallest fix.",
                     "plan": ["Read the failing check logs", "Fix the cause", "Run the same checks locally"],
                     "affected_surface": [], "risks": [], "acceptance_criteria": ["The failing checks pass."],
                     "test_strategy": "Run the failing checks' commands in the checkout.", "assumptions": [],
                     "open_questions": [], "handoff_id": None},
    }


def _pr(repo, number: int) -> dict:
    ctx = github.read("getPullRequestContext", repository_id=repo.repository_id, number=number)["data"]
    pr = ctx.get("pull_request") or {}
    head = pr.get("head") or {}
    return {"number": number, "branch": head.get("ref"), "head_sha": ctx.get("head_sha"),
            "fork": bool((head.get("repo") or {}).get("fork")) or (
                (head.get("repo") or {}).get("full_name", repo.full_name).lower() != repo.full_name.lower()),
            "url": pr.get("html_url"), "title": pr.get("title"), "state": pr.get("state")}


def require_open(repo, number: int, *, expected_head: str | None = None) -> dict:
    """Recheck provider state at admission, publication and delivery.

    Admission and publication call this within their saved observations:
    check fresh state before a new side effect, then replay that saved step
    without retroactively contradicting completed writes. Delivery validates
    its saved heads observation with check_open. Publication leases the head.
    """
    state = github.pull_request_state(repo.repository_id, number)
    return check_open(state, expected_head=expected_head)


def check_open(state: dict, *, expected_head: str | None = None) -> dict:
    """Validate a saved provider observation without rereading on replay."""
    if state["state"] != "open" or state["merged"]:
        raise FactoryStop("pull_request_closed", "The pull request is closed or merged. No automated revision "
                          "will be published; start a new request if more work is needed.")
    if expected_head is not None and state["head_sha"] != expected_head:
        raise FactoryStop("head_changed", "The pull request head changed. A person must review before continuing.")
    return state


def admit(r) -> dict:
    data = r.request.data
    number = r.request.subject.number
    cap = r.settings["FACTORY_CI_ATTEMPTS"]

    def check() -> dict:
        repo = github.repo()
        if r.request.subject.repository_id not in (None, repo.repository_id):
            return {"quiet": "other_repository"}
        pr = _pr(repo, number)
        try:
            require_open(repo, number)
        except FactoryStop as stop:
            return {"quiet": stop.code}
        if pr["fork"]:
            return {"stop": "fork_pull_request", "message": "Pull requests from forks never get automated repair."}
        if pr["head_sha"] != data.get("head_sha"):
            return {"quiet": "stale_head"}
        try:
            entry = publish.verify_owned(repo.repository_id, pr["branch"], pr["head_sha"])
        except FactoryStop as stop:
            return {"quiet": stop.code} if stop.code == "not_factory_branch" else {"stop": stop.code,
                                                                                  "message": stop.message}
        if entry.get("pr_number") not in (None, number):
            return {"quiet": "not_bound_pull_request"}
        failing = github.read("getCiFailureContext", repository_id=repo.repository_id, head_sha=pr["head_sha"],
                              number=number)["data"]
        if not failing.get("jobs"):
            return {"quiet": "ci_not_failing"}
        taken = slots(repo.repository_id, pr["branch"], cap)
        used = [s["head"] for s in taken]
        mine = next((s for s in taken if s["head"] == pr["head_sha"]), None)
        if mine and mine["item"] != hub.work_item.id:
            return {"quiet": "duplicate_failure"}
        prior = _prior(entry.get("owner_item"))
        if not prior.get("analysis"):
            prior = _fallback(pr["branch"])
        analysis = dict(prior["analysis"])
        analysis["acceptance_criteria"] = list(analysis.get("acceptance_criteria") or []) + [
            "The checks that failed at the previous head pass, without weakening or skipping them."]
        return {"repo": repo.__dict__, "pr": pr, "attempts": used, "exhausted": not mine and len(used) >= cap,
                "owner_item": entry.get("owner_item"), "ci_context": failing,
                "classification": prior["classification"], "analysis": analysis, "brain": _brain_of(repo), "context_revision": _revision_of(repo)}

    out = hub.work_item.checkpoint(routes.CI_CHECK, check)
    if out.get("quiet"):
        raise Quiet(out["quiet"], "")
    if out.get("stop"):
        raise FactoryStop(out["stop"], out["message"])
    r.repo = github.Repo(**out["repo"])
    pr = out["pr"]
    if out["exhausted"]:
        # The pull request is this work's own thread: the stop reply says it once.
        raise FactoryStop("ci_attempts_exhausted", f"Pausing automated CI fixes on this pull request to avoid a loop: "
                          f"{cap} attempts have not turned the checks green. A person needs to take it from here.")
    attempt = reserve(r.repo.repository_id, pr["branch"], pr["head_sha"], cap)
    if attempt is None:
        raise FactoryStop("ci_attempts_exhausted", f"{cap} CI repair attempts did not turn the checks green.")
    broken = ", ".join(j.get("name") or "a check" for j in out["ci_context"].get("jobs") or [])
    # Posted before the repair starts, so a run that dies mid-repair still counts.
    progress.reply(f"CI fix attempt {attempt} of {cap} starting on `{pr['head_sha'][:12]}`. Failing: {broken}.",
                   key=f"ci-attempt:{pr['head_sha']}", kind="progress")
    r.ground.update(brain=out["brain"], context_revision=out["context_revision"], subject={"number": number, "url": pr["url"], "title": pr["title"]},
                    subject_text={"title": pr["title"], "failing_checks": out["ci_context"]})
    r.record.update(repository=r.repo.full_name, branch=pr["branch"], ci_attempt=attempt, failing_head=pr["head_sha"])
    progress.record(branch=pr["branch"], ci_attempt=attempt)
    return {"branch": pr["branch"], "head_sha": pr["head_sha"], "owner_item": out["owner_item"],
            "classification": out["classification"], "analysis": out["analysis"], "ci_context": out["ci_context"],
            "revision": 1, "pr_number": number}


def admit_attended(r) -> dict:
    """A person asks to change a factory pull request (a review mention, or
    chat naming the pull request). Same ownership proof, no CI counter."""
    number = r.request.subject.number

    def check() -> dict:
        repo = github.repo()
        if not number:
            return {"stop": "policy_denied", "message": "Name the factory pull request to revise."}
        pr = _pr(repo, number)
        try:
            require_open(repo, number)
        except FactoryStop as stop:
            return {"stop": stop.code, "message": stop.message}
        if pr["fork"]:
            return {"stop": "fork_pull_request", "message": "Pull requests from forks are never changed by the "
                                                            "factory."}
        try:
            entry = publish.verify_owned(repo.repository_id, pr["branch"], pr["head_sha"])
        except FactoryStop as stop:
            return {"stop": stop.code, "message": stop.message}
        prior = _prior(entry.get("owner_item"))
        if not prior.get("analysis"):
            prior = _fallback(pr["branch"])
        return {"repo": repo.__dict__, "pr": pr, "owner_item": entry.get("owner_item"),
                "classification": prior["classification"], "analysis": prior["analysis"], "brain": _brain_of(repo),
                "context_revision": _revision_of(repo)}

    out = hub.work_item.checkpoint(routes.CI_CHECK, check)
    if out.get("stop"):
        raise FactoryStop(out["stop"], out["message"])
    r.repo = github.Repo(**out["repo"])
    pr = out["pr"]
    where = ""
    if r.request.data.get("path"):
        where = f" (on {r.request.data['path']}" + (f" line {r.request.data['line']}" if r.request.data.get(
            "line") else "") + ")"
    r.ground.update(brain=out["brain"], context_revision=out["context_revision"], subject={"number": number, "url": pr["url"], "title": pr["title"]},
                    subject_text={"title": pr["title"]})
    r.record.update(repository=r.repo.full_name, branch=pr["branch"])
    return {"branch": pr["branch"], "head_sha": pr["head_sha"], "owner_item": out["owner_item"],
            "classification": out["classification"], "analysis": out["analysis"], "ci_context": None,
            "revision": 1, "pr_number": number,
            "findings": [f"The requester asked{where}: {r.request.instruction}"]}


def _brain_of(repo) -> str:
    """Read inside the saved admission stage, so a replay sees the same brain."""
    from pathlib import Path

    from hubzoid.workflows import context

    from . import brain

    return brain.for_station(Path(context._ctx().hub_dir), repo.full_name)


def _revision_of(repo) -> str:
    from hubzoid.workflows import context
    from . import brain

    return brain.revision(context._ctx().hub_dir, repo.full_name)
