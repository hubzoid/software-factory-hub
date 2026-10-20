"""CI repair on factory branches, the ship gate, pull request orientation,
uncertain writes and recovery (HUB-6 section 9)."""
from __future__ import annotations

import pytest

from .. import conftest as h


def outcome(out):
    return out["factory_v1"]["outcome"], out["factory_v1"].get("stop_reason")


def deliver_pr(factory) -> dict:
    out = factory.run(factory.label())
    assert out["factory_v1"]["outcome"] == "review_ready"
    return out["factory_v1"]


def red_ci(factory, branch, head, number, *, delivery, suite=5):
    return factory.deliver("check_suite", {
        "action": "completed", "repository": {"id": h.REPO_ID, "full_name": h.FULL}, "installation": {"id": 7001},
        "check_suite": {"id": suite, "conclusion": "failure", "head_sha": head, "head_branch": branch,
                        "pull_requests": [{"number": number}]},
        "sender": {"id": 41898282, "login": "github-actions[bot]", "type": "Bot"}}, delivery)


# -- CI repair --------------------------------------------------------------------------------

def test_ci_repair_on_a_factory_branch(factory):
    rec = deliver_pr(factory)
    pulls_before = dict(factory.api.pulls)
    item = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="ci-1")
    assert item["route"] == "revise" and item["requester"] == "workflow:factory"
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    fix = out["factory_v1"]
    assert fix["caller_class"] == "C" and fix["ci_attempt"] == 1
    assert factory.api.pulls.keys() == pulls_before.keys()               # no new pull request
    bodies = [c["body"] for c in factory.api.comments[rec["pr_number"]]]
    start = next(i for i, b in enumerate(bodies) if b.startswith("CI fix attempt 1 of 2"))
    assert any(b.startswith("CI fix attempt 1 of 2 is pushed to pull request") for b in bodies[start + 1:])
    assert not any("Draft pull request" in b for b in bodies[start:])        # an existing PR is not reopened
    assert factory.remote.head(rec["branch"]) == fix["pushed_sha"] != rec["pushed_sha"]
    implementer = [c for c in factory.stations.calls if c["name"] == "implementer"][-1]
    assert "Failing checks" in implementer["message"] and implementer["checkout"]["ref"] == rec["branch"]


def test_ci_attempt_cap_survives_restart(factory):
    rec = deliver_pr(factory)
    head, n = rec["pushed_sha"], rec["pr_number"]
    for attempt in (1, 2):
        out = factory.run(red_ci(factory, rec["branch"], head, n, delivery=f"ci-{attempt}", suite=attempt))
        assert out["factory_v1"]["ci_attempt"] == attempt
        head = out["factory_v1"]["pushed_sha"]
    out = factory.run(red_ci(factory, rec["branch"], head, n, delivery="ci-3", suite=3))
    assert outcome(out) == ("stopped", "ci_attempts_exhausted")
    assert any("Pausing automated CI fixes" in c["body"] for c in factory.api.comments[n])


def test_duplicate_ci_single_reservation(factory):
    rec = deliver_pr(factory)
    first = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="ci-a", suite=1)
    second = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="ci-b", suite=2)
    assert second.get("id") in (None, first["id"])                    # one work item per failing head
    factory.run(first)
    from software_factory import ci

    from hubzoid import db
    from hubzoid.workflows.state import SHARED, WorkflowState

    state = WorkflowState(db.operational_engine(factory.hub_dir), "factory", "factory", owner=SHARED)
    slots = [state.get(ci.ATTEMPT.format(rid=h.REPO_ID, branch=rec["branch"], n=n)) for n in (1, 2)]
    assert slots == [{"head": rec["pushed_sha"], "item": first["id"]}, None]


