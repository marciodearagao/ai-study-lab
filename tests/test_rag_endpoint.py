from fastapi.testclient import TestClient

from app.ai import AIGenerationError
from app.interview import PDFExtractionError
from app.lessons import Lesson
from app.main import app
from app.rag import (
    GroundedLesson,
    RetrievalError,
    RetrievedChunk,
    SourceReference,
    TextChunk,
)


client = TestClient(app)


def sample_lesson() -> Lesson:
    return Lesson.model_validate(
        {
            "title": "Grounded Decorators",
            "short_explanation": "Decorators wrap functions using the supplied material.",
            "key_concepts": ["Wrapper", "Callable", "Decorator syntax"],
            "flashcards": [
                {"question": f"Question {number}?", "answer": "Answer."}
                for number in range(1, 6)
            ],
            "quiz_questions": [
                {
                    "question": f"Quiz {number}?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                    "explanation": "A is supported by the material.",
                }
                for number in range(1, 5)
            ],
        }
    )


def install_successful_pipeline(monkeypatch) -> None:
    chunks = [TextChunk("Decorator source text.", 3, 0)]
    retrieved = [RetrievedChunk("Decorator source text.", 3, 0)]

    def fake_process(pdf_data):
        assert pdf_data == b"synthetic PDF bytes"
        return chunks

    def fake_retrieve(received_chunks, query):
        assert received_chunks == chunks
        assert query == "Python decorators"
        return retrieved

    async def fake_grounded_generation(topic, level, received_chunks):
        assert topic == "Python decorators"
        assert level == "Basic"
        assert received_chunks == retrieved
        return GroundedLesson(
            lesson=sample_lesson(),
            sources=(SourceReference(page_number=3, excerpt="Decorator source text."),),
        )

    monkeypatch.setattr("app.main.process_pdf", fake_process)
    monkeypatch.setattr("app.main.retrieve_chunks", fake_retrieve)
    monkeypatch.setattr("app.main.generate_grounded_lesson", fake_grounded_generation)


def test_successful_grounded_request_returns_lesson_and_sources(monkeypatch) -> None:
    install_successful_pipeline(monkeypatch)

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python decorators", "level": "Basic"},
        files={
            "study_pdf": (
                "study.pdf",
                b"synthetic PDF bytes",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["lesson"]["title"] == "Grounded Decorators"
    assert response.json()["sources"] == [
        {"page_number": 3, "excerpt": "Decorator source text."}
    ]
    assert response.json()["used_uploaded_material"] is True
    assert len(response.json()["lesson"]["flashcards"]) == 5
    assert len(response.json()["lesson"]["quiz_questions"]) == 4


def test_grounded_endpoint_rejects_invalid_file_type() -> None:
    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={"study_pdf": ("study.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Choose one PDF file for study material."}


def test_grounded_endpoint_keeps_five_megabyte_file_limit(monkeypatch) -> None:
    def unexpected_processing(_pdf_data):
        raise AssertionError("oversized file must be rejected before PDF processing")

    monkeypatch.setattr("app.main.process_pdf", unexpected_processing)

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={
            "study_pdf": (
                "study.pdf",
                b"x" * (5 * 1024 * 1024 + 1),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "The study material PDF is too large. Choose a file under 5 MB."
    }


def test_grounded_endpoint_requires_exactly_one_pdf() -> None:
    missing = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
    )
    multiple = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files=[
            ("study_pdf", ("one.pdf", b"one", "application/pdf")),
            ("study_pdf", ("two.pdf", b"two", "application/pdf")),
        ],
    )

    assert missing.status_code == 400
    assert multiple.status_code == 400
    assert missing.json() == {
        "detail": "Choose exactly one PDF study material file."
    }


def test_grounded_endpoint_rejects_unreadable_pdf() -> None:
    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={"study_pdf": ("study.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "The study material PDF is empty or unreadable."
    }


def test_grounded_endpoint_handles_textless_pdf_safely(monkeypatch) -> None:
    def textless_pdf(_data):
        raise PDFExtractionError(
            "No readable text was found in the study material PDF. OCR is not supported."
        )

    monkeypatch.setattr("app.main.process_pdf", textless_pdf)

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={"study_pdf": ("study.pdf", b"mock PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "No readable text was found in the study material PDF. OCR is not supported."
    }


def test_grounded_endpoint_handles_retrieval_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.process_pdf", lambda _data: [TextChunk("Source", 1, 0)]
    )

    def failed_retrieval(_chunks, _query):
        raise RetrievalError("Semantic retrieval could not be completed.")

    monkeypatch.setattr("app.main.retrieve_chunks", failed_retrieval)

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={"study_pdf": ("study.pdf", b"mock PDF", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Semantic retrieval could not be completed."
    }


def test_grounded_endpoint_preserves_provider_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.process_pdf", lambda _data: [TextChunk("Source", 1, 0)]
    )
    monkeypatch.setattr(
        "app.main.retrieve_chunks",
        lambda _chunks, _query: [RetrievedChunk("Source", 1, 0)],
    )

    async def failed_generation(_topic, _level, _chunks):
        raise AIGenerationError(
            "Groq is temporarily unavailable. Please try again shortly.", 503
        )

    monkeypatch.setattr("app.main.generate_grounded_lesson", failed_generation)

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Python", "level": "Basic"},
        files={"study_pdf": ("study.pdf", b"mock PDF", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Groq is temporarily unavailable. Please try again shortly."
    }


def test_standard_json_lesson_endpoint_remains_unchanged(monkeypatch) -> None:
    async def fake_standard_generation(payload):
        assert payload.topic == "General Python"
        assert payload.level == "Intermediate"
        return sample_lesson()

    monkeypatch.setattr("app.main.generate_lesson", fake_standard_generation)

    response = client.post(
        "/api/lessons",
        json={"topic": "General Python", "level": "Intermediate"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Grounded Decorators"
    assert "lesson" not in response.json()
    assert "sources" not in response.json()
