"""Local repository mode: FACTORY_REPO is a folder on this computer.

No GitHub connection is needed. The stations still get their own clean clone
of the folder (the SDK clones a local path the same way it clones a URL), so
uncommitted edits in the person's working tree are never seen or touched.

The result is a reviewed local branch, not a draft pull request. The
implementer's patch is checked exactly as for GitHub (``scan``), applied in a
throwaway clone, and only then written into the person's repository as
``refs/heads/<branch>`` with a compare-and-swap ``git update-ref``. The person's
working tree, current branch and every other ref stay as they were, and none
of the repository's own Git hooks run. A branch that is checked out in any
worktree of the repository is never written.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .errors import FactoryStop

#: A local folder path: absolute, or starting at the home folder.
PATH = re.compile(r"^~?/")
_IMPORT_PREFIX = "refs/factory-import/"


def is_local(value: str | None) -> bool:
    return bool(value) and bool(PATH.match(str(value).strip()))


def folder(value: str) -> Path:
    return Path(os.path.expanduser(str(value).strip())).resolve()


def _same(a: Path, b: Path) -> bool:
    """The same folder on disk. On a Mac, ~/code/Widget and ~/code/widget are
    one folder, though the paths differ in letter case."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return a == b


def _common_dir(path: Path) -> Path | None:
    """The Git folder shared by every worktree of the repository at `path`."""
    out = _text(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out) if out else None


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "USER", "LANG", "TMPDIR",
                                                         "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(repo: Path, *args: str, check: bool = True, data: bytes | None = None,
         env: dict | None = None) -> subprocess.CompletedProcess:
    """Git with the repository's own hooks and filesystem monitor off."""
    argv = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(repo), *args]
    out = subprocess.run(argv, input=data, capture_output=True, timeout=300, env=env or _env())
    if check and out.returncode != 0:
        raise subprocess.CalledProcessError(out.returncode, argv, out.stdout, out.stderr)
    return out


def _text(repo: Path, *args: str) -> str | None:
    out = _git(repo, *args, check=False)
    return out.stdout.decode().strip() if out.returncode == 0 else None


def name_for(top: Path) -> str:
    """The repository's name in local mode: the folder name plus a short hash
    of its full path, so two folders with the same name never share a
    repository brief or the factory's branch records."""
    digest = hashlib.sha256(str(top).encode()).hexdigest()[:6]
    return f"local/{top.name}-{digest}"


def shown(path: str | Path) -> str:
    """A folder as people read it: ~/code/widget rather than /Users/me/code/widget."""
    text, home = str(path), os.path.expanduser("~")
    return "~" + text[len(home):] if home and home != "/" and (text == home or text.startswith(home + "/")) else text


