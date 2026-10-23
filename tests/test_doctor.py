"""The factory's doctor rows say what is true of the connection (found in the
live run: a token-mode connection with a webhook secret was reported as
unverified)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from . import conftest as h

ROOT = Path(__file__).resolve().parents[1]


def _checks():
    spec = importlib.util.spec_from_file_location("factory_doctor_checks", ROOT / "doctor" / "checks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _context(hub_dir) -> dict:
    return {"hub_dir": str(hub_dir), "settings": {
        "FACTORY_GITHUB_CONNECTION": "github", "FACTORY_REPO": h.FULL, "FACTORY_LABEL": "factory",
        "FACTORY_BOT_NAME": "", "FACTORY_CHANNELS": ["chat", "mcp", "github"]}}


def _token_mode(hub_dir, conn, *, webhook: bool) -> None:
    from hubzoid.channels import config
    from hubzoid.secretstore import store as ss

    ss.put(hub_dir, scope="channel", target="factory/github", name="token", value="ghp_" + "x" * 36, actor="test")
    cfg = {"version": 1, "id": "github", "provider": "github", "enabled": True, "workflow": "factory",
           "run_as": "workflow", "allowed_groups": [], "progress": True,
           "provider_config": {"mode": "pat", "owner": {"type": "user", "login": "factory-demo", "id": 4242},
                               "repositories": [{"id": h.REPO_ID, "full_name": h.FULL}],
                               "token_ref": "secret:channel/factory/github/token", "bot_name": "factory-demo",
                               "rules": {"mentions": True, "label": "factory", "pr_opened": True, "ci_failure": True,
                                         "routes": dict(_checks().WANT_ROUTES)}}}
    if webhook:
        cfg["provider_config"]["webhook_secret_ref"] = "secret:channel/factory/github/webhook-secret"
    v = config.load_text(hub_dir, config.render(cfg))
    assert v.valid, v.errors
    config.apply(hub_dir, v.data, expected_revision=conn.revision, actor="test")


def test_app_mode_with_its_webhook_secret_is_ok(factory_hub, conn):
    row = _checks().github(_context(factory_hub))
    assert row["status"] == "ok", row


@pytest.mark.slow
def test_narrowed_factory_route_is_reported_without_restoring_sample_defaults(factory_hub, conn):
    from hubzoid.channels import config

    active = config.export(factory_hub, "github")["config"]
    active["provider_config"]["rules"]["routes"]["label"] = "plan"
    active["provider_config"]["rules"]["pr_opened"] = False
    config.apply(factory_hub, active, expected_revision=conn.revision, actor="test-admin")
    row = _checks().github(_context(factory_hub))
    assert row["status"] == "warn" and "custom trigger routes" in row["summary"]
    assert config.export(factory_hub, "github")["config"]["provider_config"]["rules"]["pr_opened"] is False


@pytest.mark.parametrize("webhook", [True, False])
def test_token_mode_says_whether_deliveries_are_verified(factory_hub, conn, webhook):
    _token_mode(factory_hub, conn, webhook=webhook)
    row = _checks().github(_context(factory_hub))
    assert row["status"] == "warn" and "local token mode" in row["summary"]
    assert ("no webhook secret" in row["summary"]) is (not webhook)
    assert "not verified" not in row["summary"]


def test_channels_row_names_no_unsupported_tracker(factory_hub, conn):
    row = _checks().channels(_context(factory_hub))
    assert row["status"] == "ok" and "ClickUp" not in row["summary"]


@pytest.mark.parametrize("report,status,words", [
    ({"valid": False, "checks": [{"id": "provider:docker", "status": "fail", "summary": "Docker is not reachable.",
                                  "recovery_action": "Start Docker, then run doctor again."},
                                 {"id": "profile:factory", "status": "fail", "summary": "Docker is not reachable.",
                                  "recovery_action": "Correct the profile and validate again."}]},
     "fail", "Docker is not reachable. The analyst"),
    ({"valid": True, "checks": [{"id": "provider:docker", "status": "pass", "summary": "Docker 27 reachable."},
                                {"id": "profile:factory", "status": "warn", "summary": "Its image is not prepared.",
                                 "recovery_action": "Run `hubzoid sandbox profiles prepare . factory`."}]},
     "warn", "not prepared"),
    ({"valid": True, "checks": [{"id": "provider:docker", "status": "pass", "summary": "Docker 27 reachable."},
                                {"id": "profile:factory", "status": "pass", "summary": "valid."}]},
     "ok", "Docker 27 reachable."),
])
def test_sandbox_row_follows_the_sdk_sandbox_doctor(factory_hub, monkeypatch, report, status, words):
    from hubzoid.sandbox import config as sandbox_config
    from hubzoid.sandbox import service as sandbox_service

    monkeypatch.setattr(sandbox_config, "check_profile", lambda *a, **k: None)
    monkeypatch.setattr(sandbox_service, "doctor", lambda hub_dir: report)
    ctx = _context(factory_hub)
    ctx["settings"]["FACTORY_SANDBOX_PROFILE"] = "factory"
    row = _checks().sandbox(ctx)
    assert row["status"] == status and words in row["summary"], row
    if status == "fail":
        assert row["recovery"] == "Start Docker, then run doctor again."


def test_a_paused_linear_connection_is_a_warning(factory_hub, conn):
    """The example files ship paused; doctor says so instead of passing."""
    import yaml
    from hubzoid.channels import config

    data = yaml.safe_load((ROOT / "channels" / "linear.yaml.example").read_text())
    for key in ("client_secret_ref", "webhook_secret_ref"):
        data["provider_config"][key] = data["provider_config"][key].replace("software-factory", factory_hub.name)
    config.apply(factory_hub, data, expected_revision="absent", actor="test-admin")
    ctx = _context(factory_hub)
    ctx["settings"].update(FACTORY_CHANNELS=["chat", "github", "linear"], FACTORY_LINEAR_CONNECTION="linear")
    row = _checks().channels(ctx)
    assert row["status"] == "warn" and "Paused" in row["summary"] and "linear (linear)" in row["summary"]
