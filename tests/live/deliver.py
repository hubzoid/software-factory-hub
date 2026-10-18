"""Post one signed GitHub delivery to a local hub, as GitHub would, for a run
against the GitHub stand-in (setup.sh). The body is signed with the local
webhook secret, which is never printed.

  python deliver.py --hub-id ID --state DIR label 1
  python deliver.py --hub-id ID --state DIR ci 108          # the PR's head is read from the bare repository
  python deliver.py --hub-id ID --state DIR mention 2 "@factory-demo plan this" --association NONE
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = {"id": 2001, "full_name": "example-co/widget", "owner": {"login": "example-co"}}


def _github(state: Path) -> dict:
    d = json.loads((state / "state" / "github.json").read_text())
    return d.get("data", d)


def _payload(args, state: Path) -> tuple[str, dict]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if args.kind == "label":
        issue = _github(state)["issues"][str(args.number)]
        return "issues", {
            "action": "labeled", "label": {"id": 990001, "name": "factory"}, "repository": REPO,
            "issue": {**issue, "updated_at": now, "labels": issue.get("labels", []) + [{"name": "factory"}]},
            "sender": {"login": "maya-maintainer", "id": 7001, "type": "User"}}
    if args.kind == "ci":
        pull = _github(state)["pulls"][str(args.number)]
        branch = pull["head"]
        head = subprocess.run(["git", "rev-parse", branch], cwd=state / "git" / "example-co" / "widget.git",
                              capture_output=True, text=True, check=True).stdout.strip()
        return "check_suite", {
            "action": "completed", "repository": REPO,
            "check_suite": {"id": int(time.time()), "conclusion": "failure", "head_sha": head, "head_branch": branch,
                            "pull_requests": [{"number": args.number}]},
            "sender": {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}}
    issue = _github(state)["issues"][str(args.number)]
    return "issue_comment", {
        "action": "created", "repository": REPO,
        "issue": {k: issue[k] for k in ("number", "title", "body", "state", "html_url")},
        "comment": {"id": int(time.time()), "body": args.text, "author_association": args.association,
                    "html_url": f"{issue['html_url']}#issuecomment", "updated_at": now},
        "sender": {"login": "sam-reporter", "id": 7002, "type": "User"}}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hub-id", required=True)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--port", type=int, default=8701)
    p.add_argument("kind", choices=["label", "ci", "mention"])
    p.add_argument("number", type=int)
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--association", default="COLLABORATOR")
    args = p.parse_args()
    event, body = _payload(args, args.state)
    raw = json.dumps(body).encode()
    secret = (args.state / "webhook-secret").read_text().strip().encode()
    delivery = hashlib.sha256(raw).hexdigest()[:32]
    req = urllib.request.Request(
        f"http://127.0.0.1:{args.port}/api/hubs/{args.hub_id}/channels/github/webhook", data=raw, method="POST",
        headers={"Content-Type": "application/json", "X-GitHub-Event": event, "X-GitHub-Delivery": delivery,
                 "X-Hub-Signature-256": "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest(),
                 "User-Agent": "GitHub-Hookshot/standin"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(r.status, r.read().decode())
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode())


if __name__ == "__main__":
    main()
