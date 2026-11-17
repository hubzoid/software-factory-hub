"""The plan as one clean HTML page (FACTORY_PLAN_FORMAT: html).

Markdown is rendered with raw HTML turned off: the plan quotes the request,
which is untrusted, so any HTML in it shows as text and never runs. No
scripts, no external fonts or styles: the page opens the same from a ClickUp
attachment, an email or a laptop.
"""
from __future__ import annotations

import html

import markdown

STYLE = """
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1f2328;
max-width:760px;margin:40px auto;padding:0 20px;background:#fff}
h1{font-size:1.6em;margin:0 0 .4em}h2{font-size:1.2em;margin:1.6em 0 .5em;border-bottom:1px solid #d0d7de;
padding-bottom:.25em}h3{font-size:1.05em}code{background:#f6f8fa;padding:.1em .3em;border-radius:4px;
font-size:.9em}pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto}pre code{padding:0}
table{border-collapse:collapse}td,th{border:1px solid #d0d7de;padding:4px 8px}blockquote{color:#59636e;
border-left:3px solid #d0d7de;margin:0;padding-left:1em}a{color:#0969da}
@media (prefers-color-scheme:dark){body{background:#0d1117;color:#e6edf3}code,pre{background:#161b22}
h2,td,th{border-color:#30363d}a{color:#4493f8}}
""".strip()


def render(title: str, text: str) -> str:
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    body = md.convert(text)
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>\n<body>\n{body}\n</body></html>\n")
