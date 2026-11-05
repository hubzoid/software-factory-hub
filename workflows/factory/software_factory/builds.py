"""Where the analyst, implementer and reviewer work: Docker, or locally.

``FACTORY_BUILDS`` picks it: ``docker``, ``local`` (this computer, without
Docker; macOS for now) or ``auto`` (Docker when it is running, else locally).
Each work item decides once and keeps its choice, so a recovered run never
switches.

Locally, each station call gets its own work folder in the system's temporary
folder: a clone of the repository (with the person's Git credentials, which
stay out of the clone), the repository's dependencies from the setup command,
and nothing else. What the factory knows about a folder (its base commit, the
identity of its clone) is kept beside it, where the station can't write. The
station's ``repo_*`` tools find the folder through the work item that is
running, so they refuse anywhere else (in chat, over MCP). When the call ends,
the factory exports the new commits as a patch, exactly as the Docker sandbox
does, records it, and removes the folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import hostbox
from .errors import FactoryStop

MODES = ("auto", "docker", "local")
STATIONS = ("analyst", "implementer", "reviewer")
RECORD = "factory_v1:build:{call}"
IDENTITY = ("Software Factory", "software-factory@example.invalid")
CHECKOUT_PHRASE = "/workspace/repo"
LOCAL_PHRASE = "your repository folder (the repo_* tools' paths are relative to it)"
SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def station_name(agent: str) -> str:
    return f"local-{agent}"


def local_message(message: str) -> str:
    """A station message for a local build: the checkout is the repo_* tools'
    folder, not /workspace/repo."""
    return message.replace(CHECKOUT_PHRASE, LOCAL_PHRASE)


# -- choosing -------------------------------------------------------------------------------

def docker_running(hub_dir: Path) -> bool:
    try:
        from hubzoid.sandbox import service as sandbox_service

        checks = (sandbox_service.doctor(hub_dir) or {}).get("checks") or []
    except Exception:  # noqa: BLE001 - no Docker, or no sandbox.yaml: not running
        return False
    docker = [c for c in checks if str(c.get("id", "")).startswith("provider:")]
    return bool(docker) and all(c.get("status") == "pass" for c in docker)


def choose(hub_dir: Path, setting: str | None) -> dict:
    """{mode, reason}: where this work item's builds run."""
    setting = (setting or "auto").strip().lower()
    if setting not in MODES:
        raise FactoryStop("settings_invalid", f"FACTORY_BUILDS is {setting!r}; use auto, docker or local.")
    if setting == "docker":
        return {"mode": "docker", "reason": "FACTORY_BUILDS is docker."}
    if setting == "auto" and docker_running(hub_dir):
        return {"mode": "docker", "reason": "Docker is running."}
    why = hostbox.unsupported()
    if why:
        raise FactoryStop("builds_unavailable", why if setting == "local" else "Docker isn't running. " + why)
    return {"mode": "local", "reason": "FACTORY_BUILDS is local." if setting == "local"
            else "Docker isn't running, so builds run locally."}


def registry_hosts(hub_dir: Path, profile_id: str | None) -> list[str]:
    """The package registries the setup command may reach: the Docker
    profile's own setup allowlist, so both kinds of build allow the same."""
    from hubzoid.sandbox import config as config_lib

    try:
        return config_lib.load_profile(hub_dir, profile_id or "factory").setup_hosts()
    except Exception:  # noqa: BLE001 - no profile file: the standard registries
        return sorted(config_lib.PRESETS["registries-v1"])


# -- work folders ---------------------------------------------------------------------------

def root(hub_dir: Path) -> Path:
    """This hub's work folders, in the system's temporary folder: never under
    the hub or a home folder, because tools look for settings in parent
    folders (pytest finds a pytest.ini above the clone, which the sandbox
    then refuses to read). The patches stay in the hub's output."""
    hub_dir = Path(hub_dir).resolve()
    key = hashlib.sha256(str(hub_dir).encode()).hexdigest()[:10]
    base = Path(tempfile.gettempdir()).resolve() / "hubzoid-factory-builds"
    base.mkdir(mode=0o700, exist_ok=True)
    return base / f"{_safe(hub_dir.name)}-{key}"


def folder(hub_dir: Path, item_id: str, key: str) -> Path:
    return root(hub_dir) / _safe(item_id) / _safe(key)


def _safe(part: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(part))[:120].strip(".-")
    if not cleaned:
        raise ValueError("empty folder name")
    return cleaned


