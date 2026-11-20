"""A base branch per repository, several repositories in one factory, and
Engineering Desk's blocking findings fixed on the factory's own pull request."""
from __future__ import annotations

import pytest

from .. import conftest as h

OTHER_ID, OTHER = 2002, "example-co/other"
DESK = {"context": "engineering-desk/review", "poster": "desk-bot"}


def outcome(out):
    return out["factory_v1"]["outcome"], out["factory_v1"].get("stop_reason")


def values(factory, **extra):
    from hubzoid.hubs import settings

    lines = "".join(f"  {k}: {v}\n" for k, v in extra.items())
    (factory.hub_dir / "hub.settings.yaml").write_text(
        f"version: 1\nvalues:\n  FACTORY_BUILDS: docker\n  FACTORY_CHANNELS: [chat, mcp, github]\n{lines}secrets: {{}}\n")
    settings.forget()


def dev_branch(factory):
    h.git(factory.remote.bare, "branch", "dev", "main")


# -- B: base branch -----------------------------------------------------------------------------

def test_the_configured_base_branch_is_used_for_every_checkout_and_the_pull_request(factory):
    dev_branch(factory)
    values(factory, FACTORY_REPO="example-co/widget@dev")
    out = factory.run(factory.label())
    assert outcome(out) == ("review_ready", None)
    rec = out["factory_v1"]
    assert rec["base_branch"] == "dev"
    assert factory.api.pulls[rec["pr_number"]]["base"] == "dev"
    refs = {c["name"]: (c["checkout"] or {}).get("ref") for c in factory.stations.calls}
    assert refs["analyst"] == "dev" and refs["implementer"] == "dev"
    implementer = [c for c in factory.stations.calls if c["name"] == "implementer"][0]
    assert "base branch `dev`" in implementer["message"]


def test_without_a_branch_the_github_default_is_the_base(factory):
    out = factory.run(factory.label())
    assert out["factory_v1"]["base_branch"] == "main"
    assert factory.api.pulls[out["factory_v1"]["pr_number"]]["base"] == "main"


def test_a_missing_base_branch_stops_before_any_work(factory):
    values(factory, FACTORY_REPO="example-co/widget@nope")
    out = factory.run(factory.label())
    assert out["factory_v1"]["outcome"] in ("stopped", "failed")
    assert "nope" in out["factory_v1"]["reply"]
    assert not [c for c in factory.stations.calls if c["name"] != "classifier"]
    assert not factory.api.pulls


def test_a_reused_plan_keeps_its_base_after_the_setting_changes(factory):
    from hubzoid.work_items import service as wi

    dev_branch(factory)
    values(factory, FACTORY_REPO="example-co/widget@dev")
    plan_item = factory.chat("Plan the fix for the totals bug", issue=12, route="plan")
    plan = factory.run(plan_item)
    assert plan["factory_v1"]["base_branch"] == "dev"
    values(factory, FACTORY_REPO="example-co/widget")              # the setting moves back to main
    item, _ = wi.admit(factory.hub_dir, workflow="factory", key="impl-from-plan", route="implement",
                       input={"source": "chat", "request": "Build that plan",
                              "subject": {"kind": "github_issue", "number": 12}, "from_work_item": plan_item["id"]},
                       requester=h.OWNER, origin={"source": "chat", "surface": "web"})
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["base_branch"] == "dev"
    assert factory.api.pulls[out["factory_v1"]["pr_number"]]["base"] == "dev"


def test_a_ci_repair_uses_the_pull_requests_own_base(factory):
    dev_branch(factory)
    values(factory, FACTORY_REPO="example-co/widget@dev")
    rec = factory.run(factory.label())["factory_v1"]
    values(factory, FACTORY_REPO="example-co/widget")
    out = factory.run(red_ci(factory, rec))
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["base_branch"] == "dev"


# -- A: several repositories --------------------------------------------------------------------

def two_repos(factory):
    dev_branch(factory)
    h.reapply_github(factory.hub_dir, repositories=[{"id": h.REPO_ID, "full_name": h.FULL},
                                                    {"id": OTHER_ID, "full_name": OTHER}])
    values(factory, FACTORY_REPOS=f"[{h.FULL}@dev, {OTHER}]")


def test_a_github_event_works_on_its_own_repository(factory):
    two_repos(factory)
    out = factory.run(factory.label())
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["repository"] == h.FULL and out["factory_v1"]["base_branch"] == "dev"


