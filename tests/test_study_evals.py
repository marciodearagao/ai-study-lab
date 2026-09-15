from copy import deepcopy

import pytest

from evals.study_checks import evaluate_study_output, load_study_cases


CASES = load_study_cases()


def case_by_id(case_id: str) -> dict[str, object]:
    return next(case for case in CASES if case["id"] == case_id)


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["id"]))
def test_valid_synthetic_study_result_passes(case: dict[str, object]) -> None:
    assert evaluate_study_output(
        case["lesson"],
        expected_concepts=case["expected_concepts"],
        forbidden_concepts=case["forbidden_concepts"],
    ) == []


def test_duplicate_flashcard_question_fails() -> None:
    lesson = deepcopy(case_by_id("python-decorators-basic")["lesson"])
    lesson["flashcards"][1]["question"] = lesson["flashcards"][0]["question"].upper()

    failures = evaluate_study_output(lesson)

    assert any("Duplicate flashcard question" in failure for failure in failures)


def test_invalid_quiz_correct_answer_fails_schema_check() -> None:
    lesson = deepcopy(case_by_id("italian-passato-prossimo-basic")["lesson"])
    lesson["quiz_questions"][0]["correct_answer"] = "Not one of the options"

    failures = evaluate_study_output(lesson)

    assert any("correct_answer must exactly match one option" in failure for failure in failures)


def test_duplicate_quiz_question_fails() -> None:
    lesson = deepcopy(case_by_id("rag-evaluation-basic")["lesson"])
    lesson["quiz_questions"][1]["question"] = lesson["quiz_questions"][0]["question"]

    failures = evaluate_study_output(lesson)

    assert any("Duplicate quiz question" in failure for failure in failures)


def test_forbidden_concept_is_detected() -> None:
    case = case_by_id("rag-evaluation-basic")
    lesson = deepcopy(case["lesson"])
    lesson["short_explanation"] += " This refers to Red-Amber-Green status reporting."

    failures = evaluate_study_output(
        lesson, forbidden_concepts=case["forbidden_concepts"]
    )

    assert "Forbidden concept found: red-amber-green" in failures


def test_expected_concept_can_be_required() -> None:
    lesson = case_by_id("rag-evaluation-basic")["lesson"]

    assert evaluate_study_output(
        lesson, expected_concepts=["retrieval-augmented generation"]
    ) == []
    assert "Missing expected concept: semantic caching" in evaluate_study_output(
        lesson, expected_concepts=["semantic caching"]
    )
