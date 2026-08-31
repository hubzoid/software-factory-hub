"""The patch check before anything is published (gh-aw's safe outputs)."""
from software_factory import scan


def patch(path: str, added: str = "x = 1", mode: str = "") -> bytes:
    return (f"From abc Mon Sep 17 00:00:00 2001\nSubject: [PATCH] change\n\n---\n"
            f"diff --git a/{path} b/{path}\n{mode}--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+{added}\n").encode()


def test_a_plain_change_passes():
    out = scan.check(patch("calc.py"))
    assert out.ok and out.files == ["calc.py"] and out.commits == 1 and not out.cautions


def test_ci_workflows_and_git_metadata_are_refused():
    for path in (".github/workflows/ci.yml", ".gitmodules", ".git/hooks/pre-commit", ".husky/pre-push"):
        out = scan.check(patch(path))
        assert not out.ok and out.refusals, path


def test_protected_files_pass_with_a_caution():
    for path in ("package.json", "requirements-dev.txt", "AGENTS.md", "CODEOWNERS", "uv.lock", ".claude/settings.json"):
        out = scan.check(patch(path))
        assert out.ok and out.cautions, path


def test_credentials_in_added_lines_are_refused():
    out = scan.check(patch("config.py", added='TOKEN = "ghp_' + "a" * 36 + '"'))
    assert not out.ok and any("credential" in r for r in out.refusals)


def test_symlinks_paths_and_size():
    assert not scan.check(patch("link", mode="new file mode 120000\n")).ok
    assert not scan.check(patch("../outside.py")).ok
    assert not scan.check(b"x" * (scan.MAX_PATCH_BYTES + 1)).ok
    assert not scan.check(b"").ok
    many = b"".join(patch(f"f{i}.py") for i in range(scan.MAX_FILES + 1))
    assert not scan.check(many).ok


def test_quoted_paths_cannot_hide_a_workflow_change():
    """A rename from a name with a tab is a C-quoted header: still checked."""
    quoted = (b'From abc Mon Sep 17 00:00:00 2001\nSubject: [PATCH] mv\n\n---\n'
              b'diff --git "a/we\\tird" b/.github/workflows/ci.yml\nsimilarity index 100%\n'
              b'rename from "we\\tird"\nrename to .github/workflows/ci.yml\n')
    out = scan.check(quoted)
    assert not out.ok and ".github/workflows/ci.yml" in out.files
    assert any("never changed" in r for r in out.refusals)


def test_octal_quoted_names_are_decoded():
    path = scan._unquote('"caf\\303\\251.py"')
    assert path == "café.py"


def test_unreadable_patches_are_refused():
    assert not scan.check(b"diff --git broken header\n+x\n").ok
    assert not scan.check(b"not a patch at all\n").ok