def test_restarted_ci_work_runs_its_own_attempt_again(factory, monkeypatch):
    # Found in the live run: CI work that crashed after taking its attempt
    # slot was restarted by a manager, saw its own slot and stopped as a
    # duplicate.
    from software_factory import stations

    rec = deliver_pr(factory)
    item = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="ci-r")
    real, crashes = stations.call, [1]

    def crash_once(agent, *a, **kw):
        if agent == "implementer" and crashes:
            crashes.pop()
            raise RuntimeError("the hub process died")
        return real(agent, *a, **kw)

    monkeypatch.setattr(stations, "call", crash_once)
    with pytest.raises(RuntimeError):
        factory.run(item)
    out = factory.run(item, fresh_execution=True)                     # restart from the CI stage
    assert outcome(out) == ("review_ready", None) and out["factory_v1"]["ci_attempt"] == 1
    starts = [c["body"] for c in factory.api.comments[rec["pr_number"]] if c["body"].startswith("CI fix attempt")
              and "starting on" in c["body"]]
    assert len(starts) == 1                                           # the attempt note is not repeated


def test_branch_prefix_not_ownership(factory):
    factory.api.pulls[50] = {"title": "Someone's branch", "body": "", "head": "factory/not-ours", "base": "main",
                             "draft": False}
    from tests.conftest import git

    git(factory.remote.bare, "branch", "factory/not-ours", "main")
    out = factory.run(red_ci(factory, "factory/not-ours", factory.remote.base, 50, delivery="ci-x"))
    assert outcome(out) == ("ignored", "not_factory_branch")
    assert not [w for w in factory.writes() if "/issues/50/" in w[1]]


def test_stale_head_ci_ignored(factory):
    rec = deliver_pr(factory)
    out = factory.run(red_ci(factory, rec["branch"], factory.remote.base, rec["pr_number"], delivery="ci-old"))
    assert outcome(out) == ("ignored", "stale_head")


def test_fork_ci_denied(factory):
    rec = deliver_pr(factory)
    factory.api.pulls[rec["pr_number"]]["fork"] = True
    out = factory.run(red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="ci-fork"))
    assert outcome(out) == ("stopped", "fork_pull_request")


def test_a_person_pushing_to_the_factory_branch_stops_repair(factory):
    rec = deliver_pr(factory)
    _, _, foreign = factory.remote.commit_on(rec["branch"], {"calc.py": "x = 2\n"}, "manual change", push=True)
    out = factory.run(red_ci(factory, rec["branch"], foreign, rec["pr_number"], delivery="ci-manual"))
    assert outcome(out) == ("stopped", "head_changed")


def test_attended_revise_on_a_factory_pull_request(factory):
    rec = deliver_pr(factory)
    factory.model.route = {"route": "revise", "issue_number": rec["pr_number"], "act": None, "clarify": None,
                           "reason": ""}
    item = factory.chat("Please rename the variable xs to values", key="revise-1")
    from hubzoid.work_items import store

    store.update_item(factory.hub_dir, item["id"], expected_revision=item["revision"], input_json={"input": {
        "source": "chat", "request": "Please rename the variable xs to values",
        "subject": {"kind": "github_pr", "number": rec["pr_number"]}}})
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None) and out["factory_v1"]["route"] == "revise"
    implementer = [c for c in factory.stations.calls if c["name"] == "implementer"][-1]["message"]
    assert "rename the variable xs to values" in implementer


# -- the ship gate --------------------------------------------------------------------------

@pytest.mark.parametrize("requester", [h.OWNER, "admin@localhost"])
def test_mark_ready_is_a_human_github_handoff(factory, requester):
    rec = deliver_pr(factory)
    factory.model.route = {"route": "act", "issue_number": rec["pr_number"], "clarify": None, "reason": "",
                           "act": {"operation": "mark_ready", "number": rec["pr_number"]}}
    item = factory.chat(f"Mark #{rec['pr_number']} ready for review", requester=requester, key="ship-1")
    writes_before = factory.writes()
    out = factory.run(item)
    assert outcome(out) == ("stopped", "human_action_required")
    assert "in GitHub" in out["reply"]
    assert factory.api.pulls[rec["pr_number"]]["draft"] is True
    assert factory.writes() == writes_before
    assert not factory.ops(item["id"])


def test_unattended_work_never_updates_a_pull_request(factory):
    rec = deliver_pr(factory)
    from software_factory import policy

    assert policy.decide("A", "updatePullRequest", route="act").decision == "deny"
    assert policy.decide("C", "updatePullRequest", route="revise").decision == "deny"
    del rec


