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


def patch_for(repo: Path, tmp_path: Path, text: str = "def total(xs):\n    return sum(xs)\n",
              files: dict[str, bytes] | None = None) -> tuple[bytes, str]:
    """What the sandbox exports: format-patch of one commit on top of main."""
    work = tmp_path / f"box-{len(list(tmp_path.iterdir()))}"
    subprocess.run(["git", "clone", "--quiet", str(repo), str(work)], env=h.GIT_ENV, check=True)
    (work / "calc.py").write_text(text)
    for name, data in (files or {}).items():
        (work / name).write_bytes(data)
    h.git(work, "add", "-A")
    h.git(work, "commit", "--quiet", "-m", "Fix total")
    base = h.git(work, "rev-parse", "HEAD~1").strip()
    out = subprocess.run(["git", "format-patch", "--stdout", "--binary", f"{base}..HEAD"], cwd=work, env=h.GIT_ENV,
                         capture_output=True, check=True).stdout
    return out, base


def test_a_git_folder_on_a_branch_is_a_repository(folder):
    repo = local.repo(str(folder))
    assert (repo.local_path, repo.clone_url, repo.default_branch) == (str(folder), str(folder), "main")
    assert repo.full_name.startswith("local/mine-") and repo.connection == "local"


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
    assert stop.value.code == "local_write_failed" and "does not apply" in stop.value.message
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


# -- review fixes: other worktrees, folders inside the hub, replay, identity -------------

def test_a_revision_never_brings_back_a_deleted_branch(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    head = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    work = tmp_path / "box-revision"                # the revision, built on the factory's branch
    subprocess.run(["git", "clone", "--quiet", "--branch", "factory/fix", str(folder), str(work)], env=h.GIT_ENV,
                   check=True)
    (work / "calc.py").write_text("def total(xs):\n    return sum(list(xs))\n")
    h.git(work, "commit", "--quiet", "-am", "Revise total")
    later = subprocess.run(["git", "format-patch", "--stdout", "--binary", "HEAD~1..HEAD"], cwd=work,
                           env=h.GIT_ENV, capture_output=True, check=True).stdout
    h.git(folder, "merge", "--quiet", "--ff-only", "factory/fix")   # the person merged it, then deleted it
    h.git(folder, "branch", "--quiet", "-d", "factory/fix")
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=later, base_sha=head, expected_head=head)
    assert stop.value.code == "stale_head" and "no longer" in stop.value.message
    assert local.branch_head(str(folder), "factory/fix") is None


