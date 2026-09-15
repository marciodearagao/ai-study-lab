import asyncio
import json
from types import SimpleNamespace

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import AIGenerationError, generate_structured
from app.lessons import Lesson
from app.main import app


client = TestClient(app)


def lesson_payload() -> dict[str, object]:
    return {
        "title": "Python Decorators",
        "short_explanation": "Decorators wrap callables to add behavior.",
        "key_concepts": ["Wrapper", "Callable", "Decorator syntax"],
        "flashcards": [
            {"question": f"Question {number}?", "answer": f"Answer {number}."}
            for number in range(1, 6)
        ],
        "quiz_questions": [
            {
                "question": f"Quiz question {number}?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option A",
                "explanation": "Option A is correct.",
            }
            for number in range(1, 5)
        ],
    }


def groq_response(payload: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload or lesson_payload()))
            )
        ]
    )


def groq_error(error_type, status_code: int, body=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("private provider detail", response=response, body=body or {})


def install_fake_groq(monkeypatch, outcome):
    outcomes = list(outcome) if isinstance(outcome, list) else None
    calls: list[dict[str, object]] = []

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


def install_fake_gemini(monkeypatch, outcome):
    calls: list[dict[str, object]] = []

    class FakeModels:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    class FakeAsyncClient:
        def __init__(self):
            self.models = FakeModels()

        async def aclose(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("app.ai.genai.Client", FakeClient)
    return calls


@pytest.fixture(autouse=True)
def provider_configuration(monkeypatch, prevent_real_gemini_calls):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)


def post_lesson():
    return client.post(
        "/api/lessons",
        json={"topic": "Python decorators", "level": "Basic"},
    )


def test_groq_success_never_calls_gemini(monkeypatch) -> None:
    groq_calls = install_fake_groq(monkeypatch, groq_response())
    gemini_calls = install_fake_gemini(monkeypatch, AssertionError("must not run"))

    response = post_lesson()

    assert response.status_code == 200
    assert len(groq_calls) == 1
    assert gemini_calls == []


def test_groq_structured_failure_falls_back_to_gemini(monkeypatch, caplog) -> None:
    error = groq_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Generated JSON does not match the expected schema."}},
    )
    groq_calls = install_fake_groq(monkeypatch, error)
    gemini_calls = install_fake_gemini(
        monkeypatch, SimpleNamespace(text=json.dumps(lesson_payload()))
    )
    caplog.set_level("INFO")

    response = post_lesson()

    assert response.status_code == 200
    assert Lesson.model_validate(response.json()).title == "Python Decorators"
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1
    assert gemini_calls[0]["config"].response_json_schema == Lesson.model_json_schema()
    assert "primary_provider=groq" in caplog.text
    assert (
        "fallback_provider=gemini fallback_result=success "
        "model=gemini-3.1-flash-lite"
    ) in caplog.text
    assert "test-groq-key" not in caplog.text
    assert "test-gemini-key" not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        groq_error(groq.RateLimitError, 429),
        groq_error(groq.InternalServerError, 500),
    ],
)
def test_transient_groq_failure_falls_back_to_gemini(monkeypatch, error) -> None:
    groq_calls = install_fake_groq(monkeypatch, error)
    gemini_calls = install_fake_gemini(
        monkeypatch, SimpleNamespace(text=json.dumps(lesson_payload()))
    )

    response = post_lesson()

    assert response.status_code == 200
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1


def test_local_groq_validation_failure_falls_back_to_gemini(monkeypatch) -> None:
    groq_calls = install_fake_groq(monkeypatch, groq_response({"title": "Incomplete"}))
    gemini_calls = install_fake_gemini(
        monkeypatch, SimpleNamespace(text=json.dumps(lesson_payload()))
    )

    response = post_lesson()

    assert response.status_code == 200
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1


@pytest.mark.parametrize(
    "gemini_text",
    ["not JSON", json.dumps({"title": "Incomplete"})],
)
def test_invalid_gemini_output_returns_safe_primary_error(
    monkeypatch, gemini_text: str
) -> None:
    error = groq_error(groq.RateLimitError, 429)
    groq_calls = install_fake_groq(monkeypatch, error)
    gemini_calls = install_fake_gemini(monkeypatch, SimpleNamespace(text=gemini_text))

    response = post_lesson()

    assert response.status_code == 429
    assert response.json() == {"detail": "Groq is rate-limited. Please try again shortly."}
    assert "test-gemini-key" not in response.text
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        groq_error(groq.AuthenticationError, 401),
        groq_error(groq.NotFoundError, 404),
    ],
)
def test_non_eligible_groq_configuration_failures_do_not_fallback(
    monkeypatch, error
) -> None:
    groq_calls = install_fake_groq(monkeypatch, error)
    gemini_calls = install_fake_gemini(monkeypatch, AssertionError("must not run"))

    response = post_lesson()

    assert response.status_code == 502
    assert len(groq_calls) == 1
    assert gemini_calls == []


def test_malformed_input_calls_neither_provider(monkeypatch) -> None:
    groq_calls = install_fake_groq(monkeypatch, AssertionError("must not run"))
    gemini_calls = install_fake_gemini(monkeypatch, AssertionError("must not run"))

    response = client.post("/api/lessons", json={"topic": "", "level": "Basic"})

    assert response.status_code == 422
    assert groq_calls == []
    assert gemini_calls == []


def test_provider_calls_are_bounded_at_three(monkeypatch) -> None:
    groq_calls = install_fake_groq(
        monkeypatch,
        [
            groq_error(groq.RateLimitError, 429),
            groq_error(groq.InternalServerError, 500),
        ],
    )
    gemini_calls = install_fake_gemini(
        monkeypatch, RuntimeError("temporary Gemini failure")
    )

    response = post_lesson()

    assert response.status_code == 503
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1


def test_fallback_requires_explicit_product_opt_in(monkeypatch) -> None:
    groq_calls = install_fake_groq(
        monkeypatch, groq_error(groq.RateLimitError, 429)
    )
    gemini_calls = install_fake_gemini(monkeypatch, AssertionError("must not run"))

    with pytest.raises(AIGenerationError, match="rate-limited"):
        asyncio.run(
            generate_structured(
                messages=[{"role": "user", "content": "Synthetic request"}],
                response_model=Lesson,
                schema_name="lesson",
                output_label="lesson",
            )
        )

    assert len(groq_calls) == 2
    assert gemini_calls == []
