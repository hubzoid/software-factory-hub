"""Local repository mode: FACTORY_REPO is a folder on this computer.

No GitHub connection is needed. The stations still get their own clean clone
of the folder (the SDK clones a local path the same way it clones a URL), so
uncommitted edits in the person's working tree are never seen or touched.

The result is a reviewed local branch, not a draft pull request. The
implementer's patch is checked exactly as for GitHub (``scan``), applied in a
throwaway clone, and only then written into the person's repository as
``refs/heads/<branch>`` with a compare-and-swap ``git update-ref``. The person's
working tree, current branch and every other ref stay as they were, and none
of the repository's own Git hooks run.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from .errors import FactoryStop

#: A local folder path: absolute, or starting at the home folder.
PATH = re.compile(r"^~?/")
_ZERO = "0" * 40
_IMPORT_REF = "refs/factory-import/{short}"


def is_local(value: str | None) -> bool:
    return bool(value) and bool(PATH.match(str(value).strip()))


def folder(value: str) -> Path:
    return Path(os.path.expanduser(str(value).strip())).resolve()


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


def repo(value: str):
    """The folder as the factory's repository: its current branch is the base
    every plan and build starts from."""
    from .github import FactoryRefused, Repo

    path = folder(value)
    if not path.is_dir():
        raise FactoryRefused("repository_unavailable", f"{path} does not exist. Set FACTORY_REPO to a folder "
                             "with a Git repository in it.")
    if _text(path, "rev-parse", "--is-inside-work-tree") != "true":
        raise FactoryRefused("repository_unavailable", f"{path} is not a Git repository. Run `git init` there, "
                             "commit your code, then ask again.")
    top = Path(_text(path, "rev-parse", "--show-toplevel") or path).resolve()
    branch = _text(top, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise FactoryRefused("repository_unavailable", f"{top} is not on a branch (detached HEAD). Switch to the "
                             "branch the factory should start from, then ask again.")
    if not _text(top, "rev-parse", "--verify", "--quiet", "HEAD^{commit}"):
        raise FactoryRefused("repository_unavailable", f"{top} has no commits yet. Commit your code first: the "
                             "factory works from what is committed.")
    return Repo(connection="local", repository_id=0, full_name=f"local/{top.name}", default_branch=branch,
                clone_url=str(top), local_path=str(top))


def branch_head(local_path: str, branch: str) -> str | None:
    return _text(Path(local_path), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")


def _committer(local: Path) -> dict:
    """The person's own Git identity when they have one, else a plain factory one."""
    env = _env()
    if not _text(local, "config", "user.email"):
        env.update(GIT_COMMITTER_NAME="Software Factory", GIT_COMMITTER_EMAIL="factory@localhost")
    if not _text(local, "config", "user.name"):
        env.setdefault("GIT_COMMITTER_NAME", "Software Factory")
    return env


def _patch_ids(repo: Path, data: bytes) -> list[str]:
    out = _git(repo, "patch-id", "--stable", data=data, check=False)
    return [line.split()[0] for line in out.stdout.decode().splitlines() if line.strip()]


def _already_written(local: Path, base_sha: str, head: str, patch: bytes) -> bool:
    """`head` is exactly this patch on top of `base_sha`: an earlier attempt
    wrote it and the process stopped before saving that it had."""
    if _git(local, "merge-base", "--is-ancestor", base_sha, head, check=False).returncode != 0:
        return False
    written = _git(local, "log", "--reverse", "-p", "--format=commit %H", f"{base_sha}..{head}", check=False)
    wanted = _patch_ids(local, patch)
    return bool(wanted) and _patch_ids(local, written.stdout) == wanted


def import_branch(local_path: str, *, branch: str, patch: bytes, base_sha: str, expected_head: str | None) -> str:
    """Write the reviewed patch into the person's repository as `branch` and
    return its new head. A new branch must not exist yet; a revision must find
    the branch exactly at `expected_head`."""
    local = Path(local_path)
    ref = f"refs/heads/{branch}"
    current = branch_head(local_path, branch)
    if current is not None and current != expected_head and _already_written(local, base_sha, current, patch):
        return current
    if _text(local, "symbolic-ref", "--quiet", "HEAD") == ref:
        raise FactoryStop("branch_exists", f"{branch} is checked out in {local}. Switch to another branch, then "
                          "ask again.")
    if expected_head is None and current is not None:
        raise FactoryStop("branch_exists", f"{branch} already exists in {local} and the factory did not create it.")
    if expected_head is not None and current != expected_head:
        raise FactoryStop("stale_head", f"{branch} in {local} is not where the factory left it. A person must look "
                          "before anything else is written.")
    with tempfile.TemporaryDirectory(prefix="factory-import-") as tmp:
        work = Path(tmp) / "repo"
        try:
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--quiet", "--no-local",
                            "--no-checkout", "--", str(local), str(work)],
                           capture_output=True, timeout=600, env=_env(), check=True)
            _git(work, "checkout", "--quiet", "--detach", base_sha)
        except subprocess.CalledProcessError as exc:
            raise FactoryStop("push_rejected", f"Could not start from {base_sha[:12]} in {local}: "
                              + exc.stderr.decode(errors="replace")[-300:]) from None
        applied = _git(work, "am", "--quiet", "--keep-cr", "--no-3way", data=patch, check=False,
                       env=_committer(local))
        if applied.returncode != 0:
            raise FactoryStop("push_rejected", f"The reviewed change does not apply on {base_sha[:12]}. Nothing was "
                              "written to your repository.")
        head = _text(work, "rev-parse", "HEAD")
        staging = _IMPORT_REF.format(short=head[:12])
        try:
            _git(local, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", str(work), f"+HEAD:{staging}")
            # Compare and swap: only if the branch is still exactly what was checked above.
            _git(local, "update-ref", "-m", "software factory: reviewed change", ref, head, current or _ZERO)
        except subprocess.CalledProcessError:
            raise FactoryStop("stale_head", f"{branch} in {local} changed while the factory was writing it. "
                              "Nothing was overwritten.") from None
        finally:
            _git(local, "update-ref", "-d", staging, check=False)
    return head
