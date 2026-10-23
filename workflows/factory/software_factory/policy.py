"""Who may make the factory do what: caller classes and the action matrix.

The upstream template's GitHub policies (``agent/lib/github/approval.ts``, MIT, Vercel) as
data, with these fixes:

* a pull request summary session (P) can only post its own origin reply;
* a state change bundled with other issue fields must pass both policies;
* unattended label work (A) writes only on its intake issue, except the upstream template's
  dedupe close, which stays limited to issues in the same repository;
* every pull request update waits for the requester, never an administrator.

The matrix is one input to every decision. The others are the person's
current grants and the work item's route, which the SDK enforces itself. The
factory's decision is the intersection: a write needs all three.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: T trusted attended, U attended but not trusted, A unattended label,
#: C unattended CI repair, P unattended pull request summary.
CallerClass = Literal["T", "U", "A", "C", "P"]
CALLERS: tuple[str, ...] = ("T", "U", "A", "C", "P")
Decision = Literal["allow", "approval", "deny"]

#: The local machine account when sign-in is off (the upstream template's dev TUI: writes
#: wait for the person's approval).
LOCAL_ACCOUNT = "admin@localhost"


# -- the 31 upstream GitHub tools (agent/extensions/github.ts:40-70) -----------------------

READ = "read"
#: kind of each tool, which picks its row in the matrix
GITHUB_TOOLS: dict[str, str] = {
    "getRepository": READ, "getRepositoryTree": READ, "getFileContent": READ, "searchCode": READ,
    "listBranches": READ, "listCommits": READ, "getCommit": READ, "compareCommits": READ,
    "searchIssues": READ, "listIssues": READ, "getIssueContext": READ, "listIssueComments": READ,
    "createIssue": "other_write",
    "updateIssue": "update_issue",
    "closeIssue": "state_change",
    "addIssueComment": "comment",
    "listLabels": READ,
    "addLabels": "label",
    "removeLabel": "label",
    "addAssignees": "other_write",
    "removeAssignees": "other_write",
    "listPullRequests": READ, "getPullRequestContext": READ, "listPullRequestFiles": READ,
    "listPullRequestReviews": READ,
    "createPullRequest": "create_pull_request",
    "updatePullRequest": "pr_update",
    "addPullRequestComment": "other_write",
    "requestReviewers": "other_write",
    "listCheckRuns": READ, "getCiFailureContext": READ,
}
#: Tools the upstream template deliberately leaves out and the factory never offers.
ABSENT = ("mergePullRequest", "enablePullRequestAutoMerge", "createRelease", "deleteRepository",
          "createOrUpdateFileContents", "rerunWorkflow", "updateRepository")


# -- the caller matrix --------------------------------------------------------------------

#: operation -> {caller: decision}. "intake" and "bound_pr" mean allow only on
#: the issue or pull request the work came from.
MATRIX: dict[str, dict[str, str]] = {
    "read": {"T": "allow", "U": "allow", "A": "allow", "C": "allow", "P": "allow"},
    "brain_read": {"T": "allow", "U": "allow", "A": "allow", "C": "allow", "P": "allow"},
    "label": {"T": "allow", "U": "approval", "A": "intake", "C": "bound_pr", "P": "deny"},
    "comment": {"T": "allow", "U": "approval", "A": "intake", "C": "bound_pr", "P": "deny"},
    "state_change": {"T": "allow", "U": "allow", "A": "same_repository", "C": "deny", "P": "deny"},
    "other_write": {"T": "allow", "U": "approval", "A": "deny", "C": "deny", "P": "deny"},
    "create_pull_request": {"T": "implement", "U": "implement", "A": "implement", "C": "deny", "P": "deny"},
    "pr_update": {"T": "approval", "U": "approval", "A": "deny", "C": "deny", "P": "deny"},
    "linear": {"T": "allow", "U": "allow", "A": "deny", "C": "deny", "P": "deny"},
    "brain_update": {"T": "proposal", "U": "proposal", "A": "suggest", "C": "suggest", "P": "deny"},
    "origin_reply": {"T": "allow", "U": "allow", "A": "allow", "C": "allow", "P": "allow"},
}

REASONS = {
    "A": "Unattended factory runs may only label and comment on the issue they came from, close confirmed "
         "duplicates in this repository and open a draft pull request for their own branch.",
    "C": "A CI repair may only comment on its own pull request and push to the factory's own branch.",
    "P": "A pull request summary posts one orientation comment and nothing else.",
    "pr_update": "Changing pull request metadata waits for exact approval. A person marks it ready in GitHub.",
}


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


def kind_of(tool: str, arguments: dict | None = None) -> str:
    """The matrix row for one GitHub call. `updateIssue` is classified by its
    whole mutation: a state change smuggled beside labels or a title must pass
    both rows (the mixed-field bypass the upstream template's updateIssuePolicy allowed)."""
    if tool not in GITHUB_TOOLS:
        raise KeyError(f"{tool!r} is not one of the factory's GitHub tools")
    kind = GITHUB_TOOLS[tool]
    if kind != "update_issue":
        return kind
    fields = set(arguments or {}) - {"repository_id", "number"}
    if fields == {"state"}:
        return "state_change"
    return "other_write"


def decide(caller: str, operation: str, *, number: int | None = None, intake: int | None = None,
           route: str | None = None, same_repository: bool = True, arguments: dict | None = None) -> Verdict:
    """The factory's decision for one action. `operation` is a matrix row or a
    GitHub tool name. `number` is the issue or pull request the call targets,
    `intake` the one the work came from."""
    if operation == "updatePullRequest" and "draft" in (arguments or {}):
        return Verdict("deny", "A person changes draft status in GitHub. The factory never marks a PR ready.")
    if operation == "createPullRequest" and (arguments or {}).get("draft") is False:
        return Verdict("deny", "The factory opens only draft pull requests.")
    if caller not in CALLERS:
        return Verdict("deny", f"Unknown caller class {caller!r}.")
    if operation in GITHUB_TOOLS:
        kind = kind_of(operation, arguments)
        if operation == "updateIssue" and kind == "other_write" and "state" in (arguments or {}):
            # both rows must allow it
            first = decide(caller, "other_write", number=number, intake=intake, route=route,
                           same_repository=same_repository)
            second = decide(caller, "state_change", number=number, intake=intake, route=route,
                            same_repository=same_repository)
            return first if not first.allowed else second
        operation = kind
    if operation in ABSENT or operation not in MATRIX:
        return Verdict("deny", "The factory has no such action. Merging and repository administration are a "
                               "person's job.")
    rule = MATRIX[operation][caller]
    if rule == "allow":
        return Verdict("allow")
    if rule == "approval":
        return Verdict("approval", REASONS.get(operation, "This write waits for the person who asked."))
    if rule in ("intake", "bound_pr"):
        if intake is not None and number == intake:
            return Verdict("allow")
        return Verdict("deny", REASONS[caller])
    if rule == "same_repository":
        return Verdict("allow") if same_repository else Verdict("deny", REASONS[caller])
    if rule == "implement":
        return Verdict("allow") if route in ("implement", "revise") else Verdict(
            "deny", "A pull request comes only from the implement route, after an independent review.")
    if rule in ("proposal", "suggest"):
        return Verdict("approval" if rule == "proposal" else "deny",
                       "Factory brain changes are reviewed hub changes." if rule == "proposal" else
                       "Unattended work suggests a brain note in its reply instead of saving it.")
    return Verdict("deny", REASONS.get(caller, "Not allowed for this caller."))


def caller_class(*, requester: str, unattended: bool, trigger: str | None, verified: bool) -> str:
    """The caller class of a work item, from facts the SDK verified: who asked
    (the work item's requester), whether it runs unattended, and which trigger
    started it. Nothing in a message or an issue body changes it."""
    if unattended or requester.startswith("workflow:"):
        if trigger == "ci_failure":
            return "C"
        if trigger == "pull_request":
            return "P"
        return "A"
    if requester == LOCAL_ACCOUNT or not verified:
        return "U"
    return "T"


def route_ceiling(caller: str, trigger: str | None) -> tuple[str, ...]:
    """Routes this caller and trigger may end up on. Unattended work never
    widens: the label implements, CI revises, a new pull request is
    summarized. An unattended mention (a collaborator without a linked
    account) may answer, triage or plan, since only the label may open a pull
    request without a person."""
    if caller == "C":
        return ("revise",)
    if caller == "P":
        return ("summarize",)
    if caller == "A":
        return ("implement", "plan", "triage", "answer") if trigger == "label" else ("answer", "triage", "plan")
    return ("answer", "triage", "plan", "implement", "revise", "act")
