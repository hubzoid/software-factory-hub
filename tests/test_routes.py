"""The seven routes as data (HUB-6 section 6)."""
from software_factory import policy, routes


def test_seven_routes_and_one_ceiling():
    assert set(routes.ROUTES) == {"request", "answer", "triage", "plan", "implement", "revise", "summarize", "act"}
    assert next(iter(routes.ROUTES)) == "request"      # a channel that names no route lands on the ceiling


def test_every_attended_route_fits_inside_request():
    for name in routes.ATTENDED:
        assert routes.narrower("request", name), name
    assert not routes.narrower("request", "summarize")
    assert not routes.narrower("implement", "act")       # act needs pr_update, implement does not
    assert not routes.narrower("plan", "implement")


def test_route_plan_blocks_implementer():
    assert "implement" not in routes.stages("plan") and "publish" not in routes.stages("plan")
    assert routes.PUSH not in routes.actions("plan")


def test_only_implement_and_revise_push_and_only_act_updates_pull_requests():
    pushers = {r for r in routes.ROUTES if routes.PUSH in routes.actions(r)}
    assert pushers == {"request", "implement", "revise"}
    updaters = {r for r in routes.ROUTES if routes.PR_UPDATE in routes.actions(r)}
    assert updaters == {"request", "act"}


def test_answer_and_summarize_write_nothing_but_their_reply():
    for r in ("answer", "summarize"):
        assert routes.actions(r) == (routes.REPLY,)


def test_each_route_names_its_terminal_stage():
    for name, stage in routes.TERMINAL_STAGE.items():
        assert stage in routes.stages(name), name


def test_unattended_never_widens():
    assert policy.route_ceiling("C", "ci_failure") == ("revise",)
    assert policy.route_ceiling("P", "pull_request") == ("summarize",)
    assert "implement" in policy.route_ceiling("A", "label")
    assert "implement" not in policy.route_ceiling("A", "mention")
    assert "act" not in policy.route_ceiling("A", "label")
