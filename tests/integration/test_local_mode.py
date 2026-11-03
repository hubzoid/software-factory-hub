"""Local repository mode (Phase 1, plan #12): FACTORY_REPO is a folder on this
computer. Plans and builds run as usual, nothing touches GitHub, and the
result is a reviewed branch in that folder. The person's working tree, current
branch and uncommitted edits are never touched."""
from __future__ import annotations

import subprocess

import pytest

from .. import conftest as h


def outcome(out):
    return out["factory_v1"]["outcome"], out["factory_v1"].get("stop_reason")


@pytest.fixture
def mine(factory, tmp_path):
    """The person's own clone, on main, with an uncommitted edit and an untracked file."""
    folder = tmp_path / "mine"
    subprocess.run(["git", "clone", "--quiet", str(factory.remote.bare), str(folder)], env=h.GIT_ENV, check=True)
    (factory.hub_dir / "hub.settings.yaml").write_text(
        f"version: 1\nvalues:\n  FACTORY_REPO: {folder}\n  FACTORY_CHANNELS: [chat, mcp]\nsecrets: {{}}\n")
    (folder / "calc.py").write_text((folder / "calc.py").read_text() + "# my own note, not committed\n")
    (folder / "notes.txt").write_text("scratch\n")
    factory.remote.extra.append(folder)
    return folder


def untouched(folder) -> None:
    assert h.git(folder, "symbolic-ref", "--short", "HEAD").strip() == "main"
    assert "my own note, not committed" in (folder / "calc.py").read_text()
    assert h.git(folder, "status", "--porcelain") == " M calc.py\n?? notes.txt\n"


def test_a_chat_request_ends_in_a_reviewed_local_branch(factory, mine):
    out = factory.run(factory.chat("Fix total() in calc.py, it adds one too many"))
    rec = out["factory_v1"]
    assert outcome(out) == ("review_ready", None)
    branch = rec["branch"]
    head = h.git(mine, "rev-parse", f"refs/heads/{branch}").strip()
    assert head == rec["pushed_sha"] and rec["reviews"][-1]["checkout_commit"] == head
    assert h.git(mine, "show", f"{branch}:calc.py") == "def total(xs):\n    return sum(xs)\n"
    assert h.git(mine, "merge-base", "--is-ancestor", factory.remote.base, head) == ""
    untouched(mine)
    assert rec["repository"] == "local/mine" and rec["local_path"] == str(mine)
    assert {c["checkout"]["url"] for c in factory.stations.calls if c["checkout"]} == {str(mine)}
    assert [s[0] for s in factory.people.seen].count("plan") == 1            # the plan still waits for approval
    assert f"git switch {branch}" in out["reply"] and "pull request" not in out["reply"]
    assert not factory.api.calls                                              # GitHub was never asked anything
    assert not [r for r in h.git(mine, "for-each-ref", "--format=%(refname)").split() if "factory-import" in r]


def test_a_revision_continues_the_same_local_branch(factory, mine):
    factory.stations.verdicts = ["request_changes", "approve"]
    out = factory.run(factory.chat("Fix total() in calc.py, it adds one too many"))
    rec = out["factory_v1"]
    assert outcome(out) == ("review_ready", None)
    assert len(rec["reviews"]) == 2
    first, final = rec["reviews"][0]["checkout_commit"], rec["pushed_sha"]
    assert h.git(mine, "rev-parse", f"{final}^").strip() == first             # built on the factory's own head
    assert h.git(mine, "rev-parse", f"refs/heads/{rec['branch']}").strip() == final
    untouched(mine)


def test_a_branch_moved_by_someone_else_is_not_overwritten(factory, mine):
    factory.stations.verdicts = ["request_changes", "approve"]
    from software_factory import local

    real = local.import_branch
    seen = {"n": 0}

    def person_commits_in_between(path, **kw):
        seen["n"] += 1
        if seen["n"] == 2:                                                    # the person moves the branch first
            h.git(path, "branch", "-f", kw["branch"], factory.remote.base)
        return real(path, **kw)

    factory._mp.setattr(local, "import_branch", person_commits_in_between)
    out = factory.run(factory.chat("Fix total() in calc.py, it adds one too many"))
    assert outcome(out) == ("stopped", "stale_head")
    assert h.git(mine, "rev-parse", f"refs/heads/{out['factory_v1']['branch']}").strip() == factory.remote.base
    untouched(mine)


def test_github_issues_have_no_meaning_on_a_local_folder(factory, mine):
    out = factory.run(factory.chat("Fix issue 12", issue=12))
    assert outcome(out) == ("stopped", "local_mode")
    assert not factory.stations.calls and not factory.api.calls


def test_only_plan_and_implement_run_on_a_local_folder(factory, mine):
    factory.model.route = dict(factory.model.route, route="answer")
    out = factory.run(factory.chat("What does calc.py do?"))
    assert outcome(out) == ("stopped", "local_mode")
    assert not factory.stations.calls and not factory.api.calls
