"""Check an exported patch before it is published (gh-aw's safe outputs).

The implementer's commits leave the sandbox as ``git format-patch`` bytes.
Before anything is pushed, deterministic code checks them:

* size and file count caps (gh-aw ``create_pull_request.cjs`` defaults:
  4 MiB, 100 files);
* paths the factory never changes: CI workflows, git metadata and hooks,
  anything outside the repository;
* protected files that may change but need a person's eye in review
  (manifests, lockfiles, CODEOWNERS, agent instructions, top-level dot
  folders), following gh-aw's ``request-review`` default;
* credentials in added lines (Hubzoid's own redaction patterns).

A refusal stops the work with the reason; nothing is pushed. A caution is
written into the pull request body and the evidence.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

MAX_PATCH_BYTES = 4 * 2**20
MAX_FILES = 100

#: Never published by the factory.
DENY = (".github/workflows/*", ".github/workflows/**", ".git/*", ".git/**", ".gitmodules", ".githooks/**",
        ".husky/**")
#: May change, but a person must look (gh-aw's default protected list).
PROTECTED = ("package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
             "go.mod", "go.sum", "requirements*.txt", "pyproject.toml", "poetry.lock", "uv.lock", "Pipfile",
             "Pipfile.lock", "setup.py", "setup.cfg", "Gemfile", "Gemfile.lock", "pom.xml", "build.gradle",
             "build.gradle.kts", "Cargo.toml", "Cargo.lock", "mix.exs", "mix.lock", "*.csproj", "CODEOWNERS",
             ".github/CODEOWNERS", "AGENTS.md", "CLAUDE.md", "DESIGN.md", "README.md", "CONTRIBUTING.md",
             "SECURITY.md", "CODE_OF_CONDUCT.md", ".mcp.json")

_DIFF_FILE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.M)
_SYMLINK = re.compile(r"^new file mode 120000$|^new mode 120000$", re.M)


@dataclass
class ScanResult:
    ok: bool
    files: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    commits: int = 0
    bytes: int = 0

    def to_json(self) -> dict:
        return {"ok": self.ok, "files": self.files, "refusals": self.refusals, "cautions": self.cautions,
                "commits": self.commits, "bytes": self.bytes}


def _match(path: str, patterns) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or (("/" not in p) and fnmatch.fnmatch(name, p)) for p in patterns)


def _added_lines(patch: str) -> list[str]:
    out = []
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
    return out


def _secrets(lines: list[str]) -> list[str]:
    """Added lines that look like a credential, by Hubzoid's redaction rules."""
    from hubzoid import redaction

    found = []
    for i, line in enumerate(lines):
        if redaction.scrub_text(line) != line:
            found.append(f"added line {i + 1} looks like a credential")
    return found


def check(patch: bytes) -> ScanResult:
    result = ScanResult(ok=True, bytes=len(patch))
    if not patch:
        return ScanResult(ok=False, refusals=["The implementer committed nothing."])
    if len(patch) > MAX_PATCH_BYTES:
        result.refusals.append(f"The patch is {len(patch)} bytes, over the {MAX_PATCH_BYTES} byte limit.")
    text = patch.decode("utf-8", errors="replace")
    result.commits = text.count("\nSubject: ") + (1 if text.startswith("Subject: ") else 0)
    files: list[str] = []
    for a, b in _DIFF_FILE.findall(text):
        for path in (a, b):
            if path not in files:
                files.append(path)
    result.files = files
    if len(files) > MAX_FILES:
        result.refusals.append(f"The patch touches {len(files)} files, over the {MAX_FILES} file limit.")
    for path in files:
        if path.startswith("/") or ".." in path.split("/"):
            result.refusals.append(f"{path} is outside the repository.")
        elif _match(path, DENY):
            result.refusals.append(f"{path} is never changed by the factory (CI workflows and git metadata).")
        elif _match(path, PROTECTED) or (path.startswith(".") and "/" in path and not path.startswith(".github/")):
            result.cautions.append(f"{path} is a protected file. Check this change carefully before marking the "
                                   "pull request ready.")
    if _SYMLINK.search(text):
        result.refusals.append("The patch adds a symbolic link, which the factory never publishes.")
    if "GIT binary patch" in text or "\nBinary files " in text:
        result.cautions.append("The patch changes a binary file. Review it by hand.")
    result.refusals.extend(_secrets(_added_lines(text)))
    result.ok = not result.refusals
    return result
