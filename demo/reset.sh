#!/usr/bin/env bash
# Return the demo scratch repository to its starting point, so the next run gives the same result.
#
#   demo/reset.sh OWNER/factory-sample [--dry-run]
#
# Touches only that repository: closes the factory's open pull requests and deletes their
# branches, deletes any other factory/* branch, closes the sample issues with a note, and
# creates them again fresh. It never changes main, never deletes a repository, and refuses
# a repository whose name does not end in "factory-sample" unless FACTORY_DEMO_REPO matches.
set -euo pipefail

repo="${1:-}"
dry="${2:-}"
if [[ -z "$repo" || "$repo" != */* ]]; then
  echo "usage: demo/reset.sh OWNER/REPO [--dry-run]" >&2
  exit 2
fi
if [[ "$repo" != */factory-sample && "${FACTORY_DEMO_REPO:-}" != "$repo" ]]; then
  echo "Refusing: $repo is not a demo scratch repository. Set FACTORY_DEMO_REPO=$repo to confirm." >&2
  exit 2
fi
run() { if [[ "$dry" == "--dry-run" ]]; then echo "would run: $*"; else "$@"; fi; }
prefix="${FACTORY_BRANCH_PREFIX:-factory/}"

# 1. The factory's pull requests: close them and delete their branches.
gh pr list --repo "$repo" --state open --json number,headRefName --limit 100 \
  --jq ".[] | select(.headRefName | startswith(\"$prefix\")) | .number" | while read -r n; do
  run gh pr close "$n" --repo "$repo" --delete-branch --comment "Demo reset."
done

# 2. Any other factory branch.
gh api "repos/$repo/branches" --paginate --jq ".[] | select(.name | startswith(\"$prefix\")) | .name" \
  | while read -r b; do
  run gh api -X DELETE "repos/$repo/git/refs/heads/$b"
done

# 3. The sample issues: close the old copies, create fresh ones.
here="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$repo" "$here/fixtures/sample-issues.json" "$dry" <<'PY'
import json, subprocess, sys
repo, path, dry = sys.argv[1], sys.argv[2], sys.argv[3]
titles = {i["title"] for i in json.load(open(path))}
out = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open", "--json", "number,title",
                      "--limit", "100"], check=True, capture_output=True, text=True).stdout
for issue in json.loads(out):
    if issue["title"] in titles:
        cmd = ["gh", "issue", "close", str(issue["number"]), "--repo", repo, "--comment", "Demo reset."]
        print("would run: " + " ".join(cmd)) if dry == "--dry-run" else subprocess.run(cmd, check=True)
PY
if [[ "$dry" != "--dry-run" ]]; then
  python3 "$here/demo/seed_issues.py" "$repo"
fi
echo "Reset $repo."
