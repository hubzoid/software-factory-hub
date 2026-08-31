"""Cases from the Codex review of the build (HUB-6 section 9 adds)."""
from __future__ import annotations

import pytest

from .. import conftest as h


def outcome(out):
    return out["factory_v1"]["outcome"], out["factory_v1"].get("stop_reason")


def set_values(factory, **values):
    from hubzoid.hubs import settings

    lines = "".join(f"  {k}: {str(v).lower() if isinstance(v, bool) else v}\n" for k, v in values.items())
    (factory.hub_dir / "hub.settings.yaml").write_text(
        f"version: 1\nvalues:\n  FACTORY_REPO: example-co/widget\n{lines}")
    settings.forget()


def test_an_explicit_plan_approval_request_beats_the_default(factory):
    set_values(factory, FACTORY_REQUIRE_PLAN_APPROVAL=False)
    factory.model.route = dict(factory.model.route, require_plan_approval=True)
    out = factory.run(factory.chat("Implement it, but let me approve the plan first", issue=12))
    assert outcome(out) == ("delivered", None)
    assert [s for s in factory.people.seen if s[0] == "plan"]


def test_settings_are_fixed_for_the_life_of_the_work(factory):
    """A setting changed while the work waits never changes its steps."""
    item = factory.chat("Fix total", issue=12)
    factory.people.plans = [{"approved": True, "note": None, "by": h.OWNER}]
    first = factory.run(item)
    set_values(factory, FACTORY_REQUIRE_PLAN_APPROVAL=False, FACTORY_BRANCH_PREFIX="other/")
    again = factory.run(item)                     # a replay: same saved steps, same branch
    assert again["factory_v1"]["branch"] == first["factory_v1"]["branch"]
    assert first["factory_v1"]["branch"].startswith("factory/")


def test_implementation_is_built_on_the_planned_commit(factory, monkeypatch):
    from software_factory import pipeline

    real = pipeline._plan_gate

    def main_moves(*a, **kw):
        out = real(*a, **kw)
        factory.remote.commit_on("main", {"other.py": "y = 1\n"}, "someone else's change", push=True)
        return out

    monkeypatch.setattr(pipeline, "_plan_gate", main_moves)
    out = factory.run(factory.chat("Fix total", issue=12))
    assert outcome(out) == ("delivered", None)
    implementer = next(c for c in factory.stations.calls if c["name"] == "implementer")
    assert implementer["checkout"]["commit"] == out["factory_v1"]["base_sha"] == factory.remote.base
    assert factory.remote.head("main") != factory.remote.base


def test_a_branch_moved_after_review_opens_no_pull_request(factory, monkeypatch):
    from software_factory import evidence

    real = evidence.save

    def someone_pushes(output_dir, record):
        factory.remote.commit_on(record["branch"], {"calc.py": "x = 9\n"}, "manual push", push=True)
        return real(output_dir, record)

    monkeypatch.setattr(evidence, "save", someone_pushes)
    out = factory.run(factory.label())
    assert outcome(out) == ("stopped", "head_changed")
    assert not factory.api.pulls


@pytest.mark.parametrize("window", ["before_ledger", "after_ledger"])
def test_a_crash_around_the_ledger_update_replays_cleanly(factory, monkeypatch, window):
    from software_factory import publish

    real = publish.ledger_put
    crashed = {"n": 0}

    def crash(rid, branch, entry):
        if crashed["n"] == 0:
            crashed["n"] += 1
            if window == "after_ledger":
                real(rid, branch, entry)
            raise SystemExit("power cut")
        return real(rid, branch, entry)

    monkeypatch.setattr(publish, "ledger_put", crash)
    item = factory.label()
    with pytest.raises(SystemExit):
        factory.run(item)
    # the publish stage never completed: drop its unsaved step, as the engine would
    factory.steps[item["id"]] = [s for s in factory.steps[item["id"]] if s[0] != "hz_stage:publish"]
    out = factory.run(item)
    assert outcome(out) == ("delivered", None)
    pushes = [o for o in factory.ops(item["id"]) if o["name"] == "github.pushBranch"]
    assert len(pushes) == 1 and pushes[0]["state"] == "succeeded"


def test_a_reviewer_that_edited_files_proves_nothing(factory):
    factory.stations.reviewer_dirty = True
    out = factory.run(factory.label())
    assert outcome(out) == ("stopped", "review_evidence_invalid") and not factory.api.pulls


