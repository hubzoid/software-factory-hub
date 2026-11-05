"""Local builds: what the macOS sandbox lets a command do, what the repo_*
tools refuse, the setup step's registry proxy, and how FACTORY_BUILDS picks
Docker or local builds."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from . import conftest as h
from software_factory import builds, hostbox
from software_factory.errors import FactoryStop

mac = pytest.mark.skipif(sys.platform != "darwin", reason="local builds run on macOS")


@pytest.fixture
def source(tmp_path):
    """A small committed repository to clone from."""
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "app.py").write_text("print('hi')\n")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, env=h.GIT_ENV, check=True)
    return repo


@pytest.fixture
def ws(tmp_path, source):
    """A work folder made the way the factory makes one."""
    folder = builds.folder(tmp_path / "hub", "w0", "g1-analyze-r1")
    builds.prepare(tmp_path / "hub", folder, {"url": str(source), "ref": "main"}, None)
    return folder


@mac
def test_commands_run_in_the_clone_and_can_commit(ws):
    done = hostbox.run(ws, "git commit -q --allow-empty -m x && git log --oneline | wc -l && python3 -c 'print(4)'")
    assert done["exit_code"] == 0 and done["output"].split() == ["2", "4"], done


@mac
def test_the_sandbox_keeps_commands_off_the_rest_of_the_computer(ws, tmp_path):
    secret = Path.home() / ".hubzoid-sandbox-test-secret"
    outside = tmp_path / "outside.txt"           # under /private/var/folders: denied
    secret.write_text("do-not-read")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    ttys = sorted(p for p in Path("/dev").glob("ttys[0-9]*"))
    try:
        cases = {
            "home file": f"cat {secret}",
            "home folder": f"ls {Path.home()}",
            "write outside": f"echo x > {outside}",
            "network": "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)\"",
            "localhost": f"python3 -c \"import socket; socket.create_connection(('127.0.0.1', "
                         f"{listener.getsockname()[1]}), timeout=3)\"",
            "keychain": "security find-generic-password -s 'Claude Code-credentials' -w",
            "move the clone": "cd .. && mv repo r0",
            "replace the folder": "cd ../.. && rm -rf g1-analyze-r1",
            **({"a person's terminal": f"python3 -c \"open('{ttys[0]}', 'rb')\""} if ttys else {}),
        }
        for name, command in cases.items():
            done = hostbox.run(ws, command, timeout=20)
            assert done["exit_code"] != 0, (name, done)
            assert "do-not-read" not in done["output"], name
        assert not outside.exists()
        # The agent may empty its own clone, never move, remove or replace the folders themselves.
        assert (ws / "repo").is_dir() and not (ws / "repo").is_symlink() and not (ws.parent / "r0").exists()
    finally:
        secret.unlink()
        listener.close()


@mac
def test_commands_get_a_clean_environment(ws, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")  # gitleaks:allow
    monkeypatch.setenv("HUBZOID_SECRET_KEY", "hubzoid-test-secret")
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "y" * 36)  # gitleaks:allow
    done = hostbox.run(ws, "env")
    assert done["exit_code"] == 0
    names = {line.split("=", 1)[0] for line in done["output"].splitlines() if "=" in line}
    assert not names & {"ANTHROPIC_API_KEY", "HUBZOID_SECRET_KEY", "GH_TOKEN"}
    assert f"HOME={ws.resolve() / 'home'}" in done["output"]
    path = next(line for line in done["output"].splitlines() if line.startswith("PATH="))
    assert str(ws.resolve() / "repo") not in path                    # nothing from the clone is on PATH


@mac
def test_a_command_that_runs_too_long_is_stopped(ws):
    done = hostbox.run(ws, "sleep 30 & sleep 30", timeout=2)
    assert done["timed_out"] and "stopped after 2 seconds" in done["output"]


@mac
def test_a_process_that_leaves_the_group_does_not_hold_the_factory(ws):
    """It escapes the group kill, but the factory stops waiting for its output."""
    import time

    start = time.monotonic()
    done = hostbox.run(ws, "python3 -c \"import os, time\nif os.fork() == 0:\n    os.setsid(); time.sleep(20)\"; "
                           "echo parent-done", timeout=60)
    assert done["exit_code"] == 0 and "parent-done" in done["output"]
    assert time.monotonic() - start < 15


def test_without_macos_nothing_runs(ws, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    done = hostbox.run(ws, "echo ran")
    assert done["exit_code"] != 0 and "ran" not in done["output"] and "macOS" in done["output"]


@mac
def test_work_folders_have_no_project_files_above_them(factory_hub, source):
    """Tools look for settings in parent folders: under the hub, pytest found
    the hub's own pytest.ini, which the sandbox may not read."""
    (factory_hub / "pytest.ini").write_text("[pytest]\n")
    root = builds.root(factory_hub)
    assert factory_hub.resolve() not in root.parents and Path.home().resolve() not in root.parents
    target = builds.folder(factory_hub, "w2", "g1-review-r1")
    builds.prepare(factory_hub, target, {"url": str(source)}, None)
    # What pytest does to find its rootdir: read the first settings file above the clone.
    done = hostbox.run(target, "python3 -c \"from pathlib import Path; [(p / n).read_text() for p in Path.cwd()"
                               ".parents for n in ('pytest.ini', 'pyproject.toml', 'setup.cfg', 'tox.ini') "
                               "if (p / n).is_file()]; print('clean')\"")
    assert done["exit_code"] == 0 and "clean" in done["output"], done


