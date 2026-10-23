"""``publish_branch``: the factory's one way to put source on GitHub.

The implementer commits in an offline sandbox with no credentials. When its
station call finishes, the SDK exports those commits as a patch on the host.
This module then:

1. finds that exact export and binds the push to its SHA-256;
2. checks it (``scan``): size caps, paths the factory never changes,
   protected files, credentials;
3. checks branch ownership in the factory's ledger: a new branch must not
   exist yet, a revision must start from the head the factory pushed last;
4. pushes through the SDK (``push_branch``: host clone, one-repository
   ``contents: write`` token, lease on the exact head, never the default or a
   protected branch);
5. records the pushed SHA, the owning work item and later the pull request,
   so CI repairs and later revisions can prove the branch is the factory's.

A branch name prefix alone grants nothing (the upstream template's CI trusted the prefix).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hubzoid import hub

from . import github, scan
from .errors import FactoryStop

LEDGER = "factory_v1:branch:{rid}:{branch}"


@dataclass
class Published:
    branch: str
    pushed_sha: str
    previous_head: str | None
    base_sha: str
    commits: int
    html_url: str
    scan: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


def branch_name(prefix: str, *, kind: str, summary: str, number: int | None, item_id: str) -> str:
    """`factory/12-bug-fix-the-total-1a2b3c` for an issue, `factory/bug-fix-the-total-1a2b3c` otherwise.
    Decided by code from the saved classification, never by a model. The work
    item's short id keeps a new request for the same issue (a re-label after a
    stopped run) off the earlier work's branch."""
    slug = re.sub(r"[^a-z0-9]+", "-", (summary or "change").lower()).strip("-")
    slug = "-".join(slug.split("-")[:6])[:40].strip("-") or "change"
    kind = re.sub(r"[^a-z]", "", kind or "change") or "change"
    short = item_id.replace("-", "")[:6]
    if number:
        return f"{prefix}{number}-{kind}-{slug}-{short}"
    return f"{prefix}{kind}-{slug}-{short}"


def ledger_get(repository_id: int, branch: str) -> dict | None:
    value = hub.shared_state.get(LEDGER.format(rid=repository_id, branch=branch))
    return value if isinstance(value, dict) else None


def ledger_put(repository_id: int, branch: str, entry: dict) -> None:
    hub.shared_state[LEDGER.format(rid=repository_id, branch=branch)] = entry


def _export(call_id: str) -> tuple[bytes, str, str]:
    """The patch the SDK exported for one station call, its digest and the
    commit the sandbox's checkout started from."""
    from hubzoid import datadir
    from hubzoid.sandbox import service as sandbox_service
    from hubzoid.workflows import context

    hub_dir = context._ctx().hub_dir
    item_id = hub.work_item.id
    boxes = sandbox_service.list_rows(hub_dir, owner_kind="station_call", owner_id=call_id, limit=10)
    for box in boxes:
        for exp in box.get("exports_json") or []:
            path = Path(exp["file"])
            path = path if path.is_absolute() else hub_dir / path
            if path.is_file():
                data = path.read_bytes()
                digest = "sha256:" + hashlib.sha256(data).hexdigest()
                if digest != exp.get("sha256"):
                    raise FactoryStop("patch_changed", "The exported patch changed on disk after the sandbox "
                                      "wrote it. Nothing was published.")
                return data, digest, exp["base"]
    folder = datadir.resolve(hub_dir, Path("output") / "work-items" / item_id / call_id)
    raise FactoryStop("implementation_not_pushed", f"The implementer's call left no exported commits ({folder}). "
                      "Nothing was published.")


def push_recorded(repo: github.Repo, branch: str, revision: int) -> bool:
    """Whether this revision's push already happened (the process stopped
    after the push and before its stage was saved)."""
    from hubzoid.channels.github import operations

    return operations.recorded("github.pushBranch", {"repository_id": repo.repository_id, "branch": branch},
                               f"r{revision}") is not None