def test_an_api_act_route_reads_its_named_action(factory, monkeypatch):
    from hubzoid.work_items import operations as ops
    from hubzoid.work_items.errors import Parked

    monkeypatch.setattr(ops, "_approver_still_allowed", lambda *a: True)
    rec = factory.run(factory.label())["factory_v1"]
    factory.model.route = {"route": "act", "issue_number": rec["pr_number"], "clarify": None, "reason": "",
                           "act": {"operation": "mark_ready", "number": rec["pr_number"]}}
    item = factory.chat(f"Mark #{rec['pr_number']} ready", route="act", key="api-act")
    with pytest.raises(Parked):
        factory.run(item)


def test_an_earlier_plans_handoff_is_carried_into_the_new_work(factory):
    factory.model.route = dict(factory.model.route, route="plan")
    planned_item = factory.chat("Plan it", issue=12, key="p1")
    from hubzoid import db
    from hubzoid.workflows import context

    with context.run_scope(hub="factory", workflow="factory", hub_dir=factory.hub_dir,
                           engine=db.operational_engine(factory.hub_dir), run_id="r",
                           work={"item": factory.item(planned_item["id"]), "stage": None}):
        from hubzoid import hub

        doc = hub.save_handoff("analysis", "Full analysis", "# Deep notes\n\nThe + 1 is on line 2.")
    factory.stations.analysis = dict(factory.stations.analysis, handoff_id=doc["id"])
    planned = factory.run(planned_item)
    factory.model.route = dict(factory.model.route, route="implement")
    item = factory.chat("Implement it", issue=12, key="i1")
    from hubzoid.work_items import store

    store.update_item(factory.hub_dir, item["id"], expected_revision=item["revision"], input_json={"input": {
        "source": "chat", "request": "Implement it", "subject": {"kind": "github_issue", "number": 12},
        "from_work_item": planned["factory_v1"]["work_item"]}})
    out = factory.run(item)
    carried = out["factory_v1"]["analysis"]["handoff_id"]
    assert carried and carried != doc["id"]
    from hubzoid.stations import service

    assert "line 2" in service.read_handoff(factory.hub_dir, item["id"], carried)["markdown"]
    implementer = next(c for c in factory.stations.calls if c["name"] == "implementer")
    assert carried in implementer["message"] and doc["id"] not in implementer["message"]


def test_a_draft_settled_by_a_person_is_confirmed_on_github(factory, monkeypatch):
    from software_factory import github

    real = github.write

    def settled(name, **kw):
        if name == "createPullRequest":
            real(name, **kw)                                       # it really was created
            return {"data": {"resolved_by_person": True, "evidence": "saw it"}}
        return real(name, **kw)

    monkeypatch.setattr(github, "write", settled)
    out = factory.run(factory.label())
    assert outcome(out) == ("delivered", None) and out["factory_v1"]["pr_number"] in factory.api.pulls


def test_chat_keys_tell_routes_and_finished_work_apart(factory, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("factory_tools", factory.hub_dir / "tools_local" / "factory.py")
    tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools)

    class User:
        email = h.OWNER

    monkeypatch.setattr(tools, "_who", lambda: User())
    denied = tools._start("Fix total", 12, "plan", None, "mcp")
    assert denied["code"] == "permission_denied"                 # no wf_factory grant yet
    from hubzoid.work_items import service

    monkeypatch.setattr(service, "_can", lambda hub_dir, who, perm: who == h.OWNER)
    plan = tools._start("Fix total", 12, "plan", None, "mcp")
    impl = tools._start("Fix total", 12, "implement", None, "mcp")
    assert "work_item" in plan and "work_item" in impl, (plan, impl)
    assert plan["work_item"] != impl["work_item"]
    retry = tools._start("Fix total", 12, "plan", None, "mcp")
    assert retry["work_item"] == plan["work_item"] and not retry["created"]
    from hubzoid.work_items import store

    item = store.get_item(factory.hub_dir, plan["work_item"])
    store.update_item(factory.hub_dir, item["id"], expected_revision=item["revision"], state="completed")
    again = tools._start("Fix total", 12, "plan", None, "mcp")
    assert again["created"] and again["state"] != "completed"
