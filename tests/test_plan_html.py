"""The HTML plan page never runs HTML from the plan's text."""
from software_factory import plan_html


def test_markdown_renders_and_raw_html_shows_as_text():
    page = plan_html.render('Plan: <b>x</b>', "# Plan\n\n1. Fix `a < b`\n\n<script>alert(1)</script>\n\n"
                                              "Click <img src=x onerror=alert(1)> here\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<h1>Plan</h1>" in page and "<ol>" in page and "<table>" in page
    assert "<script>" not in page.split("</head>")[1] and "<img" not in page
    assert "&lt;script&gt;" in page and "<code>a &lt; b</code>" in page
    assert "<title>Plan: &lt;b&gt;x&lt;/b&gt;</title>" in page
