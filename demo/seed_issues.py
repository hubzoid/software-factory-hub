"""Create the synthetic sample's labels and issues on a scratch repository.

    python demo/seed_issues.py OWNER/factory-sample

Uses the GitHub CLI's own login (`gh auth status`); this script never sees a
token. Safe to run again: labels are updated in place, issues are created
once per title.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "fixtures"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(repo: str) -> None:
    for label in json.loads((HERE / "sample-labels.json").read_text()):
        gh("label", "create", label["name"], "--repo", repo, "--color", label["color"],
           "--description", label["description"], "--force")
    existing = {i["title"] for i in json.loads(gh("issue", "list", "--repo", repo, "--state", "open",
                                                   "--json", "title", "--limit", "100"))}
    for issue in json.loads((HERE / "sample-issues.json").read_text()):
        if issue["title"] in existing:
            continue
        args = ["issue", "create", "--repo", repo, "--title", issue["title"], "--body", issue["body"]]
        for label in issue["labels"]:
            args += ["--label", label]
        print(gh(*args).strip())


if __name__ == "__main__":
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit("usage: python demo/seed_issues.py OWNER/REPO")
    main(sys.argv[1])
