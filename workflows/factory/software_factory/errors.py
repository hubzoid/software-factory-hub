"""How a factory run stops on purpose.

A `FactoryStop` is a decided outcome, not a crash: the reviewer rejected the
change, the review cycles ran out, the patch was refused, the requester
needs to answer a question. The pipeline catches it, posts the stop reason
and what remains on the work's own thread, and finishes the work item with
``outcome: stopped`` and the reason, so nothing reads as success.
"""
from __future__ import annotations

#: Stop reasons and what a person does next.
REASONS = {
    "needs_clarification": "Answer the questions, then ask again (or re-add the label).",
    "implementation_not_pushed": "The implementer could not finish. Read its limitations, refine the issue and "
                                 "ask again.",
    "review_rejected": "The reviewer rejected the approach. Read the findings, adjust the issue and ask again.",
    "review_unresolved": "The reviewer still requests changes after the allowed revisions. A person takes it "
                         "from the pushed branch.",
    "patch_refused": "The change touched something the factory never publishes, or looked like it carried a "
                     "credential. Nothing was pushed.",
    "plan_rejected": "The plan was rejected. Ask again with what should change.",
    "plan_changes_requested": "The plan needs changes the factory could not make. Ask again with the notes.",
    "branch_owned_elsewhere": "Another piece of factory work owns that branch.",
    "branch_exists": "A branch with that name already exists and the factory did not create it.",
    "stale_head": "The branch moved after the factory pushed it. A person must look before anything else is "
                  "pushed.",
    "head_changed": "Someone else pushed to the factory's branch. Automated repair stops there.",
    "not_factory_branch": "Only branches the factory pushed itself get automated CI repair.",
    "ci_attempts_exhausted": "Automated CI repair has made its attempts. A person takes over.",
    "fork_pull_request": "Pull requests from forks never get automated repair.",
    "ci_not_failing": "The checks are no longer failing on the current head.",
    "intake_paused": "The factory is not taking new work. An administrator can turn intake back on.",
    "push_rejected": "GitHub refused the push. Nothing was overwritten.",
    "policy_denied": "That action is not allowed for this kind of request.",
    "approval_denied": "The person who asked did not approve it.",
    "reviewed_sha_mismatch": "The review did not cover the exact pushed commit, so no pull request was opened.",
    "repository_unavailable": "Check the repository setting and the GitHub App installation.",
    "stopped_by_requester": "Stopped as asked.",
    "content_too_large": "The request or a document is larger than the factory accepts.",
    "review_evidence_invalid": "The reviewer changed files while checking, so its result does not prove the "
                               "published commit. Ask again.",
    "station_failed": "A station failed twice. Check the runtime and the sandbox in Run checks, then ask again or "
                      "restart the work item.",
    "pull_request_unconfirmed": "Check GitHub for a pull request from the branch. If there is none, open one from "
                                "the branch or ask again.",
}


class FactoryStop(Exception):
    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def __reduce__(self):
        # The workflow engine stores exceptions raised inside saved steps.
        return (_rebuild, (type(self), self.code, self.message, self.details))

    @property
    def next_step(self) -> str:
        return REASONS.get(self.code, "A person decides what happens next.")


def _rebuild(cls, code, message, details):
    return cls(code, message, details=details)
