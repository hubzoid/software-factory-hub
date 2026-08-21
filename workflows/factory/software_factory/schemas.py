"""The five station results and the factory record, as closed schemas.

Ported from Foreman's ``agent/lib/stations/schemas.ts`` (MIT, Vercel), field
for field, with three Hubzoid changes:

* handoffs replace artifacts, so ``artifact_id`` is ``handoff_id``;
* the implementer never pushes. It commits in its sandbox and reports
  ``committed`` and ``head_commit``; the workflow publishes the exported patch
  and records the pushed SHA itself, so a station cannot claim a push;
* the reviewer must report ``reviewed_sha``, the commit it actually reviewed.

The JSON files in ``agents/<station>/schemas/result.json`` are generated from
these models (``python -m software_factory.schemas --write``), and a test
keeps them identical.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- classifier --------------------------------------------------------------------------

class Classification(_Closed):
    type: Literal["bug", "feature", "refactor", "question", "chore", "security"] = Field(
        description="The kind of work item.")
    priority: Literal["critical", "high", "medium", "low"] = Field(description="How urgent the work is.")
    complexity: Literal["trivial", "small", "medium", "large"] = Field(description="How big the change looks.")
    affected_area: str = Field(description="Best guess at the component, service or layer involved, for example "
                                           "'frontend/auth', 'API', 'CI pipeline' or 'unknown'.")
    actionable: bool = Field(description="Whether the request has enough information to act on.")
    needs_clarification: bool = Field(description="True when the request is ambiguous, contradictory or missing "
                                                  "essentials. The questions go in questions.")
    questions: list[str] = Field(description="Specific clarifying questions. Empty unless needs_clarification "
                                             "is true.")
    summary: str = Field(description="One-sentence restatement of the work item.")


# -- researcher --------------------------------------------------------------------------

class Source(_Closed):
    url: str = Field(description="The URL as visited.")
    title: str = Field(description="The page title or publication name.")


class Finding(_Closed):
    claim: str = Field(description="One specific factual claim.")
    sources: list[Source] = Field(min_length=1, description="At least one real source that was read. Never "
                                                            "empty, never invented.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high: several strong independent sources. medium: one solid source. low: weak or thin.")
    notes: str = Field(description="Caveats: date sensitivity, scope limits, disagreements between sources.")


class Research(_Closed):
    summary: str = Field(description="A one to three sentence synthesis to read first.")
    findings: list[Finding] = Field(description="One entry per verified claim.")
    gaps: list[str] = Field(description="What could not be found or verified.")
    handoff_id: str | None = Field(description="The research-notes handoff id, or null.")


# -- analyst -----------------------------------------------------------------------------

class Analysis(_Closed):
    problem_statement: str = Field(description="What is actually wrong or wanted, as a precise engineering "
                                               "problem.")
    approach: str = Field(description="The chosen strategy, plus the main rejected alternative and why.")
    plan: list[str] = Field(min_length=1, description="Ordered concrete steps, each independently verifiable. "
                                                     "The smallest change that fully solves the problem.")
    affected_surface: list[str] = Field(description="Files, modules, interfaces or systems touched. Public "
                                                    "contracts called out.")
    risks: list[str] = Field(description="What could break, edge cases, compatibility concerns, and mitigations.")
    acceptance_criteria: list[str] = Field(min_length=1, description="Objective, testable criteria the reviewer "
                                                                    "checks one by one, verbatim.")
    test_strategy: str = Field(description="What to test and how, grounded in the repository's own setup.")
    assumptions: list[str] = Field(description="Assumptions the plan rests on.")
    open_questions: list[str] = Field(description="External facts not resolvable from the repository.")
    handoff_id: str | None = Field(description="The analysis handoff id, or null.")


# -- implementer -------------------------------------------------------------------------

class FileChange(_Closed):
    path: str = Field(description="The file path.")
    change: str = Field(description="What changed in this file and why.")


class Check(_Closed):
    command: str = Field(description="The command as run.")
    result: str = Field(description="Pass or fail, and the relevant output.")


class Implementation(_Closed):
    branch: str = Field(description="The local branch the commits are on.")
    base: str = Field(description="The branch the work is based on, normally the default branch.")
    committed: bool = Field(description="True when the change is committed and ready for the factory to "
                                        "publish. If false, the reason is in known_limitations.")
    head_commit: str | None = Field(description="The output of git rev-parse HEAD after the last commit, or "
                                                "null when nothing was committed.")
    change_summary: list[FileChange] = Field(description="One entry per changed file.")
    verification: list[Check] = Field(description="Every check that ran, exactly as run, with its result.")
    deviations: list[str] = Field(description="Departures from the plan, with reasons. Empty when the plan "
                                              "held.")
    known_limitations: list[str] = Field(description="Anything the reviewer should look at closely.")


# -- reviewer ----------------------------------------------------------------------------

class CriterionResult(_Closed):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    criterion: str = Field(description="The acceptance criterion, verbatim.")
    passed: bool = Field(alias="pass", description="Whether it passes.")
    evidence: str = Field(description="What in the diff or the verification output shows it passing or "
                                      "failing.")


class Review(_Closed):
    verdict: Literal["approve", "request_changes", "reject"] = Field(description="The verdict.")
    reviewed_sha: str = Field(description="The output of git rev-parse HEAD in the checkout you reviewed.")
    criteria_results: list[CriterionResult] = Field(description="One entry per acceptance criterion.")
    blocking_findings: list[str] = Field(description="Each names where, what is wrong and why it matters.")
    suggestions: list[str] = Field(description="Advisory, non-blocking notes.")
    summary: str = Field(description="One paragraph on the verdict and what drove it.")


STATIONS: dict[str, type[_Closed]] = {
    "classifier": Classification,
    "researcher": Research,
    "analyst": Analysis,
    "implementer": Implementation,
    "reviewer": Review,
}


def json_schema(model: type[BaseModel]) -> dict:
    """A self-contained JSON Schema (no $ref), closed at every level, which
    both engines' structured output accept."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(dict(defs[node["$ref"].rsplit("/", 1)[1]]))
            out = {k: inline(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out["required"] = list(out.get("properties", {}))
            if "anyOf" in out and all(set(o) <= {"type"} for o in out["anyOf"]):
                out["type"] = [o["type"] for o in out.pop("anyOf")]
            return out
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(schema)


def write(hub_dir: Path) -> list[Path]:
    written = []
    for name, model in STATIONS.items():
        target = hub_dir / "agents" / name / "schemas" / "result.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(json_schema(model), indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written


if __name__ == "__main__":  # pragma: no cover - a maintainer's command
    import sys

    root = Path(__file__).resolve().parents[3]
    if "--write" in sys.argv:
        for path in write(root):
            print(path.relative_to(root))
