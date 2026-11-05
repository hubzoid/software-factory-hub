"""Repository tools for the factory's build steps on this computer (no Docker).

When builds run without Docker (``FACTORY_BUILDS``: local, or auto with Docker
stopped), the analyst, implementer and reviewer work in a clone in a work
folder. These tools read, search and change that clone and run commands in it.
They have the same names, schemas and outputs on every runtime.

They work only inside a running factory work item whose station has a work
folder open. In chat, over MCP or anywhere else they refuse. Paths are
relative to the repository folder; ``..``, absolute paths and links are
refused, and nothing outside the clone is read or written. Commands run under
macOS's sandbox with no network and a clean environment (see
``software_factory/hostbox.py``).
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import re
import stat
import sys
from pathlib import Path

from agents import function_tool

READ_LIMIT = 256 * 1024
WRITE_LIMIT = 2 * 1024 * 1024
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache"}


class _Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _hub_dir() -> Path:
    try:
        from hubzoid.workflows import context

        return Path(context._ctx().hub_dir)
    except Exception:  # noqa: BLE001
        return Path(os.environ.get("HUBZOID_HUB_DIR") or Path(__file__).resolve().parents[1])


def _builds():
    code = str(_hub_dir() / "workflows" / "factory")
    if code not in sys.path:
        sys.path.insert(0, code)
    from software_factory import builds, hostbox

    return builds, hostbox


class _Repo:
    """The running station's clone: a folder descriptor opened without
    following any link (checked to be the folder the factory made), and the
    work folder its commands run in."""

    def __init__(self, fd: int, ws: Path):
        self.fd, self.ws = fd, ws


def _found() -> _Repo:
    """The clone of the factory station running now, or a refusal."""
    try:
        from hubzoid.workflows import context

        work = context._ctx().work or {}
    except Exception:  # noqa: BLE001 - no running work item (chat, MCP)
        work = {}
    item = (work.get("item") or {}).get("id")
    if not item or not work.get("station_call"):
        raise _Refused("not_in_a_build", "These tools work only inside the factory's own build steps. In chat, ask "
                                         "the factory for work instead.")
    builds, _ = _builds()
    found = builds.active(_hub_dir(), item)
    if not found:
        raise _Refused("no_build_folder", "No build folder is open for this work item.")
    return _Repo(found["repo_fd"], Path(found["folder"]))


def _parts(raw, *, allow_root: bool = True) -> list[str]:
    if not isinstance(raw, str) or "\x00" in raw:
        raise _Refused("invalid_path", "A path is text, relative to the repository folder.")
    text = raw.strip()
    if text.startswith("/"):
        raise _Refused("invalid_path", f"{raw} is absolute. Use a path relative to the repository folder.")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise _Refused("invalid_path", f"{raw} leaves the repository folder.")
    if not parts and not allow_root:
        raise _Refused("invalid_path", "Name a file.")
    return parts


def _open_dir(repo: _Repo, parts: list[str], *, create: bool = False) -> int:
    fd = os.dup(repo.fd)
    try:
        for part in parts:
            try:
                nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=fd)
                nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nfd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_bytes(repo: _Repo, parts: list[str], limit: int) -> bytes:
    dfd = _open_dir(repo, parts[:-1])
    try:
        # Never blocks: a named pipe the agent made opens at once, then is refused below.
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    finally:
        os.close(dfd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _Refused("not_a_file", f"{'/'.join(parts)} is not a file.")
        if info.st_nlink > 1:
            raise _Refused("refused", f"{'/'.join(parts)} is a hard link; it is not read.")
        if info.st_size > limit:
            raise _Refused("too_large", f"{'/'.join(parts)} is {info.st_size} bytes, over {limit}.")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            return fh.read(limit + 1)
    finally:
        os.close(fd)


def _write_bytes(repo: _Repo, parts: list[str], data: bytes) -> None:
    if parts[0] == ".git":
        raise _Refused("refused", "The factory's Git data is not edited directly. Use git commands with repo_run.")
    if len(data) > WRITE_LIMIT:
        raise _Refused("too_large", f"The content is over {WRITE_LIMIT} bytes.")
    dfd = _open_dir(repo, parts[:-1], create=True)
    try:
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=dfd)
    finally:
        os.close(dfd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise _Refused("not_a_file", f"{'/'.join(parts)} is not a file.")
    os.ftruncate(fd, 0)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _walk(repo: _Repo, parts: list[str]):
    """(relative path, name, dir fd) for every file under `parts`, never
    following a link, skipping Git data and dependency folders."""
    top_fd = _open_dir(repo, parts)
    try:
        for dirpath, dirnames, filenames, dirfd in os.fwalk(".", follow_symlinks=False, dir_fd=top_fd):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            rel_dir = "/".join([*parts, *[p for p in dirpath.split("/") if p not in ("", ".")]])
            for name in sorted(filenames):
                yield (f"{rel_dir}/{name}" if rel_dir else name), name, dirfd
    finally:
        os.close(top_fd)


def _ok(value) -> str:
    return json.dumps(value)


async def _guarded(fn, *args):
    repo = None
    try:
        repo = _found()
        return _ok(await asyncio.to_thread(fn, repo, *args))
    except _Refused as exc:
        return _ok({"error": exc.code, "message": exc.message})
    except FileNotFoundError:
        return _ok({"error": "not_found", "message": "No such file or folder in the repository."})
    except NotADirectoryError:
        return _ok({"error": "not_a_folder", "message": "That path is not a folder."})
    except OSError as exc:
        if exc.errno in (40, 62):          # ELOOP on Linux and macOS: a link
            return _ok({"error": "refused", "message": "That path is a link; links are not followed."})
        return _ok({"error": "os_error", "message": exc.strerror or str(exc)})
    finally:
        if repo is not None:
            os.close(repo.fd)


# -- the tools --------------------------------------------------------------------------------

def _list(repo: _Repo, path: str) -> dict:
    parts = _parts(path)
    fd = _open_dir(repo, parts)
    try:
        entries = []
        for name in sorted(os.listdir(fd)):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            kind = ("folder" if stat.S_ISDIR(info.st_mode) else "link" if stat.S_ISLNK(info.st_mode)
                    else "file" if stat.S_ISREG(info.st_mode) else "other")
            entries.append({"name": name, "type": kind, **({"bytes": info.st_size} if kind == "file" else {})})
            if len(entries) >= 1000:
                break
    finally:
        os.close(fd)
    return {"path": "/".join(parts) or ".", "entries": entries}


@function_tool(strict_mode=False)
async def repo_list(path: str = ".") -> str:
    """List a folder of the repository you are working on (names, types, sizes). Only for the factory's build
    steps. Paths are relative to the repository folder; "." is its top."""
    return await _guarded(_list, path)


def _read(repo: _Repo, path: str, offset: int, limit: int) -> dict:
    parts = _parts(path, allow_root=False)
    data = _read_bytes(repo, parts, READ_LIMIT)
    if b"\x00" in data[:8192]:
        return {"path": "/".join(parts), "binary": True, "bytes": len(data)}
    lines = data.decode("utf-8", errors="replace").splitlines()
    start = max(int(offset or 1), 1)
    count = min(max(int(limit or 400), 1), 2000)
    chunk = lines[start - 1:start - 1 + count]
    return {"path": "/".join(parts), "total_lines": len(lines), "from_line": start,
            "text": "\n".join(f"{start + i:>6}\t{line}" for i, line in enumerate(chunk)),
            **({"more": f"Lines {start + len(chunk)} to {len(lines)} not shown."}
               if start - 1 + len(chunk) < len(lines) else {})}


@function_tool(strict_mode=False)
async def repo_read(path: str, offset: int = 1, limit: int = 400) -> str:
    """Read a text file of the repository you are working on, with line numbers. Only for the factory's build
    steps. `offset` is the first line (from 1), `limit` the number of lines (at most 2000)."""
    return await _guarded(_read, path, offset, limit)


def _find(repo: _Repo, pattern: str) -> dict:
    if not isinstance(pattern, str) or not pattern.strip():
        raise _Refused("invalid_request", "Give a pattern, such as **/*.py or src/*.ts.")
    pattern = pattern.strip().lstrip("./")
    found = []
    for rel, name, _ in _walk(repo, []):
        if fnmatch.fnmatch(rel, pattern) or ("/" not in pattern and fnmatch.fnmatch(name, pattern)) or (
                pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:])):
            found.append(rel)
            if len(found) >= 500:
                return {"files": found, "more": "Over 500 files match; narrow the pattern."}
    return {"files": found}


@function_tool(strict_mode=False)
async def repo_find(pattern: str) -> str:
    """Find files in the repository you are working on by name pattern (for example **/*.py, src/*.ts or
    *.md). Only for the factory's build steps. Git data and dependency folders are skipped."""
    return await _guarded(_find, pattern)


def _search(repo: _Repo, pattern: str, path: str, files: str) -> dict:
    """grep -E in the clone, confined and stopped after 30 seconds, so no
    pattern can stall the hub."""
    if not isinstance(pattern, str) or not pattern:
        raise _Refused("invalid_request", "Give a pattern (an extended regular expression, as grep -E takes).")
    parts = _parts(path)
    os.close(_open_dir(repo, parts))           # the folder exists and is no link
    _, hostbox = _builds()
    argv = ["/usr/bin/grep", "-rnIE", *[f"--exclude-dir={d}" for d in sorted(SKIP_DIRS)]]
    if files:
        argv.append(f"--include={files}")
    argv += ["-e", pattern, "--", "/".join(parts) or "."]
    done = hostbox.run(repo.ws, argv, timeout=30, limit=200_000)
    if done["timed_out"]:
        raise _Refused("too_slow", "The search took over 30 seconds. Narrow the pattern or the path.")
    if done["exit_code"] not in (0, 1):
        raise _Refused("invalid_request", "grep refused the pattern: " + done["output"].strip()[-300:])
    matches = []
    for line in done["output"].splitlines():
        hit = re.match(r"^(.*?):(\d+):(.*)$", line)
        if not hit:
            continue
        matches.append({"path": hit.group(1).removeprefix("./"), "line": int(hit.group(2)),
                        "text": hit.group(3)[:300]})
        if len(matches) >= 200:
            return {"matches": matches, "more": "Over 200 matches; narrow the pattern or the path."}
    return {"matches": matches}


@function_tool(strict_mode=False)
async def repo_search(pattern: str, path: str = ".", files: str = "") -> str:
    """Search the text of the repository you are working on with an extended regular expression (as grep -E
    takes: [0-9], not \\d). Only for the factory's build steps. `path` limits it to a folder, `files` to a name
    pattern such as *.py."""
    return await _guarded(_search, pattern, path, files)


def _write(repo: _Repo, path: str, content: str) -> dict:
    parts = _parts(path, allow_root=False)
    if not isinstance(content, str):
        raise _Refused("invalid_request", "content is the file's full text.")
    data = content.encode("utf-8")
    _write_bytes(repo, parts, data)
    return {"path": "/".join(parts), "bytes": len(data)}


@function_tool(strict_mode=False)
async def repo_write(path: str, content: str) -> str:
    """Create or replace a file in the repository you are working on with the full text given. Only for the
    factory's implementer. Folders are created as needed."""
    return await _guarded(_write, path, content)


def _edit(repo: _Repo, path: str, old: str, new: str, replace_all: bool) -> dict:
    parts = _parts(path, allow_root=False)
    if not isinstance(old, str) or not old or not isinstance(new, str):
        raise _Refused("invalid_request", "old is the exact text to replace (not empty); new is its replacement.")
    text = _read_bytes(repo, parts, WRITE_LIMIT).decode("utf-8")
    count = text.count(old)
    if count == 0:
        raise _Refused("not_found", "old does not appear in the file. Read the file and copy the text exactly.")
    if count > 1 and not replace_all:
        raise _Refused("ambiguous", f"old appears {count} times. Give more surrounding text, or replace_all.")
    changed = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    _write_bytes(repo, parts, changed.encode("utf-8"))
    return {"path": "/".join(parts), "replaced": count if replace_all else 1}


@function_tool(strict_mode=False)
async def repo_edit(path: str, old: str, new: str, replace_all: bool = False) -> str:
    """Replace exact text in a file of the repository you are working on. Only for the factory's implementer.
    `old` must appear exactly once unless `replace_all` is true."""
    return await _guarded(_edit, path, old, new, replace_all)


def _run(repo: _Repo, command: str, timeout_seconds: int) -> dict:
    if not isinstance(command, str) or not command.strip():
        raise _Refused("invalid_request", "Give a shell command.")
    _, hostbox = _builds()
    done = hostbox.run(repo.ws, command, timeout=min(max(int(timeout_seconds or 300), 1), 1800))
    return {"exit_code": done["exit_code"], "output": done["output"], "timed_out": done["timed_out"]}


@function_tool(strict_mode=False)
async def repo_run(command: str, timeout_seconds: int = 300) -> str:
    """Run a shell command in the repository folder you are working on, such as the tests, lint or git. Only for
    the factory's build steps. It runs offline, without credentials, confined to the work folder, and must not
    wait for input. Returns the exit code and the output (long output is shortened)."""
    return await _guarded(_run, command, timeout_seconds)
