"""One request shape from every way work arrives.

GitHub (mention, label, red CI, new pull request), Slack, Linear, chat, MCP
and the API all start the same ``factory`` work item. This module turns the
item's input into a `Request`, keeping two things apart:

* **instructions**: only the verified requester's own words (a mention, a
  Slack message, a chat message, an API request). The label's implicit
  instruction is "implement this issue";
* **data**: issue bodies, pull request text, Linear descriptions, comments
  and files. They are quoted to stations as data and never widen the route.

Who asked, and whether the work runs unattended, come from the work item
itself (the SDK verified them), never from the input.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MAX_TEXT = 64 * 1024

#: What each trigger means when nobody typed an instruction.
IMPLICIT = {
    "label": "Implement the GitHub issue this label was added to, and deliver a reviewed draft pull request.",
    "pull_request": "Write one orientation comment for reviewers of this new pull request.",
    "ci_failure": "Repair the failing checks on this factory pull request.",
}


@dataclass
class Subject:
    kind: str = "none"                  # github_issue, github_pr, linear_issue, none
    number: int | None = None
    repository_id: int | None = None
    full_name: str | None = None
    identifier: str | None = None       # a Linear identifier such as ENG-12
    url: str | None = None
    title: str | None = None


@dataclass
class Request:
    source: str                         # github, slack, linear, chat, mcp, api
    trigger: str                        # mention, review_mention, label, pull_request, ci_failure, chat, api, ...
    instruction: str                    # the requester's own words (or the trigger's implicit task)
    subject: Subject = field(default_factory=Subject)
    data: dict[str, Any] = field(default_factory=dict)     # untrusted context, quoted as data
    channel: str | None = None
    delivery_id: str | None = None
    from_work_item: str | None = None   # "implement the plan from work X"
    route_hint: str | None = None       # what an API caller or chat tool asked for

    def to_json(self) -> dict:
        return asdict(self)


def _int(v) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _clip(text: str | None) -> str:
    text = (text or "").strip()
    return text[:MAX_TEXT]


def from_input(payload: Any) -> Request:
    """The request a work item was started with."""
    if not isinstance(payload, dict):
        return Request(source="api", trigger="api", instruction=_clip(str(payload or "")))
    if "channel" in payload and "origin" in payload and "kind" in payload:
        return _from_channel(payload)
    return _from_direct(payload)


def _from_channel(p: dict) -> Request:
    origin = p.get("origin") or {}
    provider = origin.get("provider") or "channel"
    coords = origin.get("coordinates") or {}
    data = dict(p.get("data") or {})
    kind = p.get("kind") or "message"
    text = _clip(p.get("text"))
    subject = Subject(url=origin.get("url"))
    untrusted: dict[str, Any] = {}
    if provider == "github":
        is_pr = kind in ("pull_request", "ci_failure", "review_mention", "review_comment") or bool(
            data.get("is_pull_request"))
        subject = Subject(kind="github_pr" if is_pr else "github_issue", number=_int(coords.get("number")),
                          repository_id=_int(coords.get("repository_id")), full_name=coords.get("full_name"),
                          url=origin.get("url"), title=data.get("title"))
        if kind in IMPLICIT:
            # The label, a new pull request and red CI carry no typed instruction.
            # Their text is the issue or pull request itself: data.
            untrusted["body"] = text
            instruction = IMPLICIT[kind]
        else:
            instruction = text
        for key in ("head_sha", "head_branch", "base_sha", "fork", "pull_requests", "check_suite_id", "path",
                    "line", "association", "labeler", "label"):
            if key in data:
                untrusted[key] = data[key]
    elif provider == "linear":
        issue = data.get("issue") or {}
        subject = Subject(kind="linear_issue", identifier=issue.get("identifier"), url=issue.get("url"),
                          title=issue.get("title"))
        instruction = text or "Work on the Linear issue this session was started from."
        if data.get("prompt_context"):
            untrusted["linear_context"] = _clip(data["prompt_context"])
        untrusted["agent_session_id"] = data.get("agent_session_id")
    else:
        instruction = text
        untrusted.update({k: data[k] for k in ("channel", "thread_ts") if k in data})
    if p.get("files"):
        untrusted["files"] = p["files"]
    return Request(source=provider, trigger=kind, instruction=instruction, subject=subject, data=untrusted,
                   channel=p.get("channel"), delivery_id=p.get("delivery_id"))


def _from_direct(p: dict) -> Request:
    """Chat, MCP and the API: `{request, subject?, route?, from_work_item?}`."""
    source = p.get("source") if p.get("source") in ("chat", "mcp", "api") else "api"
    raw = p.get("subject") or {}
    subject = Subject()
    if isinstance(raw, dict) and raw.get("kind") in ("github_issue", "github_pr"):
        subject = Subject(kind=raw["kind"], number=_int(raw.get("number")))
    elif isinstance(raw, dict) and raw.get("kind") == "linear_issue":
        subject = Subject(kind="linear_issue", identifier=str(raw.get("identifier") or "")[:40] or None)
    route = p.get("route") if isinstance(p.get("route"), str) else None
    return Request(source=source, trigger=source, instruction=_clip(p.get("request") or p.get("text")),
                   subject=subject, from_work_item=p.get("from_work_item") if isinstance(
                       p.get("from_work_item"), str) else None, route_hint=route)


def unattended(requester: str) -> bool:
    return requester.startswith("workflow:")


def verified(request: Request, requester: str) -> bool:
    """Whether the person behind the request is verified beyond the local
    machine account: a linked channel identity, or a signed-in Hubzoid
    account. The local account with sign-in off is Foreman's dev TUI."""
    from .policy import LOCAL_ACCOUNT

    return bool(requester) and requester != LOCAL_ACCOUNT and not unattended(requester)