def test_chat_naming_a_repository_uses_it(factory):
    from hubzoid.work_items import service as wi

    two_repos(factory)
    item, _ = wi.admit(factory.hub_dir, workflow="factory", key="chat-named-repo", route="implement",
                       input={"source": "chat", "request": "Fix the totals bug", "repo": "widget",
                              "subject": {"kind": "github_issue", "number": 12}},
                       requester=h.OWNER, origin={"source": "chat", "surface": "web"})
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["base_branch"] == "dev"
    assert not [s for s in factory.people.seen if s[0] == "ask"]


def test_chat_without_a_repository_asks_and_the_reply_decides(factory):
    two_repos(factory)
    factory.people.answers = ["widget"]
    out = factory.run(factory.chat("Fix the totals bug", issue=12, route="implement"))
    asks = [s[1]["question"] for s in factory.people.seen if s[0] == "ask"]
    assert asks and "Which repository" in asks[0] and "widget" in asks[0] and "other" in asks[0]
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["repository"] == h.FULL


def test_a_reply_naming_no_single_repository_stops(factory):
    two_repos(factory)
    factory.people.answers = ["either is fine"]
    out = factory.run(factory.chat("Fix the totals bug", issue=12, route="implement"))
    assert outcome(out) == ("stopped", "repository_unclear")
    assert not factory.api.pulls


def _clickup_run(tags, *, attended):
    import types

    from software_factory import intake, pipeline

    req = intake.Request(source="clickup", trigger="task_ready", instruction="Work on the ClickUp task.",
                         subject=intake.Subject(kind="clickup_task", identifier="86abc"),
                         data={"clickup_tags": tags})
    settings = pipeline._normalized({"FACTORY_REPO": "", "FACTORY_REPOS": [f"{h.FULL}@dev", OTHER]})
    return types.SimpleNamespace(settings=settings, request=req, attended=attended, requester=h.OWNER)


def test_a_clickup_tag_picks_the_repository(factory):
    from software_factory import pipeline

    two_repos(factory)
    assert pipeline._target(_clickup_run(["urgent", "Widget"], attended=False)).full_name == h.FULL


@pytest.mark.parametrize("tags", [[], ["widget", "other"]])
def test_unattended_work_that_names_no_single_repository_stops_with_how_to_fix_it(factory, tags):
    from software_factory import pipeline
    from software_factory.errors import FactoryStop

    two_repos(factory)
    with pytest.raises(FactoryStop) as stop:
        pipeline._target(_clickup_run(tags, attended=False))
    assert stop.value.code == "repository_unclear"
    assert "Add exactly one repository tag (widget, other)" in str(stop.value)


def test_a_repository_outside_the_list_is_refused(factory):
    two_repos(factory)
    from hubzoid.work_items import service as wi
    from hubzoid.work_items import store

    item, _ = wi.admit(factory.hub_dir, workflow="factory", key="chat-bad-repo", route="implement",
                       input={"source": "chat", "request": "Fix it", "repo": "example-co/secret"},
                       requester=h.OWNER, origin={"source": "chat", "surface": "web"})
    out = factory.run(store.get_item(factory.hub_dir, item["id"]))
    assert outcome(out) == ("stopped", "repository_unavailable")


# -- C: Engineering Desk findings on the factory's pull request ---------------------------------

def red_ci(factory, rec, *, delivery="ci-1", suite=5):
    return factory.deliver("check_suite", {
        "action": "completed", "repository": {"id": h.REPO_ID, "full_name": h.FULL}, "installation": {"id": 7001},
        "check_suite": {"id": suite, "conclusion": "failure", "head_sha": rec["pushed_sha"],
                        "head_branch": rec["branch"], "pull_requests": [{"number": rec["pr_number"]}]},
        "sender": {"id": 41898282, "login": "github-actions[bot]", "type": "Bot"}}, delivery)


def desk_loop(factory):
    h.reapply_github(factory.hub_dir, status_failures=[DESK])


def desk_review(factory, rec, *, head=None, poster="desk-bot", marker=True, findings="calc.py: total adds 1"):
    """The Desk's summary comment and its failed gate status on the head."""
    head = head or rec["pushed_sha"]
    factory.api.next += 1
    cid = factory.api.next
    body = f"Engineering Desk review: 1 blocking finding.\n\n- {findings}\n"
    if marker:
        body += f"\n<!-- engineering-desk:head:{head} -->"
    factory.api.comments.setdefault(rec["pr_number"], []).append(
        {"id": cid, "body": body, "user": {"login": poster}, "html_url": f"https://github.com/c/{cid}"})
    factory.api.statuses[head] = [{"context": "engineering-desk/review", "state": "failure",
                                   "description": "1 open finding, 1 blocking", "creator": {"login": poster},
                                   "target_url": f"file://{factory.remote.root}/{h.FULL}/pull/{rec['pr_number']}"
                                                 f"#issuecomment-{cid}"}]
    return head


