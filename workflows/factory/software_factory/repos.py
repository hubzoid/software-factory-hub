"""The repositories this factory works on, and which one a work item uses.

`FACTORY_REPO` names one repository, `FACTORY_REPOS` several (never both).
Each entry is `owner/name`, or `owner/name@branch` to build on, and open pull
requests into, that branch instead of the repository's GitHub default. Cyrus
keeps a `baseBranch` per repository and routes an issue to a repository by its
label (`docs/CONFIG_FILE.md`, `routingLabels`); this follows the same idea with
a safe default branch.

A work item gets exactly one repository before anything is read. With one
repository configured that is always it. With several, a GitHub event names its
own, a ClickUp task names one by a tag equal to the repository's short name or
`owner/name`, and chat, MCP and the API pass `repo`. Anything else is asked,
never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
MAX_REPOS = 50


class RepoSettingError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    full_name: str
    base_branch: str | None = None

    @property
    def short(self) -> str:
        return self.full_name.split("/", 1)[1].lower()

    def names(self) -> set[str]:
        return {self.short, self.full_name.lower()}

    def to_json(self) -> dict:
        return {"full_name": self.full_name, "base_branch": self.base_branch}


def valid_branch(name: str) -> bool:
    """Git's ref-name rules (git check-ref-format), for a branch name."""
    if not name or len(name) > 200 or name.startswith(("-", "/")) or name.endswith((".", "/", ".lock")):
        return False
    if ".." in name or "//" in name or "@{" in name or name == "@":
        return False
    if any(ord(ch) < 32 or ch in " ~^:?*[\\\x7f" for ch in name):
        return False
    return all(part and not part.startswith(".") for part in name.split("/"))


def parse(text: str) -> Entry:
    raw = (text or "").strip()
    name, _, branch = raw.partition("@")
    if not NAME_RE.match(name):
        raise RepoSettingError(f"{raw!r} is not owner/name or owner/name@branch.")
    if _ and not valid_branch(branch):
        raise RepoSettingError(f"{branch!r} in {raw!r} is not a valid branch name.")
    return Entry(name, branch or None)


def entries(settings: dict) -> list[Entry]:
    """The configured repositories, in order. Local folder mode has none here."""
    from . import local

    one = (settings.get("FACTORY_REPO") or "").strip()
    many = [s for s in (settings.get("FACTORY_REPOS") or []) if str(s).strip()]
    if one and many:
        raise RepoSettingError("Set FACTORY_REPO for one repository or FACTORY_REPOS for several, not both.")
    if one and local.is_local(one):
        return []
    out = [parse(one)] if one else [parse(s) for s in many]
    if len(out) > MAX_REPOS:
        raise RepoSettingError(f"FACTORY_REPOS lists {len(out)} repositories. The most is {MAX_REPOS}.")
    seen: dict[str, str] = {}
    for e in out:
        for n in (e.short, e.full_name.lower()):
            if n in seen and seen[n] != e.full_name:
                raise RepoSettingError(f"{seen[n]} and {e.full_name} share the name {n!r}. Repository short "
                                       "names must be unique so a tag or reply picks exactly one.")
            seen[n] = e.full_name
    return out


def matching(words, choices: list[Entry]) -> list[Entry]:
    """The repositories named by these tags or words (case is ignored)."""
    wanted = {str(w).strip().lower() for w in words or [] if str(w).strip()}
    return [e for e in choices if e.names() & wanted]


def from_answer(text: str, choices: list[Entry]) -> list[Entry]:
    """The repositories a free-text reply names, as whole words."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9._/-]*", text or "")
    return matching([w.rstrip(".,") for w in words], choices)


def find(name: str, choices: list[Entry]) -> Entry | None:
    got = matching([name], choices)
    return got[0] if len(got) == 1 else None
