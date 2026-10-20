"""Station results: the upstream template's closed schemas, with the Hubzoid additions."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from software_factory import schemas

HUB = Path(__file__).resolve().parents[1]
UPSTREAM_FIELDS = {
    "classifier": {"type", "priority", "complexity", "affected_area", "actionable", "needs_clarification",
                   "questions", "summary"},
    "researcher": {"summary", "findings", "gaps", "handoff_id"},
    "analyst": {"problem_statement", "approach", "plan", "affected_surface", "risks", "acceptance_criteria",
                "test_strategy", "assumptions", "open_questions", "handoff_id"},
    "implementer": {"branch", "base", "committed", "head_commit", "change_summary", "verification", "deviations",
                    "known_limitations"},
    "reviewer": {"verdict", "reviewed_sha", "criteria_results", "blocking_findings", "suggestions", "summary"},
}


@pytest.mark.parametrize("name", sorted(schemas.STATIONS))
def test_files_match_the_models(name):
    on_disk = json.loads((HUB / "agents" / name / "schemas" / "result.json").read_text())
    assert on_disk == schemas.json_schema(schemas.STATIONS[name])
    assert set(on_disk["properties"]) == UPSTREAM_FIELDS[name]


def _closed(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        for v in node.values():
            _closed(v)
    elif isinstance(node, list):
        for v in node:
            _closed(v)


@pytest.mark.parametrize("name", sorted(schemas.STATIONS))
def test_closed_at_every_level(name):
    _closed(schemas.json_schema(schemas.STATIONS[name]))
    assert "$ref" not in json.dumps(schemas.json_schema(schemas.STATIONS[name]))


def test_schema_false_push_has_no_sha():
    impl = schemas.Implementation(branch="x", base="main", committed=False, head_commit=None, change_summary=[],
                                  verification=[], deviations=[], known_limitations=["blocked"])
    assert impl.committed is False and impl.head_commit is None
    assert "pushed" not in schemas.Implementation.model_fields       # a station can never claim a push


def test_reviewer_must_name_the_commit_and_judge_each_criterion():
    with pytest.raises(ValidationError):
        schemas.Review.model_validate({"verdict": "approve", "criteria_results": [], "blocking_findings": [],
                                       "suggestions": [], "summary": "ok"})
    r = schemas.Review.model_validate({"verdict": "approve", "reviewed_sha": "abc1234", "criteria_results": [
        {"criterion": "c", "pass": True, "evidence": "e"}], "blocking_findings": [], "suggestions": [],
        "summary": "ok"})
    assert r.criteria_results[0].passed is True


def test_research_findings_need_a_real_source():
    with pytest.raises(ValidationError):
        schemas.Research.model_validate({"summary": "s", "findings": [{"claim": "c", "sources": [],
                                                                       "confidence": "high", "notes": ""}],
                                         "gaps": [], "handoff_id": None})


def test_extra_fields_are_refused():
    with pytest.raises(ValidationError):
        schemas.Classification.model_validate({"type": "bug", "priority": "low", "complexity": "small",
                                               "affected_area": "x", "actionable": True,
                                               "needs_clarification": False, "questions": [], "summary": "s",
                                               "route": "implement"})