def repo(value: str, *, hub_dir: str | Path | None = None):
    """The folder as the factory's repository: its current branch is the base
    every plan and build starts from. It must be the top folder of its own Git
    repository, outside the hub."""
    from .github import FactoryRefused, Repo

    path = folder(value)
    if path.exists() and not path.is_dir():
        raise FactoryRefused("repository_unavailable", f"{path} is a file. Set FACTORY_REPO to the folder that "
                             "holds your Git repository.")
    if not path.is_dir():
        raise FactoryRefused("repository_unavailable", f"{path} does not exist. Set FACTORY_REPO to a folder "
                             "with a Git repository in it.")
    if _text(path, "rev-parse", "--is-inside-work-tree") != "true":
        raise FactoryRefused("repository_unavailable", f"{path} is not a Git repository. Run `git init` there, "
                             "commit your code, then ask again.")
    top = Path(_text(path, "rev-parse", "--show-toplevel") or path).resolve()
    if hub_dir is not None:
        hub = Path(hub_dir).resolve()
        if _same(top, hub) or any(_same(p, hub) for p in top.parents):
            raise FactoryRefused("repository_unavailable", f"{path} is inside the hub's own folder or Git "
                                 "repository, so the factory would change the hub itself. Copy it somewhere "
                                 "else (for example cp -R fixtures/sample-repo ~/code/factory-sample), run "
                                 "`git init` and commit there, and set FACTORY_REPO to the copy.")
        if any(_same(p, top) for p in hub.parents):
            raise FactoryRefused("repository_unavailable", f"{top} holds the hub's own folder, so the factory would "
                                 "change the hub itself. Set FACTORY_REPO to a repository outside it.")
        shared = _common_dir(hub)
        if shared is not None and _same(shared, _common_dir(top) or top):
            raise FactoryRefused("repository_unavailable", f"{top} is another worktree of the hub's own Git "
                                 "repository, so the factory's branches would land in the hub's repository. Set "
                                 "FACTORY_REPO to a separate repository.")
    if not _same(top, path):
        raise FactoryRefused("repository_unavailable", f"{path} is a folder inside the Git repository {top}. "
                             f"Set FACTORY_REPO to {top}, or copy the folder out, run `git init` and commit "
                             "there, and set FACTORY_REPO to the copy.")
    branch = _text(top, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise FactoryRefused("repository_unavailable", f"{top} is not on a branch (detached HEAD). Switch to the "
                             "branch the factory should start from, then ask again.")
    if not _text(top, "rev-parse", "--verify", "--quiet", "HEAD^{commit}"):
        raise FactoryRefused("repository_unavailable", f"{top} has no commits yet. Commit your code first: the "
                             "factory works from what is committed.")
    name = name_for(top)
    return Repo(connection="local", repository_id=int(name[-6:], 16), full_name=name, default_branch=branch,
                clone_url=str(top), local_path=str(top))


def branch_head(local_path: str, branch: str) -> str | None:
    return _text(Path(local_path), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")


def _committer(local: Path) -> dict:
    """The person's own Git identity, read from their repository (its own
    config included), else a plain factory one. The import runs in a scratch
    clone that does not have the repository's config, so it is passed in."""
    env = _env()
    email, name = _text(local, "config", "user.email"), _text(local, "config", "user.name")
    if not email:
        email, name = "factory@localhost", "Software Factory"
    env.update(GIT_COMMITTER_NAME=name or "Software Factory", GIT_COMMITTER_EMAIL=email)
    return env


def checked_out_in(local: Path, branch: str) -> str | None:
    """The worktree, if any, where `branch` is checked out: the folder itself
    or any linked worktree of the same repository."""
    wanted, where = f"branch refs/heads/{branch}", None
    for line in (_text(local, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            where = line[len("worktree "):]
        elif line.strip() == wanted:
            return where or str(local)
    return None


def _trees(repo: Path, base_sha: str, head: str) -> list[str]:
    """The tree of each commit from base_sha to head. Tree ids depend only on
    content, never on the person's Git settings (colour, prefixes, renames,
    textconv) or on binary files."""
    out = _git(repo, "rev-list", "--no-commit-header", "--format=%T", f"{base_sha}..{head}", check=False)
    if out.returncode != 0:
        out = _git(repo, "rev-list", f"{base_sha}..{head}", check=False)
        return [_text(repo, "rev-parse", f"{c}^{{tree}}") or "" for c in out.stdout.decode().split()]
    return out.stdout.decode().split()


def _descends(local: Path, base_sha: str, current: str) -> bool:
    return _git(local, "merge-base", "--is-ancestor", base_sha, current, check=False).returncode == 0


def _already_written(local: Path, work: Path, base_sha: str, current: str, head: str) -> bool:
    """`current` is exactly this patch on top of `base_sha`: an earlier attempt
    wrote it and the process stopped before saving that it had."""
    wanted = _trees(work, base_sha, head)
    return bool(wanted) and _trees(local, base_sha, current) == wanted


def _not_ours(local: Path, branch: str, expected_head: str | None) -> FactoryStop:
    if expected_head is None:
        return FactoryStop("branch_exists", f"{branch} already exists in {local} and the factory did not create it.")
    return FactoryStop("stale_head", f"{branch} in {local} is not where the factory left it. A person must look "
                       "before anything else is written.")


def _stop(message: str) -> FactoryStop:
    return FactoryStop("local_write_failed", message)


def import_branch(local_path: str, *, branch: str, patch: bytes, base_sha: str, expected_head: str | None) -> str:
    """Write the reviewed patch into the person's repository as `branch` and
    return its new head. A new branch must not exist yet; a revision must find
    the branch exactly at `expected_head`."""
    try:
        return _import(Path(local_path), branch=branch, patch=patch, base_sha=base_sha, expected_head=expected_head)
    except subprocess.TimeoutExpired:
        raise _stop(f"Git took too long writing {branch} in {local_path}. Nothing was overwritten.") from None


def _import(local: Path, *, branch: str, patch: bytes, base_sha: str, expected_head: str | None) -> str:
    ref = f"refs/heads/{branch}"
    current = branch_head(str(local), branch)
    if expected_head is not None and current is None:
        raise FactoryStop("stale_head", f"{branch} is no longer in {local}: it was deleted after the factory wrote "
                          "it. Nothing was written. Ask for a new change instead.")
    # The branch is not where this write expects it: either an earlier attempt
    # already wrote this change, or someone else's work is there.
    replay = current is not None and current != expected_head
    if replay and not _descends(local, base_sha, current):
        raise _not_ours(local, branch, expected_head)
    where = None if replay else checked_out_in(local, branch)
    if where:
        raise FactoryStop("branch_exists", f"{branch} is checked out in {where}. Switch that worktree to another "
                          "branch, then ask again.")
    with tempfile.TemporaryDirectory(prefix="factory-import-") as tmp:
        work = Path(tmp) / "repo"
        try:
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--quiet", "--no-local",
                            "--no-checkout", "--", str(local), str(work)],
                           capture_output=True, timeout=600, env=_env(), check=True)
            _git(work, "checkout", "--quiet", "--detach", base_sha)
        except subprocess.CalledProcessError as exc:
            raise _stop(f"Could not start from {base_sha[:12]} in {local}: "
                        + exc.stderr.decode(errors="replace")[-300:]) from None
        applied = _git(work, "am", "--quiet", "--keep-cr", "--no-3way", data=patch, check=False,
                       env=_committer(local))
        if applied.returncode != 0:
            said = (applied.stdout + applied.stderr).decode(errors="replace")
            if "Patch is empty" in said or not patch.strip():
                raise _stop("The reviewed change has no file changes, so there is nothing to write. Nothing was "
                            "written to your repository.")
            raise _stop(f"The reviewed change does not apply on {base_sha[:12]}. Nothing was written to your "
                        "repository.")
        head = _text(work, "rev-parse", "HEAD")
        if replay:
            if _already_written(local, work, base_sha, current, head):
                return current
            raise _not_ours(local, branch, expected_head)
        # Staging refs a stopped import left behind. The objects stay until Git's
        # own pruning grace period, so a concurrent import is unaffected.
        for old in (_text(local, "for-each-ref", "--format=%(refname)", _IMPORT_PREFIX) or "").split():
            _git(local, "update-ref", "-d", old, check=False)
        staging = f"{_IMPORT_PREFIX}{head[:12]}"
        try:
            _git(local, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules",
                 str(work), f"+HEAD:{staging}")
            # Compare and swap: only if the branch is still exactly what was checked above.
            _git(local, "update-ref", "-m", "software factory: reviewed change", ref, head,
                 current or "0" * len(head))
        except subprocess.CalledProcessError:
            raise FactoryStop("stale_head", f"{branch} in {local} changed while the factory was writing it. "
                              "Nothing was overwritten.") from None
        finally:
            _git(local, "update-ref", "-d", staging, check=False)
    return head
