from copy import deepcopy

from fastapi.testclient import TestClient

from app.ai import AIGenerationError
from app.interview import InterviewAnalysis
from app.lessons import Lesson
from app.main import app
from app.rag import GroundedLesson, RetrievedChunk, SourceReference, TextChunk
from app.telemetry import record_fallback, record_provider_call, record_provider_result
from evals.interview_checks import load_interview_cases
from evals.study_checks import load_study_cases


client = TestClient(app)


def lesson(*, title: str = "Synthetic lesson") -> Lesson:
    payload = deepcopy(load_study_cases()[0]["lesson"])
    payload["title"] = title
    return Lesson.model_validate(payload)


def telemetry_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.getMessage().startswith("telemetry ")]


def assert_one_telemetry_record(caplog) -> str:
    messages = telemetry_messages(caplog)
    assert len(messages) == 1
    return messages[0]


def test_successful_standard_study_telemetry(monkeypatch, caplog) -> None:
    async def fake_generation(_payload):
        record_provider_call("groq")
        record_provider_result("groq", success=True)
        return lesson(title="SECRET_GENERATED_CONTENT")

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)
    caplog.set_level("INFO", logger="uvicorn.error")

    response = client.post(
        "/api/lessons",
        json={"topic": "SECRET_PROMPT_CONTENT", "level": "Basic"},
    )
    message = assert_one_telemetry_record(caplog)

    assert response.status_code == 200
    assert "endpoint=/api/lessons" in message
    assert "success=true" in message
    assert "primary_provider=groq final_provider=groq" in message
    assert "groq_calls=1 gemini_calls=0" in message
    assert "SECRET_PROMPT_CONTENT" not in message
    assert "SECRET_GENERATED_CONTENT" not in message


def test_successful_rag_telemetry_includes_only_retrieval_metadata(
    monkeypatch, caplog
) -> None:
    chunks = [TextChunk("SECRET_DOCUMENT_CONTENT", 3, 0)]
    retrieved = [
        RetrievedChunk("SECRET_DOCUMENT_CONTENT", 3, 0),
        RetrievedChunk("More private document text", 7, 1),
        RetrievedChunk("Repeated page text", 3, 2),
    ]

    monkeypatch.setattr("app.main.process_pdf", lambda _data: chunks)
    monkeypatch.setattr(
        "app.main.retrieve_chunks", lambda _chunks, _topic: retrieved
    )

    async def fake_grounded(_topic, _level, _retrieved):
        record_provider_call("groq")
        record_provider_result("groq", success=True)
        return GroundedLesson(
            lesson=lesson(title="SECRET_RAG_OUTPUT"),
            sources=(SourceReference(page_number=3, excerpt="Synthetic excerpt"),),
        )

    monkeypatch.setattr("app.main.generate_grounded_lesson", fake_grounded)
    caplog.set_level("INFO", logger="uvicorn.error")

    response = client.post(
        "/api/lessons/pdf",
        data={"topic": "Private study question", "level": "Basic"},
        files={"study_pdf": ("study.pdf", b"private pdf bytes", "application/pdf")},
    )
    message = assert_one_telemetry_record(caplog)

    assert response.status_code == 200
    assert "retrieved_pages=[3,7]" in message
    assert "retrieved_chunk_count=3" in message
    for private_value in (
        "SECRET_DOCUMENT_CONTENT",
        "SECRET_RAG_OUTPUT",
        "Private study question",
        "private pdf bytes",
    ):
        assert private_value not in message


def test_groq_to_gemini_fallback_telemetry(monkeypatch, caplog) -> None:
    async def fake_generation(_payload):
        for _ in range(2):
            record_provider_call("groq")
            record_provider_result("groq", success=False, error_category="rate_limit")
        record_fallback()
        record_provider_call("gemini")
        record_provider_result("gemini", success=True)
        return lesson()

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)
    caplog.set_level("INFO", logger="uvicorn.error")

    response = client.post(
        "/api/lessons", json={"topic": "Decorators", "level": "Basic"}
    )
    message = assert_one_telemetry_record(caplog)

    assert response.status_code == 200
    assert "final_provider=gemini fallback_used=true" in message
    assert "groq_calls=2 gemini_calls=1" in message
    assert "error_category=none" in message


def test_handled_failure_emits_one_failed_telemetry_record(monkeypatch, caplog) -> None:
    async def failed_generation(_payload):
        for _ in range(2):
            record_provider_call("groq")
            record_provider_result("groq", success=False, error_category="rate_limit")
        raise AIGenerationError(
            "Provider temporarily unavailable.", status_code=429, category="rate_limit"
        )

    monkeypatch.setattr("app.main.generate_lesson", failed_generation)
    caplog.set_level("INFO", logger="uvicorn.error")

    response = client.post(
        "/api/lessons", json={"topic": "Decorators", "level": "Basic"}
    )
    message = assert_one_telemetry_record(caplog)

    assert response.status_code == 429
    assert "success=false error_category=rate_limit" in message
    assert "final_provider=none fallback_used=false" in message
    assert "groq_calls=2 gemini_calls=0" in message
    assert "Provider temporarily unavailable" not in message


def test_interview_coach_telemetry(monkeypatch, caplog) -> None:
    case = load_interview_cases()[0]

    async def fake_analysis(_payload):
        record_provider_call("groq")
        record_provider_result("groq", success=True)
        return InterviewAnalysis.model_validate(case["analysis"])

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)
    caplog.set_level("INFO", logger="uvicorn.error")

    response = client.post(
        "/api/interview-analysis",
        json={
            "job_description": "SECRET_JOB_DESCRIPTION",
            "resume_text": "SECRET_RESUME_TEXT",
        },
    )
    message = assert_one_telemetry_record(caplog)

    assert response.status_code == 200
    assert "endpoint=/api/interview-analysis" in message
    assert "success=true" in message
    assert "final_provider=groq" in message
    assert "SECRET_JOB_DESCRIPTION" not in message
    assert "SECRET_RESUME_TEXT" not in message
