#!/usr/bin/env bash
# Install the Software Factory into a copy of a Hubzoid test hub and wire the
# local stand-ins (GitHub and sandbox). Proof and demo use only: no real
# account, no network, nothing leaves this machine.
#
#   tests/live/setup.sh <hub-dir> <state-dir>
#   . <state-dir>/env.sh && cd <hub-dir> && hubzoid run . --port 8701 --bridge-port 8702
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HUB="$(cd "$1" && pwd)"
STATE="$(mkdir -p "$2" && cd "$2" && pwd)"
PY="${PY:-python3}"
HUB_ID="$(basename "$HUB" | tr '[:upper:]' '[:lower:]')"

echo "1. Hub files into $HUB"
for d in agents skills knowledge workflows tools_local doctor quality evals sandboxes; do
  mkdir -p "$HUB/$d" && cp -R "$REPO/$d/." "$HUB/$d/"
done
for f in AGENTS.md settings.yaml hub.manifest.yaml work-items.yaml sandbox.yaml hitl.yaml; do cp "$REPO/$f" "$HUB/$f"; done
sed 's#FACTORY_REPO: .*#FACTORY_REPO: example-co/widget#' "$REPO/hub.settings.yaml" > "$HUB/hub.settings.yaml"
grep -q '^HUBZOID_SCHEDULES=' "$HUB/.env" 2>/dev/null || echo 'HUBZOID_SCHEDULES=1' >> "$HUB/.env"
grep -q '^,admin@localhost,engineering,' "$HUB/identity/access.csv" 2>/dev/null \
  || { mkdir -p "$HUB/identity"; echo ',admin@localhost,engineering,' >> "$HUB/identity/access.csv"; }

echo "2. Synthetic repository example-co/widget as a local bare repository"
rm -rf "$STATE/git" "$STATE/state" && mkdir -p "$STATE/git/example-co" "$STATE/state"
SEED="$(mktemp -d)"
cp -R "$REPO/fixtures/sample-repo/." "$SEED/"
git -C "$SEED" init -q -b main && git -C "$SEED" add -A
git -C "$SEED" -c user.name=Hubzoid -c user.email=sample@example.invalid commit -q -m "Synthetic sample for the Software Factory demo"
git clone -q --bare "$SEED" "$STATE/git/example-co/widget.git" && rm -rf "$SEED"

cat > "$STATE/env.sh" <<ENV
export PYTHONPATH="$REPO/tests/live\${PYTHONPATH:+:\$PYTHONPATH}"
export FACTORY_LIVE_SANDBOX=standin FACTORY_LIVE_GITHUB=fake
export FACTORY_LIVE_STATE="$STATE/state" FACTORY_LIVE_REMOTE="$STATE/git"
export HUBZOID_GITHUB_WEB_URL="file://$STATE/git"
ENV
# shellcheck disable=SC1091
. "$STATE/env.sh"

echo "3. GitHub connection in token mode, against the stand-in"
echo "standin-not-a-token" | "$PY" -m hubzoid channels github connect "$HUB" github --mode pat \
  --repository example-co/widget --token-stdin >/dev/null
REV="$("$PY" -m hubzoid channels list "$HUB" --json | "$PY" -c 'import json,sys; print(next(c["revision"] for c in json.load(sys.stdin)["items"] if c["id"]=="github"))')"
sed "s#HUB_ID#$HUB_ID#g" "$REPO/tests/live/github.standin.yaml" > "$HUB/channels/github.yaml"
"$PY" -m hubzoid channels apply "$HUB" --file "$HUB/channels/github.yaml" --expected-revision "$REV" >/dev/null

echo "4. A local webhook secret (never printed) and the account link"
umask 077 && "$PY" -c 'import secrets; print(secrets.token_hex(24))' > "$STATE/webhook-secret"
"$PY" - "$HUB" "$HUB_ID" "$STATE/webhook-secret" <<'PYEOF'
import sys
from pathlib import Path
from hubzoid.secretstore import store
hub, hub_id, secret = sys.argv[1:4]
store.put(Path(hub), scope="channel", target=f"{hub_id}/github", name="webhook-secret",
          value=Path(secret).read_text().strip(), actor="admin@localhost", surface="cli")
PYEOF
LINK="$PY -m hubzoid channels link $HUB github --external-id 4242 --account admin@localhost"
$LINK >/dev/null 2>&1 || NEED_LINK=1

echo "Ready. Start the hub:"
echo "  . $STATE/env.sh && cd $HUB && $PY -m hubzoid run . --port 8701 --bridge-port 8702"
if [ -n "${NEED_LINK:-}" ]; then
  echo "After the hub starts and you open it once in a browser (that creates the local owner account), link the stand-in GitHub account:"
  echo "  . $STATE/env.sh && $LINK"
fi
echo "Then label issue #1 (signed delivery to the hub's real webhook endpoint):"
echo "  $PY $REPO/tests/live/deliver.py --hub-id $HUB_ID --state $STATE label 1"
