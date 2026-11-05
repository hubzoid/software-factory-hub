"""Builds on this computer, without Docker (FACTORY_BUILDS: local, or auto
with Docker stopped). The analyst, implementer and reviewer run as their
local- versions in a work folder, through the repo_* tools, with every
command confined by macOS's sandbox. These tests drive the real tools and the
real sandbox; only the models are scripted."""
from __future__ import annotations

import asyncio
import contextvars
import json
import sys
import threading

import pytest

from .. import conftest as h

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="builds without Docker run on macOS")


def outcome(out):
    return out["factory_v1"]["outcome"], out["factory_v1"].get("stop_reason")


def call_tool(registry, name, **args) -> dict:
    """Call a station's tool the way a runtime does, from a thread of its own."""
    from agents.tool_context import ToolContext

    box, raw = {}, json.dumps(args)
    ctx = ToolContext(context=None, tool_name=name, tool_call_id="t1", tool_arguments=raw)

    def go():
        box["out"] = asyncio.run(registry[name].on_invoke_tool(ctx, raw))

    here = contextvars.copy_context()           # a runtime runs tools inside the station's own run
    t = threading.Thread(target=lambda: here.run(go))
    t.start()
    t.join()
    return json.loads(box["out"])


@pytest.fixture
def local(factory, monkeypatch):
    """The factory with builds on this computer and scripted models that use the repo_* tools."""
    from hubzoid.access import store_for
    from hubzoid.access.store import USE_HUB

    # The run's account (the harness runs as admin@localhost) may use the agent, as a real owner can.
    store_for(factory.hub_dir).grant("admin@localhost", factory.hub_dir.name, USE_HUB, actor="test")
    settings = factory.hub_dir / "hub.settings.yaml"
    settings.write_text(settings.read_text().replace("FACTORY_BUILDS: docker", "FACTORY_BUILDS: local\n"
                                                     "  FACTORY_LOCAL_SETUP: mkdir -p \"$FACTORY_ENV/bin\""))
    fake = factory.stations
    docker_run = fake.run
    seen = {"tools": {}, "heads": []}

    def run(hub_dir, definition, message, *, subject=None, timeout=None, registry=None):
        name = definition["name"]
        if not name.startswith("local-"):
            return docker_run(hub_dir, definition, message, subject=subject, timeout=timeout, registry=registry)
        fake.calls.append({"name": name, "message": message, "checkout": definition.get("checkout"),
                           "tools": sorted(registry or {})})
        seen["tools"][name] = sorted(registry or {})
        if name == "local-analyst":
            assert "planted bug" in call_tool(registry, "repo_read", path="calc.py")["text"]
            out = dict(fake.analysis)
        elif name == "local-implementer":
            assert call_tool(registry, "repo_write", path="calc.py",
                             content="def total(xs):\n    return sum(xs)\n")["bytes"] > 0
            done = call_tool(registry, "repo_run", command="git add -A && git commit -q -m 'Fix total' && "
                                                           "git rev-parse HEAD")
            assert done["exit_code"] == 0, done
            head = done["output"].strip().splitlines()[-1]
            out = {"branch": "factory/fix", "base": "main", "committed": True, "head_commit": head,
                   "change_summary": [{"path": "calc.py", "change": "fixed"}],
                   "verification": [{"command": "python3 -m pytest", "result": "pass"}], "deviations": [],
                   "known_limitations": []}
        else:
            ran = call_tool(registry, "repo_run", command="python3 -c 'from calc import total; "
                                                         "assert total([1, 2]) == 3' && git rev-parse HEAD")
            assert ran["exit_code"] == 0, ran
            head = ran["output"].strip().splitlines()[-1]
            seen["heads"].append(head)
            task = message.split("verbatim:", 1)[-1]
            crit = [line[2:].strip() for line in task.splitlines() if line.startswith("- ")]
            out = {"verdict": "approve", "reviewed_sha": head,
                   "criteria_results": [{"criterion": c, "pass": True, "evidence": "ran it"} for c in crit],
                   "blocking_findings": [], "suggestions": [], "summary": "Approve."}
        return {"text": json.dumps(out), "output": out, "model": "fake", "usage": {}}

    from hubzoid import runtime

    monkeypatch.setattr(runtime, "run_station", run)
    factory.seen = seen
    return factory


