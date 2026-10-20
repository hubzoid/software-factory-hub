"""Evidence, the pull request body and the wrap-up.

The pull request body follows Foreman's delivery rule
(``agent/instructions.ts:63-69``, MIT, Vercel): the problem, the approach
and why, the acceptance criteria as a checklist with the reviewer's result for
each, the verification commands and results, deviations, and ``Closes #N``
for an issue. Long documents (research notes, analysis) are linked by id,
never pasted. The evidence document binds the plan digest, the base, the
pushed SHA and the reviewed SHA, and goes into the work item as a handoff
and into the hub's output folder.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import Analysis, Implementation, Review

MAX_BODY = 60_000


def plan_markdown(*, title: str, request: str, analysis: Analysis, research_summary: str | None,
                  repository: str, base_branch: str, base_sha: str | None) -> str:
    lines = [f"# Plan: {title}", "", f"Repository: {repository}, base `{base_branch}`"
             + (f" at `{base_sha[:12]}`" if base_sha else ""), "", "## Request", "", request.strip() or "(none)",
             "", "## Problem", "", analysis.problem_statement, "", "## Approach", "", analysis.approach, "",
             "## Steps", ""]
    lines += [f"{i}. {step}" for i, step in enumerate(analysis.plan, 1)]
    lines += ["", "## Acceptance criteria", ""] + [f"- [ ] {c}" for c in analysis.acceptance_criteria]
    if analysis.affected_surface:
        lines += ["", "## Affected surface", ""] + [f"- {s}" for s in analysis.affected_surface]
    if analysis.risks:
        lines += ["", "## Risks", ""] + [f"- {r}" for r in analysis.risks]
    lines += ["", "## Test strategy", "", analysis.test_strategy]
    if analysis.assumptions:
        lines += ["", "## Assumptions", ""] + [f"- {a}" for a in analysis.assumptions]
    if analysis.open_questions:
        lines += ["", "## Open questions", ""] + [f"- {q}" for q in analysis.open_questions]
    if research_summary:
        lines += ["", "## Research", "", research_summary]
    if analysis.handoff_id:
        lines += ["", f"Full analysis: handoff `{analysis.handoff_id}`."]
    return "\n".join(lines).strip() + "\n"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def pr_body(*, analysis: Analysis, implementation: Implementation, review: Review, subject_kind: str,
            subject_number: int | None, evidence_url: str | None, cautions: list[str], pushed_sha: str,
            plan_digest: str | None) -> str:
    results = {r.criterion.strip(): r for r in review.criteria_results}
    lines = ["## Problem", "", analysis.problem_statement, "", "## Approach", "", analysis.approach, "",
             "## Acceptance criteria", ""]
    for c in analysis.acceptance_criteria:
        r = results.get(c.strip())
        mark = "x" if r and r.passed else " "
        lines.append(f"- [{mark}] {c}" + (f" (reviewer: {r.evidence.strip()[:300]})" if r else ""))
    lines += ["", "## Verification", ""]
    if implementation.verification:
        lines += [f"- `{v.command}`: {v.result.strip()[:400]}" for v in implementation.verification]
    else:
        lines.append("- The implementer reported no checks.")
    lines += ["", "## Deviations from the plan", ""]
    lines += [f"- {d}" for d in implementation.deviations] or ["- None."]
    if cautions:
        lines += ["", "## Look carefully", ""] + [f"- {c}" for c in cautions]
    lines += ["", "## Review", "", f"Independent review: **{review.verdict}** at `{review.reviewed_sha[:12]}`. "
              + review.summary.strip()]
    if review.suggestions:
        lines += ["", "Suggestions (not blocking):", ""] + [f"- {s}" for s in review.suggestions]
    lines += ["", "---", "", f"Built by the Software Factory hub. Pushed `{pushed_sha[:12]}`"
              + (f", plan `{plan_digest[7:19]}`" if plan_digest else "") + "."
              + (f" Evidence: {evidence_url}" if evidence_url else "")
              + " This is a draft: a person reviews it, marks it ready and merges."]
    if subject_kind == "github_issue" and subject_number:
        lines += ["", f"Closes #{subject_number}"]
    body = "\n".join(lines)
    return body[:MAX_BODY]


def evidence_markdown(record: dict) -> str:
    """The work's evidence as a readable document."""
    out = [f"# Factory evidence: work {record.get('work_item', '')[:8]}", ""]
    for key, label in (("route", "Route"), ("caller_class", "Caller class"), ("repository", "Repository"),
                       ("base_sha", "Base commit"), ("context_revision", "Approved Hub context revision"), ("plan_digest", "Plan digest"), ("branch", "Branch"),
                       ("pushed_sha", "Pushed commit"), ("reviewed_sha", "Reviewed commit"),
                       ("pr_url", "Draft pull request"), ("outcome", "Outcome"), ("stop_reason", "Stop reason")):
        if record.get(key) not in (None, ""):
            out.append(f"- {label}: {record[key]}")
    for title, key in (("Classification", "classification"), ("Research", "research"), ("Analysis", "analysis"),
                       ("Implementation", "implementation"), ("Review", "review"), ("Patch check", "scan")):
        if record.get(key):
            out += ["", f"## {title}", "", "```json", json.dumps(record[key], indent=2)[:20000], "```"]
    if record.get("reviews"):
        out += ["", "## Review rounds", "", "```json", json.dumps(record["reviews"], indent=2)[:20000], "```"]
    return "\n".join(out) + "\n"


def save(output_dir: Path, record: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evidence.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    target = output_dir / "evidence.md"
    target.write_text(evidence_markdown(record), encoding="utf-8")
    return target