def desk_status(factory, rec, *, head=None, delivery="desk-1", sender="desk-bot"):
    head = head or rec["pushed_sha"]
    return factory.deliver("status", {
        "id": abs(hash(delivery)) % 10**8, "sha": head, "state": "failure", "context": "engineering-desk/review",
        "description": "1 open finding, 1 blocking", "repository": {"id": h.REPO_ID, "full_name": h.FULL},
        "installation": {"id": 7001}, "sender": {"id": 9, "login": sender, "type": "User"}}, delivery)


def delivered(factory):
    out = factory.run(factory.label())
    assert outcome(out) == ("review_ready", None)
    factory.api.failing_jobs = []                     # CI is green; only the Desk fails
    return out["factory_v1"]


def test_a_desk_blocking_finding_is_fixed_on_the_same_pull_request(factory):
    desk_loop(factory)
    rec = delivered(factory)
    desk_review(factory, rec)
    item = desk_status(factory, rec)
    assert item["route"] == "revise"
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    fix = out["factory_v1"]
    assert fix["desk_attempt"] == 1 and fix["ci_attempt"] is None and fix["repair_kinds"] == ["status"]
    assert len(factory.api.pulls) == 1                                    # the same pull request
    implementer = [c for c in factory.stations.calls if c["name"] == "implementer"][-1]
    assert "calc.py: total adds 1" in implementer["message"] and "Engineering Desk review findings" in \
        implementer["message"]
    bodies = [c["body"] for c in factory.api.comments[rec["pr_number"]]]
    assert any(b.startswith("Engineering Desk fix attempt 1 of 2 starting") for b in bodies)
    assert any(b.startswith("Engineering Desk fix attempt 1 of 2 is pushed") for b in bodies)


def test_a_status_from_anyone_else_starts_nothing(factory):
    desk_loop(factory)
    rec = delivered(factory)
    desk_review(factory, rec)
    got = desk_status(factory, rec, sender="mallory")
    assert "id" not in got
    assert got["delivery"]["status"] == "ignored"


def test_a_summary_for_another_head_stops_without_using_a_round(factory):
    desk_loop(factory)
    rec = delivered(factory)
    desk_review(factory, rec, marker=False)
    out = factory.run(desk_status(factory, rec))
    assert outcome(out) == ("stopped", "desk_evidence_missing")
    from software_factory import ci

    from hubzoid import db
    from hubzoid.workflows.state import SHARED, WorkflowState

    state = WorkflowState(db.operational_engine(factory.hub_dir), "factory", "factory", owner=SHARED)
    assert state.get(ci.DESK_ATTEMPT.format(rid=h.REPO_ID, branch=rec["branch"], n=1)) is None


def test_red_ci_and_a_red_desk_on_one_head_are_one_repair_charging_both(factory):
    desk_loop(factory)
    rec = delivered(factory)
    factory.api.failing_jobs = [{"name": "tests", "conclusion": "failure"}]
    desk_review(factory, rec)
    first = red_ci(factory, rec)
    second = desk_status(factory, rec)
    out = factory.run(first)
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["ci_attempt"] == 1 and out["factory_v1"]["desk_attempt"] == 1
    if second.get("id") and second["id"] != first["id"]:
        factory.run(second)                    # the head moved on: nothing more to repair
    assert len([c for c in factory.stations.calls if c["name"] == "implementer"]) == 2   # build + one repair