def test_a_label_becomes_a_reviewed_draft_without_docker(local):
    out = local.run(local.label())
    rec = out["factory_v1"]
    assert outcome(out) == ("review_ready", None)
    assert rec["builds"] == "local"
    assert [c["name"] for c in local.stations.calls] == ["classifier", "local-analyst", "local-implementer",
                                                         "local-reviewer"]
    assert not local.stations.boxes                                         # Docker's sandbox was never asked
    assert all(c["checkout"] is None for c in local.stations.calls)
    assert all("/workspace/repo" not in c["message"] for c in local.stations.calls)
    assert local.seen["tools"]["local-implementer"] == sorted(
        ["repo_list", "repo_read", "repo_find", "repo_search", "repo_write", "repo_edit", "repo_run", "read_handoff"])
    assert "repo_write" not in local.seen["tools"]["local-reviewer"]
    # The reviewer reviewed exactly the published commit, which holds the fix.
    assert rec["pushed_sha"] == rec["reviewed_sha"] == local.remote.head(rec["branch"]) == local.seen["heads"][0]
    assert h.git(local.remote.bare, "show", f"{rec['branch']}:calc.py") == "def total(xs):\n    return sum(xs)\n"
    assert local.api.pulls[rec["pr_number"]]["draft"] is True
    # Work folders are gone once each station is done.
    from software_factory import builds

    builds_root = builds.root(local.hub_dir) / rec["work_item"]
    assert not builds_root.exists() or not [p for p in builds_root.iterdir() if p.is_dir()]


def test_a_replay_runs_no_station_and_no_build_again(local):
    item = local.label()
    first = local.run(item)
    calls = len(local.stations.calls)
    second = local.run(item)
    assert second["factory_v1"]["pr_number"] == first["factory_v1"]["pr_number"]
    assert len(local.stations.calls) == calls


def test_a_failing_setup_stops_with_its_output(local):
    settings = local.hub_dir / "hub.settings.yaml"
    settings.write_text(settings.read_text().replace('mkdir -p "$FACTORY_ENV/bin"', "echo no-such-lockfile; exit 3"))
    out = local.run(local.label())
    assert outcome(out) == ("stopped", "setup_failed")
    assert "no-such-lockfile" in out["factory_v1"]["reply"] and "FACTORY_LOCAL_SETUP" in out["factory_v1"]["reply"]
    assert [c["name"] for c in local.stations.calls] == ["classifier"]       # no agent ran in a half-built folder
    from software_factory import builds

    leftover = builds.root(local.hub_dir) / out["factory_v1"]["work_item"]
    assert not leftover.exists() or not [p for p in leftover.iterdir() if p.is_dir()]


def test_auto_without_docker_builds_on_this_computer(local, monkeypatch):
    from software_factory import builds

    settings = local.hub_dir / "hub.settings.yaml"
    settings.write_text(settings.read_text().replace("FACTORY_BUILDS: local", "FACTORY_BUILDS: auto"))
    monkeypatch.setattr(builds, "docker_running", lambda hub_dir: False)
    out = local.run(local.label())
    assert outcome(out) == ("review_ready", None) and out["factory_v1"]["builds"] == "local"


def test_work_from_before_local_builds_stays_on_docker_with_the_same_steps(factory, monkeypatch):
    """Its saved settings have no FACTORY_BUILDS: it stays on Docker and saves
    no new step, so a replay takes exactly the steps it took before."""
    from software_factory import builds, pipeline

    real = pipeline._settings_now

    def before():
        out = real()
        for key in ("FACTORY_BUILDS", "FACTORY_LOCAL_SETUP", "FACTORY_SANDBOX_PROFILE"):
            out.pop(key, None)
        return out

    monkeypatch.setattr(pipeline, "_settings_now", before)
    monkeypatch.setattr(builds, "choose", lambda *a: pytest.fail("no new decision for older work"))
    item = factory.label()
    out = factory.run(item)
    assert outcome(out) == ("review_ready", None) and out["factory_v1"]["builds"] == "docker"
    assert [c["name"] for c in factory.stations.calls] == ["classifier", "analyst", "implementer", "reviewer"]
    steps = [name for name, _ in factory.steps[item["id"]]]
    assert factory.run(item)["factory_v1"]["pr_number"] == out["factory_v1"]["pr_number"]
    assert [name for name, _ in factory.steps[item["id"]]] == steps
