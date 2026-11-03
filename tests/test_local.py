"""Local repository mode's Git side (software_factory.local): which folders
qualify, and how a reviewed patch becomes a branch without touching anything else."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hubzoid.hubs import settings as hub_settings
from software_factory import local
from software_factory.errors import FactoryStop
from software_factory.github import FactoryRefused

from . import conftest as h

HUB = Path(__file__).resolve().parents[1]


@pytest.fixture
def folder(tmp_path) -> Path:
    repo = tmp_path / "mine"
    repo.mkdir()
    h.git(repo, "init", "--quiet", "--initial-branch=main")
    (repo / "calc.py").write_text("def total(xs):\n    return sum(xs) + 1\n")
    h.git(repo, "add", ".")
    h.git(repo, "commit", "--quiet", "-m", "Initial")
    return repo


def patch_for(repo: Path, tmp_path: Path, text: str = "def total(xs):\n    return sum(xs)\n") -> tuple[bytes, str]:
    """What the sandbox exports: format-patch of one commit on top of main."""
    work = tmp_path / f"box-{len(list(tmp_path.iterdir()))}"
    subprocess.run(["git", "clone", "--quiet", str(repo), str(work)], env=h.GIT_ENV, check=True)
    (work / "calc.py").write_text(text)
    h.git(work, "commit", "--quiet", "-am", "Fix total")
    base = h.git(work, "rev-parse", "HEAD~1").strip()
    return h.git(work, "format-patch", "--stdout", f"{base}..HEAD").encode(), base


def test_a_git_folder_on_a_branch_is_a_repository(folder):
    repo = local.repo(str(folder))
    assert (repo.local_path, repo.clone_url, repo.default_branch) == (str(folder), str(folder), "main")
    assert repo.full_name == "local/mine" and repo.connection == "local"


@pytest.mark.parametrize("setup,words", [
    (lambda p: p.rmdir(), "does not exist"),
    (lambda p: None, "not a Git repository"),
    (lambda p: h.git(p, "init", "--quiet"), "no commits"),
])
def test_unusable_folders_say_what_to_do(tmp_path, setup, words):
    path = tmp_path / "empty"
    path.mkdir()
    setup(path)
    with pytest.raises(FactoryRefused, match=words):
        local.repo(str(path))


def test_a_detached_head_is_refused(folder):
    h.git(folder, "checkout", "--quiet", "--detach")
    with pytest.raises(FactoryRefused, match="detached"):
        local.repo(str(folder))


def test_import_writes_only_the_branch(folder, tmp_path):
    (folder / "calc.py").write_text("# uncommitted\n")
    patch, base = patch_for(folder, tmp_path)
    head = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert h.git(folder, "show", "factory/fix:calc.py") == "def total(xs):\n    return sum(xs)\n"
    assert h.git(folder, "rev-parse", "factory/fix~1").strip() == base
    assert (folder / "calc.py").read_text() == "# uncommitted\n"
    assert h.git(folder, "symbolic-ref", "--short", "HEAD").strip() == "main"
    assert h.git(folder, "for-each-ref", "--format=%(refname)").split() == ["refs/heads/factory/fix",
                                                                           "refs/heads/main"]
    assert head == h.git(folder, "rev-parse", "factory/fix").strip()


def test_a_replay_after_the_write_settles_on_the_same_head(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    first = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    again = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert again == first


def test_a_branch_the_factory_did_not_write_is_refused(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    h.git(folder, "branch", "factory/fix")
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert stop.value.code == "branch_exists"
    assert h.git(folder, "rev-parse", "factory/fix").strip() == base


def test_the_checked_out_branch_is_never_written(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    h.git(folder, "checkout", "--quiet", "factory/fix")
    head = h.git(folder, "rev-parse", "HEAD").strip()
    later, _ = patch_for(folder, tmp_path, "def total(xs):\n    return sum(list(xs))\n")
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=later, base_sha=head, expected_head=head)
    assert stop.value.code == "branch_exists"


def test_a_patch_that_does_not_apply_writes_nothing(folder, tmp_path):
    patch, _ = patch_for(folder, tmp_path)
    (folder / "calc.py").write_text("something else entirely\n")
    h.git(folder, "commit", "--quiet", "-am", "Rewrite")
    moved = h.git(folder, "rev-parse", "HEAD").strip()
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=moved, expected_head=None)
    assert stop.value.code == "push_rejected"
    assert "factory/fix" not in h.git(folder, "branch", "--list")


def test_the_setting_accepts_a_folder_path():
    def problems(value):
        _, found = hub_settings.validate(HUB, hub_settings.parse_values(
            {"version": 1, "values": {"FACTORY_REPO": value}}), env={})
        return [p for p in found if p.key == "FACTORY_REPO"]

    assert problems("/Users/me/code/widget") == [] and problems("~/code/widget") == []
    assert problems("example-co/widget") == [] and problems("code") != []


def test_doctor_reports_a_local_folder_without_github(folder):
    import importlib.util

    spec = importlib.util.spec_from_file_location("factory_checks_local", HUB / "doctor" / "checks.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    row = checks.github({"hub_dir": str(HUB), "settings": {"FACTORY_REPO": str(folder)}})
    assert row["status"] == "ok" and "GitHub is not needed" in row["summary"]
    row = checks.github({"hub_dir": str(HUB), "settings": {"FACTORY_REPO": str(folder / "missing")}})
    assert row["status"] == "fail" and "does not exist" in row["summary"]
