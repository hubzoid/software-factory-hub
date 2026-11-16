"""The wait for the repository's own checks before the draft pull request:
every page is read, and a check that already failed blocks even while others
still run. No network, no waiting."""
import pytest

from software_factory import ci


class Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 30)


@pytest.fixture
def clock(monkeypatch):
    import time

    c = Clock()
    monkeypatch.setattr(time, "monotonic", c.monotonic)
    monkeypatch.setattr(time, "sleep", c.sleep)
    return c


def pages(monkeypatch, *pages_):
    calls = []

    def read(name, **args):
        calls.append(args)
        n = int(args.get("cursor") or 1) - 1
        return {"data": pages_[n], "next_cursor": str(n + 2) if n + 1 < len(pages_) else None}

    monkeypatch.setattr(ci.github, "read", read)
    return calls


def run(name, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion if status == "completed" else None}


def test_a_failure_on_a_later_page_counts(monkeypatch, clock):
    calls = pages(monkeypatch, [run(f"ok-{i}") for i in range(100)], [run("lint", "failure")])
    out = ci.wait_before_pr(1, "a" * 40, minutes=5)
    assert out["state"] == "failure" and out["failed"] == ["lint"] and len(calls) == 2


def test_a_known_failure_blocks_even_while_another_check_hangs(monkeypatch, clock):
    pages(monkeypatch, [run("tests", "failure"), run("deploy-preview", status="in_progress")])
    out = ci.wait_before_pr(1, "a" * 40, minutes=1)
    assert out["state"] == "failure" and out["failed"] == ["tests"]


def test_only_pending_checks_time_out(monkeypatch, clock):
    pages(monkeypatch, [run("tests", status="queued")])
    assert ci.wait_before_pr(1, "a" * 40, minutes=1)["state"] == "timeout"


def test_no_checks_at_all_is_none(monkeypatch, clock):
    pages(monkeypatch, [])
    assert ci.wait_before_pr(1, "a" * 40, minutes=30)["state"] == "none"


def test_all_green(monkeypatch, clock):
    pages(monkeypatch, [run("tests"), run("lint", "skipped")])
    assert ci.wait_before_pr(1, "a" * 40, minutes=5) == {"state": "success", "failed": [], "checks": 2}
