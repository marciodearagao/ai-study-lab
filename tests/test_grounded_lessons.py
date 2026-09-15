import asyncio

import pytest

from app.ai import AIGenerationError
from app.lessons import Lesson, LessonRequest, build_lesson_messages, generate_lesson
from app.rag import (
    MAX_GROUNDED_CONTEXT_CHARS,
    GroundedLesson,
    RetrievalError,
    RetrievedChunk,
    SourceReference,
    build_grounded_context,
    generate_grounded_lesson,
)


def sample_lesson() -> Lesson:
    return Lesson.model_validate(
        {
            "title": "Grounded Python Decorators",
            "short_explanation": "A decorator wraps a function to add behavior.",
            "key_concepts": ["Wrapper", "Callable", "Decorator syntax"],
            "flashcards": [
                {"question": f"Grounded question {number}?", "answer": "Answer."}
                for number in range(1, 6)
            ],
            "quiz_questions": [
                {
                    "question": f"Grounded quiz {number}?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                    "explanation": "The source supports A.",
                }
                for number in range(1, 5)
            ],
        }
    )


def install_mock_generation(monkeypatch, captured: dict[str, object]) -> None:
    async def fake_generation(**kwargs):
        captured.update(kwargs)
        return sample_lesson()

    monkeypatch.setattr("app.lessons.generate_structured", fake_generation)


def test_grounded_context_and_page_metadata_are_sent_to_existing_schema(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    install_mock_generation(monkeypatch, captured)
    chunks = [
        RetrievedChunk("Decorators wrap Python functions.", 2, 0),
        RetrievedChunk("A wrapper can add behavior before a call.", 4, 1),
    ]

    result = asyncio.run(generate_grounded_lesson("Python decorators", "Basic", chunks))

    messages = captured["messages"]
    assert captured["response_model"] is Lesson
    assert captured["schema_name"] == "lesson"
    assert captured["allow_gemini_fallback"] is True
    assert "PDF SOURCE CONTEXT" in messages[1]["content"]
    assert "[Page 2]" in messages[1]["content"]
    assert "[Page 4]" in messages[1]["content"]
    assert "Decorators wrap Python functions." in messages[1]["content"]
    assert "Base factual claims only" in messages[0]["content"]
    assert isinstance(result, GroundedLesson)
    assert isinstance(result.lesson, Lesson)


def test_source_references_only_use_retrieved_pages_and_deduplicate(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    install_mock_generation(monkeypatch, captured)
    chunks = [
        RetrievedChunk("First passage from page two.", 2, 0),
        RetrievedChunk("Another passage from page two.", 2, 1),
        RetrievedChunk("Passage from page seven.", 7, 2),
    ]

    result = asyncio.run(
        generate_grounded_lesson("Synthetic topic", "Intermediate", chunks)
    )

    assert result.sources == (
        SourceReference(page_number=2, excerpt="First passage from page two."),
        SourceReference(page_number=7, excerpt="Passage from page seven."),
    )
    assert all(
        reference.page_number in {chunk.page_number for chunk in chunks}
        for reference in result.sources
    )


def test_grounded_context_is_bounded() -> None:
    chunks = [RetrievedChunk("word " * 2_000, 3, 0)]

    context, included = build_grounded_context(chunks)

    assert len(context) <= MAX_GROUNDED_CONTEXT_CHARS
    assert included == chunks


def test_empty_retrieval_is_rejected_without_fallback() -> None:
    with pytest.raises(RetrievalError, match="required for grounded lesson"):
        asyncio.run(generate_grounded_lesson("Python", "Basic", []))


@pytest.mark.parametrize(
    "chunk",
    [
        RetrievedChunk("", 1, 0),
        RetrievedChunk("Text", 0, 0),
        RetrievedChunk("Text", 1, -1),
        {"text": "Text", "page_number": 1, "chunk_index": 0},
    ],
)
def test_malformed_retrieved_chunks_are_rejected(chunk) -> None:
    with pytest.raises(RetrievalError, match="malformed"):
        build_grounded_context([chunk])


def test_grounded_generation_preserves_provider_failure(monkeypatch) -> None:
    async def failed_generation(**_kwargs):
        raise AIGenerationError("Groq is temporarily unavailable. Please try again shortly.")

    monkeypatch.setattr("app.lessons.generate_structured", failed_generation)

    with pytest.raises(AIGenerationError, match="temporarily unavailable"):
        asyncio.run(
            generate_grounded_lesson(
                "Python",
                "Basic",
                [RetrievedChunk("Python source material.", 1, 0)],
            )
        )


def test_invalid_structured_output_error_remains_safe(monkeypatch) -> None:
    async def invalid_generation(**_kwargs):
        raise AIGenerationError(
            "The AI returned an invalid lesson format. Please try again."
        )

    monkeypatch.setattr("app.lessons.generate_structured", invalid_generation)

    with pytest.raises(AIGenerationError, match="invalid lesson format"):
        asyncio.run(
            generate_grounded_lesson(
                "Python",
                "Basic",
                [RetrievedChunk("Python source material.", 1, 0)],
            )
        )


def test_non_rag_lesson_generation_messages_remain_unchanged(monkeypatch) -> None:
    captured: dict[str, object] = {}
    install_mock_generation(monkeypatch, captured)
    request = LessonRequest(topic="General Python", level="Basic")

    lesson = asyncio.run(generate_lesson(request))

    assert lesson == sample_lesson()
    assert captured["messages"] == build_lesson_messages(request)
    assert "PDF SOURCE CONTEXT" not in captured["messages"][1]["content"]
