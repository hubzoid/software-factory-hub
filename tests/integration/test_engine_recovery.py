"""The durability contract on the real workflow engine: the engine is killed
in the middle of the review, starts again, and the work finishes from its saved
steps with one push and one draft pull request. Runs the factory workflow in a
child process (DBOS is a process-wide singleton), as the SDK's own engine
tests do."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .. import conftest as h

pytestmark = [pytest.mark.slow, pytest.mark.skipif(os.name == "nt", reason="uses SIGKILL")]
CHILD = Path(__file__).resolve().parents[1] / "engine_child.py"


class Engine:
    def __init__(self, hub_dir, state_dir, remote_root):
        self.stop = state_dir / f"stop-{time.time_ns()}"
        self.proc = subprocess.Popen([sys.executable, str(CHILD), str(hub_dir), str(self.stop), str(state_dir),
                                      str(remote_root)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, env=dict(os.environ))
        deadline = time.time() + 90
        lines = []
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            lines.append(line)
            if line.startswith("READY"):
                return
            if not line and self.proc.poll() is not None:
                break
        raise RuntimeError("the engine did not start:\n" + "".join(lines[-40:]))

    def kill(self):
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(10)

    def close(self):
        self.stop.write_text("1")
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.kill()


def wait(predicate, timeout=120, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.3)
    raise AssertionError(f"timed out waiting for {what}")


def test_a_killed_engine_finishes_the_work_once(factory_hub, conn, api, remote, tmp_path, monkeypatch):
    from hubzoid.channels import admission, router, store
    from hubzoid.work_items import store as wstore

    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [os.environ.get("PYTHONPATH")])))
    state = tmp_path / "engine-state"
    state.mkdir()
    (state / "stall-review").write_text("1")
    engine = Engine(factory_hub, state, remote.root)
    try:
        import hashlib
        import hmac

        issue = api.issues[12]
        body = {"action": "labeled", "label": {"name": "factory", "id": 77},
                "issue": {"number": 12, "title": issue["title"], "body": issue["body"],
                          "updated_at": "2026-10-20T00:00:00Z", "html_url": issue["html_url"]},
                "repository": {"id": h.REPO_ID, "full_name": h.FULL}, "installation": {"id": 7001},
                "sender": {"id": 501, "login": "ana", "type": "User"}}
        raw = json.dumps(body).encode()
        sig = "sha256=" + hmac.new(h.HOOK.encode(), raw, hashlib.sha256).hexdigest()
        admission.receive(factory_hub, "github", raw, {"x-hub-signature-256": sig, "x-github-event": "issues",
                                                       "x-github-delivery": "abcdef0123456789-0000-0000"}, {})
        for row in store.open_deliveries(factory_hub, "factory"):
            router._route_one(factory_hub, row, None)
        item_id = store.list_deliveries(factory_hub, "factory", "github")["items"][0]["route_json"]["work_item_id"]
        wait(lambda: (state / "review-stalled").exists(), what="the review to start")
        engine.kill()                                            # mid-review: power cut
        assert wstore.get_item(factory_hub, item_id)["state"] not in wstore.TERMINAL
        engine = Engine(factory_hub, state, remote.root)
        item = wait(lambda: (lambda i: i if i["state"] in wstore.TERMINAL else None)(
            wstore.get_item(factory_hub, item_id)), what="the work to finish")
        assert item["state"] == "completed", item
        result = item["result_json"]["result"]["factory_v1"]
        assert result["outcome"] == "delivered" and result["pr_number"]
        ops = wstore.list_ops(factory_hub, "factory", item_id=item_id)
        assert [o["state"] for o in ops if o["name"] == "github.pushBranch"] == ["succeeded"]
        assert [o["state"] for o in ops if o["name"] == "github.createPullRequest"] == ["succeeded"]
        runs = (state / "stations.log").read_text().split()
        assert runs.count("classifier") == 1 and runs.count("analyst") == 1 and runs.count("implementer") == 1
        assert runs.count("reviewer") == 2                    # the interrupted review, resumed once
        writes = [json.loads(line) for line in (state / "github-writes.jsonl").read_text().splitlines()]
        assert sum(1 for m, p in writes if m == "POST" and p.endswith("/pulls")) == 1
        assert remote.head(result["branch"]) == result["pushed_sha"]
    finally:
        engine.close()


def test_approval_continues_the_parked_work_on_the_engine(factory_hub, conn, api, remote, tmp_path, monkeypatch):
    """The ship gate: the work parks for the requester, the approval forks a
    new execution from the saved step, and the earlier steps replay exactly
    (the scope narrowing among them) before the change is sent once."""
    from hubzoid.work_items import operations as ops
    from hubzoid.work_items import service
    from hubzoid.work_items import store as wstore

    monkeypatch.setattr(ops, "_approver_still_allowed", lambda hub_dir, hub, subject: subject == h.OWNER)
    state = tmp_path / "engine-state"
    state.mkdir()
    (state / "pulls.json").write_text(json.dumps({"101": {"title": "Fix", "body": "", "head": "factory/12-fix",
                                                          "base": "main", "draft": True}}))
    (state / "model.json").write_text(json.dumps({"route": "act", "issue_number": 101, "clarify": None,
                                                 "reason": "", "act": {"operation": "mark_ready", "number": 101}}))
    engine = Engine(factory_hub, state, remote.root)
    try:
        item, _ = service.admit_and_start(factory_hub, workflow="factory", key="chat:ship-engine", route="request",
                                          input={"source": "chat", "request": "Mark #101 ready for review"},
                                          requester=h.OWNER, origin={"source": "chat", "surface": "web"})
        parked = wait(lambda: (lambda i: i if i["state"] == "waiting" else None)(
            wstore.get_item(factory_hub, item["id"])), what="the work to park")
        assert parked["reason"] == "approval_required"
        op = next(o for o in wstore.list_ops(factory_hub, "factory", item_id=item["id"])
                  if o["name"] == "github.updatePullRequest")
        assert op["state"] == "awaiting_approval"
        writes = (state / "github-writes.jsonl")
        assert not writes.exists() or "/graphql" not in writes.read_text()
        service.approve(factory_hub, op["id"], h.OWNER, digest=op["args_digest"])
        done = wait(lambda: (lambda i: i if i["state"] in wstore.TERMINAL else None)(
            wstore.get_item(factory_hub, item["id"])), what="the approved work to finish")
        assert done["state"] == "completed", done
        assert done["result_json"]["result"]["factory_v1"]["outcome"] == "acted"
        graphql = [line for line in writes.read_text().splitlines() if "/graphql" in line]
        assert len(graphql) == 1
    finally:
        engine.close()
