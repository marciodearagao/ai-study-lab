from copy import deepcopy

import pytest

from evals.interview_checks import evaluate_interview_output, load_interview_cases


CASES = load_interview_cases()


def case_by_id(case_id: str) -> dict[str, object]:
    return next(case for case in CASES if case["id"] == case_id)


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["id"]))
def test_valid_synthetic_interview_result_passes(case: dict[str, object]) -> None:
    assert evaluate_interview_output(
        case["analysis"],
        expected_evidence=case["expected_evidence"],
        forbidden_evidence=case["forbidden_evidence"],
        expected_gaps=case["expected_gaps"],
    ) == []


def test_expected_evidence_is_detected() -> None:
    case = case_by_id("backend-gap-kubernetes")

    assert evaluate_interview_output(
        case["analysis"], expected_evidence=["Python", "FastAPI"]
    ) == []


def test_missing_expected_evidence_fails() -> None:
    case = case_by_id("backend-gap-kubernetes")

    failures = evaluate_interview_output(
        case["analysis"], expected_evidence=["PostgreSQL"]
    )

    assert "Missing expected evidence: PostgreSQL" in failures


def test_forbidden_evidence_fails() -> None:
    case = case_by_id("backend-gap-kubernetes")
    analysis = deepcopy(case["analysis"])
    analysis["evidence"].append("CV: Managed Kubernetes production clusters.")

    failures = evaluate_interview_output(
        analysis, forbidden_evidence=case["forbidden_evidence"]
    )

    assert "Forbidden evidence found: Kubernetes" in failures


def test_expected_gap_is_detected() -> None:
    case = case_by_id("speech-gap-text-to-speech")

    assert evaluate_interview_output(
        case["analysis"], expected_gaps=["text-to-speech"]
    ) == []


def test_incorrect_source_label_fails() -> None:
    case = case_by_id("multiple-synthetic-sources")
    analysis = deepcopy(case["analysis"])
    analysis["evidence"][0] = "Resume: Built Python APIs."

    failures = evaluate_interview_output(analysis)

    assert any("Invalid evidence source label" in failure for failure in failures)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [("fit_summary", ""), ("interview_questions", [])],
)
def test_empty_or_invalid_structured_content_fails(
    field: str, invalid_value: object
) -> None:
    analysis = deepcopy(case_by_id("backend-gap-kubernetes")["analysis"])
    analysis[field] = invalid_value

    failures = evaluate_interview_output(analysis)

    assert any("Invalid interview schema" in failure for failure in failures)