# -- the setup step's network -------------------------------------------------------------------

def _connect(port: int, target: str) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        return s.recv(200)


def test_the_setup_proxy_tunnels_to_listed_public_hosts_only():
    with hostbox.RegistryProxy(["pypi.org", "localhost"]) as proxy:
        assert b" 403 " in _connect(proxy.port, "example.com:443")           # not listed
        assert b" 403 " in _connect(proxy.port, "pypi.org:22")               # not 443
        assert b" 403 " in _connect(proxy.port, "localhost:443")             # listed, but a private address
    with pytest.raises(OSError):
        _connect(proxy.port, "pypi.org:443")                                 # closed with the setup step


@mac
def test_setup_reaches_the_proxy_and_nothing_else(ws):
    other = socket.socket()
    other.bind(("127.0.0.1", 0))
    other.listen(1)
    try:
        with hostbox.RegistryProxy([]) as proxy:
            reach = ("python3 -c \"import socket, sys; s = socket.create_connection(('127.0.0.1', int(sys.argv[1])), "
                     "timeout=3); print('connected')\" ")
            assert "connected" in hostbox.run(ws, reach + str(proxy.port), proxy_port=proxy.port)["output"]
            assert hostbox.run(ws, reach + str(other.getsockname()[1]), proxy_port=proxy.port)["exit_code"] != 0
            assert "HTTPS_PROXY=http://127.0.0.1:" in hostbox.run(ws, "env", proxy_port=proxy.port)["output"]
            keychain = "security find-generic-password -s 'Claude Code-credentials' -w"
            assert hostbox.run(ws, keychain, proxy_port=proxy.port)["exit_code"] != 0        # still no keychain
    finally:
        other.close()


# -- the repo_* tools ---------------------------------------------------------------------------

def _tools(hub_dir: Path):
    spec = importlib.util.spec_from_file_location("factory_repo_tools", h.HUB_ROOT / "tools_local" / "factory_repo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _invoke(tool, **args) -> dict:
    from agents.tool_context import ToolContext

    raw = json.dumps(args)
    ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="t1", tool_arguments=raw)
    return json.loads(asyncio.run(tool.on_invoke_tool(ctx, raw)))


def test_the_tools_refuse_outside_a_factory_build(factory_hub):
    tools = _tools(factory_hub)
    for name, args in (("repo_run", {"command": "id"}), ("repo_read", {"path": "app.py"}),
                       ("repo_write", {"path": "x", "content": "y"})):
        assert _invoke(getattr(tools, name), **args)["error"] == "not_in_a_build", name


@pytest.fixture
def building(factory_hub, source):
    """A factory station running for work item w1, with its own work folder."""
    from hubzoid import db
    from hubzoid.workflows import context
    from hubzoid.workflows.identity import RunIdentity

    target = builds.folder(factory_hub, "w1", "g1-implement-r1")
    builds.prepare(factory_hub, target, {"url": str(source)}, None)
    builds.activate(factory_hub, "w1", target, "implementer")
    ident = RunIdentity("admin@localhost", None, "test", "admin@localhost").to_dict()
    with context.run_scope(hub="factory", workflow="factory", hub_dir=factory_hub,
                           engine=db.operational_engine(factory_hub), identity=ident, run_id="run-w1",
                           work={"item": {"id": "w1"}, "station_call": "call-1"}):
        yield _tools(factory_hub), target / "repo"