def test_a_branch_checked_out_in_another_worktree_is_never_written(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    head = h.git(folder, "rev-parse", "factory/fix").strip()
    other = tmp_path / "other"
    h.git(folder, "worktree", "add", "--quiet", str(other), "factory/fix")
    later, _ = patch_for(folder, tmp_path, "def total(xs):\n    return sum(list(xs))\n")
    for path in (folder, other):                    # FACTORY_REPO as the main folder or the linked worktree
        with pytest.raises(FactoryStop) as stop:
            local.import_branch(str(path), branch="factory/fix", patch=later, base_sha=head, expected_head=head)
        assert stop.value.code == "branch_exists" and str(other.resolve()) in stop.value.message
    assert h.git(folder, "rev-parse", "factory/fix").strip() == head
    assert h.git(other, "status", "--porcelain") == ""


def test_a_linked_worktree_can_be_the_repository(folder, tmp_path):
    other = tmp_path / "other"
    h.git(folder, "worktree", "add", "--quiet", "-b", "dev", str(other))
    repo = local.repo(str(other))
    assert repo.default_branch == "dev" and repo.local_path == str(other.resolve())


def test_a_folder_inside_the_hub_is_refused(tmp_path):
    with pytest.raises(FactoryRefused, match="inside the hub"):
        local.repo(str(HUB / "fixtures" / "sample-repo"), hub_dir=HUB)
    with pytest.raises(FactoryRefused, match="inside the hub"):
        local.repo(str(HUB), hub_dir=HUB)
    # A Git repository made inside the hub folder is refused too.
    hub = tmp_path / "hub"
    inner = hub / "sample"
    inner.mkdir(parents=True)
    h.git(inner, "init", "--quiet", "--initial-branch=main")
    (inner / "a.txt").write_text("a\n")
    h.git(inner, "add", ".")
    h.git(inner, "commit", "--quiet", "-m", "a")
    with pytest.raises(FactoryRefused, match="inside the hub"):
        local.repo(str(inner), hub_dir=hub)
    # And a repository that contains the hub.
    with pytest.raises(FactoryRefused, match="holds the hub"):
        local.repo(str(inner), hub_dir=inner / "nested-hub")


def test_another_worktree_of_the_hubs_repository_is_refused(folder, tmp_path):
    hub_wt = tmp_path / "hub-wt"
    h.git(folder, "worktree", "add", "--quiet", "-b", "hub", str(hub_wt))
    with pytest.raises(FactoryRefused, match="worktree of the hub"):
        local.repo(str(folder), hub_dir=hub_wt)        # the hub is a linked worktree
    with pytest.raises(FactoryRefused, match="worktree of the hub"):
        local.repo(str(hub_wt), hub_dir=folder)        # FACTORY_REPO is a linked worktree of the hub's repository


def _other_case(path: Path) -> Path:
    """The same folder with its name typed in another letter case, or skip on a
    case-sensitive filesystem (Linux), where that is a different folder."""
    typed = path.parent / path.name.swapcase()
    if not typed.exists():
        pytest.skip("case-sensitive filesystem")
    return typed


def test_a_folder_typed_in_another_letter_case_is_the_same_folder(folder):
    # macOS: FACTORY_REPO typed ~/code/Widget for ~/code/widget is that folder.
    repo = local.repo(str(_other_case(folder)))
    assert Path(repo.local_path).samefile(folder) and repo.default_branch == "main"
    # The hub given in another letter case is still the hub.
    with pytest.raises(FactoryRefused, match="inside the hub"):
        local.repo(str(HUB), hub_dir=_other_case(HUB))


def test_a_subfolder_of_a_repository_is_refused(folder):
    (folder / "pkg").mkdir()
    with pytest.raises(FactoryRefused, match="inside the Git repository"):
        local.repo(str(folder / "pkg"))


def test_a_file_path_says_it_is_a_file(folder):
    with pytest.raises(FactoryRefused, match="is a file"):
        local.repo(str(folder / "calc.py"))


def test_two_folders_with_the_same_name_are_different_repositories(tmp_path):
    names = set()
    for parent in ("work", "oss"):
        path = tmp_path / parent / "api"
        path.mkdir(parents=True)
        h.git(path, "init", "--quiet", "--initial-branch=main")
        (path / "a.txt").write_text("a\n")
        h.git(path, "add", ".")
        h.git(path, "commit", "--quiet", "-m", "a")
        repo = local.repo(str(path))
        names.add((repo.full_name, repo.repository_id))
    assert len(names) == 2 and all(n.startswith("local/api-") for n, _ in names)


@pytest.mark.parametrize("config", [None, ("color.ui", "always"), ("diff.noprefix", "true"),
                                    ("diff.renames", "false"), ("log.showSignature", "true")])
def test_a_replay_settles_whatever_the_persons_git_settings(folder, tmp_path, config):
    if config:
        h.git(folder, "config", *config)
    patch, base = patch_for(folder, tmp_path)
    first = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    again = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert again == first


def test_a_replay_settles_with_a_binary_file(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path, files={"logo.png": bytes(range(256)) * 4})
    first = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert h.git(folder, "cat-file", "-s", "factory/fix:logo.png").strip() == "1024"
    again = local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert again == first


def test_a_different_change_on_the_branch_is_not_mistaken_for_a_replay(folder, tmp_path):
    patch, base = patch_for(folder, tmp_path)
    other, _ = patch_for(folder, tmp_path, "def total(xs):\n    return 0\n")
    local.import_branch(str(folder), branch="factory/fix", patch=other, base_sha=base, expected_head=None)
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert stop.value.code == "branch_exists"


def test_the_committer_is_the_identity_in_the_repositorys_own_config(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    h.git(folder, "config", "user.name", "Ana Example")
    h.git(folder, "config", "user.email", "ana@example.org")
    patch, base = patch_for(folder, tmp_path)
    local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert h.git(folder, "log", "-1", "--format=%cn <%ce>", "factory/fix").strip() == "Ana Example <ana@example.org>"


def test_without_an_identity_the_committer_is_the_factory(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    patch, base = patch_for(folder, tmp_path)
    local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert (h.git(folder, "log", "-1", "--format=%cn <%ce>", "factory/fix").strip()
            == "Software Factory <factory@localhost>")


def test_a_sha256_repository_works(tmp_path):
    repo = tmp_path / "sha"
    repo.mkdir()
    h.git(repo, "init", "--quiet", "--initial-branch=main", "--object-format=sha256")
    (repo / "calc.py").write_text("def total(xs):\n    return sum(xs) + 1\n")
    h.git(repo, "add", ".")
    h.git(repo, "commit", "--quiet", "-m", "Initial")
    patch, base = patch_for(repo, tmp_path)
    head = local.import_branch(str(repo), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert len(head) == 64 and h.git(repo, "rev-parse", "factory/fix").strip() == head


def test_stale_import_refs_are_cleared(folder, tmp_path):
    base = h.git(folder, "rev-parse", "HEAD").strip()
    h.git(folder, "update-ref", "refs/factory-import/abcdef012345", base)
    patch, base = patch_for(folder, tmp_path)
    local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert "factory-import" not in h.git(folder, "for-each-ref", "--format=%(refname)")


def test_an_empty_change_says_so(folder, tmp_path):
    work = tmp_path / "box-empty"
    subprocess.run(["git", "clone", "--quiet", str(folder), str(work)], env=h.GIT_ENV, check=True)
    h.git(work, "commit", "--quiet", "--allow-empty", "-m", "Nothing")
    base = h.git(work, "rev-parse", "HEAD~1").strip()
    patch = subprocess.run(["git", "format-patch", "--stdout", f"{base}..HEAD"], cwd=work, env=h.GIT_ENV,
                           capture_output=True, check=True).stdout
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert stop.value.code == "local_write_failed" and "no file changes" in stop.value.message


def test_a_git_timeout_is_a_clear_stop(folder, tmp_path, monkeypatch):
    patch, base = patch_for(folder, tmp_path)
    real = subprocess.run

    def slow(argv, *a, **kw):
        if "clone" in argv:
            raise subprocess.TimeoutExpired(argv, 600)
        return real(argv, *a, **kw)

    monkeypatch.setattr(local.subprocess, "run", slow)
    with pytest.raises(FactoryStop) as stop:
        local.import_branch(str(folder), branch="factory/fix", patch=patch, base_sha=base, expected_head=None)
    assert stop.value.code == "local_write_failed" and "too long" in stop.value.message
    assert "factory/fix" not in h.git(folder, "branch", "--list")


def test_folders_are_shown_from_the_home_folder(monkeypatch):
    monkeypatch.setenv("HOME", "/Users/ana")
    assert local.shown("/Users/ana/code/acme") == "~/code/acme"
    assert local.shown("/Users/anabel/x") == "/Users/anabel/x" and local.shown("/srv/x") == "/srv/x"


def _checks():
    import importlib.util

    spec = importlib.util.spec_from_file_location("factory_checks_local", HUB / "doctor" / "checks.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    return checks


def test_doctor_refuses_the_sample_inside_the_hub():
    row = _checks().github({"hub_dir": str(HUB), "settings": {"FACTORY_REPO": str(HUB / "fixtures" / "sample-repo")}})
    assert row["status"] == "fail" and "inside the hub" in row["summary"]


def test_doctor_says_the_github_channel_is_not_used_in_local_mode(folder):
    checks = _checks()
    row = checks.channels({"hub_dir": str(HUB), "settings": {"FACTORY_REPO": str(folder),
                                                            "FACTORY_CHANNELS": ["chat", "mcp", "github"]}})
    assert row["status"] == "ok" and "github channel is not used" in row["summary"]
    row = checks.channels({"hub_dir": str(HUB), "settings": {"FACTORY_REPO": str(folder),
                                                            "FACTORY_CHANNELS": ["chat", "mcp"]}})
    assert "not used" not in row["summary"]


def test_the_reviewer_is_not_shown_the_implementers_own_commit():
    from types import SimpleNamespace

    from software_factory import stations
    from software_factory.schemas import Analysis, Implementation

    a = Analysis(problem_statement="p", approach="a", plan=["s"], affected_surface=[], risks=[],
                 acceptance_criteria=["total is right"], test_strategy="t", assumptions=[], open_questions=[],
                 handoff_id=None)
    impl = Implementation.model_construct(committed=True, head_commit="9f5a193" + "0" * 33)
    request = SimpleNamespace(source="chat", trigger="chat", instruction="Fix total")
    msg = stations.reviewer_message(request, {}, a, impl, "", branch="factory/fix", base_sha="a" * 40,
                                    pushed_sha="04bfd28" + "0" * 33)
    assert "9f5a193" not in msg and "04bfd28" in msg
