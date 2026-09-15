import json

import pytest
import groq
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from types import SimpleNamespace

from app.ai import AIGenerationError
from app.lessons import Flashcard, Lesson, LessonRequest, QuizQuestion, build_lesson_messages
from app.main import app


client = TestClient(app)


def sample_flashcards() -> list[Flashcard]:
    return [
        Flashcard(question=f"Question {number}?", answer=f"Answer {number}.")
        for number in range(1, 6)
    ]


def sample_quiz_questions() -> list[QuizQuestion]:
    return [
        QuizQuestion(
            question=f"Quiz question {number}?",
            options=["Option A", "Option B", "Option C", "Option D"],
            correct_answer="Option A",
            explanation=f"Explanation {number}.",
        )
        for number in range(1, 5)
    ]


def install_fake_groq(monkeypatch, outcome):
    outcomes = list(outcome) if isinstance(outcome, list) else None
    calls = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            current = outcomes.pop(0) if outcomes is not None else outcome
            if isinstance(current, Exception):
                raise current
            return current

    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.ai.AsyncGroq", FakeClient)
    return calls


def groq_status_error(error_type, status_code: int, body=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("private provider detail", response=response, body=body or {})


def valid_groq_lesson_response():
    lesson = Lesson(
        title="Vectors",
        short_explanation="Vectors represent magnitude and direction.",
        key_concepts=["Magnitude", "Direction", "Components"],
        flashcards=sample_flashcards(),
        quiz_questions=sample_quiz_questions(),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=lesson.model_dump_json()))]
    )


def test_valid_lesson_request(monkeypatch) -> None:
    async def fake_generation(payload):
        assert payload.topic == "Neural networks"
        assert payload.level == "Intermediate"
        return Lesson(
            title="How Neural Networks Learn",
            short_explanation="They adjust internal weights by measuring and reducing prediction errors.",
            key_concepts=["Weights", "Loss function", "Backpropagation"],
            flashcards=sample_flashcards(),
            quiz_questions=sample_quiz_questions(),
        )

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)

    response = client.post(
        "/api/lessons", json={"topic": "Neural networks", "level": "Intermediate"}
    )

    assert response.status_code == 200
    assert response.json()["key_concepts"] == ["Weights", "Loss function", "Backpropagation"]
    assert len(response.json()["flashcards"]) == 5
    assert response.json()["flashcards"][0] == {
        "question": "Question 1?",
        "answer": "Answer 1.",
    }
    assert len(response.json()["quiz_questions"]) == 4
    assert response.json()["quiz_questions"][0]["correct_answer"] == "Option A"


@pytest.mark.parametrize("topic", ["", "   "])
def test_empty_topic_is_rejected(topic: str) -> None:
    response = client.post("/api/lessons", json={"topic": topic, "level": "Basic"})

    assert response.status_code == 422


def test_structured_lesson_validation() -> None:
    with pytest.raises(ValidationError):
        Lesson.model_validate(
            {
                "title": "Incomplete lesson",
                "short_explanation": "This response has no concepts.",
                "key_concepts": [],
                "flashcards": [card.model_dump() for card in sample_flashcards()],
                "quiz_questions": [question.model_dump() for question in sample_quiz_questions()],
            }
        )


@pytest.mark.parametrize("key_points", [["One", "Two"], ["One", "Two", "Three", "Four", "Five"]])
def test_lesson_requires_three_or_four_key_points(key_points: list[str]) -> None:
    with pytest.raises(ValidationError):
        Lesson(
            title="Vectors",
            short_explanation="Vectors represent magnitude and direction.",
            key_concepts=key_points,
            flashcards=sample_flashcards(),
            quiz_questions=sample_quiz_questions(),
        )


def test_flashcard_structured_validation() -> None:
    card = Flashcard.model_validate({"question": "What is a vector?", "answer": "A quantity with magnitude and direction."})

    assert card.question == "What is a vector?"
    with pytest.raises(ValidationError):
        Flashcard.model_validate({"question": "   ", "answer": "A valid answer"})


def test_quiz_question_structured_validation() -> None:
    question = sample_quiz_questions()[0]

    assert question.correct_answer == "Option A"
    assert len(question.options) == 4


@pytest.mark.parametrize(
    "options",
    [
        ["A", "B", "C"],
        ["A", "B", "C", "D", "E"],
        ["A", "A", "C", "D"],
        ["A", "B", " ", "D"],
    ],
)
def test_quiz_requires_four_distinct_non_empty_options(options: list[str]) -> None:
    with pytest.raises(ValidationError):
        QuizQuestion(
            question="Choose an answer",
            options=options,
            correct_answer="A",
            explanation="A short explanation.",
        )


