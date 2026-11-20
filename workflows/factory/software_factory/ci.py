"""Admission for the revise route: red CI and requested changes on a factory
pull request.

The upstream template's CI loop (``agent/channels/github.ts:102-125, 201-221``, MIT,
Vercel) trusts the branch prefix and counts its own comments, judged by the
model. Both are weak checks. Here a repair needs, freshly checked:

* a pull request in the configured repository, not from a fork;
* a branch the factory pushed itself (its ledger and the SDK's record of the
  push), with the failing head equal to the pull request's current head and
  to the factory's last push;
* checks still failing at that head;
* an attempt left, counted once per failing head in the ledger, capped at
  ``FACTORY_CI_ATTEMPTS`` and surviving restarts. A slot names the work
  that took it, so that work may run again after a manager restarts it,
  while other work for the same head stays a duplicate.

Engineering Desk's merge gate reaches the same path: a failed
``engineering-desk/review`` status (the GitHub channel's
``rules.status_failures``) arrives as a failed check whose job has
``kind: status`` and the Desk's summary comment. Its rounds have their own
ledger and cap (``FACTORY_DESK_ATTEMPTS``), so a red CI run never uses up the
Desk's rounds or the other way round. One repair runs per head whatever
failed, and charges each kind it repairs. A Desk failure counts only when the
summary names the exact failing head (its hidden head marker); otherwise the
repair stops without using a round. Machinist's PR watcher treats failing
statuses the same way (``internal/controlplane/github_followups.go``).

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
DESK_ATTEMPT = "factory_v1:desk:{rid}:{branch}:{n}"
DESK_HEAD = "<!-- engineering-desk:head:{sha} -->"
LEDGERS = {"check": ATTEMPT, "status": DESK_ATTEMPT}
SINGULAR = {"check": "CI fix", "status": "Engineering Desk fix"}


def slots(repository_id: int, branch: str, cap: int, ledger: str = ATTEMPT) -> list[dict]:
    """The repair attempts already used on this branch, in order: the failing
    head and the work item that took the slot. Each attempt is its own
    write-once key, so no other writer's update of the branch ledger can
    erase one, and a new head never resets the count."""
    out = []
    for n in range(1, cap + 2):
        value = hub.shared_state.get(ledger.format(rid=repository_id, branch=branch, n=n))
        if not value:
            break
        out.append(value if isinstance(value, dict) else {"head": value, "item": None})
    return out


def attempts(repository_id: int, branch: str, cap: int, ledger: str = ATTEMPT) -> list[str]:
    """The failing heads that already used a repair attempt on this branch."""
    return [s["head"] for s in slots(repository_id, branch, cap, ledger)]


def reserve(repository_id: int, branch: str, head: str, cap: int, ledger: str = ATTEMPT,
            extra: dict | None = None) -> int | None:
    """This failing head's attempt number, reserving the next slot once.
    None when the cap is used up. CI work on one pull request runs one at a
    time (one active work item per thread), so slots are not contended."""
    used = attempts(repository_id, branch, cap, ledger)
    if head in used:
        return used.index(head) + 1
    if len(used) >= cap:
        return None
    hub.shared_state[ledger.format(rid=repository_id, branch=branch, n=len(used) + 1)] = {
        "head": head, "item": hub.work_item.id, **(extra or {})}
    return len(used) + 1


def desk_evidence(job: dict, head: str) -> bool:
    """The Desk's summary comment names this exact head."""
    return DESK_HEAD.format(sha=head) in str(job.get("comment") or "")


