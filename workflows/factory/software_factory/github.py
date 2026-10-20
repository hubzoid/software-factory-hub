"""GitHub through the SDK's channel connection, with the factory's policy.

Every read and write goes through ``hubzoid.channels.github.operations``: the
host holds the credential, writes are recorded work-item operations that are
never repeated on their own, and pushes use ``push_branch``. This module adds
the factory's own decision (the caller matrix) in front of each write, and
asks the requester first when the matrix says so. The hub never holds a token.
"""
from __future__ import annotations

from dataclasses import dataclass

from hubzoid import hub

from . import policy


class FactoryRefused(Exception):
    """The factory's policy refused an action before anything was sent, or
    GitHub refused a read (an unreachable or moved repository)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

    def __reduce__(self):
        return (type(self), (self.code, self.message))


def _refused(exc) -> FactoryRefused:
    return FactoryRefused(getattr(exc, "code", "repository_unavailable"),
                          getattr(exc, "message", None) or str(exc))


@dataclass
class Repo:
    connection: str
    repository_id: int
    full_name: str
    default_branch: str
    clone_url: str


def connection():
    from hubzoid.channels import config

    cid = hub.setting("FACTORY_GITHUB_CONNECTION", "github") or "github"
    try:
        return config.active(_hub_dir(), cid)
    except Exception as exc:  # noqa: BLE001 - say what to do, never a stack trace
        raise FactoryRefused("repository_unavailable", f"The GitHub connection {cid!r} is not set up. Run "
                             f"`hubzoid channels doctor . {cid}`.") from exc


def _hub_dir():
    from hubzoid.workflows import context

    return context._ctx().hub_dir


def configured_repository_id() -> int:
    """FACTORY_REPO's numeric id in the connection. Work from chat, the API,
    Slack or Linear has no GitHub coordinates, so the SDK would accept any
    repository of the connection: the factory itself allows only this one."""
    conn = connection()
    wanted = (hub.setting("FACTORY_REPO") or "").lower()
    match = next((r for r in conn.settings.repositories or [] if r.full_name.lower() == wanted), None)
    if match is None:
        raise FactoryRefused("repository_unavailable", f"{wanted or 'FACTORY_REPO'} is not one of the connection's "
                             "repositories.")
    return int(match.id)


def _only_factory_repo(repository_id) -> None:
    if repository_id != configured_repository_id():
        raise FactoryRefused("repository_unavailable", "The factory writes only to FACTORY_REPO.")


def repo() -> Repo:
    """The configured repository, looked up through the connection by name,
    then always used by its numeric id."""
    from hubzoid.channels.github import client as gh

    conn = connection()
    wanted = (hub.setting("FACTORY_REPO") or "").lower()
    match = next((r for r in conn.settings.repositories or [] if r.full_name.lower() == wanted), None)
    if match is None:
        raise FactoryRefused("repository_unavailable", f"{wanted or 'FACTORY_REPO'} is not one of the "
                             "connection's repositories. Check the spelling and the App installation. The factory "
                             "never switches repositories on its own.")
    info = read("getRepository", repository_id=match.id)["data"]
    return Repo(connection=conn.id, repository_id=match.id, full_name=info.get("full_name") or match.full_name,
                default_branch=info.get("default_branch") or "main",
                clone_url=f"{gh.web_url()}/{info.get('full_name') or match.full_name}.git")


def read(name: str, **arguments) -> dict:
    from hubzoid.channels.github import operations

    from hubzoid.channels.errors import ChannelError

    if policy.GITHUB_TOOLS.get(name) != policy.READ:
        raise FactoryRefused("not_a_read", f"{name} is not a read.")
    try:
        return operations.call(connection(), name, arguments)
    except ChannelError as exc:
        raise _refused(exc) from None


def write(name: str, *, caller: str, route: str, intake: int | None, requester: str, **arguments) -> dict:
    """One GitHub write, after the factory's own decision. A write that needs
    the requester's approval waits for it first (U callers, and every pull
    request update, which the SDK also gates by its exact digest)."""
    from hubzoid.channels.github import operations

    _only_factory_repo(arguments.get("repository_id"))
    verdict = policy.decide(caller, name, number=arguments.get("number"), intake=intake, route=route,
                            arguments=arguments)
    if verdict.decision == "deny":
        raise FactoryRefused("policy_denied", verdict.reason)
    if verdict.decision == "approval" and name != "updatePullRequest":
        # The SDK records the write; the person approves this exact call first.
        shown = {k: v for k, v in arguments.items() if k != "repository_id"}
        decision = hub.approve(f"GitHub {name}", details=shown, approvers=[requester])
        if not decision.get("approved"):
            raise FactoryRefused("approval_denied", f"{name} was not approved"
                                 + (f": {decision['note']}" if decision.get("note") else "."))
    from hubzoid.channels.errors import ChannelError

    try:
        return operations.call(connection(), name, arguments)
    except ChannelError as exc:
        raise _refused(exc) from None


def push(*, repository_id: int, branch: str, patch: bytes, patch_sha256: str, base_sha: str,
         expected_head: str | None, base_branch: str, key: str | None = None) -> dict:
    from hubzoid.channels.github import operations

    _only_factory_repo(repository_id)
    return operations.push_branch(connection(), repository_id=repository_id, branch=branch, patch=patch,
                                  patch_sha256=patch_sha256, base_sha=base_sha, expected_head=expected_head,
                                  base_branch=base_branch, key=key)


def find_pull_request(branch: str) -> dict | None:
    """The pull request whose head is `branch` in FACTORY_REPO, if any."""
    from hubzoid.channels.github import client as gh
    from hubzoid.channels.github import operations

    conn = connection()
    rid = configured_repository_id()
    web = gh.for_repo(conn, rid, gh.READ)
    found = operations.find_pull_request(conn, web, gh.current_name(conn, web, rid), branch)
    return {k: found.get(k) for k in ("number", "html_url", "draft", "head")} if found else None


def branch_head(repository_id: int, branch: str) -> str | None:
    """The branch's current head on GitHub, or None when it doesn't exist."""
    from urllib.parse import quote

    from hubzoid.channels.github import client as gh

    conn = connection()
    web = gh.for_repo(conn, repository_id, gh.READ)
    full = gh.current_name(conn, web, repository_id)
    try:
        got = web.request("GET", f"/repos/{full}/branches/{quote(branch, safe='')}").json() or {}
    except Exception as exc:  # noqa: BLE001
        if gh.status_of(exc) == 404:
            return None
        raise
    return (got.get("commit") or {}).get("sha")


def bot_name() -> str:
    name = hub.setting("FACTORY_BOT_NAME") or ""
    if name:
        return name
    conn = connection()
    return getattr(conn.settings, "bot_name", None) or "factory"


def pull_request_state(repository_id: int, number: int) -> dict:
    """Fresh minimal state for revision fences, using the SDK's scoped read client.

    getPullRequestContext omits merged/merged_at on the baseline SDK. No
    model or issue text participates in deciding whether a PR can be changed.
    """
    from hubzoid.channels.github import client as gh

    _only_factory_repo(repository_id)
    conn = connection()
    web = gh.for_repo(conn, repository_id, gh.READ)
    full = gh.current_name(conn, web, repository_id)
    got = web.request("GET", f"/repos/{full}/pulls/{int(number)}").json() or {}
    return {"state": got.get("state"), "merged": bool(got.get("merged") or got.get("merged_at")),
            "head_sha": (got.get("head") or {}).get("sha")}