def test_quiz_correct_answer_must_match_an_option() -> None:
    with pytest.raises(ValidationError):
        QuizQuestion(
            question="Choose an answer",
            options=["A", "B", "C", "D"],
            correct_answer="E",
            explanation="A short explanation.",
        )


@pytest.mark.parametrize("field", ["question", "correct_answer", "explanation"])
def test_quiz_rejects_empty_required_content(field: str) -> None:
    values = {
        "question": "Choose an answer",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "explanation": "A short explanation.",
    }
    values[field] = "   "

    with pytest.raises(ValidationError):
        QuizQuestion.model_validate(values)


@pytest.mark.parametrize("count", [0, 4, 6, 9])
def test_lesson_rejects_invalid_flashcard_counts(count: int) -> None:
    cards = sample_flashcards()
    if count > 5:
        cards = cards + sample_flashcards()[: count - 5]
    else:
        cards = cards[:count]

    with pytest.raises(ValidationError):
        Lesson(
            title="Vectors",
            short_explanation="Vectors represent magnitude and direction.",
            key_concepts=["Magnitude", "Direction", "Components"],
            flashcards=cards,
            quiz_questions=sample_quiz_questions(),
        )


@pytest.mark.parametrize("count", [0, 3, 5, 7])
def test_lesson_rejects_invalid_quiz_question_counts(count: int) -> None:
    questions = sample_quiz_questions()
    if count > 4:
        questions = questions + questions[: count - 4]
    else:
        questions = questions[:count]

    with pytest.raises(ValidationError):
        Lesson(
            title="Vectors",
            short_explanation="Vectors represent magnitude and direction.",
            key_concepts=["Magnitude", "Direction", "Components"],
            flashcards=sample_flashcards(),
            quiz_questions=questions,
        )


def test_ambiguous_technical_acronym_prompt_preserves_context() -> None:
    messages = build_lesson_messages(LessonRequest(topic="RAG evaluation", level="Basic"))

    assert 'Requested topic: "RAG evaluation"' in messages[1]["content"]
    assert "preserve an acronym" in messages[0]["content"]
    assert "Retrieval-Augmented Generation" in messages[0]["content"]
    assert "unrelated expansion" in messages[0]["content"]


def test_lesson_prompt_requests_stable_activity_counts_and_exact_answers() -> None:
    messages = build_lesson_messages(LessonRequest(topic="Python", level="Basic"))

    assert "exactly 5 concise flashcards" in messages[0]["content"]
    assert "exactly 4 multiple-choice quiz questions" in messages[0]["content"]
    assert "non-near-duplicate option" in messages[0]["content"]
    assert "adhere exactly to the structured schema" in messages[0]["content"].lower()
    assert "character for character" in messages[0]["content"]


def test_lesson_json_schema_expresses_provider_enforceable_constraints() -> None:
    schema = Lesson.model_json_schema()
    lesson_properties = schema["properties"]
    quiz_properties = schema["$defs"]["QuizQuestion"]["properties"]

    assert lesson_properties["flashcards"]["minItems"] == 5
    assert lesson_properties["flashcards"]["maxItems"] == 5
    assert lesson_properties["quiz_questions"]["minItems"] == 4
    assert lesson_properties["quiz_questions"]["maxItems"] == 4
    assert quiz_properties["options"]["minItems"] == 4
    assert quiz_properties["options"]["maxItems"] == 4
    # Groq's strict-schema subset rejects uniqueItems; local validation still
    # enforces distinct options after generation.
    assert "uniqueItems" not in quiz_properties["options"]
    assert quiz_properties["question"]["maxLength"] == 240
    assert quiz_properties["correct_answer"]["maxLength"] == 160


def test_missing_ai_configuration_is_friendly(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "AI is not configured yet. Add GROQ_API_KEY to .env and restart the app."
    }


