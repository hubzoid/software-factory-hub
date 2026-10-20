"""Test harness for the Software Factory hub.

Unit tests import the factory's modules directly. Integration tests run the
real hub folder (copied to a temporary directory) through the real SDK work
items, stations, operations, channels and push, with three doubles:

* GitHub: a fake REST API (``FakeGitHub``) plus a local bare repository that
  stands in for GitHub's Git endpoint, so ``push_branch`` really pushes;
* stations: ``FakeStations`` replaces the model behind each station and
  makes real commits in a clone when the implementer runs, exported through
  the SDK's export path;
* model calls: ``FakeModel`` answers ``hub.call_llm`` and ``hub.call_agent``.

Approvals and questions (``hub.review_plan``, ``hub.approve``, ``hub.ask``)
are scripted per test. No network, no Docker, no model.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

HUB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB_ROOT / "workflows" / "factory"))

OWNER = "ana@example.org"
REPO_ID = 2001
FULL = "example-co/widget"
HOOK = "factory-hook-value"  # gitleaks:allow (a test value)
GIT_ENV = {"GIT_AUTHOR_NAME": "Agent", "GIT_AUTHOR_EMAIL": "agent@sandbox.invalid",
           "GIT_COMMITTER_NAME": "Agent", "GIT_COMMITTER_EMAIL": "agent@sandbox.invalid",
           "GIT_AUTHOR_DATE": "2026-10-20T10:00:00Z", "GIT_COMMITTER_DATE": "2026-10-20T10:00:00Z",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
COPY = ("AGENTS.md", "agents", "skills", "knowledge", "workflows", "tools_local", "settings.yaml",
        "work-items.yaml", "hitl.yaml", "sandbox.yaml", "sandboxes", "hub.manifest.yaml", "doctor")


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout


# -- the repository ---------------------------------------------------------------------------

class Remote:
    """example-co/widget: a tiny synthetic Python project with a planted bug."""

    def __init__(self, root: Path):
        self.root = root
        self.bare = root / "example-co" / "widget.git"
        self.bare.mkdir(parents=True)
        git(self.bare, "init", "--quiet", "--bare", "--initial-branch=main")
        seed = root / "seed"
        seed.mkdir()
        git(seed, "init", "--quiet", "--initial-branch=main")
        (seed / "calc.py").write_text("def total(xs):\n    return sum(xs) + 1   # planted bug\n")
        (seed / "test_calc.py").write_text("from calc import total\n\n\ndef test_total():\n    assert total([1, 2]) == 3\n")
        git(seed, "add", ".")
        git(seed, "commit", "--quiet", "-m", "Initial")
        git(seed, "remote", "add", "origin", str(self.bare))
        git(seed, "push", "--quiet", "origin", "main")
        self.base = git(seed, "rev-parse", "HEAD").strip()
        self.n = 0

    @classmethod
    def attach(cls, root: Path) -> "Remote":
        """The same repository from another process."""
        r = cls.__new__(cls)
        r.root, r.bare, r.n = root, root / "example-co" / "widget.git", 1000
        r.base = r.head("main")
        return r

    def head(self, ref: str) -> str | None:
        res = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=self.bare,
                             env=GIT_ENV, capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
        res = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}"], cwd=self.bare,
                             env=GIT_ENV, capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else None

    def commit_on(self, ref: str, files: dict[str, str], message: str, *, push: bool = False
                  ) -> tuple[str, bytes, str]:
        """Clone at `ref`, write files, commit: what a sandbox would do. Returns
        (start commit, format-patch bytes, new head). A content that matches
        what is there already gets a revision line, so every run changes
        something. `push` publishes the commit, as a person would."""
        self.n += 1
        work = self.root / f"sandbox-{self.n}"
        subprocess.run(["git", "clone", "--quiet", str(self.bare), str(work)], env=GIT_ENV, check=True)
        start = self.head(ref) or ref
        git(work, "checkout", "--quiet", "--detach", start)
        for path, text in files.items():
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_text() == text:
                text = text + f"# revision {self.n}\n"
            target.write_text(text)
        git(work, "add", ".")
        git(work, "commit", "--quiet", "-m", message)
        patch = git(work, "format-patch", "--stdout", f"{start}..HEAD").encode()
        head = git(work, "rev-parse", "HEAD").strip()
        if push:
            git(work, "push", "--quiet", "--force", str(self.bare), f"HEAD:refs/heads/{ref}")
        return start, patch, head


# -- the GitHub REST API ------------------------------------------------------------------------

class FakeGitHub:
    def __init__(self, remote: Remote):
        self.remote = remote
        self.calls: list[tuple[str, str, dict]] = []
        self.issues = {12: {"number": 12, "title": "total() is off by one",
                            "body": "total([1, 2]) returns 4. It should return 3.", "state": "open", "labels": [],
                            "html_url": f"https://github.com/{FULL}/issues/12", "comments": 0}}
        self.labels = [{"name": "bug", "description": "Something is broken"},
                       {"name": "enhancement", "description": "New feature"},
                       {"name": "area:core", "description": "The calc module"}]
        self.comments: dict[int, list[dict]] = {}
        self.pulls: dict[int, dict] = {}
        self.permission = "write"
        self.failing_jobs = [{"name": "tests", "conclusion": "failure"}]
        self.next = 100

    def _pr_json(self, n):
        pr = self.pulls[n]
        head = self.remote.head(pr["head"]) or pr.get("head_sha")
        return {"number": n, "title": pr["title"], "body": pr["body"], "state": pr.get("state", "open"), "draft": pr["draft"],
                "merged": pr.get("merged", False), "merged_at": pr.get("merged_at"),
                "html_url": f"https://github.com/{FULL}/pull/{n}", "user": {"login": "factory[bot]"},
                "head": {"ref": pr["head"], "sha": head, "repo": {"full_name": pr.get("head_repo", FULL),
                                                                  "fork": pr.get("fork", False)}},
                "base": {"ref": pr["base"], "sha": self.remote.head(pr["base"])}, "changed_files": 1,
                "node_id": f"PR_{n}"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        raw = request.url.raw_path.decode().split("?")[0]
        body = json.loads(request.content) if request.content else {}
        self.calls.append((method, path, body))
        R = httpx.Response
        if method == "POST" and re.fullmatch(r"/app/installations/\d+/access_tokens", path):
            return R(201, json={"token": "ghs_testtoken", "expires_at": "2099-01-01T00:00:00Z"})
        if path == "/app":
            return R(200, json={"id": 9001, "slug": "acme-factory", "owner": {"login": "example-co"}})
        if re.fullmatch(r"/repositories/\d+", path):
            return R(200, json={"id": REPO_ID, "full_name": FULL, "owner": {"login": "example-co"}})
        if path == f"/repos/{FULL}":
            return R(200, json={"id": REPO_ID, "full_name": FULL, "default_branch": "main"})
        m = re.fullmatch(rf"/repos/{FULL}/branches/(.+)", raw)
        if m:
            head = self.remote.head(unquote(m.group(1)))
            if head is None:
                return R(404, json={"message": "Branch not found"})
            return R(200, json={"name": unquote(m.group(1)), "commit": {"sha": head}, "protected": False})
        if path == f"/repos/{FULL}/labels":
            return R(200, json=self.labels)
        m = re.fullmatch(rf"/repos/{FULL}/collaborators/([^/]+)/permission", path)
        if m:
            return R(200, json={"permission": self.permission, "role_name": self.permission})
        if path == "/search/issues":
            return R(200, json={"items": [{"number": 3, "title": "Totals look wrong", "state": "closed"}],
                                "incomplete_results": False})
        m = re.fullmatch(rf"/repos/{FULL}/issues/(\d+)", path)
        if m:
            n = int(m.group(1))
            if method == "GET":
                if n in self.pulls:
                    return R(200, json={**self._pr_json(n), "pull_request": {"url": "x"},
                                        "comments": len(self.comments.get(n, []))})
                issue = self.issues.get(n)
                return R(200, json={**issue, "comments": len(self.comments.get(n, []))}) if issue else R(404, json={})
            self.issues.setdefault(n, {}).update({k: v for k, v in body.items() if k in ("state", "title", "body")})
            return R(200, json=self.issues[n])
        m = re.fullmatch(rf"/repos/{FULL}/issues/(\d+)/comments", path)
        if m:
            n = int(m.group(1))
            if method == "POST":
                self.next += 1
                c = {"id": self.next, "body": body["body"], "user": {"login": "acme-factory[bot]"},
                     "html_url": f"https://github.com/c/{self.next}"}
                self.comments.setdefault(n, []).append(c)
                return R(201, json=c)
            return R(200, json=self.comments.get(n, []))
        m = re.fullmatch(rf"/repos/{FULL}/issues/(\d+)/labels", path)
        if m:
            n = int(m.group(1))
            labels = self.issues.setdefault(n, {}).setdefault("labels", [])
            labels += [{"name": x} for x in body.get("labels", [])]
            return R(200, json=labels)
        if path == f"/repos/{FULL}/pulls" and method == "GET":
            head = (request.url.params.get("head") or "").split(":", 1)[-1]
            return R(200, json=[self._pr_json(n) for n, pr in self.pulls.items() if not head or pr["head"] == head])
        if path == f"/repos/{FULL}/pulls" and method == "POST":
            self.next += 1
            n = self.next
            self.pulls[n] = {"title": body["title"], "body": body["body"], "head": body["head"], "base": body["base"],
                             "draft": body.get("draft")}
            return R(201, json=self._pr_json(n))
        m = re.fullmatch(rf"/repos/{FULL}/pulls/(\d+)", path)
        if m:
            n = int(m.group(1))
            if method == "PATCH":
                self.pulls[n].update({k: v for k, v in body.items() if k in ("title", "body")})
            return R(200, json=self._pr_json(n))
        m = re.fullmatch(rf"/repos/{FULL}/pulls/(\d+)/(files|reviews)", path)
        if m:
            return R(200, json=[{"filename": "calc.py", "status": "modified", "additions": 1, "deletions": 1,
                                 "changes": 2, "patch": "@@ -1 +1 @@"}] if m.group(2) == "files" else [])
        m = re.fullmatch(rf"/repos/{FULL}/commits/([0-9a-f]+)/check-runs", path)
        if m:
            return R(200, json={"check_runs": [{"id": 1, "name": j["name"], "conclusion": j["conclusion"],
                                                "app": {"slug": "other"}, "output": {"summary": "1 failed"}}
                                               for j in self.failing_jobs]})
        if path == "/graphql":
            n = int(body["variables"]["id"].split("_")[1])
            self.pulls[n]["draft"] = "convertPullRequestToDraft" in body["query"]
            name = "markPullRequestReadyForReview" if not self.pulls[n]["draft"] else "convertPullRequestToDraft"
            return R(200, json={"data": {name: {"pullRequest": {"number": n, "isDraft": self.pulls[n]["draft"]}}}})
        return R(404, json={"message": f"not faked: {method} {path}"})


# -- the models behind stations and hub calls ----------------------------------------------------

class FakeStations:
    """Scripted station results. The implementer makes real commits."""

    def __init__(self, remote: Remote):
        self.remote = remote
        self.calls: list[dict] = []
        self.classification = {"type": "bug", "priority": "high", "complexity": "trivial", "affected_area": "calc",
                               "actionable": True, "needs_clarification": False, "questions": [],
                               "summary": "Fix the off-by-one in total"}
        self.analysis = {"problem_statement": "total() adds 1 to the sum.", "approach": "Return the plain sum.",
                         "plan": ["Remove the + 1 in calc.total", "Run the tests"],
                         "affected_surface": ["calc.py"], "risks": [],
                         "acceptance_criteria": ["total([1, 2]) returns 3", "The tests pass"],
                         "test_strategy": "pytest", "assumptions": [], "open_questions": [], "handoff_id": None}
        self.classifications: list[dict] = []
        self.research = None
        self.verdicts = ["approve"]
        self.changes = [{"calc.py": "def total(xs):\n    return sum(xs)\n"}]
        self.committed = True
        self.reviewed_override = None
        self.reviewer_dirty = False
        self.boxes: dict[str, dict] = {}
        self.failures: dict[str, int] = {}     # station name -> runs that crash

    def run(self, hub_dir, definition, message, *, subject=None, timeout=None, registry=None):
        name = definition["name"]
        self.calls.append({"name": name, "message": message, "checkout": definition.get("checkout"),
                           "tools": sorted(registry or {})})
        if self.failures.get(name):
            from hubzoid import runtime

            self.failures[name] -= 1
            raise runtime.AgentRunError("the runtime exited before answering")
        if name == "classifier":
            out = dict(self.classifications.pop(0) if self.classifications else self.classification)
        elif name == "researcher":
            out = self.research
        elif name == "analyst":
            out = dict(self.analysis)
        elif name == "implementer":
            box = self.boxes[self._box_for(definition)]
            if not self.committed:
                out = {"branch": "x", "base": "main", "committed": False, "head_commit": None, "change_summary": [],
                       "verification": [], "deviations": [], "known_limitations": ["The plan needs a decision."]}
            else:
                files = self.changes.pop(0) if len(self.changes) > 1 else self.changes[0]
                start, patch, head = self.remote.commit_on(box["commit"], files, "Fix total")
                box["patch"], box["start"] = patch, start
                out = {"branch": "factory/fix", "base": "main", "committed": True, "head_commit": head,
                       "change_summary": [{"path": p, "change": "fixed"} for p in files],
                       "verification": [{"command": "pytest", "result": "pass: 1 passed"}], "deviations": [],
                       "known_limitations": []}
        else:
            box = self.boxes[self._box_for(definition)]
            verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
            # judge exactly the criteria the reviewer was handed, verbatim
            task = message.split("verbatim:", 1)[-1]
            crit = [line[2:].strip() for line in task.splitlines() if line.startswith("- ")]
            out = {"verdict": verdict, "reviewed_sha": self.reviewed_override or box["commit"],
                   "criteria_results": [{"criterion": c, "pass": verdict == "approve", "evidence": "ran pytest"}
                                        for c in crit],
                   "blocking_findings": [] if verdict == "approve" else ["calc.py: the sum is still wrong"],
                   "suggestions": [], "summary": f"Verdict {verdict}."}
        return {"text": json.dumps(out), "output": out, "model": "fake", "usage": {}}

    def _box_for(self, definition) -> str:
        # the most recent sandbox allocated for this definition's call
        return next(k for k in reversed(list(self.boxes)) if self.boxes[k]["agent"] == definition["name"])


class FakeModel:
    """hub.call_llm and hub.call_agent, scripted by what is asked."""

    def __init__(self):
        self.route = {"route": "implement", "issue_number": None, "act": None, "clarify": None, "reason": "clear"}
        self.labels = {"labels": ["bug", "area:core"], "duplicate_of": None, "reason": ""}
        self.research = {"needed": False, "question": ""}
        self.brain = {"note": None}
        self.prompts: list[dict] = []
        self.agent_replies: list[str] = []

    def llm(self, spec, hub_dir=None, subject=None):
        self.prompts.append(spec)
        system = spec.get("system") or ""
        if "route requests" in system:
            out = self.route
        elif "label GitHub issues" in system:
            out = self.labels
        elif "needs web research" in system:
            out = self.research
        elif "curated list of facts" in system:
            out = self.brain
        else:
            out = {}
        return {"text": json.dumps(out), "json": out}

    def agent(self, task, hub_dir=None, subject=None):
        self.prompts.append({"agent": task})
        return self.agent_replies.pop(0) if self.agent_replies else "The repository is a small calculator."


# -- fixtures -------------------------------------------------------------------------------

@pytest.fixture
def remote(tmp_path, monkeypatch):
    r = Remote(tmp_path / "git")
    monkeypatch.setenv("HUBZOID_GITHUB_WEB_URL", f"file://{tmp_path / 'git'}")
    return r


@pytest.fixture
def factory_hub(tmp_path, monkeypatch, remote):
    """The real hub folder in a temporary directory, with an applied fake
    GitHub App connection to example-co/widget."""
    for key in ("DATABASE_URL", "HUBZOID_OPERATIONAL_DB", "WEBUI_AUTH", "HUBZOID_AUTH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HUBZOID_PUBLIC_URL", "https://factory.example.test")
    root = tmp_path / "factory"
    root.mkdir()
    for name in COPY:
        src = HUB_ROOT / name
        if src.is_dir():
            shutil.copytree(src, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            shutil.copy2(src, root / name)
    (root / "hub.settings.yaml").write_text(
        "version: 1\nvalues:\n  FACTORY_REPO: example-co/widget\n  FACTORY_CHANNELS: [chat, mcp, github]\n"
        "secrets: {}\n")
    (root / ".env").write_text("MODEL=claude-local\nHUBZOID_SCHEDULES=1\n")
    monkeypatch.setenv("HUBZOID_HUB_DIR", str(root))
    return root


@pytest.fixture
def api(monkeypatch, remote):
    from githubkit.cache import DEFAULT_CACHE_STRATEGY

    from hubzoid.channels.github import client as gh

    fake = FakeGitHub(remote)
    monkeypatch.setattr(gh, "transport", httpx.MockTransport(fake))
    gh._NAMES.clear()
    cache = getattr(DEFAULT_CACHE_STRATEGY, "_cache", None)
    if cache is not None:
        cache._cache.clear()
    return fake


@pytest.fixture
def conn(factory_hub, api):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from hubzoid.channels import config
    from hubzoid.secretstore import store as ss

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    ss.put(factory_hub, scope="channel", target="factory/github", name="private-key", value=pem, actor="test")
    ss.put(factory_hub, scope="channel", target="factory/github", name="webhook-secret", value=HOOK, actor="test")
    text = (factory_hub / "channels_github.yaml")
    cfg = {"version": 1, "id": "github", "provider": "github", "enabled": True, "workflow": "factory",
           "run_as": "workflow", "allowed_groups": [], "progress": True,
           "provider_config": {"mode": "app", "owner": {"type": "organization", "login": "example-co", "id": 101},
                               "app_id": 9001, "installation_id": 7001,
                               "repositories": [{"id": REPO_ID, "full_name": FULL}],
                               "private_key_ref": "secret:channel/factory/github/private-key",
                               "webhook_secret_ref": "secret:channel/factory/github/webhook-secret",
                               "bot_name": "acme-factory",
                               "rules": {"mentions": True, "label": "factory", "pr_opened": True,
                                         "ci_failure": True,
                                         "routes": {"mention": "request", "review_mention": "request",
                                                    "label": "implement", "pull_request": "summarize",
                                                    "ci_failure": "revise"}}}}
    del text
    v = config.load_text(factory_hub, config.render(cfg))
    assert v.valid, v.errors
    config.apply(factory_hub, v.data, expected_revision="absent", actor="test")
    return config.active(factory_hub, "github")


@pytest.fixture
def stations_fake(monkeypatch, remote, factory_hub):
    from hubzoid import runtime
    from hubzoid.sandbox import config as sandbox_config
    from hubzoid.sandbox import service as sandbox_service

    fake = FakeStations(remote)
    monkeypatch.setattr(runtime, "run_station", fake.run)
    monkeypatch.setattr(sandbox_config, "check_profile", lambda hub_dir, profile: None)

    def allocate(hub_dir, *, owner_kind, owner_id, profile_id, item_id=None, actor="", checkout=None,
                 profile_json=None):
        from hubzoid.stations import service as st

        call = st.get_call(hub_dir, owner_id)
        sid = f"box-{len(fake.boxes) + 1}"
        ref = (checkout or {}).get("ref") or "main"
        commit = (checkout or {}).get("commit") or remote.head(ref)
        fake.boxes[sid] = {"id": sid, "owner_id": owner_id, "agent": call["agent"], "ref": ref,
                           "commit": commit, "state": "ready", "live_key": sid}
        return {"id": sid}

    def rows(hub_dir, *, owner_kind=None, owner_id=None, state=None, limit=50):
        out = []
        for sid, b in fake.boxes.items():
            if owner_id is not None and b["owner_id"] != owner_id:
                continue
            out.append({"id": sid, "state": b["state"], "live_key": b.get("live_key"),
                        "checkouts_json": [{"path": "/workspace/repo", "commit": b["commit"], "ref": b["ref"]}],
                        "exports_json": b.get("exports") or []})
        return out

    def export(hub_dir, sandbox_id, out_dir):
        box = fake.boxes[sandbox_id]
        if not box.get("patch"):
            box["exports"] = [{"checkout": "/workspace/repo", "base": box["commit"], "commits": 0, "bytes": 0,
                               "dirty": fake.reviewer_dirty if box["agent"] == "reviewer" else False,
                               "sha256": "sha256:" + hashlib.sha256(b"").hexdigest(), "file": ""}]
            return box["exports"]
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"repo-{box['start'][:12]}.patch"
        target.write_bytes(box["patch"])
        box["exports"] = [{"checkout": "/workspace/repo", "base": box["start"], "commits": 1, "dirty": False,
                           "bytes": len(box["patch"]),
                           "sha256": "sha256:" + hashlib.sha256(box["patch"]).hexdigest(), "file": str(target)}]
        return box["exports"]

    monkeypatch.setattr(sandbox_service, "allocate", allocate)
    monkeypatch.setattr(sandbox_service, "list_rows", rows)
    monkeypatch.setattr(sandbox_service, "get", lambda hub_dir, sid: {"checkouts_json": [{"commit": "x"}]})
    monkeypatch.setattr(sandbox_service, "export_patches", export)
    monkeypatch.setattr(sandbox_service, "release", lambda *a, **k: None)
    monkeypatch.setattr(sandbox_service, "stop", lambda *a, **k: None)
    monkeypatch.setattr(sandbox_service, "attach", lambda hub_dir, sid: {"id": sid})
    return fake


@pytest.fixture
def model(monkeypatch):
    from hubzoid.workflows import context

    fake = FakeModel()
    monkeypatch.setattr(context, "_LLM", fake.llm)
    monkeypatch.setattr(context, "_AGENT", fake.agent)
    monkeypatch.setattr(context, "_LLM_STEP", None)
    monkeypatch.setattr(context, "_AGENT_STEP", None)
    return fake


class People:
    """Scripted human decisions for hub.review_plan, hub.approve and hub.ask."""

    def __init__(self):
        self.plans: list[dict] = [{"approved": True, "note": None, "by": OWNER}]
        self.approvals: list[dict] = [{"approved": True, "note": None, "by": OWNER}]
        self.answers: list[str] = ["The emails are the password reset emails."]
        self.seen: list[tuple[str, dict]] = []


@pytest.fixture
def people(monkeypatch):
    from hubzoid.workflows import context

    p = People()

    def review_plan(self, path, *, title=None, approvers=None):
        p.seen.append(("plan", {"path": str(path), "title": title, "approvers": approvers,
                                "text": Path(path).read_text()}))
        return p.plans.pop(0) if len(p.plans) > 1 else p.plans[0]

    def approve(self, action, *, details=None, approvers=None):
        p.seen.append(("approve", {"action": action, "details": details, "approvers": approvers}))
        return p.approvals.pop(0) if len(p.approvals) > 1 else p.approvals[0]

    def ask(self, question, *, options=None, approvers=None):
        p.seen.append(("ask", {"question": question, "approvers": approvers}))
        return p.answers.pop(0) if len(p.answers) > 1 else p.answers[0]

    def publish(self, path, *, title=None, audience="owner", share_with=(), key=None, digest=None):
        p.seen.append(("publish", {"path": str(path), "title": title, "share_with": list(share_with)}))
        return {"id": "art-1", "url": f"https://factory.example.test/a/{Path(path).name}"}

    monkeypatch.setattr(context.Hub, "review_plan", review_plan)
    monkeypatch.setattr(context.Hub, "approve", approve)
    monkeypatch.setattr(context.Hub, "ask", ask)
    monkeypatch.setattr(context.Hub, "publish_artifact", publish)
    return p


@pytest.fixture
def factory(factory_hub, conn, api, remote, stations_fake, model, people, monkeypatch):
    """Everything wired: start work and run the pipeline to its outcome."""
    from hubzoid.work_items import service as wi

    monkeypatch.setattr(wi, "start", lambda hub_dir, item: item)
    return Harness(factory_hub, conn, api, remote, stations_fake, model, people, monkeypatch)


class Harness:
    def __init__(self, hub_dir, conn, api, remote, stations, model, people, mp):
        self.hub_dir, self.conn, self.api, self.remote = hub_dir, conn, api, remote
        self.stations, self.model, self.people = stations, model, people
        self._mp = mp
        self.steps: dict[str, list] = {}

    # starting work the ways people do
    def chat(self, request: str, *, issue: int | None = None, requester: str = OWNER, route: str = "request",
             key: str | None = None) -> dict:
        from hubzoid.work_items import service as wi

        payload = {"source": "chat", "request": request}
        if issue:
            payload["subject"] = {"kind": "github_issue", "number": issue}
        item, _ = wi.admit(self.hub_dir, workflow="factory", key=key or f"chat:{request[:20]}:{issue}", route=route,
                           input=payload, requester=requester, origin={"source": "chat", "surface": "web"})
        return item

    def deliver(self, event: str, body: dict, delivery: str = "d1") -> dict:
        """A signed GitHub webhook, routed by the SDK's channel router."""
        from hubzoid.channels import admission, router, store
        from hubzoid.work_items import store as wstore

        raw = json.dumps(body).encode()
        sig = "sha256=" + hmac.new(HOOK.encode(), raw, hashlib.sha256).hexdigest()
        hexid = hashlib.sha1(delivery.encode()).hexdigest()[:16]
        headers = {"x-hub-signature-256": sig, "x-github-delivery": f"{hexid}-0000-0000", "x-github-event": event}
        before = {r["id"] for r in store.list_deliveries(self.hub_dir, "factory", "github")["items"]}
        admission.receive(self.hub_dir, "github", raw, headers, {})
        for row in store.open_deliveries(self.hub_dir, "factory"):
            router._route_one(self.hub_dir, row, None)
        rows = [r for r in store.list_deliveries(self.hub_dir, "factory", "github")["items"] if r["id"] not in before]
        routed = [r for r in rows if (r.get("route_json") or {}).get("work_item_id")]
        if not routed:
            return {"delivery": rows[0] if rows else None}
        return wstore.get_item(self.hub_dir, routed[0]["route_json"]["work_item_id"])

    def label(self, number: int = 12, delivery: str = "d-label") -> dict:
        issue = self.api.issues[number]
        return self.deliver("issues", {
            "action": "labeled", "label": {"name": "factory", "id": 77},
            "issue": {"number": number, "title": issue["title"], "body": issue["body"],
                      "updated_at": "2026-10-20T00:00:00Z", "html_url": issue["html_url"]},
            "repository": {"id": REPO_ID, "full_name": FULL}, "installation": {"id": 7001},
            "sender": {"id": 501, "login": "ana", "type": "User"}}, delivery)

    def run(self, item: dict, *, fresh_execution: bool = False) -> dict:
        """Run the factory workflow body for one item, as the engine would:
        saved steps (stages, station calls, follow-up reads) replay their
        recorded output in order, and the result is stored on the item."""
        from hubzoid import db
        from hubzoid.work_items import facade
        from hubzoid.work_items import store as wstore
        from hubzoid.workflows import context
        from hubzoid.workflows.identity import RunIdentity
        from software_factory import pipeline

        item = wstore.get_item(self.hub_dir, item["id"])
        if fresh_execution:
            self.steps.pop(item["id"], None)
        recorded = self.steps.setdefault(item["id"], [])
        position = {"n": 0}

        def step(name, fn):
            n = position["n"]
            position["n"] += 1
            if n < len(recorded):
                assert recorded[n][0] == name, f"replay diverged at step {n}: {recorded[n][0]} != {name}"
                return recorded[n][1]
            value = fn()
            recorded.append((name, value))
            return value

        self._mp.setattr(facade, "_step", step)
        ident = RunIdentity("admin@localhost", None, "test", "admin@localhost").to_dict()
        with context.run_scope(hub="factory", workflow="factory", hub_dir=self.hub_dir,
                               engine=db.operational_engine(self.hub_dir), identity=ident, run_id=f"run-{item['id']}",
                               work={"item": item, "stage": None}):
            out = pipeline.run()
        current = wstore.get_item(self.hub_dir, item["id"])
        wstore.update_item(self.hub_dir, item["id"], expected_revision=current["revision"], state="completed",
                           result_json={"result": out})
        return out

    def item(self, item_id: str) -> dict:
        from hubzoid.work_items import store as wstore

        return wstore.get_item(self.hub_dir, item_id)

    def ops(self, item_id: str) -> list[dict]:
        from hubzoid.work_items import store as wstore

        return wstore.list_ops(self.hub_dir, "factory", item_id=item_id)

    def writes(self) -> list[tuple[str, str, dict]]:
        return [c for c in self.api.calls if c[0] in ("POST", "PATCH", "DELETE", "PUT")
                and not c[1].endswith("/access_tokens")]
