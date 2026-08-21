"""Progress people can see while the factory works.

On a channel (a GitHub issue, a Slack thread, a Linear session) a short note
goes to the work's own thread after each intermediate station, keyed so a
replay never posts twice. The last station's note is the wrap-up itself
(Foreman's rule). Chat, MCP and API work has no thread: progress is kept in
the factory's record, which the chat tools and the Console read.
"""
from __future__ import annotations

import time

from hubzoid import hub

RECORD = "factory_v1:item:{id}"


def thread_available() -> bool:
    try:
        hub.thread  # noqa: B018 - raises for work that has no channel thread
    except Exception:  # noqa: BLE001
        return False
    return True


def record(**fields) -> dict:
    """Merge fields into this work item's factory record (stage, outcome,
    links). Writes are idempotent, so a replay leaves the same record."""
    key = RECORD.format(id=hub.work_item.id)
    current = hub.shared_state.get(key) or {}
    current = dict(current, **fields, updated=time.time())
    hub.shared_state[key] = current
    return current


def stage(name: str, note: str, *, post: bool = True) -> None:
    """A station finished: record it, and post a short note on the thread."""
    entry = hub.shared_state.get(RECORD.format(id=hub.work_item.id)) or {}
    stages = list(entry.get("stages") or [])
    if not any(s.get("stage") == name and s.get("note") == note for s in stages):
        stages.append({"stage": name, "note": note, "at": time.time()})
    record(stage=name, stages=stages)
    if post and thread_available():
        hub.thread.post(note, key=f"progress:{name}:{len(stages)}", kind="progress")


def reply(text: str, *, key: str, kind: str = "result") -> bool:
    """Post to the work's own thread when it has one. Returns whether it did."""
    if not thread_available():
        return False
    hub.thread.post(text, key=key, kind=kind)
    return True


def read(item_id: str) -> dict:
    return hub.shared_state.get(RECORD.format(id=item_id)) or {}