# -- orientation comments -------------------------------------------------------------------

def test_pr_opened_gets_one_orientation_comment_and_nothing_else(factory):
    factory.api.pulls[60] = {"title": "Add caching", "body": "Caches totals.", "head": "feature/cache",
                             "base": "main", "draft": False}
    factory.model.agent_replies = ["This pull request caches totals.\n\n| path | kind | what |\n|---|---|---|\n"
                                   "| calc.py | modified | adds a cache |\n\nStart with calc.py."]
    item = factory.deliver("pull_request", {
        "action": "opened", "repository": {"id": h.REPO_ID, "full_name": h.FULL}, "installation": {"id": 7001},
        "pull_request": {"number": 60, "title": "Add caching", "body": "Caches totals.",
                         "head": {"sha": "abc1234", "ref": "feature/cache", "repo": {"fork": False}},
                         "base": {"sha": factory.remote.base}},
        "sender": {"id": 9, "login": "bob", "type": "User"}}, "pr-60")
    assert item["route"] == "summarize"
    writes_before = len(factory.writes())
    out = factory.run(item)
    assert outcome(out) == ("summarized", None) and out["factory_v1"]["caller_class"] == "P"
    new = factory.writes()[writes_before:]
    assert len(new) == 1 and new[0][1].endswith("/issues/60/comments") and "Start with calc.py" in new[0][2]["body"]
    assert not factory.stations.calls[-1:] or factory.stations.calls[-1]["name"] != "implementer"


def test_bot_pull_requests_get_no_summary(factory):
    out = factory.deliver("pull_request", {
        "action": "opened", "repository": {"id": h.REPO_ID, "full_name": h.FULL}, "installation": {"id": 7001},
        "pull_request": {"number": 61, "title": "Bump", "body": "", "head": {"sha": "abc1234", "ref": "dep",
                                                                             "repo": {"fork": False}},
                         "base": {"sha": factory.remote.base}},
        "sender": {"id": 49699333, "login": "dependabot[bot]", "type": "Bot"}}, "pr-61")
    assert "id" not in out


# -- uncertain writes and recovery ------------------------------------------------------------

def test_uncertain_draft_never_blind_retry(factory, monkeypatch):
    from hubzoid.work_items.errors import Parked

    real = factory.api.__call__
    attempts = []

    def flaky(request):
        if request.method == "POST" and request.url.path.endswith("/pulls"):
            attempts.append(1)
            raise RuntimeError("connection reset by peer")
        return real(request)

    import httpx
    from hubzoid.channels.github import client as gh

    monkeypatch.setattr(gh, "transport", httpx.MockTransport(flaky))
    item = factory.label()
    with pytest.raises(Parked) as parked:
        factory.run(item)
    assert parked.value.kind == "ambiguous" and len(attempts) == 1
    with pytest.raises(Parked):
        factory.run(item)                                             # still waiting for the requester
    assert len(attempts) == 1


def test_recover_after_a_crash_between_stages(factory, monkeypatch):
    """A process that dies after the push resumes from its saved steps: no
    station runs twice and nothing is pushed twice."""
    from software_factory import pipeline

    real = pipeline._deliver
    crashed = {"done": False}

    def crash_once(*a, **kw):
        if not crashed["done"]:
            crashed["done"] = True
            raise SystemExit("power cut")
        return real(*a, **kw)

    monkeypatch.setattr(pipeline, "_deliver", crash_once)
    item = factory.label()
    with pytest.raises(SystemExit):
        factory.run(item)
    calls = len(factory.stations.calls)
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    assert len(factory.stations.calls) == calls                     # the saved station results were reused
    pushes = [o for o in factory.ops(item["id"]) if o["name"] == "github.pushBranch"]
    assert len(pushes) == 1 and len(factory.api.pulls) == 1


def test_cancelled_work_runs_no_more_stations(factory):
    from hubzoid.work_items import store

    item = factory.label()
    current = store.get_item(factory.hub_dir, item["id"])
    store.update_item(factory.hub_dir, item["id"], expected_revision=current["revision"], cancel_requested=1)
    with pytest.raises(Exception):
        factory.run(item)
    assert not factory.stations.calls or factory.stations.calls[-1]["name"] == "classifier"


