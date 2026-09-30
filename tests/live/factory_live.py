"""Stand-ins for a live run of the Software Factory on a machine without a
container runtime, for the proof only. Never part of the hub's runtime.

Enabled per process by putting this folder on PYTHONPATH (its
sitecustomize.py calls install()) and setting:

* FACTORY_LIVE_SANDBOX=standin: the three sandboxed stations (analyst,
  implementer, reviewer) return scripted results, and the "implementer"
  commits the fixture's known fix in a host clone made by test code. No model
  and no agent command runs on the host. The classifier and researcher, the
  chat agent, the routing model calls, approvals, the Console and every
  GitHub call stay real. Every scripted result says it is a stand-in.
* FACTORY_LIVE_GITHUB=fake (optional): a file-backed stand-in for GitHub's
  REST API and a local bare repository for Git, for runs before a real
  scratch repository and token exist. Leave it unset to use real GitHub.
* FACTORY_LIVE_STATE: a folder for the stand-ins' state.
* FACTORY_LIVE_REMOTE: with the fake GitHub, the folder holding the bare
  repository (also HUBZOID_GITHUB_WEB_URL=file://<folder>).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
HUB_ROOT = HERE.parents[1]
STANDIN = "Scripted stand-in (no container runtime on this machine): "
GIT_ENV = {"GIT_AUTHOR_NAME": "Factory implementer (stand-in)", "GIT_AUTHOR_EMAIL": "implementer@sandbox.invalid",
           "GIT_COMMITTER_NAME": "Factory implementer (stand-in)", "GIT_COMMITTER_EMAIL": "implementer@sandbox.invalid",
           "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"),
           "GIT_TERMINAL_PROMPT": "0"}


def _state() -> Path:
    p = Path(os.environ["FACTORY_LIVE_STATE"])
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def _locked(name: str):
    path = _state() / f"{name}.json"
    with open(_state() / f"{name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {}
        box = {"data": data}
        yield box
        path.write_text(json.dumps(box["data"], indent=1, default=str))


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout


# -- GitHub stand-in ----------------------------------------------------------------------

def _fake_github():
    import httpx

    import tests.conftest as h

    class FileGitHub(h.FakeGitHub):
        """The harness's GitHub double, with its state in a file shared by
        every process of the hub (CLI, bridge, engine)."""

        def __call__(self, request: httpx.Request) -> httpx.Response:
            with _locked("github") as box:
                d = box["data"]
                if d:
                    self.issues = {int(k): v for k, v in d["issues"].items()}
                    self.comments = {int(k): v for k, v in d["comments"].items()}
                    self.pulls = {int(k): v for k, v in d["pulls"].items()}
                    self.next = d["next"]
                else:
                    seed = json.loads((HUB_ROOT / "fixtures" / "sample-issues.json").read_text())
                    self.issues = {n: {"number": n, "title": i["title"], "body": i["body"], "state": "open",
                                       "labels": [{"name": x} for x in i["labels"]],
                                       "html_url": f"https://github.com/{h.FULL}/issues/{n}", "comments": 0}
                                   for n, i in enumerate(seed, start=1)}
                    self.labels = json.loads((HUB_ROOT / "fixtures" / "sample-labels.json").read_text())
                read = _repository_read(self.remote.bare, request) if request.method == "GET" else None
                if request.url.path == "/user":
                    resp = httpx.Response(200, json={"login": "factory-demo", "id": 4242})
                elif read is not None:
                    resp = httpx.Response(read[0], json=read[1])
                else:
                    resp = super().__call__(request)
                box["data"] = {"issues": self.issues, "comments": self.comments, "pulls": self.pulls,
                               "next": self.next}
                if request.method in ("POST", "PATCH", "DELETE") and not request.url.path.endswith(
                        "/access_tokens"):
                    with (_state() / "github-writes.jsonl").open("a") as f:
                        f.write(json.dumps({"method": request.method, "path": request.url.path,
                                            "body": json.loads(request.content or b"{}")}) + "\n")
                return resp

    remote = h.Remote.attach(Path(os.environ["FACTORY_LIVE_REMOTE"]))
    return httpx.MockTransport(FileGitHub(remote))



def _repository_read(bare: Path, request) -> tuple[int, object] | None:
    """Repository reads GitHub serves from git (contents, trees, branches,
    commits, code search), answered from the local bare repository the
    factory pushes to. None for anything else."""
    import base64
    from urllib.parse import unquote

    import tests.conftest as h
    from hubzoid.sandbox.service import _git_env

    raw = request.url.raw_path.decode().split("?")[0]
    prefix = f"/repos/{h.FULL}"
    params = dict(request.url.params)

    def run(*args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=bare, capture_output=True, env=_git_env(), timeout=60)

    def resolve(ref: str | None) -> str | None:
        res = run("rev-parse", "--verify", "--quiet", f"{ref or 'main'}^{{commit}}")
        return res.stdout.decode().strip() if res.returncode == 0 else None

    if raw.startswith(prefix + "/contents"):
        path = unquote(raw[len(prefix + "/contents"):]).strip("/")
        sha = resolve(params.get("ref"))
        if sha is None:
            return 404, {"message": "No commit found for the ref"}
        kind = run("cat-file", "-t", f"{sha}:{path}" if path else f"{sha}^{{tree}}").stdout.decode().strip()
        if kind == "tree":
            listing = run("ls-tree", sha, *([path + "/"] if path else [])).stdout.decode().splitlines()
            return 200, [{"path": line.split("\t", 1)[1], "name": line.split("\t", 1)[1].rsplit("/", 1)[-1],
                          "type": "dir" if " tree " in line else "file"} for line in listing]
        if kind != "blob":
            return 404, {"message": "Not Found"}
        blob = run("rev-parse", f"{sha}:{path}").stdout.decode().strip()
        body = run("cat-file", "blob", blob).stdout
        return 200, {"type": "file", "path": path, "name": path.rsplit("/", 1)[-1], "sha": blob, "size": len(body),
                     "encoding": "base64", "content": base64.b64encode(body).decode()}
    m = re.fullmatch(re.escape(prefix) + r"/git/trees/(.+)", raw)
    if m:
        sha = resolve(unquote(m.group(1)))
        if sha is None:
            return 404, {"message": "Not Found"}
        rows = run("ls-tree", "-r", "-t", "-l", sha).stdout.decode().splitlines()
        tree = []
        for line in rows:
            meta, path = line.split("\t", 1)
            _mode, kind, _obj, size = meta.split()
            tree.append({"path": path, "type": kind, "size": None if size == "-" else int(size)})
        return 200, {"sha": sha, "tree": tree, "truncated": False}
    if raw == prefix + "/branches":
        refs = run("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads").stdout.decode()
        return 200, [{"name": n, "commit": {"sha": c}, "protected": n == "main"}
                     for n, c in (line.split() for line in refs.splitlines())]
    if raw == prefix + "/commits":
        sha = resolve(params.get("sha"))
        log = run("log", "--format=%H%x09%an%x09%aI%x09%s", "-n", "30", sha or "main").stdout.decode()
        return 200, [{"sha": c, "commit": {"message": subj, "author": {"name": who, "date": when}}}
                     for c, who, when, subj in (line.split("\t", 3) for line in log.splitlines())]
    if raw == "/search/code":
        words = [w for w in (params.get("q") or "").split() if ":" not in w]
        if not words:
            return 200, {"total_count": 0, "incomplete_results": False, "items": []}
        args = ["grep", "-l", "-i", "-F"]
        for w in words:
            args += ["-e", w]
        found = run(*args, "main").stdout.decode().splitlines()
        items = [{"name": f.split(":", 1)[1].rsplit("/", 1)[-1], "path": f.split(":", 1)[1],
                  "repository": {"full_name": h.FULL}} for f in found]
        return 200, {"total_count": len(items), "incomplete_results": False, "items": items}
    return None

# -- sandbox and station stand-ins ------------------------------------------------------------

def _plan_for(message: str) -> dict:
    if re.search(r"\bcents?\b|\bround", message, re.I):
        return {
            "problem_statement": "total_with_tax rounds each line before adding them up, so some baskets are "
                                 "charged a cent too much. Three items at 0.10 with 5% tax charge 0.33 instead "
                                 "of 0.32.",
            "approach": "Discount and tax the subtotal, then round once at the end, as CONTRIBUTING.md asks. "
                        "Rejected: keeping per-line rounding and correcting the sum afterwards, which hides the "
                        "cause.",
            "plan": ["In invoice/totals.py, compute the discounted subtotal with subtotal() and apply_discount()",
                     "Apply the tax rate to that amount and round once with ROUND_HALF_UP",
                     "Run python -m pytest -q"],
            "affected_surface": ["invoice/totals.py: total_with_tax (public function)"],
            "risks": ["Baskets that relied on per-line rounding change by up to a cent; this is the intended fix"],
            "acceptance_criteria": ["total_with_tax rounds once, after tax, so three lines of 0.10 at 5% tax "
                                    "total 0.32",
                                    "tests/test_totals.py passes, including test_total_rounds_once_not_per_line",
                                    "No other public function changes behaviour"],
            "test_strategy": "Run python -m pytest -q. The existing regression test covers the bug.",
            "assumptions": [STANDIN + "this plan is the fixture's expected plan for the planted bug."],
            "open_questions": [], "handoff_id": None}
    return {
        "problem_statement": "The README has no section telling reporters what to include in a bug report.",
        "approach": "Add a short Reporting bugs section to README.md.",
        "plan": ["Add a Reporting bugs section to README.md asking for the version and steps to reproduce"],
        "affected_surface": ["README.md"], "risks": [],
        "acceptance_criteria": ["README.md has a Reporting bugs section asking for the version and steps to "
                                "reproduce"],
        "test_strategy": "Read the rendered README.", "assumptions": [STANDIN + "fixture plan."],
        "open_questions": [], "handoff_id": None}


def _fix_files(message: str) -> dict[str, str]:
    if re.search(r"\bcents?\b|\bround", message, re.I):
        return {"invoice/totals.py": (HUB_ROOT / "fixtures" / "sample-fix" / "invoice" / "totals.py").read_text()}
    return {"README.md": (HUB_ROOT / "fixtures" / "sample-repo" / "README.md").read_text()
            + "\n## Reporting bugs\n\nPlease include the version you use and the steps to reproduce.\n"}



def _ci_repair_files(base: str) -> dict[str, str]:
    """A CI repair on a factory branch: a scripted follow-up commit (the
    stand-in cannot run the failing check, so it adds the regression case the
    check reported)."""
    return {f"tests/test_totals_discount_{base[:7]}.py": (
        "from decimal import Decimal\n\nfrom invoice.totals import Line, total_with_tax\n\n\n"
        "def test_discounted_basket_rounds_once():\n"
        "    lines = [Line(\"a\", 3, Decimal(\"0.10\"))]\n"
        "    assert total_with_tax(lines, Decimal(\"0.05\"), Decimal(\"10\")) == Decimal(\"0.28\")\n")}

def _box(sid: str) -> dict:
    with _locked("boxes") as b:
        return dict(b["data"].get(sid) or {})


def _save_box(sid: str, **fields) -> None:
    with _locked("boxes") as b:
        b["data"][sid] = {**(b["data"].get(sid) or {}), **fields}


def install() -> None:
    from hubzoid import runtime as hub_runtime

    if os.environ.get("FACTORY_LIVE_GITHUB") == "fake":
        from hubzoid.channels.github import client as gh

        gh.transport = _fake_github()
    if os.environ.get("FACTORY_LIVE_SANDBOX") != "standin":
        return
    from hubzoid.sandbox import config as sandbox_config
    from hubzoid.sandbox import service as sandbox_service

    real_run_station = hub_runtime.run_station
    sandbox_config.check_profile = lambda hub_dir, profile: None

    def allocate(hub_dir, *, owner_kind, owner_id, profile_id, item_id=None, actor="", checkout=None,
                 profile_json=None):
        """A host clone made by test code, standing in for the sandbox's
        checkout. The SDK clones on the host the same way, then copies the
        tree into the container."""
        from hubzoid.sandbox.service import _git_env
        from hubzoid.stations import service as st

        call = st.get_call(hub_dir, owner_id)
        sid = f"standin-{owner_id[:8]}-{os.urandom(3).hex()}"
        dest = _state() / "boxes" / sid
        dest.parent.mkdir(parents=True, exist_ok=True)
        url, ref = (checkout or {}).get("url"), (checkout or {}).get("ref")
        args = ["git", "-c", "core.hooksPath=/dev/null"]
        if (url or "").startswith("https://github.com/"):
            # A private scratch repository: the machine's own GitHub CLI login, for this clone only.
            args += ["-c", "credential.https://github.com.helper=", "-c",
                     "credential.https://github.com.helper=!gh auth git-credential"]
        args += ["clone", "--quiet"] + (["--branch", ref] if ref else [])
        subprocess.run(args + ["--", url, str(dest)], check=True, capture_output=True, env=_git_env(), timeout=300)
        if (checkout or {}).get("commit"):
            _git(dest, "checkout", "--quiet", "--detach", checkout["commit"])
        commit = _git(dest, "rev-parse", "HEAD").strip()
        _save_box(sid, owner_id=owner_id, agent=call["agent"], path=str(dest), commit=commit, ref=ref,
                  state="ready", live_key=sid)
        return {"id": sid}

    def rows(hub_dir, *, owner_kind=None, owner_id=None, state=None, limit=50, **_):
        with _locked("boxes") as b:
            data = b["data"]
        return [{"id": sid, "state": v["state"], "live_key": v.get("live_key"),
                 "checkouts_json": [{"path": "/workspace/repo", "commit": v["commit"], "ref": v.get("ref")}],
                 "exports_json": v.get("exports") or []}
                for sid, v in data.items() if owner_id is None or v["owner_id"] == owner_id][:limit]

    def export(hub_dir, sid, out_dir):
        box = _box(sid)
        patch = (box.get("patch") or "").encode()
        exports = [{"checkout": "/workspace/repo", "base": box["commit"], "commits": 0, "dirty": False, "bytes": 0,
                    "sha256": "sha256:" + hashlib.sha256(b"").hexdigest(), "file": ""}]
        if patch:
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"repo-{box['commit'][:12]}.patch"
            target.write_bytes(patch)
            exports = [{"checkout": "/workspace/repo", "base": box["commit"], "commits": 1, "dirty": False,
                        "bytes": len(patch), "sha256": "sha256:" + hashlib.sha256(patch).hexdigest(),
                        "file": str(target)}]
        _save_box(sid, exports=exports)
        return exports

    def run_station(hub_dir, definition, message, *, subject=None, timeout=None, registry=None):
        name = definition["name"]
        if not definition.get("sandbox"):
            return real_run_station(hub_dir, definition, message, subject=subject, timeout=timeout,
                                    registry=registry)
        with (_state() / "stations.log").open("a") as f:
            f.write(json.dumps({"station": name, "standin": True}) + "\n")
        with _locked("boxes") as b:
            sid = next(k for k, v in reversed(list(b["data"].items())) if v["agent"] == name)
        box = _box(sid)
        if name == "analyst":
            out = _plan_for(message)
        elif name == "implementer":
            path = Path(box["path"])
            branch = re.search(r"local branch `([^`]+)`", message)
            if branch:
                _git(path, "checkout", "--quiet", "-b", branch.group(1))
            repair = "Failing checks" in message
            files_now = _ci_repair_files(box["commit"]) if repair else _fix_files(message)
            for rel, text in files_now.items():
                (path / rel).parent.mkdir(parents=True, exist_ok=True)
                (path / rel).write_text(text)
            _git(path, "add", "-A")
            _git(path, "commit", "--quiet", "-m", "Cover the discounted basket the failing check reported" if repair
                 else "Round invoice totals once, after tax" if re.search(r"\bcents?\b|\bround", message, re.I)
                 else "Add a Reporting bugs section")
            head = _git(path, "rev-parse", "HEAD").strip()
            patch = _git(path, "format-patch", "--stdout", f"{box['commit']}..HEAD")
            _save_box(sid, patch=patch)
            files = list(files_now)
            out = {"branch": branch.group(1) if branch else "factory/fix", "base": "main", "committed": True,
                   "head_commit": head, "change_summary": [{"path": p, "change": "applied the planned change"}
                                                           for p in files],
                   "verification": [{"command": "python -m pytest -q",
                                     "result": "not run: " + STANDIN + "commands cannot run without a sandbox"}],
                   "deviations": [], "known_limitations": [STANDIN + "the change is the fixture's known fix and the "
                                                            "checks were not run in a sandbox."]}
        else:
            criteria = [line[2:].strip() for line in message.split("verbatim:", 1)[-1].splitlines()
                        if line.startswith("- ")]
            out = {"verdict": "approve", "reviewed_sha": box["commit"],
                   "criteria_results": [{"criterion": c, "pass": True,
                                         "evidence": STANDIN + "judged from the fixture's known fix."}
                                        for c in criteria],
                   "blocking_findings": [], "suggestions": [],
                   "summary": STANDIN + "approved the fixture's known fix at the pushed commit. A real reviewer "
                                        "runs in a sandbox with the repository's checks."}
        return {"text": json.dumps(out), "output": out, "model": "stand-in", "usage": {}}

    hub_runtime.run_station = run_station
    sandbox_service.allocate = allocate
    sandbox_service.list_rows = rows
    sandbox_service.export_patches = export
    sandbox_service.get = lambda hub_dir, sid: {"checkouts_json": [{"commit": _box(sid).get("commit")}]}
    sandbox_service.release = lambda hub_dir, sid, reason: _save_box(sid, state="deleted", live_key=None)
    sandbox_service.stop = lambda hub_dir, sid, reason="idle": _save_box(sid, state="stopped")
    sandbox_service.attach = lambda hub_dir, sid: {"id": sid}
    sandbox_service.reap = lambda hub_dir, dry_run=True: {"stand_in": True, "removed": []}
