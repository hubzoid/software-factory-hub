"""Every factory setting validates, with a tested error for each bad value."""
from pathlib import Path

import pytest

from hubzoid.hubs import settings as hub_settings

HUB = Path(__file__).resolve().parents[1]
GOOD = {"FACTORY_REPO": "example-org/factory-sample"}

BAD = [
    ("FACTORY_REPO", "not a repo"),
    ("FACTORY_REPO", "owner/"),
    ("FACTORY_REPO", "-owner/repo"),
    ("FACTORY_LABEL", " leading space"),
    ("FACTORY_LABEL", "x" * 51),
    ("FACTORY_BRANCH_PREFIX", "factory"),
    ("FACTORY_BRANCH_PREFIX", "../evil/"),
    ("FACTORY_BRANCH_PREFIX", "a/b/"),
    ("FACTORY_BOT_NAME", "bad name"),
    ("FACTORY_GITHUB_CONNECTION", "GitHub"),
    ("FACTORY_LINEAR_CONNECTION", "has space"),
    ("FACTORY_SLACK_CONNECTION", "UPPER"),
    ("FACTORY_CHANNELS", ["chat", "clickup"]),
    ("FACTORY_CHANNELS", ["email"]),
    ("FACTORY_INTAKE_ENABLED", "sometimes"),
    ("FACTORY_REQUIRE_PLAN_APPROVAL", "maybe"),
    ("FACTORY_REVIEW_CYCLES", 3),
    ("FACTORY_REVIEW_CYCLES", -1),
    ("FACTORY_CI_ATTEMPTS", 5),
    ("FACTORY_SANDBOX_PROFILE", "Bad Profile"),
    ("FACTORY_CONCURRENCY", 0),
    ("FACTORY_CONCURRENCY", 17),
    ("FACTORY_CONCURRENCY", "four"),
]


def problems(values: dict) -> list:
    _, found = hub_settings.validate(HUB, hub_settings.parse_values({"version": 1, "values": values}), env={})
    return found


def test_the_shipped_values_and_defaults_are_valid():
    assert problems(GOOD) == []
    resolved = {r.decl.name: r.value for r in hub_settings.validate(
        HUB, hub_settings.parse_values({"version": 1, "values": GOOD}), env={})[0]}
    assert resolved["FACTORY_LABEL"] == "factory" and resolved["FACTORY_BRANCH_PREFIX"] == "factory/"
    assert resolved["FACTORY_REVIEW_CYCLES"] == 2 and resolved["FACTORY_CI_ATTEMPTS"] == 2
    assert resolved["FACTORY_REQUIRE_PLAN_APPROVAL"] is True and resolved["FACTORY_CONCURRENCY"] == 4
    assert resolved["FACTORY_CHANNELS"] == ["chat", "mcp", "github"]


@pytest.mark.parametrize("key,value", BAD)
def test_each_bad_value_is_refused_with_its_key(key, value):
    found = problems({**GOOD, key: value})
    assert any(p.key == key for p in found), (key, value, [p.public() for p in found])
    assert all(p.message for p in found)


def test_repository_is_required():
    found = problems({})
    assert any(p.key == "FACTORY_REPO" for p in found)


def test_unknown_keys_and_clickup_are_refused():
    assert any(p.code == "setting_unknown" for p in problems({**GOOD, "FACTORY_CLICKUP_CONNECTION": "x"}))
    assert any(p.code == "setting_unknown" for p in problems({**GOOD, "FACTORY_SETUP_COMMAND": "npm ci"}))


def test_every_setting_is_documented():
    names = {d.name for d in hub_settings.declarations(HUB)}
    doc = (HUB / "docs" / "settings.md").read_text()
    for name in names:
        assert name in doc, name