def _kind(job: dict) -> str:
    return "status" if job.get("kind") == "status" else "check"


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
            "base": (pr.get("base") or {}).get("ref"),
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

    desk_cap = r.settings.get("FACTORY_DESK_ATTEMPTS", 2)
    caps = {"check": cap, "status": desk_cap}

    def check() -> dict:
        entry = github.entry_for(r.request.subject.repository_id) if r.request.subject.repository_id else None
        if entry is None:
            return {"quiet": "other_repository"}
        repo = github.repo(entry, check_base=False)     # an existing pull request keeps its own base
        pr = _pr(repo, number)
        repo.base_branch = pr.get("base") or repo.base_branch
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
        jobs = failing.get("jobs") or []
        if not jobs:
            return {"quiet": "ci_not_failing"}
        unproven = [j["name"] for j in jobs if _kind(j) == "status" and not desk_evidence(j, pr["head_sha"])]
        jobs = [j for j in jobs if _kind(j) == "check" or desk_evidence(j, pr["head_sha"])]
        kinds = sorted({_kind(j) for j in jobs})
        used, exhausted, earlier = {}, [], []
        for kind in ("check", "status"):
            taken = slots(repo.repository_id, pr["branch"], caps[kind], LEDGERS[kind])
            if kind == "status":
                earlier = [s["findings"] for s in taken if s.get("findings") and s["head"] != pr["head_sha"]]
            mine = next((s for s in taken if s["head"] == pr["head_sha"]), None)
            if mine and mine["item"] != hub.work_item.id:
                return {"quiet": "duplicate_failure"}      # one repair per head, whatever failed
            used[kind] = [s["head"] for s in taken]
            if kind in kinds and not mine and len(taken) >= caps[kind]:
                exhausted.append(kind)
        if not kinds:
            return {"stop": "desk_evidence_missing", "message": "Engineering Desk's status failed, but its summary "
                    f"does not name the head {pr['head_sha'][:12]}, so the factory does not act on it. No repair "
                    "round was used. A person can check the review, or the Desk reviews the head again."}
        failing = {**failing, "jobs": [j for j in jobs if _kind(j) not in exhausted]}
        if earlier:
            # Found live: a later round undid an earlier round's fix because
            # the original plan still said otherwise. Earlier findings travel
            # with the branch, as data.
            failing["earlier_desk_findings"] = earlier
        prior = _prior(entry.get("owner_item"))
        if not prior.get("analysis"):
            prior = _fallback(pr["branch"])
        analysis = dict(prior["analysis"])
        repairing = [k for k in kinds if k not in exhausted]
        added = []
        if "check" in repairing:
            added.append("The checks that failed at the previous head pass, without weakening or skipping them.")
        if "status" in repairing:
            added.append("Each blocking Engineering Desk finding at the previous head is fixed, or explained in "
                         "deviations as not a defect. Where a finding conflicts with an earlier acceptance "
                         "criterion, the finding wins and the deviation names the criterion it replaces.")
        if earlier:
            added.append("Fixes already made on this branch for earlier Engineering Desk findings (earlier_desk_findings "
                         "in the failing checks) stay in place. Those findings also win over conflicting earlier "
                         "acceptance criteria.")
        analysis["acceptance_criteria"] = list(analysis.get("acceptance_criteria") or []) + added
        return {"repo": repo.__dict__, "pr": pr, "attempts": used, "kinds": [k for k in kinds if k not in exhausted],
                "exhausted": exhausted, "unproven": unproven,
                "owner_item": entry.get("owner_item"), "ci_context": failing,
                "classification": prior["classification"], "analysis": analysis, "brain": _brain_of(repo), "context_revision": _revision_of(repo)}

    out = hub.work_item.checkpoint(routes.CI_CHECK, check)
    if out.get("quiet"):
        raise Quiet(out["quiet"], "")
    if out.get("stop"):
        raise FactoryStop(out["stop"], out["message"])
    r.repo = github.bind(github.Repo(**out["repo"]))
    pr = out["pr"]
    # Work admitted before the Desk loop saved `exhausted` as a flag for CI.
    exhausted = out["exhausted"] if isinstance(out["exhausted"], list) else (["check"] if out["exhausted"] else [])
    kinds = out.get("kinds", [] if exhausted else ["check"])
    names = {"check": "CI fixes", "status": "Engineering Desk fixes"}
    if not kinds:
        # The pull request is this work's own thread: the stop reply says it once.
        what = " and ".join(names[k] for k in exhausted)
        raise FactoryStop("ci_attempts_exhausted", f"Pausing automated {what} on this pull request to avoid a loop: "
                          "the allowed attempts have not turned it green. A person needs to take it from here.")
    numbers, taken = [], {}
    for kind in kinds:
        extra = None
        if kind == "status":
            text = "\n\n".join(str(j.get("comment") or j.get("summary") or "") for j in out["ci_context"].get("jobs") or []
                               if _kind(j) == "status")
            extra = {"findings": text[:4000]}
        n = reserve(r.repo.repository_id, pr["branch"], pr["head_sha"], caps[kind], LEDGERS[kind], extra)
        if n is None:
            raise FactoryStop("ci_attempts_exhausted", f"The allowed {names[kind]} did not turn it green.")
        taken[kind] = n
        numbers.append(f"{SINGULAR[kind]} attempt {n} of {caps[kind]}")
    jobs = out["ci_context"].get("jobs") or []
    broken = ", ".join(("Engineering Desk findings" if _kind(j) == "status" else j.get("name") or "a check")
                       for j in jobs)
    left = "".join(f" {names[k]} are used up, so a person takes those from here." for k in exhausted)
    if out.get("unproven"):
        left += " Engineering Desk's status failed but its summary is for another head, so it is left as it is."
    # Posted before the repair starts, so a run that dies mid-repair still counts.
    progress.reply(f"{'; '.join(numbers)} starting on `{pr['head_sha'][:12]}`. Failing: {broken}.{left}",
                   key=f"ci-attempt:{pr['head_sha']}", kind="progress")
    attempt = taken.get("check")
    desk_attempt = taken.get("status")
    r.ground.update(brain=out["brain"], context_revision=out["context_revision"], subject={"number": number, "url": pr["url"], "title": pr["title"]},
                    subject_text={"title": pr["title"], "failing_checks": out["ci_context"]})
    r.record.update(repository=r.repo.full_name, base_branch=r.repo.base, branch=pr["branch"], ci_attempt=attempt,
                    desk_attempt=desk_attempt, failing_head=pr["head_sha"], repair_kinds=kinds)
    progress.record(branch=pr["branch"], ci_attempt=attempt, desk_attempt=desk_attempt)
    return {"branch": pr["branch"], "head_sha": pr["head_sha"], "owner_item": out["owner_item"],
            "classification": out["classification"], "analysis": out["analysis"], "ci_context": out["ci_context"],
            "revision": 1, "pr_number": number}