def publish_branch(*, repo: github.Repo, call_id: str, branch: str, revision: int, owner_item: str,
                   expected_head: str | None) -> Published:
    """Check and publish one implementer call's commits to `branch`."""
    data, digest, base_sha = _export(call_id)
    checked = scan.check(data)
    if not checked.ok:
        raise FactoryStop("patch_refused", "The change was not published: " + "; ".join(checked.refusals),
                          details=checked.to_json())
    entry = ledger_get(repo.repository_id, branch)
    key = f"r{revision}"
    if push_recorded(repo, branch, revision):
        # This exact push was already recorded (the process stopped before the
        # stage was saved): the SDK settles it from its record, with the same
        # arguments. The ledger may already show its result, so it is not
        # checked again.
        pass
    elif expected_head is None:
        if entry is not None and entry.get("owner_item") != owner_item:
            raise FactoryStop("branch_owned_elsewhere", f"{branch} belongs to other factory work "
                              f"({str(entry.get('owner_item'))[:8]}).")
    else:
        if entry is None or entry.get("pushed_sha") != expected_head:
            raise FactoryStop("stale_head", f"{branch} is not where the factory left it. A person must look "
                              "before anything else is pushed.")
        if base_sha != expected_head:
            raise FactoryStop("stale_head", f"The revision was made on {base_sha[:12]}, but {branch} was last "
                              f"pushed at {expected_head[:12]}. Nothing was published.")
    try:
        out = github.push(repository_id=repo.repository_id, branch=branch, patch=data, patch_sha256=digest,
                          base_sha=base_sha, expected_head=expected_head, base_branch=repo.default_branch,
                          key=key)
    except Exception as exc:  # noqa: BLE001 - the SDK's codes become the factory's stop reasons
        code = getattr(exc, "code", None)
        if code in ("branch_exists", "stale_head", "branch_protected", "default_branch_refused", "patch_changed",
                    "validation_failed", "patch_too_large", "operation_rejected"):
            raise FactoryStop(code if code != "operation_rejected" else "push_rejected",
                              getattr(exc, "message", str(exc))) from None
        raise
    # Read again just before writing, and change only this push's fields.
    latest = ledger_get(repo.repository_id, branch) or {}
    ledger_put(repo.repository_id, branch, dict(latest, owner_item=latest.get("owner_item") or owner_item,
                                                branch=branch, repository_id=repo.repository_id,
                                                base_branch=repo.default_branch, pushed_sha=out["head_sha"],
                                                last_item=hub.work_item.id))
    return Published(branch=branch, pushed_sha=out["head_sha"], previous_head=out.get("previous_head"),
                     base_sha=out.get("base_sha") or base_sha, commits=out.get("commits") or checked.commits,
                     html_url=out.get("html_url") or "", scan=checked.to_json())


def record_pull_request(repository_id: int, branch: str, number: int) -> None:
    entry = ledger_get(repository_id, branch) or {}
    if entry.get("pr_number") != number:
        ledger_put(repository_id, branch, dict(entry, pr_number=number))


def verify_owned(repository_id: int, branch: str, head_sha: str) -> dict:
    """Prove a branch is the factory's and that `head_sha` is what the factory
    pushed last, from the ledger and the SDK's own record of that push."""
    from hubzoid.work_items import store as wi_store
    from hubzoid.workflows import context

    entry = ledger_get(repository_id, branch)
    if entry is None:
        raise FactoryStop("not_factory_branch", f"{branch} was not created by the factory. A branch name prefix "
                          "is not proof of ownership.")
    if entry.get("pushed_sha") != head_sha:
        raise FactoryStop("head_changed", f"{branch} has commits the factory did not push. A person must take "
                          "over.")
    ctx = context._ctx()
    ops = wi_store.list_ops(ctx.hub_dir, ctx.hub, item_id=entry.get("last_item"), state="succeeded")
    if not any(o.get("name") == "github.pushBranch" and (o.get("result_json") or {}).get("head_sha") == head_sha
               for o in ops):
        raise FactoryStop("not_factory_branch", f"No recorded factory push matches {head_sha[:12]} on {branch}.")
    return entry
