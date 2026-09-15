"""Deterministic checks for synthetic Interview Coach outputs."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from app.interview import InterviewAnalysis


CASES_PATH = Path(__file__).with_name("interview_cases.json")
VALID_EVIDENCE_LABELS = ("CV:", "LinkedIn:", "Cover Letter:")


def load_interview_cases() -> list[dict[str, object]]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Interview cases must be a JSON list.")
    return data


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def evaluate_interview_output(
    output: Mapping[str, object],
    *,
    expected_evidence: Sequence[str] = (),
    forbidden_evidence: Sequence[str] = (),
    expected_gaps: Sequence[str] = (),
) -> list[str]:
    """Return deterministic failures for one interview-analysis output."""

    try:
        analysis = InterviewAnalysis.model_validate(output)
    except ValidationError as error:
        return [
            "Invalid interview schema at "
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors(include_url=False, include_input=False)
        ]

    failures: list[str] = []
    for evidence in analysis.evidence:
        if not evidence.startswith(VALID_EVIDENCE_LABELS):
            failures.append(f"Invalid evidence source label: {evidence}")

    evidence_text = _normalized(" ".join(analysis.evidence))
    gaps_text = _normalized(" ".join(analysis.gaps))

    for concept in expected_evidence:
        if _normalized(concept) not in evidence_text:
            failures.append(f"Missing expected evidence: {concept}")
    for concept in forbidden_evidence:
        if _normalized(concept) in evidence_text:
            failures.append(f"Forbidden evidence found: {concept}")
    for concept in expected_gaps:
        if _normalized(concept) not in gaps_text:
            failures.append(f"Missing expected gap: {concept}")

    return failures
