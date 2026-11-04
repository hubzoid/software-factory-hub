"""The Software Factory's doctor checks. Each returns one row with what is
wrong and the exact next step, and never prints a credential. They run in
their own processes, so one failing check never hides another: a builder
sees every setup problem at once.

Some rows also carry a `card`: the short line and detail the chat's Get started
cards show a manager (get-started.yaml). Older Hubzoid versions ignore it."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FACTORY = "factory"
STATIONS = ("classifier", "researcher", "analyst", "implementer", "reviewer")
BUILDS = "Plans and builds run in Docker"
CHANNEL_NAMES = {"chat": "Chat", "mcp": "MCP", "github": "GitHub", "linear": "Linear", "slack": "Slack"}
WANT_ROUTES = {"mention": "request", "review_mention": "request", "label": "implement", "pull_request": "summarize",
               "ci_failure": "revise"}


def _row(status: str, summary: str, recovery: str | None = None, details: dict | None = None,
         card: dict | None = None) -> dict:
    out = {"status": status, "summary": summary}
    if recovery:
        out["recovery"] = recovery
    if details:
        out["details"] = details
    if card:
        out["card"] = card
    return out


def _cut(text: str, limit: int, *, keep_end: bool = False) -> str:
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):] if keep_end else text[:limit - 1].rstrip() + "…"


def _card(line: str, detail: str | None = None, *, path: bool = False) -> dict:
    """A Get started card: a line of at most 60 characters (a long folder keeps
    its end) and an optional detail of at most 80."""
    card = {"line": _cut(line, 60, keep_end=path)}
    if detail:
        card["detail"] = _cut(detail, 80)
    return card


def _is_local(value) -> bool:
    return str(value or "").startswith(("/", "~/"))


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


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
    results = "Reviewed branches in your folder" if _is_local(s.get("FACTORY_REPO")) else "Reviewed draft pull requests"
    if "linear" in channels and not s.get("FACTORY_LINEAR_CONNECTION"):
        problems.append("linear is in FACTORY_CHANNELS but FACTORY_LINEAR_CONNECTION is empty")
    if "slack" in channels and not s.get("FACTORY_SLACK_CONNECTION"):
        problems.append("slack is in FACTORY_CHANNELS but FACTORY_SLACK_CONNECTION is empty")
    if "github" not in channels and not ({"chat", "mcp"} & set(channels)):
        problems.append("FACTORY_CHANNELS has no way to ask the factory for work")
    if not s.get("FACTORY_INTAKE_ENABLED", True):
        return _row("warn", "Intake is paused: no new work starts. Waiting decisions and recovery still work.",
                    "Set FACTORY_INTAKE_ENABLED: true in hub.settings.yaml and run hubzoid hub configure . --apply.",
                    card=_card(results, "New work is paused"))
    if problems:
        return _row("fail", "; ".join(problems) + ".", "Fix hub.settings.yaml, then hubzoid hub configure . --check.",
                    card=_card(results, "Settings need a fix"))
    approval = "on" if s.get("FACTORY_REQUIRE_PLAN_APPROVAL", True) else "off"
    return _row("ok", f"{s.get('FACTORY_REPO')}: label {s.get('FACTORY_LABEL')!r}, branches "
                      f"{s.get('FACTORY_BRANCH_PREFIX')}*, {s.get('FACTORY_REVIEW_CYCLES')} review cycles, "
                      f"{s.get('FACTORY_CI_ATTEMPTS')} CI attempts, plan approval {approval}.",
                card=_card(results, f"Plan approval {approval}. A person merges each one."))


def github(context) -> dict:
    """The GitHub connection exists, is enabled, covers FACTORY_REPO and
    routes its triggers to the factory."""
    hub_dir = _hub(context)
    s = context["settings"]
    if _is_local(s.get("FACTORY_REPO")):
        return _local_repository(hub_dir, s["FACTORY_REPO"])
    cid = s.get("FACTORY_GITHUB_CONNECTION") or "github"
    name = str(s.get("FACTORY_REPO") or "")
    try:
        from hubzoid.channels import config

        conn = config.active(hub_dir, cid)
    except Exception:  # noqa: BLE001
        return _row("fail", f"The GitHub connection {cid!r} is not applied.",
                    f"Connect it: hubzoid channels github connect . {cid} --owner <org> --owner-type organization "
                    f"--name <app-name> --open (a hosted hub), or hubzoid channels github connect . {cid} --mode pat "
                    f"--repository {s.get('FACTORY_REPO')} (a laptop). See SETUP.md, step 5.",
                    card=_card(name, "GitHub not connected"))
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
        notes.append("custom trigger routes differ from the sample defaults: " + json.dumps(wrong)
                     + "; caller route ceilings still apply")
    if not conn.config.enabled:
        notes.append("paused (enabled: false), so GitHub events are recorded but start nothing")
    if cfg.mode == "pat":
        notes.append("PAT mode does not provide event delivery: use manual intake unless verified public "
                     "forwarding is configured")
        notes.append("local token mode: replies use your own GitHub account, and pushes use your whole personal "
                     "token (not narrowed to one repository, so use a fine-grained token limited to it)")
    if not getattr(cfg, "webhook_secret_ref", None):
        notes.append("no webhook secret, so GitHub deliveries are refused and work starts only by manual intake "
                     "(hubzoid channels github intake)")
        if not (s.get("FACTORY_BOT_NAME") or getattr(cfg, "bot_name", None)):
            notes.append("token mode needs FACTORY_BOT_NAME (or bot_name in the channel file) for mentions")
    if problems:
        return _row("fail", f"GitHub connection {cid}: " + "; ".join(problems) + ".",
                    f"Edit channels/{cid}.yaml and apply it with hubzoid channels apply . --file channels/{cid}.yaml "
                    "--expected-revision <current>.", card=_card(name, "GitHub connected, needs a change"))
    if notes:
        state = ", paused" if not conn.config.enabled else ", token mode" if cfg.mode == "pat" else ""
        return _row("warn", f"GitHub connection {cid}: " + "; ".join(notes) + ".",
                    f"hubzoid channels doctor . {cid}", card=_card(name, f"GitHub connected{state}"))
    return _row("ok", f"GitHub connection {cid} covers {want} and routes label, mention, CI and new pull requests to "
                      "the factory.", card=_card(name, "GitHub connected"))


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
    """The sandbox profile is valid and the SDK's sandbox doctor passes
    (config, provider, runtime, prepared image). Hubzoid never falls back to
    the host shell."""
    hub_dir = _hub(context)
    profile = context["settings"].get("FACTORY_SANDBOX_PROFILE")
    try:
        from hubzoid.sandbox import config as sandbox_config

        sandbox_config.check_profile(hub_dir, sandbox_config.load_profile(hub_dir, profile))
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"Sandbox profile {profile!r}: {getattr(exc, 'message', exc)}",
                    f"Fix sandboxes/{profile}.yaml, then hubzoid sandbox profiles validate .",
                    card=_card("Build setup needs a fix", BUILDS))
    try:
        from hubzoid.sandbox import service as sandbox_service

        report = sandbox_service.doctor(hub_dir)
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"The sandbox doctor could not run: {getattr(exc, 'message', exc)}",
                    "hubzoid sandbox doctor .", card=_card("Could not check Docker", BUILDS))
    checks = report.get("checks") or []
    docker = [c for c in checks if str(c.get("id", "")).startswith("provider:")]
    up = bool(docker) and all(c.get("status") == "pass" for c in docker)
    line = "Docker running" if up else "Docker not running" if docker else "Sandboxes are off"
    failed = [c for c in checks if c.get("status") == "fail"]
    if failed:
        said = " ".join(dict.fromkeys(c["summary"] for c in failed))         # one engine error can fail two checks
        return _row("fail", said + " The analyst, implementer and reviewer cannot run.",
                    failed[0].get("recovery_action") or "hubzoid sandbox doctor .",
                    card=_card(line, "The build setup needs a fix" if up else BUILDS))
    warned = [c for c in checks if c.get("status") == "warn"]
    if warned:
        return _row("warn", " ".join(dict.fromkeys(c["summary"] for c in warned)),
                    warned[0].get("recovery_action") or f"hubzoid sandbox profiles prepare . {profile}",
                    card=_card(line, "Build image not prepared yet"))
    found = " ".join(c["summary"] for c in docker)
    return _row("ok", f"Sandbox profile {profile} is valid and prepared. {found} Agent commands run offline after "
                      "setup.".replace("  ", " "), card=_card(line, BUILDS))


def write_modes(context) -> dict:
    """Metadata updates wait for the requester; draft status and merge are human-only."""
    hub_dir = _hub(context)
    try:
        from hubzoid.work_items import config

        cfg = config.load(hub_dir)
    except Exception as exc:  # noqa: BLE001
        return _row("fail", f"work-items.yaml: {getattr(exc, 'message', exc)}", "Fix the line shown.")
    mode = cfg.write_modes.get("github.pr_update", "off")
    if mode != "approve":
        return _row("warn", f"github.pr_update is {mode!r}: supported metadata edits cannot run after approval.", "Set github.pr_update: approve in work-items.yaml.")
    return _row("ok", "Pull request metadata updates wait for exact approval. A person alone marks drafts ready and merges in GitHub.")


def _local_repository(hub_dir: Path, value: str) -> dict:
    """Local repository mode needs no GitHub: FACTORY_REPO is a Git folder
    with commits, on a branch."""
    _workflow_code(hub_dir)
    try:
        from software_factory import local

        repo = local.repo(value, hub_dir=hub_dir)
    except Exception as exc:  # noqa: BLE001 - the row says what to do
        return _row("fail", getattr(exc, "message", None) or str(exc),
                    "Set FACTORY_REPO to the top folder of a Git repository outside the hub, with at least one "
                    "commit on a branch.", card=_unusable(value, exc))
    return _row("ok", f"Local repository {repo.local_path}, starting from the branch {repo.default_branch}. "
                      "GitHub is not needed: each result is a reviewed branch in that folder.",
                card=_card(local.shown(repo.local_path), _working_tree(local, repo), path=True))


def _unusable(value: str, exc: Exception) -> dict | None:
    """The card for a folder the factory can't use: the folder, and why in one sentence."""
    try:
        from software_factory import local
    except Exception:  # noqa: BLE001
        return None
    where = str(local.folder(value))
    reason = (getattr(exc, "message", None) or str(exc)).split(". ")[0].rstrip(".") + "."
    if reason.startswith(where):
        reason = "The folder" + reason[len(where):]
    return _card(local.shown(where), local.shown(reason), path=True)


