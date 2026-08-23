"""The scope step's choice is clamped to the caller's ceiling."""
from software_factory import scope


def d(route, **kw):
    return scope.ScopeDecision(route=route, **kw)


def test_attended_choice_stands():
    assert scope.check(d("implement"), caller="T", trigger="chat").route == "implement"
    assert scope.check(d("plan"), caller="U", trigger="chat").route == "plan"


def test_unattended_mention_cannot_implement():
    out = scope.check(d("implement"), caller="A", trigger="mention")
    assert out.route == "plan" and "linked account" in out.reason


def test_ci_and_summaries_never_take_a_person_route():
    assert scope.check(d("implement"), caller="C", trigger="ci_failure").route == "answer"
    assert scope.check(d("act"), caller="P", trigger="pull_request").route == "answer"


def test_act_needs_a_named_operation():
    out = scope.check(d("act"), caller="T", trigger="chat")
    assert out.route == "answer" and out.clarify
    ok = scope.check(d("act", act=scope.ActRequest(operation="mark_ready", number=7)), caller="T", trigger="chat")
    assert ok.route == "act" and ok.act.number == 7


def test_fixed_routes():
    assert scope.fixed_route("request") is None
    assert scope.fixed_route("implement") == "implement"