def test_successful_structured_groq_lesson(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = install_fake_groq(monkeypatch, valid_groq_lesson_response())

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 200
    assert response.json()["title"] == "Vectors"
    assert len(calls) == 1
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_authentication_failure_does_not_leak_provider_details(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-key")
    error = groq_status_error(groq.AuthenticationError, 401)
    install_fake_groq(monkeypatch, error)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json()["detail"].startswith("Groq authentication failed")
    assert "private provider detail" not in response.text
    assert "test-secret-key" not in response.text


def test_authentication_failure_is_not_retried(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = install_fake_groq(
        monkeypatch, groq_status_error(groq.AuthenticationError, 401)
    )

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert len(calls) == 1


def test_invalid_model_is_reported_cleanly(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = install_fake_groq(monkeypatch, groq_status_error(groq.NotFoundError, 404))

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Advanced"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The configured Groq model is invalid or unavailable. Check GROQ_MODEL in .env."
    }
    assert len(calls) == 1


def test_temporary_provider_failure_is_friendly(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = install_fake_groq(monkeypatch, groq_status_error(groq.RateLimitError, 429))
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 429
    assert response.json() == {"detail": "Groq is rate-limited. Please try again shortly."}
    assert len(calls) == 2


def test_transient_rate_limit_retries_once_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    error = groq_status_error(groq.RateLimitError, 429)
    calls = install_fake_groq(monkeypatch, [error, valid_groq_lesson_response()])
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 200
    assert len(calls) == 2


def test_provider_5xx_retries_then_returns_temporary_failure(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    error = groq_status_error(groq.InternalServerError, 500)
    calls = install_fake_groq(monkeypatch, error)
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Groq is temporarily unavailable. Please try again shortly."
    }
    assert len(calls) == 2


def test_timeout_retries_then_reports_timeout(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    calls = install_fake_groq(monkeypatch, groq.APITimeoutError(request=request))
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The AI request timed out. Please try again shortly."
    }
    assert len(calls) == 2


def test_network_failure_retries_then_reports_connection_issue(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    calls = install_fake_groq(
        monkeypatch, groq.APIConnectionError(request=request)
    )
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The AI service could not be reached. Check your connection and try again."
    }
    assert len(calls) == 2


def test_structured_output_bad_request_retries_once_then_fails_safely(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    error = groq_status_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Generated JSON does not match the expected schema."}},
    )
    calls = install_fake_groq(monkeypatch, error)
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI returned an invalid lesson format. Please try again."
    }
    assert len(calls) == 2


def test_invalid_provider_schema_is_not_retried(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    error = groq_status_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Invalid schema for response_format: uniqueItems is not permitted."}},
    )
    calls = install_fake_groq(monkeypatch, error)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI response configuration is invalid. Check the server log."
    }
    assert len(calls) == 1


def test_structured_output_retry_can_succeed(monkeypatch, caplog) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    error = groq_status_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Generated JSON does not match the expected schema."}},
    )
    calls = install_fake_groq(monkeypatch, [error, valid_groq_lesson_response()])
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)
    caplog.set_level("INFO")

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 200
    assert len(calls) == 2
    assert "Regenerate the entire lesson" in calls[1]["messages"][-1]["content"]
    assert "structured output retry succeeded" in caplog.text


@pytest.mark.parametrize("invalid_part", ["duplicate_options", "wrong_flashcard_count"])
def test_lesson_structure_failures_trigger_one_targeted_retry(
    monkeypatch, invalid_part: str
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    payload = json.loads(valid_groq_lesson_response().choices[0].message.content)
    if invalid_part == "duplicate_options":
        payload["quiz_questions"][0]["options"][1] = "Option A"
    else:
        payload["flashcards"] = payload["flashcards"][:4]
    invalid = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )
    calls = install_fake_groq(monkeypatch, [invalid, valid_groq_lesson_response()])
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 200
    assert len(calls) == 2


def test_malformed_json_is_reported_as_invalid_structured_output(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    malformed = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{not-json"))]
    )
    install_fake_groq(monkeypatch, malformed)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI returned an invalid lesson format. Please try again."
    }


def test_pydantic_validation_failure_logs_locations_without_content(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    invalid = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"title": "Only"})))]
    )
    calls = install_fake_groq(monkeypatch, invalid)
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert len(calls) == 2
    assert "category=pydantic_validation" in caplog.text
    assert "structured output retry exhausted" in caplog.text
    assert "Only" not in caplog.text


def test_local_validation_retry_can_succeed(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    invalid = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"title": "Only"})))]
    )
    calls = install_fake_groq(monkeypatch, [invalid, valid_groq_lesson_response()])
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 200
    assert len(calls) == 2


def test_transient_and_structured_failures_share_two_attempt_budget(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    rate_limit = groq_status_error(groq.RateLimitError, 429)
    structured = groq_status_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Generated JSON does not match the expected schema."}},
    )
    calls = install_fake_groq(monkeypatch, [rate_limit, structured])
    async def no_wait(_delay):
        return None
    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert len(calls) == 2


def test_invalid_structured_lesson_is_reported_cleanly(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    invalid_lesson = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"title":"Too short"}'))]
    )
    install_fake_groq(monkeypatch, invalid_lesson)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI returned an invalid lesson format. Please try again."
    }


def test_invalid_provider_response_is_reported_cleanly(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    install_fake_groq(monkeypatch, SimpleNamespace(choices=[]))

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Basic"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI returned an invalid lesson format. Please try again."
    }


def test_ai_failure_is_handled_cleanly(monkeypatch) -> None:
    async def failed_generation(_payload):
        raise AIGenerationError("Groq could not generate a valid lesson right now.")

    monkeypatch.setattr("app.main.generate_lesson", failed_generation)

    response = client.post("/api/lessons", json={"topic": "Vectors", "level": "Advanced"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Groq could not generate a valid lesson right now."}
