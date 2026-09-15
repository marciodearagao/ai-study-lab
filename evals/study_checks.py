"""Deterministic checks for synthetic Study lesson outputs."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from app.lessons import Lesson


CASES_PATH = Path(__file__).with_name("study_cases.json")


def load_study_cases() -> list[dict[str, object]]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Study cases must be a JSON list.")
    return data


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _lesson_text(lesson: Lesson) -> str:
    values = [lesson.title, lesson.short_explanation, *lesson.key_concepts]
    for card in lesson.flashcards:
        values.extend((card.question, card.answer))
    for item in lesson.quiz_questions:
        values.extend(
            (item.question, *item.options, item.correct_answer, item.explanation)
        )
    return _normalized(" ".join(values))


def _duplicate_questions(questions: Sequence[str], label: str) -> list[str]:
    seen: set[str] = set()
    failures: list[str] = []
    for question in questions:
        normalized = _normalized(question)
        if normalized in seen:
            failures.append(f"Duplicate {label} question: {question}")
        seen.add(normalized)
    return failures


def evaluate_study_output(
    output: Mapping[str, object],
    *,
    expected_concepts: Sequence[str] = (),
    forbidden_concepts: Sequence[str] = (),
) -> list[str]:
    """Return deterministic failures for one lesson-shaped output."""

    try:
        lesson = Lesson.model_validate(output)
    except ValidationError as error:
        return [
            "Invalid lesson schema at "
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors(include_url=False, include_input=False)
        ]

    failures = _duplicate_questions(
        [card.question for card in lesson.flashcards], "flashcard"
    )
    failures.extend(
        _duplicate_questions(
            [item.question for item in lesson.quiz_questions], "quiz"
        )
    )

    content = _lesson_text(lesson)
    for concept in expected_concepts:
        if _normalized(concept) not in content:
            failures.append(f"Missing expected concept: {concept}")
    for concept in forbidden_concepts:
        if _normalized(concept) in content:
            failures.append(f"Forbidden concept found: {concept}")

    return failures