@pytest.mark.slow
@pytest.mark.parametrize("existing_pr", [False, True])
def test_replay_after_recorded_pr_side_effect_keeps_its_saved_fences(factory, monkeypatch, existing_pr):
    """A real SDK push/PR operation completed before the simulated crash.

    Later context activation or PR closure cannot retroactively turn that
    completed side effect into a stop or make recovery open a duplicate PR.
    """
    from software_factory import pipeline

    if existing_pr:
        rec = deliver_pr(factory)
        item = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="replay-after-delivery")
    else:
        item = factory.chat("Fix total and get an independent review", issue=12, key="replay-after-create")
    real, crashed = pipeline._done, []

    def die_before_done(r, result, *args, **kwargs):
        if result == "review_ready" and not crashed:
            crashed.append(True)
            raise SystemExit("power cut after recorded GitHub operation")
        return real(r, result, *args, **kwargs)

    monkeypatch.setattr(pipeline, "_done", die_before_done)
    with pytest.raises(SystemExit):
        factory.run(item)
    assert len(factory.api.pulls) == 1
    assert any(op["name"] == "github.pushBranch" and op["state"] == "succeeded"
               for op in factory.ops(item["id"]))
    calls = len(factory.stations.calls)
    (factory.hub_dir / "knowledge/factory-brain/example-co-widget.md").write_text(
        "# Activated correction after delivery\nUse the updated verification command next time.\n")
    if existing_pr:
        factory.api.pulls[rec["pr_number"]].update(state="closed", merged=True)
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    assert len(factory.api.pulls) == 1 and len(factory.stations.calls) == calls
    assert sum(op["name"] == "github.pushBranch" for op in factory.ops(item["id"])) == 1
    assert sum(method == "POST" and path.endswith("/pulls") for method, path, _ in factory.writes()) == 1


@pytest.mark.slow
def test_changed_context_after_push_names_the_remaining_branch(factory, monkeypatch):
    from software_factory import stations

    real = stations.call

    def activate_after_review(agent, *args, **kwargs):
        result = real(agent, *args, **kwargs)
        if agent == "reviewer":
            (factory.hub_dir / "knowledge/factory-brain/example-co-widget.md").write_text(
                "# New team rule\nReview the changed policy before further work.\n")
        return result

    monkeypatch.setattr(stations, "call", activate_after_review)
    out = factory.run(factory.label())
    assert outcome(out) == ("stopped", "context_changed")
    assert out["factory_v1"]["branch"] in out["reply"]
    assert not factory.api.pulls


@pytest.mark.slow
@pytest.mark.parametrize("state,merged", [("closed", False), ("closed", True), ("open", True)])
def test_closed_or_merged_pr_never_starts_ci_repair(factory, state, merged):
    rec = deliver_pr(factory)
    factory.api.pulls[rec["pr_number"]].update(state=state, merged=merged)
    calls, writes = len(factory.stations.calls), factory.writes()
    out = factory.run(red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="closed"))
    assert outcome(out) == ("ignored", "pull_request_closed")
    assert len(factory.stations.calls) == calls and factory.writes() == writes
    assert factory.remote.head(rec["branch"]) == rec["pushed_sha"]


@pytest.mark.slow
def test_pr_closed_while_implementer_runs_never_pushes(factory, monkeypatch):
    from software_factory import stations

    rec = deliver_pr(factory)
    real = stations.call

    def close_after_implementation(agent, *args, **kwargs):
        out = real(agent, *args, **kwargs)
        if agent == "implementer":
            factory.api.pulls[rec["pr_number"]]["state"] = "closed"
        return out

    monkeypatch.setattr(stations, "call", close_after_implementation)
    item = red_ci(factory, rec["branch"], rec["pushed_sha"], rec["pr_number"], delivery="close-during")
    out = factory.run(item)
    assert outcome(out) == ("stopped", "pull_request_closed")
    assert factory.remote.head(rec["branch"]) == rec["pushed_sha"]
    assert not [o for o in factory.ops(item["id"]) if o["name"] == "github.pushBranch"]