def test_paths_stay_inside_the_clone(building, tmp_path):
    tools, repo = building
    outside = tmp_path / "secret.txt"
    outside.write_text("do-not-read")
    os.symlink(outside, repo / "link.txt")
    os.link(repo / "app.py", repo / "twin.py")
    os.mkfifo(repo / "pipe")
    refused = [("repo_read", {"path": "/etc/hosts"}), ("repo_read", {"path": "../repo/app.py"}),
               ("repo_read", {"path": "link.txt"}), ("repo_read", {"path": "twin.py"}),
               ("repo_write", {"path": "link.txt", "content": "x"}),
               ("repo_write", {"path": ".git/config", "content": "x"}),
               ("repo_read", {"path": "pipe"}), ("repo_write", {"path": "pipe", "content": "x"})]
    for name, args in refused:
        out = _invoke(getattr(tools, name), **args)
        assert "error" in out and "do-not-read" not in json.dumps(out), (name, args, out)
    assert outside.read_text() == "do-not-read"


def test_a_clone_swapped_for_a_link_is_refused(building, tmp_path):
    """The sandbox refuses the swap; if the clone is replaced anyway, the
    tools, which run outside the sandbox, never follow it."""
    tools, repo = building
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secret.txt").write_text("do-not-read")
    os.rename(repo, repo.parent / "r0")
    os.symlink(outside, repo)
    for name, args in (("repo_read", {"path": "secret.txt"}), ("repo_list", {}),
                       ("repo_write", {"path": "planted.txt", "content": "x"})):
        out = _invoke(getattr(tools, name), **args)
        assert out.get("error") == "no_build_folder", (name, out)
    assert sorted(p.name for p in outside.iterdir()) == ["secret.txt"]
    os.unlink(repo)                               # a new folder at the same place is not the clone either
    os.mkdir(repo)
    assert _invoke(tools.repo_list).get("error") == "no_build_folder"


def test_the_tools_read_search_and_change_the_clone(building):
    tools, repo = building
    assert _invoke(tools.repo_write, path="pkg/mod.py", content="VALUE = 1\n")["bytes"] == 10
    assert _invoke(tools.repo_edit, path="pkg/mod.py", old="1", new="2")["replaced"] == 1
    assert "VALUE = 2" in _invoke(tools.repo_read, path="pkg/mod.py")["text"]
    assert _invoke(tools.repo_find, pattern="**/*.py")["files"] == ["app.py", "pkg/mod.py"]
    assert {e["name"] for e in _invoke(tools.repo_list)["entries"]} >= {"app.py", "pkg"}
    if sys.platform == "darwin":
        hits = _invoke(tools.repo_search, pattern="VALUE = [0-9]", files="*.py")["matches"]
        assert hits == [{"path": "pkg/mod.py", "line": 1, "text": "VALUE = 2"}]
        assert "pkg/mod.py" in _invoke(tools.repo_run, command="git status --porcelain -uall")["output"]


@mac
def test_a_search_runs_in_its_own_confined_process(building, monkeypatch):
    """A pattern that backtracks can't stall the hub: grep runs in the sandbox, stopped after 30 seconds."""
    tools, repo = building
    seen = []
    real = hostbox.run
    monkeypatch.setattr(hostbox, "run", lambda ws, argv, **kw: seen.append((argv, kw)) or real(ws, argv, **kw))
    (repo / "long.txt").write_text("a" * 5000 + "!\n")
    out = _invoke(tools.repo_search, pattern="(a|aa)+$")
    assert "matches" in out or out.get("error") == "too_slow"
    assert seen and seen[0][0][0] == "/usr/bin/grep" and seen[0][1]["timeout"] == 30


# -- choosing where builds run ------------------------------------------------------------------

@pytest.mark.parametrize("setting,docker_up,can_run_here,mode", [
    ("docker", False, True, "docker"),
    ("auto", True, True, "docker"),
    ("auto", False, True, "local"),
    ("local", True, True, "local"),
])
def test_where_builds_run(monkeypatch, tmp_path, setting, docker_up, can_run_here, mode):
    monkeypatch.setattr(builds, "docker_running", lambda hub_dir: docker_up)
    monkeypatch.setattr(hostbox, "unsupported", lambda: None if can_run_here else "Needs macOS.")
    assert builds.choose(tmp_path, setting)["mode"] == mode


@pytest.mark.parametrize("setting", ["auto", "local", "sometimes"])
def test_no_docker_and_no_mac_is_a_clear_stop(monkeypatch, tmp_path, setting):
    monkeypatch.setattr(builds, "docker_running", lambda hub_dir: False)
    monkeypatch.setattr(hostbox, "unsupported", lambda: "Builds without Docker run on macOS only for now.")
    with pytest.raises(FactoryStop) as stop:
        builds.choose(tmp_path, setting)
    assert stop.value.code in ("builds_unavailable", "settings_invalid")


def test_setup_registries_follow_the_docker_profile(factory_hub):
    hosts = builds.registry_hosts(factory_hub, "factory")
    assert "pypi.org" in hosts and "registry.npmjs.org" in hosts and "github.com" not in hosts
