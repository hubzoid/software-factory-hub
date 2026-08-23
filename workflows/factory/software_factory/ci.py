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
  ``FACTORY_CI_ATTEMPTS`` and surviving restarts.

The attempt comment is posted before the repair starts, so a run that dies
mid-repair still counts. Stale or duplicate events stop quietly.
"""
from __future__ import annotations

from hubzoid import hub

from . import github, progress, publish, routes
from .errors import FactoryStop


class Quiet(FactoryStop):
    """Nothing to do and nothing to say (green checks, a stale head, a duplicate)."""


def _prior(owner_item: str) -> dict:
    """The classification and plan of the work that created the branch."""
    from hubzoid.work_items import store as wi_store
    from hubzoid.workflows import context

    item = wi_store.get_item(context._ctx().hub_dir, owner_item) if owner_item else None
    result = (((item or {}).get("result_json") or {}).get("result") or {}).get("factory_v1") or {}
    return {"classification": result.get("classification"), "analysis": result.get("analysis")}


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


def admit(r) -> dict:
    data = r.request.data
    number = r.request.subject.number
    cap = int(hub.setting("FACTORY_CI_ATTEMPTS", 2))

    def check() -> dict:
        repo = github.repo()
        if r.request.subject.repository_id not in (None, repo.repository_id):
            return {"quiet": "other_repository"}
        pr = _pr(repo, number)
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
        attempts = list(entry.get("ci_attempts") or [])
        if pr["head_sha"] in attempts:
            return {"quiet": "duplicate_failure"}
        prior = _prior(entry.get("owner_item"))
        if not prior.get("analysis"):
            prior = _fallback(pr["branch"])
        analysis = dict(prior["analysis"])
        analysis["acceptance_criteria"] = list(analysis.get("acceptance_criteria") or []) + [
            "The checks that failed at the previous head pass, without weakening or skipping them."]
        return {"repo": repo.__dict__, "pr": pr, "attempts": attempts, "exhausted": len(attempts) >= cap,
                "owner_item": entry.get("owner_item"), "ci_context": failing,
                "classification": prior["classification"], "analysis": analysis}

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
    attempt = len(out["attempts"]) + 1
    entry = publish.ledger_get(r.repo.repository_id, pr["branch"]) or {}
    if pr["head_sha"] not in (entry.get("ci_attempts") or []):
        publish.ledger_put(r.repo.repository_id, pr["branch"],
                           dict(entry, ci_attempts=list(entry.get("ci_attempts") or []) + [pr["head_sha"]]))
    broken = ", ".join(j.get("name") or "a check" for j in out["ci_context"].get("jobs") or [])
    # Posted before the repair starts, so a run that dies mid-repair still counts.
    progress.reply(f"CI fix attempt {attempt} of {cap} starting on `{pr['head_sha'][:12]}`. Failing: {broken}.",
                   key=f"ci-attempt:{pr['head_sha']}", kind="progress")
    r.ground.update(brain=_brain(r), subject={"number": number, "url": pr["url"], "title": pr["title"]},
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
                "classification": prior["classification"], "analysis": prior["analysis"]}

    out = hub.work_item.checkpoint(routes.CI_CHECK, check)
    if out.get("stop"):
        raise FactoryStop(out["stop"], out["message"])
    r.repo = github.Repo(**out["repo"])
    pr = out["pr"]
    where = ""
    if r.request.data.get("path"):
        where = f" (on {r.request.data['path']}" + (f" line {r.request.data['line']}" if r.request.data.get(
            "line") else "") + ")"
    r.ground.update(brain=_brain(r), subject={"number": number, "url": pr["url"], "title": pr["title"]},
                    subject_text={"title": pr["title"]})
    r.record.update(repository=r.repo.full_name, branch=pr["branch"])
    return {"branch": pr["branch"], "head_sha": pr["head_sha"], "owner_item": out["owner_item"],
            "classification": out["classification"], "analysis": out["analysis"], "ci_context": None,
            "revision": 1, "pr_number": number,
            "findings": [f"The requester asked{where}: {r.request.instruction}"]}


def _brain(r) -> str:
    from pathlib import Path

    from hubzoid.workflows import context

    from . import brain

    return brain.for_station(Path(context._ctx().hub_dir), r.repo.full_name)
