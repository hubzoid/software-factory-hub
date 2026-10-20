"""Chat and MCP tools for the Software Factory.

A person asks in the web chat or from their own assistant over MCP. These
tools start the same durable ``factory`` work item every channel starts, as
that signed-in person, and let them follow it. Starting work needs the
person's grant to run the factory workflow (``wf_factory``) or to run and
control workflows. Approvals never happen here: a plan or a pull request
update waits for the person in Hubzoid (Waiting for you, or Work items).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from agents import function_tool

WORKFLOW = "factory"
ROUTES = ("auto", "triage", "plan", "implement", "revise", "act")


def _hub_dir() -> Path:
    return Path(os.environ.get("HUBZOID_HUB_DIR") or Path(__file__).resolve().parents[1])


def _who():
    from hubzoid import current_user

    return current_user(_hub_dir())


def _link(item_id: str) -> str:
    base = (os.environ.get("HUBZOID_PUBLIC_URL") or "").rstrip("/")
    path = f"/settings#/me/work/{_hub_dir().name.lower()}/{item_id}"
    return (base + path) if base else path


def _record(item_id: str) -> dict:
    from hubzoid import db
    from hubzoid.workflows.state import SHARED, WorkflowState

    state = WorkflowState(db.operational_engine(_hub_dir()), _hub_dir().name.lower(), WORKFLOW, owner=SHARED)
    return state.get(f"factory_v1:item:{item_id}") or {}


def _start(request: str, issue_number: int | None, route: str, from_work_item: str | None, surface: str) -> dict:
    from hubzoid import _request_ctx
    from hubzoid.work_items import service
    from hubzoid.work_items.errors import WorkItemError

    user = _who()
    if user is None:
        return {"refused": "Sign in to ask the factory for work."}
    request = (request or "").strip()
    if not request:
        return {"refused": "Say what the factory should do."}
    if route not in ROUTES:
        return {"refused": f"route is one of {', '.join(ROUTES)}."}
    payload = {"source": surface, "request": request[:60000], "route": route}
    if issue_number:
        payload["subject"] = {"kind": "github_issue", "number": int(issue_number)}
    if from_work_item:
        payload["from_work_item"] = from_work_item
    turn = _request_ctx.get_turn_id() or ""
    chat = _request_ctx.get_chat_id() or ""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    key = f"{surface}:{user.email}:{chat}:{turn}:{digest}" if turn else f"{surface}:{user.email}:{digest}"
    from hubzoid.work_items import store

    kwargs = dict(workflow=WORKFLOW, key=key[:500], route="request" if route == "auto" else route, input=payload,
                  requester=user.email, origin={"source": "chat", "surface": surface}, actor=user.email)
    try:
        # A retry of the same call returns the same work while it runs. The
        # same request after that work finished is new work.
        item, created = service.admit_and_start(_hub_dir(), generation_mode="reuse", **kwargs)
        if not created and item["state"] in store.TERMINAL:
            item, created = service.admit_and_start(_hub_dir(), generation_mode="new", **kwargs)
    except WorkItemError as exc:
        return {"refused": exc.message, "code": exc.code}
    from hubzoid.hubs import settings

    gated = route in ("auto", "implement") and settings.effective(_hub_dir()).get("FACTORY_REQUIRE_PLAN_APPROVAL",
                                                                                 True)
    note = ("Nothing is built until you approve this work's plan under Waiting for you. A plan from earlier work "
            "is reused as the starting point, never as an approval. " if gated else "")
    return {"work_item": item["id"], "state": item["state"], "created": created, "link": _link(item["id"]),
            "note": note + "The factory works in the background. Pull request updates wait for your approval under "
                           "Waiting for you. Ask for its status any time."}


def _status(work_item: str) -> dict:
    from hubzoid.work_items import service
    from hubzoid.work_items.errors import WorkItemError

    user = _who()
    if user is None:
        return {"refused": "Sign in to see factory work."}
    try:
        view = service.show(_hub_dir(), work_item, user.email)
    except WorkItemError as exc:
        return {"refused": exc.message, "code": exc.code}
    rec = _record(work_item) if view.get("result") is not None or view.get("input") is not None else {}
    out = {"work_item": work_item, "state": view["state"], "reason": view.get("reason"), "route": view["route"],
           "stages": [s.get("stage") or s.get("name") for s in view.get("stages") or []], "link": _link(work_item)}
    for key in ("stage", "outcome", "stop_reason", "waiting", "plan_url", "branch", "pushed_sha", "pr_number",
                "pr_url", "evidence_url", "context_revision", "reply"):
        if rec.get(key) not in (None, ""):
            out[key] = rec[key]
    if rec.get("plan_url"):
        # Finished work: the result is the full record. Running work: the progress record.
        result = (view.get("result") or {}).get("factory_v1") or {}
        approved = result.get("plan_approved") or rec.get("plan_approved")
        out["plan_approval"] = (f"approved by {approved.get('by')} (version {approved.get('version')})" if approved
                                else "not approved: this work's plan was not approved by anyone")
    waiting = [o for o in view.get("operations") or [] if o.get("state") in ("awaiting_approval", "ambiguous")]
    if waiting:
        out["waiting_on_you"] = [{"operation": o.get("id"), "name": o.get("name"), "state": o.get("state")}
                                 for o in waiting]
    return out


def _list(limit: int) -> dict:
    from hubzoid.work_items import service

    user = _who()
    if user is None:
        return {"refused": "Sign in to see factory work."}
    page = service.list_items(_hub_dir(), user.email, workflow=WORKFLOW, limit=max(1, min(int(limit), 25)),
                              mine=True)
    items = page.get("items") if isinstance(page, dict) else page
    return {"work": [{"work_item": i["id"], "state": i["state"], "route": i["route"], "created": i["created"],
                      "outcome": _record(i["id"]).get("outcome")} for i in items or []]}


def _repository() -> dict:
    """FACTORY_REPO and its numeric id in the GitHub connection: every GitHub
    read tool needs the id, and a name alone can belong to someone else later."""
    from hubzoid.channels import config
    from hubzoid.hubs import settings

    values = settings.effective(_hub_dir())
    wanted = (values.get("FACTORY_REPO") or "").lower()
    cid = values.get("FACTORY_GITHUB_CONNECTION") or "github"
    try:
        conn = config.active(_hub_dir(), cid)
    except Exception:  # noqa: BLE001
        return {"repository": wanted, "refused": f"The GitHub connection {cid} is not set up. Run checks in Setup."}
    match = next((r for r in conn.settings.repositories or [] if r.full_name.lower() == wanted), None)
    if match is None:
        return {"repository": wanted, "refused": f"{wanted} is not one of the {cid} connection's repositories."}
    return {"repository": match.full_name, "repository_id": int(match.id), "connection": cid,
            "label": values.get("FACTORY_LABEL"), "branch_prefix": values.get("FACTORY_BRANCH_PREFIX")}


@function_tool
async def factory_repository() -> str:
    """The repository the factory works on and its numeric repository_id. Call it once before the GitHub read
    tools (github__getFileContent, github__searchCode and the rest), which all take that repository_id."""
    return json.dumps(await asyncio.to_thread(_repository))


@function_tool
async def start_factory_work(request: str, issue_number: int | None = None, route: str = "auto",
                             from_work_item: str | None = None) -> str:
    """Hand engineering work to the Software Factory as the person asking. It classifies, plans, implements in
    an isolated sandbox, gets an independent review and opens a draft pull request (it never merges). Use it
    when the person asks to triage, plan, fix, build, change or revise something in the repository, or to update
    supported pull request metadata. Marking a draft ready and merging require the person in GitHub. Do not use it for questions you can answer by reading the repository.

    Args:
        request: The person's request in their own words, with any constraints they gave (for example "stop after
            the plan").
        issue_number: The GitHub issue or pull request number it is about, when they named one.
        route: auto (the factory decides from their words), triage, plan, implement, revise or act.
        from_work_item: To implement a plan an earlier factory request produced, that work item's id.
    """
    from hubzoid.access import current_identity

    surface = "mcp" if getattr(current_identity(), "surface", "") == "mcp" else "chat"
    out = await asyncio.to_thread(_start, request, issue_number, route, from_work_item, surface)
    return json.dumps(out)


@function_tool
async def factory_status(work_item: str) -> str:
    """Where one factory work item stands: its stage, what it is waiting for, the plan, the branch and the
    draft pull request, or why it stopped. Only the person who asked (or a manager) sees the details.

    Args:
        work_item: The work item id start_factory_work returned.
    """
    return json.dumps(await asyncio.to_thread(_status, work_item), default=str)


@function_tool
async def list_factory_work(limit: int = 10) -> str:
    """The person's own recent factory work items, newest first.

    Args:
        limit: How many to list (1 to 25).
    """
    return json.dumps(await asyncio.to_thread(_list, limit), default=str)