def admit_attended(r) -> dict:
    """A person asks to change a factory pull request (a review mention, or
    chat naming the pull request). Same ownership proof, no CI counter."""
    number = r.request.subject.number
    from .pipeline import _target

    target = None if r.request.subject.repository_id else _target(r)

    def check() -> dict:
        entry = github.entry_for(r.request.subject.repository_id) if r.request.subject.repository_id else target
        if entry is None:
            return {"stop": "repository_unavailable", "message": "This pull request is not in one of the factory's "
                    "repositories."}
        repo = github.repo(entry, check_base=False)     # an existing pull request keeps its own base
        if not number:
            return {"stop": "policy_denied", "message": "Name the factory pull request to revise."}
        pr = _pr(repo, number)
        repo.base_branch = pr.get("base") or repo.base_branch
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
    r.repo = github.bind(github.Repo(**out["repo"]))
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


# -- CI before the pull request ------------------------------------------------------------

#: check conclusions that count as passing; anything else that finished is a failure
PASSING = ("success", "neutral", "skipped")
#: how long a commit may have no checks at all before "this repository runs no CI on a push"
NO_CHECKS_GRACE_SECONDS = 120
POLL_SECONDS = 20


def wait_before_pr(repository_id: int, head_sha: str, *, minutes: int) -> dict:
    """Wait for the repository's own checks on the pushed commit, before any
    pull request exists (VisionForge Foreman's gate, with the repository's CI
    as the runner: the factory, not a model, decides from the checks' own
    conclusions). Returns ``{"state": "success" | "failure" | "none" |
    "timeout", "failed": [names], "checks": n}``. "none" means no check started
    for this commit within two minutes: the repository runs no CI on a push."""
    import time

    deadline = time.monotonic() + max(1, minutes) * 60
    first_seen = time.monotonic() + NO_CHECKS_GRACE_SECONDS
    while True:
        runs = _all_check_runs(repository_id, head_sha)
        failed = [r.get("name") or "check" for r in runs
                  if (r.get("status") == "completed" and (r.get("conclusion") or "") not in PASSING)]
        if runs:
            pending = [r for r in runs if (r.get("status") or "") != "completed"]
            if failed and not pending:
                return {"state": "failure", "failed": failed, "checks": len(runs)}
            if not pending:
                return {"state": "success", "failed": [], "checks": len(runs)}
        elif time.monotonic() > first_seen:
            return {"state": "none", "failed": [], "checks": 0}
        if time.monotonic() > deadline:
            # A check that already failed blocks the pull request, even while others still run.
            return {"state": "failure" if failed else "timeout", "failed": failed, "checks": len(runs)}
        time.sleep(POLL_SECONDS)


def failed_on(repository_id: int, sha: str) -> list[str]:
    """The checks that finished failing on a commit (the base, to tell a
    failure the change caused from one that was already there)."""
    return sorted({r.get("name") or "check" for r in _all_check_runs(repository_id, sha)
                   if r.get("status") == "completed" and (r.get("conclusion") or "") not in PASSING})


def _all_check_runs(repository_id: int, head_sha: str, *, max_pages: int = 50) -> list[dict]:
    """Every check run on the commit, all pages: a failure on page two counts.
    More pages than it reads counts as a failed check, never as a pass."""
    out: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        args = {"repository_id": repository_id, "head_sha": head_sha, "page_size": 100}
        if cursor:
            args["cursor"] = cursor
        page = github.read("listCheckRuns", **args)
        items = page.get("data")
        out += items if isinstance(items, list) else (items or {}).get("items") or []
        cursor = page.get("next_cursor")
        if not cursor:
            return out
    return out + [{"name": f"more than {len(out)} checks (not all read)", "status": "completed",
                   "conclusion": "failure"}]
