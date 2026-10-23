"""The caller matrix and the 31 upstream GitHub tools."""
import pytest

from software_factory import policy

#: (operation, caller) -> expected decision with the intake issue as the target
EXPECTED = {
    "read": dict(T="allow", U="allow", A="allow", C="allow", P="allow"),
    "label": dict(T="allow", U="approval", A="allow", C="allow", P="deny"),
    "comment": dict(T="allow", U="approval", A="allow", C="allow", P="deny"),
    "state_change": dict(T="allow", U="allow", A="allow", C="deny", P="deny"),
    "other_write": dict(T="allow", U="approval", A="deny", C="deny", P="deny"),
    "pr_update": dict(T="approval", U="approval", A="deny", C="deny", P="deny"),
    "linear": dict(T="allow", U="allow", A="deny", C="deny", P="deny"),
    "origin_reply": dict(T="allow", U="allow", A="allow", C="allow", P="allow"),
}


@pytest.mark.parametrize("operation", sorted(EXPECTED))
@pytest.mark.parametrize("caller", policy.CALLERS)
def test_policy_matrix_all_callers(operation, caller):
    got = policy.decide(caller, operation, number=12, intake=12, route="implement").decision
    assert got == EXPECTED[operation][caller]


def test_thirty_one_tools_and_no_merge():
    assert len(policy.GITHUB_TOOLS) == 31
    reads = [t for t, k in policy.GITHUB_TOOLS.items() if k == policy.READ]
    assert len(reads) == 19 and len(policy.GITHUB_TOOLS) - len(reads) == 12
    for absent in policy.ABSENT:
        assert absent not in policy.GITHUB_TOOLS
        assert policy.decide("T", absent).decision == "deny"
    assert not any("merge" in t.lower() for t in policy.GITHUB_TOOLS)


def test_sdk_offers_the_same_31_tools():
    from hubzoid.channels.github import operations

    assert set(operations.OPS) == set(policy.GITHUB_TOOLS)
    for name, op in operations.OPS.items():
        assert (op.kind == "read") == (policy.GITHUB_TOOLS[name] == policy.READ), name


@pytest.mark.parametrize("tool", sorted(policy.GITHUB_TOOLS))
@pytest.mark.parametrize("caller", policy.CALLERS)
def test_every_tool_has_a_decision_for_every_caller(tool, caller):
    verdict = policy.decide(caller, tool, number=12, intake=12, route="implement", arguments={"number": 12})
    assert verdict.decision in ("allow", "approval", "deny")
    if caller == "P":
        assert verdict.decision == "deny" or policy.GITHUB_TOOLS[tool] == policy.READ


def test_unattended_writes_stay_on_the_intake_issue():
    assert policy.decide("A", "addIssueComment", number=12, intake=12).allowed
    assert policy.decide("A", "addIssueComment", number=99, intake=12).decision == "deny"
    assert policy.decide("C", "addLabels", number=7, intake=7).allowed
    assert policy.decide("C", "addLabels", number=8, intake=7).decision == "deny"


def test_mixed_issue_update_checks_every_field():
    # A state change alone passes for A (the upstream template's dedupe), but smuggling a title beside it does not.
    assert policy.decide("A", "updateIssue", arguments={"number": 5, "state": "closed"}).allowed
    mixed = policy.decide("A", "updateIssue", arguments={"number": 5, "state": "closed", "title": "x"})
    assert mixed.decision == "deny"
    assert policy.decide("U", "updateIssue", arguments={"number": 5, "state": "closed", "labels": ["x"]}
                         ).decision == "approval"
    assert policy.kind_of("updateIssue", {"number": 1, "state": "open"}) == "state_change"


def test_draft_pull_requests_only_from_implement():
    for caller in ("T", "U", "A"):
        assert policy.decide(caller, "createPullRequest", route="implement").allowed
        assert policy.decide(caller, "createPullRequest", route="plan").decision == "deny"
    assert policy.decide("C", "createPullRequest", route="revise").decision == "deny"
    assert policy.decide("P", "createPullRequest", route="implement").decision == "deny"


def test_summary_origin_only():
    for tool, kind in policy.GITHUB_TOOLS.items():
        if kind != policy.READ:
            assert policy.decide("P", tool, number=7, intake=7, route="summarize").decision == "deny", tool
    assert policy.decide("P", "origin_reply").allowed


def test_brain_updates_are_reviewed_or_suggested():
    assert policy.decide("T", "brain_update").decision == "approval"
    assert policy.decide("A", "brain_update").decision == "deny"


@pytest.mark.parametrize("requester,unattended,trigger,verified,expected", [
    ("workflow:factory", True, "label", False, "A"),
    ("workflow:factory", True, "ci_failure", False, "C"),
    ("workflow:factory", True, "pull_request", False, "P"),
    ("workflow:factory", True, "mention", False, "A"),
    ("admin@localhost", False, "chat", False, "U"),
    ("ana@example.org", False, "chat", True, "T"),
    ("ana@example.org", False, "mention", True, "T"),
])
def test_caller_class_comes_from_verified_facts(requester, unattended, trigger, verified, expected):
    assert policy.caller_class(requester=requester, unattended=unattended, trigger=trigger,
                               verified=verified) == expected


@pytest.mark.parametrize("caller", policy.CALLERS)
def test_no_caller_can_change_draft_status(caller):
    for draft in (False, True):
        assert policy.decide(caller, "updatePullRequest", route="act",
                             arguments={"draft": draft}).decision == "deny"
    assert policy.decide(caller, "createPullRequest", route="implement",
                         arguments={"draft": False}).decision == "deny"