def _ready_file(ws: Path) -> Path:
    """What the factory knows about a work folder, beside it (the station writes only inside it)."""
    return ws.parent / f"{ws.name}.ready.json"


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "USER", "LANG", "SSH_AUTH_SOCK",
                                                           "GIT_SSH_COMMAND", "TMPDIR")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _host_git(repo: Path, *args, timeout: int = 120) -> str:
    return subprocess.run([hostbox.git_path() or "git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True, timeout=timeout, env=_git_env()).stdout


def _plain(url: str) -> str:
    from hubzoid.sandbox.service import plain_url

    return plain_url(url)


def _identity(path: Path) -> list[int]:
    st = os.stat(path, follow_symlinks=False)
    return [st.st_dev, st.st_ino]


def prepare(hub_dir: Path, ws: Path, checkout: dict, setup: str | None, *, hosts=()) -> dict:
    """The work folder, ready: cloned at the requested ref or commit on the
    host (credentials stay out of the clone), then the setup command,
    confined, reaching only the package registries in `hosts`. Safe to call
    again: a ready folder is kept."""
    marker = _ready_file(ws)
    if marker.is_file() and ws.is_dir():
        return json.loads(marker.read_text())
    marker.unlink(missing_ok=True)
    if ws.exists() or ws.is_symlink():
        shutil.rmtree(ws, ignore_errors=True)          # a start that was cut off
    ws.mkdir(parents=True, mode=0o700)
    parts = hostbox.folders(ws)
    for name in ("home", "tmp"):
        parts[name].mkdir(mode=0o700)
    url, ref, pin = checkout.get("url") or "", checkout.get("ref"), checkout.get("commit")
    if not url:
        raise FactoryStop("checkout_failed", "The factory has no repository to check out.")
    args = [hostbox.git_path() or "git", "-c", "core.hooksPath=/dev/null", "clone", "--quiet", "--no-local"]
    if ref:
        args += ["--branch", ref]
    try:
        cloned = subprocess.run(args + ["--", url, str(parts["repo"])], capture_output=True, text=True,
                                timeout=600, env=_git_env())
    except subprocess.TimeoutExpired:
        raise FactoryStop("checkout_failed", "Cloning the repository took longer than 10 minutes.") from None
    if cloned.returncode != 0:
        raise FactoryStop("checkout_failed", "Could not clone the repository: " + _scrub(cloned.stderr)[-400:])
    repo = parts["repo"]
    if pin:
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", str(pin)):
            raise FactoryStop("checkout_failed", "The commit to build on is not a commit id.")
        try:
            _host_git(repo, "checkout", "--quiet", "--detach", pin)
        except subprocess.CalledProcessError:
            raise FactoryStop("checkout_failed", f"The commit {str(pin)[:12]} is not in the repository's "
                                                 "history.") from None
    # The clone keeps the plain address and no credential settings.
    _host_git(repo, "remote", "set-url", "origin", _plain(url) if "://" in url else "https://invalid.local/repo.git")
    config = repo / ".git" / "config"
    config.write_text("\n".join(line for line in config.read_text().splitlines()
                                if not any(k in line.lower() for k in ("extraheader", "credential", "askpass")))
                      + "\n")
    _host_git(repo, "config", "user.name", IDENTITY[0])
    _host_git(repo, "config", "user.email", IDENTITY[1])
    commit = _host_git(repo, "rev-parse", "HEAD").strip()
    if not SHA.fullmatch(commit):
        raise FactoryStop("checkout_failed", "The clone's commit could not be read.")
    if setup and setup.strip():
        with hostbox.RegistryProxy(hosts) as proxy:
            done = hostbox.run(ws, setup, proxy_port=proxy.port, timeout=900, limit=4000)
        if done["exit_code"] != 0:
            raise FactoryStop("setup_failed", f"The setup command (FACTORY_LOCAL_SETUP) exited with "
                              f"{done['exit_code']}" + (" (timed out)" if done["timed_out"] else "")
                              + ". It may reach only the package registries in sandboxes/factory.yaml. "
                              "Last output:\n" + _scrub(done["output"])[-1500:])
    ready = {"commit": commit, "ref": ref, "source": _plain(url) if "://" in url else url,
             "ws": _identity(ws), "repo": _identity(repo)}
    marker.write_text(json.dumps(ready))
    return ready


def _scrub(text: str) -> str:
    try:
        from hubzoid import redaction

        return redaction.scrub_text(text)
    except Exception:  # noqa: BLE001
        return text


# -- the station's folder -------------------------------------------------------------------

def _active_file(hub_dir: Path, item_id: str) -> Path:
    return root(hub_dir) / _safe(item_id) / "active.json"


def activate(hub_dir: Path, item_id: str, ws: Path, agent: str) -> None:
    ready = json.loads(_ready_file(ws).read_text())
    target = _active_file(hub_dir, item_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"key": ws.name, "agent": agent, "ws": ready["ws"], "repo": ready["repo"]}))


