"""The Software Factory's doctor checks. Each returns one row with what is
wrong and the exact next step, and never prints a credential. They run in
their own processes, so one failing check never hides another: a builder
sees every setup problem at once."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FACTORY = "factory"
STATIONS = ("classifier", "researcher", "analyst", "implementer", "reviewer")
WANT_ROUTES = {"mention": "request", "review_mention": "request", "label": "implement", "pull_request": "summarize",
               "ci_failure": "revise"}


def _row(status: str, summary: str, recovery: str | None = None, details: dict | None = None) -> dict:
    out = {"status": status, "summary": summary}
    if recovery:
        out["recovery"] = recovery
    if details:
        out["details"] = details
    return out


def _hub(context) -> Path:
    return Path(context["hub_dir"])


def _workflow_code(hub_dir: Path) -> None:
    code = str(hub_dir / "workflows" / "factory")
    if code not in sys.path:
        sys.path.insert(0, code)


def settings(context) -> dict:
    """The settings validate (types, ranges, patterns) and fit together."""
    s = context["settings"]
    problems = []
    channels = s.get("FACTORY_CHANNELS") or []
    if "linear" in channels and not s.get("FACTORY_LINEAR_CONNECTION"):
        problems.append("linear is in FACTORY_CHANNELS but FACTORY_LINEAR_CONNECTION is empty")
    if "slack" in channels and not s.get("FACTORY_SLACK_CONNECTION"):
        problems.append("slack is in FACTORY_CHANNELS but FACTORY_SLACK_CONNECTION is empty")
    if "github" not in channels and not ({"chat", "mcp"} & set(channels)):
        problems.append("FACTORY_CHANNELS has no way to ask the factory for work")
    if not s.get("FACTORY_INTAKE_ENABLED", True):
        return _row("warn", "Intake is paused: no new work starts. Waiting decisions and recovery still work.",
                    "Set FACTORY_INTAKE_ENABLED: true in hub.settings.yaml and run hubzoid hub configure . --apply.")
    if problems:
        return _row("fail", "; ".join(problems) + ".", "Fix hub.settings.yaml, then hubzoid hub configure . --check.")
    return _row("ok", f"{s.get('FACTORY_REPO')}: label {s.get('FACTORY_LABEL')!r}, branches "
                      f"{s.get('FACTORY_BRANCH_PREFIX')}*, {s.get('FACTORY_REVIEW_CYCLES')} review cycles, "
                      f"{s.get('FACTORY_CI_ATTEMPTS')} CI attempts, plan approval "
                      f"{'on' if s.get('FACTORY_REQUIRE_PLAN_APPROVAL', True) else 'off'}.")


def github(context) -> dict:
    """The GitHub connection exists, is enabled, covers FACTORY_REPO and
    routes its triggers to the factory."""
    hub_dir = _hub(context)
    s = context["settings"]
    cid = s.get("FACTORY_GITHUB_CONNECTION") or "github"
    try:
        from hubzoid.channels import config

        conn = config.active(hub_dir, cid)
    except Exception:  # noqa: BLE001
        return _row("fail", f"The GitHub connection {cid!r} is not applied.",
                    f"Connect it: hubzoid channels github connect . {cid} --owner <org> --owner-type organization "
                    f"--name <app-name> --open (a hosted hub), or hubzoid channels github connect . {cid} --mode pat "
                    f"--repository {s.get('FACTORY_REPO')} (a laptop). See docs/setup.md.")
    cfg = conn.settings
    problems, notes = [], []
    if conn.config.workflow != FACTORY:
        problems.append(f"it starts {conn.config.workflow or 'the chat agent'}, not the factory workflow")
    repos = {r.full_name.lower(): r.id for r in (cfg.repositories or [])}
    want = (s.get("FACTORY_REPO") or "").lower()
    if want not in repos:
        problems.append(f"{want} is not one of its repositories ({', '.join(sorted(repos)) or 'none'})")
    if cfg.rules.label != s.get("FACTORY_LABEL"):
        problems.append(f"its label rule is {cfg.rules.label!r}, FACTORY_LABEL is {s.get('FACTORY_LABEL')!r}")
    routes = {k: cfg.rules.route(k) for k in WANT_ROUTES}
    wrong = {k: v for k, v in routes.items() if v != WANT_ROUTES[k]}
    if wrong:
        problems.append("rules.routes should be " + json.dumps(WANT_ROUTES) + f" (now {json.dumps(routes)})")
    if not conn.config.enabled:
        notes.append("paused (enabled: false), so GitHub events are recorded but start nothing")
    if cfg.mode == "pat":
        notes.append("local token mode: replies use your own GitHub account, pushes use your whole personal token "
                     "(not narrowed to one repository, so use a fine-grained token limited to it), and webhooks "
                     "are not verified")
        if not s.get("FACTORY_BOT_NAME"):
            notes.append("token mode needs FACTORY_BOT_NAME set for mentions")
    if problems:
        return _row("fail", f"GitHub connection {cid}: " + "; ".join(problems) + ".",
                    f"Edit channels/{cid}.yaml and apply it with hubzoid channels apply . --file channels/{cid}.yaml "
                    "--expected-revision <current>.")
    if notes:
        return _row("warn", f"GitHub connection {cid}: " + "; ".join(notes) + ".",
                    f"hubzoid channels doctor . {cid}")
    return _row("ok", f"GitHub connection {cid} covers {want} and routes label, mention, CI and new pull requests to "
                      "the factory.")


def stations(context) -> dict:
    """All five stations load, with closed schemas identical to the factory's
    own result models."""
    hub_dir = _hub(context)
    _workflow_code(hub_dir)
    try:
        from hubzoid.stations import definitions
        from software_factory.schemas import STATIONS as MODELS, json_schema

        loaded = definitions.load_all(hub_dir)
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"Stations do not load: {getattr(exc, 'message', exc)}",
                    "Fix the file named above, then hubzoid stations validate .")
    missing = [n for n in STATIONS if n not in loaded]
    if missing:
        return _row("fail", f"Missing stations: {', '.join(missing)}.", "Restore agents/<name>/AGENTS.md.")
    drift = [n for n in STATIONS if loaded[n].schema != json_schema(MODELS[n])]
    if drift:
        return _row("fail", f"Result schemas differ from the factory's models: {', '.join(drift)}.",
                    "Regenerate them: cd workflows/factory && python -m software_factory.schemas --write")
    boxed = [n for n in ("analyst", "implementer", "reviewer") if loaded[n].sandbox != context["settings"].get(
        "FACTORY_SANDBOX_PROFILE")]
    if boxed:
        return _row("fail", f"{', '.join(boxed)} must use the sandbox profile "
                            f"{context['settings'].get('FACTORY_SANDBOX_PROFILE')}.",
                    "Set sandbox: in agents/<name>/AGENTS.md to FACTORY_SANDBOX_PROFILE.")
    engines = sorted({loaded[n].engine for n in STATIONS})
    return _row("ok", f"Five stations load on {', '.join(engines)}: " + ", ".join(
        f"{n} ({len(loaded[n].tools)} tools)" for n in STATIONS) + ".")


def sandbox(context) -> dict:
    """The sandbox profile is valid and Docker answers. Hubzoid never falls
    back to the host shell."""
    hub_dir = _hub(context)
    profile = context["settings"].get("FACTORY_SANDBOX_PROFILE")
    try:
        from hubzoid.sandbox import config as sandbox_config

        sandbox_config.check_profile(hub_dir, sandbox_config.load_profile(hub_dir, profile))
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"Sandbox profile {profile!r}: {getattr(exc, 'message', exc)}",
                    f"Fix sandboxes/{profile}.yaml, then hubzoid sandbox profiles validate .")
    docker = shutil.which("docker")
    if not docker:
        return _row("fail", "Docker is not installed, so the analyst, implementer and reviewer cannot run.",
                    "Install a Docker engine (Docker Desktop, Colima or OrbStack), then hubzoid sandbox doctor .")
    try:
        res = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                             timeout=15)
    except subprocess.TimeoutExpired:
        res = None
    if res is None or res.returncode != 0:
        return _row("fail", "Docker is installed but its engine is not running.",
                    "Start Docker, then hubzoid sandbox doctor . and hubzoid sandbox profiles prepare . " + profile)
    return _row("ok", f"Sandbox profile {profile} is valid. Docker {res.stdout.strip()} answers. Agent commands run "
                      "offline after setup.")


def write_modes(context) -> dict:
    """Every pull request update waits for the requester, and nothing can merge."""
    hub_dir = _hub(context)
    try:
        from hubzoid.work_items import config

        cfg = config.load(hub_dir)
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"work-items.yaml: {getattr(exc, 'message', exc)}", "Fix the line shown.")
    mode = cfg.write_modes.get("github.pr_update", "off")
    if mode != "approve":
        return _row("warn", f"github.pr_update is {mode!r}: the factory cannot mark a pull request ready, even after "
                            "approval.", "Set github.pr_update: approve in work-items.yaml.")
    return _row("ok", "Pull request updates wait for the requester's approval of the exact change. There is no merge "
                      "tool.")


def channels(context) -> dict:
    hub_dir = _hub(context)
    s = context["settings"]
    rows = []
    try:
        from hubzoid.channels import config
    except Exception:  # noqa: BLE001
        return _row("warn", "Channels are not available in this Hubzoid install.")
    for name, key in (("linear", "FACTORY_LINEAR_CONNECTION"), ("slack", "FACTORY_SLACK_CONNECTION")):
        if name not in (s.get("FACTORY_CHANNELS") or []):
            continue
        cid = s.get(key)
        try:
            conn = config.active(hub_dir, cid)
        except Exception:  # noqa: BLE001
            rows.append(f"{name}: connection {cid!r} is not applied")
            continue
        if conn.config.workflow != FACTORY:
            rows.append(f"{name}: connection {cid} does not start the factory workflow")
    if rows:
        return _row("fail", "; ".join(rows) + ".", "Apply the channel file (see channels/*.yaml.example).")
    enabled = ", ".join(s.get("FACTORY_CHANNELS") or [])
    return _row("ok", f"Requests come from {enabled}. ClickUp and other trackers work by pulling an issue in through "
                      "their MCP server.")


def runtime(context) -> dict:
    """An installed Claude Code or Codex login runs the stations; no API key."""
    found = [name for name in ("claude", "codex") if shutil.which(name)]
    schedules = os.environ.get("HUBZOID_SCHEDULES")
    env_file = _hub(context) / ".env"
    if env_file.is_file() and "HUBZOID_SCHEDULES=1" in env_file.read_text(encoding="utf-8", errors="ignore"):
        schedules = "1"
    problems = []
    if not found:
        problems.append("neither Claude Code nor Codex is installed")
    if schedules not in ("1", "true", "yes"):
        problems.append("HUBZOID_SCHEDULES=1 is not set, so `hubzoid run` will not run factory work")
    if problems:
        return _row("warn", "; ".join(problems) + ".", "Install and sign in to Claude Code or Codex, and put "
                    "HUBZOID_SCHEDULES=1 in the hub's .env.")
    return _row("ok", f"Installed runtime: {', '.join(found)}. Work items run under hubzoid run.")


def brain(context) -> dict:
    hub_dir = _hub(context)
    folder = hub_dir / "knowledge" / "factory-brain"
    big = [p.name for p in folder.glob("*.md") if len(p.read_text(encoding="utf-8")) > 40_000]
    if big:
        return _row("warn", f"Factory brain files over 40,000 characters: {', '.join(big)}.",
                    "Curate them: keep durable repository facts only.")
    count = len([p for p in folder.glob("*.md") if p.name != "README.md"])
    return _row("ok", f"{count} factory brain file(s). Changes go through reviewed hub changes.")
