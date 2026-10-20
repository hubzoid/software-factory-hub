"""Builder helpers preserve connection authority and produce source-linked context."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from . import conftest as h

spec = importlib.util.spec_from_file_location("factory_setup", h.HUB_ROOT / "scripts/factory_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_connection_composition_keeps_credentials_scope_and_paused_state():
    original = {"id": "github", "provider": "github", "enabled": False, "agent": "chat",
                "allowed_groups": ["engineering-read"], "provider_config": {
                    "token_ref": "secret:channel/factory/github/token", "repositories": [{"id": 123}],
                    "rules": {"ignore_actors": ["release-bot"], "routes": {"custom": "plan"}}}}
    merged = setup.compose_connection(original, label="build-it")
    assert merged["workflow"] == "factory" and "agent" not in merged
    assert merged["enabled"] is False and merged["allowed_groups"] == original["allowed_groups"]
    assert merged["provider_config"]["token_ref"] == original["provider_config"]["token_ref"]
    assert merged["provider_config"]["rules"]["ignore_actors"] == ["release-bot"]
    assert merged["provider_config"]["rules"]["routes"] == dict(setup.ROUTES, custom="plan")
    assert merged == setup.compose_connection(merged, label="build-it")
    assert original["agent"] == "chat" and "workflow" not in original


def test_existing_factory_connection_keeps_disabled_triggers_and_narrowed_routes():
    original = {"provider": "github", "workflow": "factory", "enabled": False, "provider_config": {
        "rules": {"label": "review-first", "mentions": False, "pr_opened": False, "ci_failure": False,
                  "routes": {"label": "plan", "mention": "answer"}}}}
    merged = setup.compose_connection(original, label="factory")
    rules = merged["provider_config"]["rules"]
    assert rules["label"] == "review-first"
    assert rules["mentions"] is rules["pr_opened"] is rules["ci_failure"] is False
    assert rules["routes"]["label"] == "plan" and rules["routes"]["mention"] == "answer"
    assert "provider_config.rules.pr_opened" not in setup.changed_keys(original, merged)
    assert "provider_config.rules.routes.ci_failure" in setup.changed_keys(original, merged)


def test_connection_candidate_does_not_overwrite_or_activate(factory_hub, conn, capsys):
    from hubzoid.channels import config

    before = (factory_hub / "channels/github.yaml").read_bytes()
    assert setup.main(["--hub", str(factory_hub), "connection"]) == 0
    out = json.loads(capsys.readouterr().out)
    candidate = config.load_file(factory_hub, Path(out["candidate"]))
    assert candidate.valid, candidate.errors
    assert out["expected_revision"] == conn.revision
    assert "changed_keys" in out
    assert (factory_hub / "channels/github.yaml").read_bytes() == before
    assert config.active(factory_hub, "github").revision == conn.revision


def test_connection_candidate_refuses_real_sdk_unapplied_file_edit(factory_hub, conn, capsys):
    from hubzoid.channels import config

    path = factory_hub / "channels/github.yaml"
    edited = path.read_text().replace("pr_opened: true", "pr_opened: false")
    assert edited != path.read_text()
    path.write_text(edited)
    assert config.export(factory_hub, "github")["file_matches"] is False
    assert setup.main(["--hub", str(factory_hub), "connection"]) == 1
    assert "unapplied edits" in json.loads(capsys.readouterr().err)["message"]
    assert path.read_text() == edited and config.active(factory_hub, "github").revision == conn.revision


@pytest.mark.parametrize("command,flags", [
    (["channels", "github", "intake"], ["--url", "--task"]),
    (["channels", "validate"], ["--file"]),
    (["channels", "resume"], ["--expected-revision"]),
    (["hub-changes", "show"], ["change_id"]),
    (["hub-changes", "decide"], ["--decision"]),
    (["work-items", "list"], ["--workflow", "--json"]),
    (["hub", "settings"], ["--json"]),
])
def test_setup_commands_exist_in_the_selected_sdk(command, flags):
    # In-process help only: no provider call, model, daemon or child process.
    from typer.testing import CliRunner
    from hubzoid.cli import app

    result = CliRunner().invoke(app, [*command, "--help"], color=False)
    assert result.exit_code == 0, result.output
    for flag in flags:
        assert flag in result.output, result.output


@pytest.mark.slow
def test_brief_cites_committed_sources_and_rejects_path_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    h.git(root, "init", "-b", "main")
    (root / "README.md").write_text("# Useful project\nRun the tests before changing totals.\n")
    h.git(root, "add", "README.md")
    h.git(root, "commit", "-m", "Source")
    commit = h.git(root, "rev-parse", "HEAD").strip()
    (root / "README.md").write_text("An uncommitted instruction must not be attributed to the source SHA.")
    brief = setup.repository_brief(root, "example-co/widget", ["README.md"], "pytest")
    assert commit in brief and f"blob/{commit}/README.md" in brief
    assert "Run the tests before" in brief and "uncommitted instruction" not in brief
    with pytest.raises(ValueError, match="inside the checkout"):
        setup.repository_brief(root, "example-co/widget", ["../secret.md"], "pytest")
    with pytest.raises(subprocess.CalledProcessError):
        setup.repository_brief(root, "example-co/widget", ["untracked.md"], "pytest")


@pytest.mark.slow
def test_repeated_bootstrap_reuses_pending_change_and_never_activates(factory_hub, conn, remote, capsys):
    from hubzoid import auth
    from hubzoid.access import store_for
    from hubzoid.hub_changes import service

    checkout = remote.root / "bootstrap"
    subprocess.run(["git", "clone", "--quiet", str(remote.bare), str(checkout)], check=True, env=h.GIT_ENV)
    command = ["--hub", str(factory_hub), "context", "--checkout", str(checkout), "--repository", h.FULL,
               "--source", "calc.py", "--test-command", "pytest", "--propose"]
    # Bootstrap must not grant its own owner permission. An administrator's
    # existing SDK grant is necessary, exactly as for the native proposal CLI.
    assert setup.main(command) == 1
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["error"] == "permission_denied"
    store_for(factory_hub).grant(auth.local_owner(factory_hub).email, factory_hub.name, "curator", actor="test-admin")
    assert setup.main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert setup.main(command) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["change"] == first["change"] and second["reused"]
    changed = list(command)
    changed[changed.index("--test-command") + 1] = "pytest -q"
    assert setup.main(changed) == 1
    assert "different content" in json.loads(capsys.readouterr().err)["message"]
    assert service.get(factory_hub, first["change"])["status"] == "pending"
    assert not (factory_hub / "knowledge/factory-brain/example-co-widget.md").exists()