def deactivate(hub_dir: Path, item_id: str) -> None:
    _active_file(hub_dir, item_id).unlink(missing_ok=True)


def _tidy(ws: Path) -> None:
    """Remove a work folder, and its work item's folder once nothing is left in it."""
    shutil.rmtree(ws, ignore_errors=True)
    _ready_file(ws).unlink(missing_ok=True)
    try:
        ws.parent.rmdir()
    except OSError:
        pass                      # another station's folder or the active marker is still there


def discard(hub_dir: Path, item_id: str, ws: Path) -> None:
    """Remove the work folder of a station that stopped the work."""
    deactivate(hub_dir, item_id)
    _tidy(ws)


def active(hub_dir: Path, item_id: str) -> dict | None:
    """The station running now for this work item: its work folder, and its
    clone opened as a folder descriptor that never followed a link and is the
    same folder the factory made. The caller closes `repo_fd`."""
    try:
        data = json.loads(_active_file(hub_dir, item_id).read_text())
        item_fd = os.open(root(hub_dir) / _safe(item_id), _DIR)
    except (OSError, ValueError):
        return None
    try:
        ws_fd = os.open(_safe(data["key"]), _DIR, dir_fd=item_fd)
        try:
            repo_fd = os.open("repo", _DIR, dir_fd=ws_fd)
            ws_id = os.fstat(ws_fd)
        finally:
            os.close(ws_fd)
    except (OSError, KeyError, ValueError):
        return None
    finally:
        os.close(item_fd)
    repo_id = os.fstat(repo_fd)
    if [ws_id.st_dev, ws_id.st_ino] != data.get("ws") or [repo_id.st_dev, repo_id.st_ino] != data.get("repo"):
        os.close(repo_fd)
        return None
    return {"folder": root(hub_dir) / _safe(item_id) / _safe(data["key"]), "repo_fd": repo_fd,
            "agent": data.get("agent")}


# -- after the call -------------------------------------------------------------------------

def finish(hub_dir: Path, item_id: str, ws: Path, call_id: str, *, export: bool) -> dict:
    """Record what the station left (its commits as a patch, whether files
    were changed without a commit), then remove the work folder. Done once:
    a recovered run finds the record."""
    from hubzoid import hub

    key = RECORD.format(call=call_id)
    saved = hub.shared_state.get(key)
    if isinstance(saved, dict):
        _tidy(ws)
        return saved
    marker = _ready_file(ws)
    if not marker.is_file() or not ws.is_dir():
        raise FactoryStop("implementation_not_pushed", "The build folder is gone and nothing was recorded. "
                          "Nothing was published.")
    ready = json.loads(marker.read_text())
    base = str(ready.get("commit") or "")
    if not SHA.fullmatch(base):
        raise FactoryStop("export_failed", "The build folder's record is not valid. Nothing was published.")
    head = hostbox.git(ws, "rev-parse", "HEAD")
    status = hostbox.git(ws, "status", "--porcelain", "--untracked-files=normal")
    count = hostbox.git(ws, "rev-list", "--count", f"{base}..HEAD")
    commits = count["stdout"].decode(errors="replace").strip() if count["exit_code"] == 0 else ""
    record = {"mode": "local", "commit": base, "ref": ready.get("ref"),
              "head": head["stdout"].decode(errors="replace").strip() if head["exit_code"] == 0 else None,
              "commits": int(commits) if commits.isdigit() else 0,
              "dirty": status["exit_code"] != 0 or bool(status["stdout"].strip()), "exports": []}
    if export:
        patch = hostbox.git(ws, "format-patch", "--stdout", f"{base}..HEAD", timeout=120)
        if patch["exit_code"] != 0 or patch.get("overflow"):
            raise FactoryStop("export_failed", "git format-patch failed: " + (
                "the patch is over 64 MiB" if patch.get("overflow") else _scrub(patch["stderr"])[-400:]))
        data = patch["stdout"]
        from hubzoid import datadir

        out_dir = Path(datadir.resolve(Path(hub_dir), Path("output") / "work-items" / item_id / call_id))
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"repo-{base[:12]}.patch"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        record["exports"] = [{"checkout": "repo", "base": base, "commits": record["commits"], "bytes": len(data),
                              "dirty": record["dirty"], "file": str(target),
                              "sha256": "sha256:" + hashlib.sha256(data).hexdigest()}]
    hub.shared_state[key] = record
    _tidy(ws)
    return record


def record(call_id: str | None) -> dict | None:
    """What a local station call left, or None (a Docker call)."""
    if not call_id:
        return None
    from hubzoid import hub

    value = hub.shared_state.get(RECORD.format(call=call_id))
    return value if isinstance(value, dict) else None