def _working_tree(local, repo) -> str:
    """The branch and how many files are uncommitted, from one `git status`
    (through the factory's own Git call: no hooks, no filesystem monitor) that
    takes no lock, so it never gets in the way of the person's own Git."""
    out = local._text(Path(repo.local_path), "--no-optional-locks", "status", "--porcelain")
    if out is None:
        return f"Branch {repo.default_branch}"
    count = len([line for line in out.splitlines() if line.strip()])
    if not count:
        return f"Branch {repo.default_branch}, clean"
    return f"Branch {repo.default_branch}, {count} uncommitted file{'s' if count != 1 else ''}"


def channels(context) -> dict:
    hub_dir = _hub(context)
    s = context["settings"]
    rows = []
    listed = list(s.get("FACTORY_CHANNELS") or [])
    in_folder = _is_local(s.get("FACTORY_REPO"))
    used = [CHANNEL_NAMES.get(c, c) for c in listed if not (in_folder and c == "github")]
    asked = _and(used) if used else "No channels"
    try:
        from hubzoid.channels import config
    except Exception:  # noqa: BLE001
        return _row("warn", "Channels are not available in this Hubzoid install.")
    paused = []
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
        elif not conn.config.enabled:
            paused.append(f"{name} ({cid})")
    if rows:
        return _row("fail", "; ".join(rows) + ".", "Apply the channel file (see channels/*.yaml.example).",
                    card=_card(asked, "; ".join(rows)))
    if paused:
        return _row("warn", f"Paused, so its requests start no work: {', '.join(paused)}. The example files ship "
                            "paused.", "Resume each after doctor passes: hubzoid channels resume . <id> "
                                       "--expected-revision <rev>.", card=_card(asked, "Paused: " + ", ".join(paused)))
    enabled = ", ".join(s.get("FACTORY_CHANNELS") or [])
    if in_folder:
        card = _card(asked, "GitHub isn't used with a local folder")
    else:
        label = s.get("FACTORY_LABEL") or "factory"
        card = _card(asked, f"GitHub issues labelled {label} start work" if "github" in listed else None)
    if in_folder and "github" in listed:
        return _row("ok", f"Requests come from {enabled}. The github channel is not used while FACTORY_REPO is a "
                          "folder on this computer: ask in chat or through MCP.",
                    "To tidy it, set FACTORY_CHANNELS to [chat, mcp].", card=card)
    return _row("ok", f"Requests come from {enabled}. Other trackers are not built in: a chat request can pull an "
                      "issue in through that tracker's MCP server when one is connected.", card=card)


