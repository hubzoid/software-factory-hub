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

_SYMLINK = re.compile(r"^new file mode 120000$|^new mode 120000$", re.M)
_ESCAPES = {"a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def _unquote(token: str) -> str:
    """A path as Git writes it in a patch header: plain, or C-quoted with
    escapes and octal bytes when it holds unusual characters."""
    if not (len(token) >= 2 and token.startswith('"') and token.endswith('"')):
        return token
    raw, out, i = token[1:-1], bytearray(), 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt in "01234567" and i + 3 < len(raw) + 1 and re.fullmatch(r"[0-7]{3}", raw[i + 1:i + 4] or ""):
                out.append(int(raw[i + 1:i + 4], 8))
                i += 4
                continue
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt].encode()
                i += 2
                continue
            raise ValueError(f"unknown escape in {token!r}")
        out += ch.encode()
        i += 1
    return out.decode("utf-8", errors="replace")


def _split_header(rest: str) -> tuple[str, str]:
    """The two paths of `diff --git <a> <b>`, quoted or not."""
    tokens: list[str] = []
    i = 0
    while i < len(rest) and len(tokens) < 2:
        if rest[i] == " ":
            i += 1
            continue
        if rest[i] == '"':
            j = i + 1
            while j < len(rest) and not (rest[j] == '"' and rest[j - 1] != "\\"):
                j += 1
            tokens.append(rest[i:j + 1])
            i = j + 1
        else:
            # unquoted: "a/x b/y" with no quotes; split at " b/" (Git's own rule for sane paths)
            k = rest.find(" b/", i) if not tokens else len(rest)
            tokens.append(rest[i:k] if k != -1 else rest[i:])
            i = k if k != -1 else len(rest)
    if len(tokens) != 2:
        raise ValueError("unparsable diff header")
    a, b = (_unquote(t) for t in tokens)
    if not (a.startswith("a/") and b.startswith("b/")):
        raise ValueError("unparsable diff header")
    return a[2:], b[2:]


def _header_paths(text: str) -> tuple[list[str], int]:
    """Every path a patch names (old and new names of renames and copies),
    and the number of file sections. Raises on anything unparsable."""
    paths: list[str] = []
    sections = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            sections += 1
            a, b = _split_header(line[len("diff --git "):])
            paths += [a, b]
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            paths.append(_unquote(line.split(" ", 2)[2]))
    return paths, sections


def _git_paths(patch: bytes) -> list[str] | None:
    """The new path of every file section, as Git itself reads the patch
    (NUL-delimited, no quoting). None when Git is not available."""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("git"):
        return None
    with tempfile.TemporaryDirectory(prefix="factory-scan-") as tmp:
        res = subprocess.run(["git", "apply", "--numstat", "-z", "-"], input=patch, cwd=tmp, capture_output=True,
                             timeout=60)
    if res.returncode != 0:
        raise ValueError("git could not read the patch")
    out: list[str] = []
    parts = res.stdout.split(b"\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry:
            i += 1
            continue
        fields = entry.split(b"\t", 2)
        if len(fields) == 3 and fields[2]:
            out.append(fields[2].decode("utf-8", errors="replace"))
            i += 1
        elif len(fields) == 3:          # a rename: the old and new paths follow
            out += [parts[i + 1].decode("utf-8", errors="replace"), parts[i + 2].decode("utf-8", errors="replace")]
            i += 3
        else:
            raise ValueError("unexpected numstat output")
    return out


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
    try:
        named, sections = _header_paths(text)
        from_git = _git_paths(patch)
    except (ValueError, IndexError) as exc:
        return ScanResult(ok=False, refusals=[f"The patch could not be read safely ({exc}). Nothing was published."],
                          bytes=len(patch))
    if sections == 0 and patch.strip():
        return ScanResult(ok=False, refusals=["The patch has no file changes the factory can read."],
                          bytes=len(patch))
    for path in named + (from_git or []):
        if path not in files:
            files.append(path)
    if from_git is not None and set(from_git) - set(named):
        result.refusals.append("Git reads paths in the patch that its headers do not show. Nothing was published.")
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
