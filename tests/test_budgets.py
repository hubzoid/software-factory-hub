"""The shipped spending limits: on by default, and usable with either login."""
from pathlib import Path

from hubzoid import budgets

HUB = Path(__file__).resolve().parents[1]


def test_limits_are_on_by_default():
    cfg = budgets.load(HUB)
    assert cfg.present
    assert cfg.limits["run"]["max_turns"] and cfg.limits["run"]["max_output_tokens"]
    assert cfg.limits["work_item"]["max_output_tokens"]


def test_no_dollar_limit_so_a_codex_login_is_not_refused():
    # A dollar limit refuses every unpriced model (`unpriced_model`), and a Codex
    # login reports no cost. The dollar lines ship commented out for that reason.
    assert not budgets.priced("codex-local")
    cfg = budgets.load(HUB)
    assert not any("max_cost_usd" in scope for scope in cfg.limits.values())