def runtime(context) -> dict:
    """Check the installed runtime binary; authentication and hosting are the operator's to confirm."""
    found = [name for name in ("claude", "codex") if shutil.which(name)]
    schedules = os.environ.get("HUBZOID_SCHEDULES")
    env_file = _hub(context) / ".env"
    if env_file.is_file() and "HUBZOID_SCHEDULES=1" in env_file.read_text(encoding="utf-8", errors="ignore"):
        schedules = "1"
    on = schedules in ("1", "true", "yes")
    problems = []
    if not found:
        problems.append("neither Claude Code nor Codex is installed")
    if not on:
        problems.append("HUBZOID_SCHEDULES=1 is not set, so `hubzoid run` will not run factory work")
    if not found:
        detail = "Claude Code or Codex not installed"
    elif not on:
        detail = "Requests wait until it is turned on"
    else:
        detail = _and([{"claude": "Claude Code", "codex": "Codex"}[n] for n in found]) + " installed"
    card = _card("Work runs in the background" if on else "Background work is off", detail)
    if problems:
        return _row("warn", "; ".join(problems) + ".", "Install and sign in to Claude Code or Codex, and put "
                    "HUBZOID_SCHEDULES=1 in the hub's .env.", card=card)
    return _row("ok", f"Installed runtime: {', '.join(found)}. Work items run under hubzoid run.", card=card)


def brain(context) -> dict:
    hub_dir = _hub(context)
    folder = hub_dir / "knowledge" / "factory-brain"
    big = [p.name for p in folder.glob("*.md") if len(p.read_text(encoding="utf-8")) > 40_000]
    if big:
        return _row("warn", f"Factory brain files over 40,000 characters: {', '.join(big)}.",
                    "Curate them: keep durable repository facts only.")
    count = len([p for p in folder.glob("*.md") if p.name != "README.md"])
    return _row("ok", f"{count} factory brain file(s). Changes go through reviewed hub changes.")
