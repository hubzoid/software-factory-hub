"""The factory on the real workflow engine, in its own process, with the same
doubles as the in-process harness: GitHub's REST API (writes logged to a
file), the station models (sandboxes kept in a file, so a restart finds them)
and the routing model. Used by tests/integration/test_engine_recovery.py.

    python tests/engine_child.py HUB_DIR STOP_FILE STATE_DIR
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
hub_dir, stop, state_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(hub_dir / "workflows" / "factory"))

import httpx  # noqa: E402

from tests import conftest as h  # noqa: E402


class LoggedGitHub(h.FakeGitHub):
    def __call__(self, request):
        out = super().__call__(request)
        if request.method in ("POST", "PATCH", "DELETE") and not request.url.path.endswith("/access_tokens"):
            with (state_dir / "github-writes.jsonl").open("a") as f:
                f.write(json.dumps([request.method, request.url.path]) + "\n")
        return out


class PersistedStations(h.FakeStations):
    """Station results as in the harness; sandboxes persisted to a file, and
    the first review stalls so the test can kill the engine mid-review."""

    def run(self, hub_dir_, definition, message, **kw):
        with (state_dir / "stations.log").open("a") as f:
            f.write(definition["name"] + "\n")
        self._load()
        if definition["name"] == "reviewer" and (state_dir / "stall-review").exists() \
                and not (state_dir / "review-stalled").exists():
            (state_dir / "review-stalled").write_text("1")
            time.sleep(300)                      # killed here
        out = super().run(hub_dir_, definition, message, **kw)
        self._save()
        return out

    def _save(self):
        (state_dir / "boxes.json").write_text(json.dumps(
            {k: {**v, "patch": v["patch"].decode() if isinstance(v.get("patch"), bytes) else v.get("patch")}
             for k, v in self.boxes.items()}))

    def _load(self):
        p = state_dir / "boxes.json"
        if p.exists():
            self.boxes = {k: {**v, "patch": v["patch"].encode() if isinstance(v.get("patch"), str) else None}
                          for k, v in json.loads(p.read_text()).items()}


def install():
    from hubzoid import runtime as hub_runtime
    from hubzoid.channels.github import client as gh
    from hubzoid.sandbox import config as sandbox_config
    from hubzoid.sandbox import service as sandbox_service
    from hubzoid.workflows import context

    remote = h.Remote.attach(Path(sys.argv[4]))
    fake_github = LoggedGitHub(remote)
    seeded = state_dir / "pulls.json"
    if seeded.exists():
        fake_github.pulls.update({int(k): v for k, v in json.loads(seeded.read_text()).items()})
    gh.transport = httpx.MockTransport(fake_github)
    stations = PersistedStations(remote)
    stations._load()
    hub_runtime.run_station = stations.run
    sandbox_config.check_profile = lambda hub_dir_, profile: None

    def allocate(hub_dir_, *, owner_kind, owner_id, profile_id, item_id=None, actor="", checkout=None,
                 profile_json=None):
        from hubzoid.stations import service as st

        stations._load()
        call = st.get_call(hub_dir_, owner_id)
        sid = f"box-{owner_id[:8]}-{len(stations.boxes) + 1}"
        ref = (checkout or {}).get("ref") or "main"
        stations.boxes[sid] = {"id": sid, "owner_id": owner_id, "agent": call["agent"], "ref": ref,
                               "commit": (checkout or {}).get("commit") or remote.head(ref), "state": "ready",
                               "live_key": sid}
        stations._save()
        return {"id": sid}

    def rows(hub_dir_, *, owner_kind=None, owner_id=None, state=None, limit=50):
        stations._load()
        return [{"id": sid, "state": b["state"], "live_key": b.get("live_key"),
                 "checkouts_json": [{"path": "/workspace/repo", "commit": b["commit"], "ref": b["ref"]}],
                 "exports_json": b.get("exports") or []}
                for sid, b in stations.boxes.items() if owner_id is None or b["owner_id"] == owner_id]

    def export(hub_dir_, sid, out_dir):
        import hashlib

        stations._load()
        box = stations.boxes[sid]
        if not box.get("patch"):
            box["exports"] = [{"checkout": "/workspace/repo", "base": box["commit"], "commits": 0, "dirty": False,
                               "bytes": 0, "sha256": "sha256:", "file": ""}]
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"repo-{box['start'][:12]}.patch"
            target.write_bytes(box["patch"])
            box["exports"] = [{"checkout": "/workspace/repo", "base": box["start"], "commits": 1, "dirty": False,
                               "bytes": len(box["patch"]),
                               "sha256": "sha256:" + hashlib.sha256(box["patch"]).hexdigest(), "file": str(target)}]
        stations._save()
        return box["exports"]

    sandbox_service.allocate = allocate
    sandbox_service.list_rows = rows
    sandbox_service.export_patches = export
    sandbox_service.get = lambda hub_dir_, sid: {"checkouts_json": [{"commit": "x"}]}
    sandbox_service.release = lambda *a, **k: None
    sandbox_service.stop = lambda *a, **k: None
    sandbox_service.attach = lambda hub_dir_, sid: {"id": sid}
    model = h.FakeModel()
    scripted = state_dir / "model.json"

    def llm(spec, hub_dir=None, subject=None):
        if scripted.exists():
            model.route = json.loads(scripted.read_text())
        return model.llm(spec, hub_dir=hub_dir, subject=subject)

    context.configure(llm=llm, agent=model.agent)
    from hubzoid.work_items import operations as ops

    # The test's requester has no account in this throwaway hub.
    ops._approver_still_allowed = lambda hub_dir_, hub, subject: subject == h.OWNER


install()
from hubzoid.workflows import runtime  # noqa: E402

runtime.init(str(hub_dir), hub_name="factory")
runtime.load_workflows(str(hub_dir))
runtime.launch()
runtime._OWNER.heartbeat(runtime.ready_record())
print("READY", flush=True)
beat = time.time()
while not stop.exists():
    time.sleep(0.2)
    if time.time() - beat > 5:
        runtime._OWNER.heartbeat(runtime.ready_record())
        beat = time.time()
runtime.shutdown()
