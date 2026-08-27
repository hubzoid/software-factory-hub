"""Hidden content out of untrusted text before a model reads it.

Issue bodies, comments and pull request text can carry instructions people
never see on GitHub: HTML comments, zero-width and invisible characters,
bidirectional overrides. Following claude-code-action's sanitizer
(``src/github/utils/sanitizer.ts``, MIT), the factory removes them and says
how much it removed, so a station reads what a person would read.
"""
from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\u00ad]")


def clean(text):
    """Text with hidden parts removed, and a note when anything was."""
    if not isinstance(text, str) or not text:
        return text
    comments = len(_COMMENT.findall(text))
    out = _COMMENT.sub("", text)
    invisible = len(_INVISIBLE.findall(out))
    out = _INVISIBLE.sub("", out)
    if comments or invisible:
        out += (f"\n\n[Hidden content removed before reading: {comments} HTML comment(s), "
                f"{invisible} invisible character(s).]")
    return out


def deep(value):
    """Clean every string in a JSON-like value."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [deep(v) for v in value]
    if isinstance(value, dict):
        return {k: deep(v) for k, v in value.items()}
    return value