def test_desk_rounds_have_their_own_limit(factory):
    desk_loop(factory)
    rec = delivered(factory)
    head = rec["pushed_sha"]
    for n in (1, 2):
        desk_review(factory, {**rec, "pushed_sha": head})
        out = factory.run(desk_status(factory, {**rec, "pushed_sha": head}, delivery=f"desk-{n}"))
        assert out["factory_v1"]["desk_attempt"] == n
        head = out["factory_v1"]["pushed_sha"]
    desk_review(factory, {**rec, "pushed_sha": head})
    out = factory.run(desk_status(factory, {**rec, "pushed_sha": head}, delivery="desk-3"))
    assert outcome(out) == ("stopped", "ci_attempts_exhausted")
    assert any("Engineering Desk fixes" in c["body"] for c in factory.api.comments[rec["pr_number"]])
    # CI still has both of its own attempts.
    factory.api.failing_jobs = [{"name": "tests", "conclusion": "failure"}]
    factory.api.statuses.clear()
    out = factory.run(red_ci(factory, {**rec, "pushed_sha": head}, delivery="ci-after", suite=9))
    assert out["factory_v1"]["ci_attempt"] == 1


def test_a_finding_the_factory_judges_not_a_defect_is_explained_and_handed_over(factory):
    desk_loop(factory)
    rec = delivered(factory)
    desk_review(factory, rec)
    factory.stations.committed = False
    factory.stations.uncommitted_deviations = ["calc.py: adding 1 is the documented service fee, not a bug."]
    out = factory.run(desk_status(factory, rec))
    assert outcome(out) == ("stopped", "desk_findings_disputed")
    last = factory.api.comments[rec["pr_number"]][-1]["body"]
    assert "made no change for Engineering Desk's findings" in last and "/hubzoid dismiss" in last
    assert "documented service fee" in last
    assert factory.remote.head(rec["branch"]) == rec["pushed_sha"]          # no empty commit


def test_an_unfinished_desk_repair_is_not_presented_as_a_dispute(factory):
    desk_loop(factory)
    rec = delivered(factory)
    desk_review(factory, rec)
    factory.stations.committed = False                       # no deviations: it could not finish
    out = factory.run(desk_status(factory, rec))
    assert outcome(out) == ("stopped", "implementation_not_pushed")


def test_a_repair_works_even_when_the_configured_base_branch_is_gone(factory):
    dev_branch(factory)
    values(factory, FACTORY_REPO="example-co/widget@dev")
    rec = factory.run(factory.label())["factory_v1"]
    values(factory, FACTORY_REPO="example-co/widget@gone")
    out = factory.run(red_ci(factory, rec))
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["base_branch"] == "dev"


def test_a_plan_saved_before_base_branches_keeps_the_default_branch(factory):
    from hubzoid.work_items import service as wi
    from hubzoid.work_items import store

    dev_branch(factory)
    plan_item = factory.chat("Plan the fix for the totals bug", issue=12, route="plan")
    factory.run(plan_item)
    saved = store.get_item(factory.hub_dir, plan_item["id"])
    result = saved["result_json"]
    result["result"]["factory_v1"].pop("base_branch", None)                  # as the old factory saved it
    store.update_item(factory.hub_dir, plan_item["id"], expected_revision=saved["revision"], result_json=result)
    values(factory, FACTORY_REPO="example-co/widget@dev")
    item, _ = wi.admit(factory.hub_dir, workflow="factory", key="impl-from-old-plan", route="implement",
                       input={"source": "chat", "request": "Build that plan",
                              "subject": {"kind": "github_issue", "number": 12}, "from_work_item": plan_item["id"]},
                       requester=h.OWNER, origin={"source": "chat", "surface": "web"})
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None)
    assert out["factory_v1"]["base_branch"] == "main"
    assert factory.api.pulls[out["factory_v1"]["pr_number"]]["base"] == "main"


# -- upgrade ---------------------------------------------------------------------------------------

def test_work_saved_before_the_upgrade_replays(factory):
    """A run saved by the previous factory: its settings snapshot has no
    FACTORY_REPOS or FACTORY_DESK_ATTEMPTS and its repository no base branch.
    Replaying it gives the same pull request on the default branch."""
    item = factory.label()
    first = factory.run(item)
    assert outcome(first) == ("review_ready", None)
    for n, (name, value) in enumerate(factory.steps[item["id"]]):
        if isinstance(value, dict) and isinstance(value.get("settings"), dict):
            value["settings"].pop("FACTORY_REPOS", None)
            value["settings"].pop("FACTORY_DESK_ATTEMPTS", None)
        if isinstance(value, dict) and isinstance(value.get("repo"), dict):
            value["repo"].pop("base_branch", None)
    again = factory.run(item)
    assert outcome(again) == ("review_ready", None)
    assert again["factory_v1"]["pr_number"] == first["factory_v1"]["pr_number"]
    assert again["factory_v1"]["base_branch"] == "main"
    assert len(factory.api.pulls) == 1
