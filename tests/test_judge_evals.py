import asyncio
import json
from types import SimpleNamespace

import groq
import httpx
import pytest
from pydantic import ValidationError

from app.ai import AIGenerationError
from evals.interview_checks import load_interview_cases
from evals.run_judge import (
    InterviewJudgeResult,
    StudyJudgeResult,
    main,
    run_judging,
)
from evals.study_checks import load_study_cases


def study_candidate() -> dict[str, object]:
    case = load_study_cases()[0]
    return {"id": case["id"], "output": case["lesson"], "failures": []}


def interview_candidate() -> dict[str, object]:
    case = load_interview_cases()[0]
    return {"id": case["id"], "output": case["analysis"], "failures": []}


async def fake_judge(**kwargs):
    if kwargs["response_model"] is StudyJudgeResult:
        return StudyJudgeResult(
            topic_relevance=5,
            difficulty_alignment=4,
            factual_coherence_quality=5,
            pedagogical_usefulness=4,
            concise_notes=["Focused and useful."],
        )
    return InterviewJudgeResult(
        grounding=5,
        false_evidence_risk=1,
        false_gap_risk=1,
        usefulness=4,
        concise_notes=["Grounded in the supplied CV."],
    )


def test_valid_study_judge_result(monkeypatch) -> None:
    monkeypatch.setattr("evals.run_judge.generate_structured", fake_judge)
    candidates = {"study": [study_candidate()], "interview_coach": []}

    results, failures = asyncio.run(run_judging(candidates))

    assert failures == 0
    assert results["study"][0]["status"] == "good"
    assert results["study"][0]["metrics"]["topic_relevance"] == 5


def test_valid_interview_judge_result(monkeypatch) -> None:
    monkeypatch.setattr("evals.run_judge.generate_structured", fake_judge)
    candidates = {"study": [], "interview_coach": [interview_candidate()]}

    results, failures = asyncio.run(run_judging(candidates))

    assert failures == 0
    result = results["interview_coach"][0]
    assert result["status"] == "good"
    assert result["metrics"]["false_evidence_risk"] == 1


@pytest.mark.parametrize("score", [0, 6, 3.5, "5"])
def test_invalid_metric_range_or_type_is_rejected(score) -> None:
    with pytest.raises(ValidationError):
        StudyJudgeResult(
            topic_relevance=score,
            difficulty_alignment=4,
            factual_coherence_quality=4,
            pedagogical_usefulness=4,
            concise_notes=["Short note."],
        )


def test_provider_failure_candidate_is_skipped(monkeypatch) -> None:
    async def unexpected_call(**_kwargs):
        raise AssertionError("Provider-failure candidate was sent to the judge.")

    monkeypatch.setattr("evals.run_judge.generate_structured", unexpected_call)
    candidates = {
        "study": [
            {
                "id": "python-decorators-basic",
                "output": None,
                "failures": ["Generation failed: temporary provider failure."],
            }
        ],
        "interview_coach": [],
    }

    results, failures = asyncio.run(run_judging(candidates))

    assert failures == 0
    assert results["study"][0]["status"] == "provider_failure"


def test_missing_candidate_artifact_is_safe(tmp_path, capsys) -> None:
    exit_code = asyncio.run(
        main(
            candidates_path=tmp_path / "missing.json",
            output_path=tmp_path / "judge.json",
        )
    )

    assert exit_code == 1
    assert "Candidate artifact not found" in capsys.readouterr().out
    assert not (tmp_path / "judge.json").exists()


def test_judge_processing_failure_returns_nonzero(monkeypatch, tmp_path) -> None:
    async def failed_judge(**_kwargs):
        raise AIGenerationError("Groq is temporarily unavailable. Please try again shortly.")

    monkeypatch.setattr("evals.run_judge.generate_structured", failed_judge)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps({"study": [study_candidate()], "interview_coach": []}),
        encoding="utf-8",
    )

    exit_code = asyncio.run(
        main(candidates_path=candidates_path, output_path=tmp_path / "judge.json")
    )

    assert exit_code == 1
    saved = json.loads((tmp_path / "judge.json").read_text(encoding="utf-8"))
    assert saved["study"][0]["status"] == "judge_failure"


def test_judge_tests_use_mocked_ai_only(monkeypatch) -> None:
    calls = 0

    async def counted_judge(**kwargs):
        nonlocal calls
        calls += 1
        return await fake_judge(**kwargs)

    monkeypatch.setattr("evals.run_judge.generate_structured", counted_judge)
    candidates = {
        "study": [study_candidate()],
        "interview_coach": [interview_candidate()],
    }

    _, failures = asyncio.run(run_judging(candidates))

    assert failures == 0
    assert calls == 2


def judge_payload() -> dict[str, object]:
    return {
        "topic_relevance": 5,
        "difficulty_alignment": 4,
        "factual_coherence_quality": 5,
        "pedagogical_usefulness": 4,
        "concise_notes": ["Focused and useful."],
    }


def provider_error(error_type, status_code: int, body=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("synthetic provider detail", response=response, body=body or {})


def install_judge_providers(monkeypatch, groq_outcomes, gemini_text: str):
    outcomes = list(groq_outcomes)
    groq_calls = []
    gemini_calls = []

    class FakeCompletions:
        async def create(self, **kwargs):
            groq_calls.append(kwargs)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    class FakeGeminiModels:
        async def generate_content(self, **kwargs):
            gemini_calls.append(kwargs)
            return SimpleNamespace(text=gemini_text)

    class FakeGeminiAsync:
        def __init__(self):
            self.models = FakeGeminiModels()

        async def aclose(self):
            return None

    class FakeGemini:
        def __init__(self, **_kwargs):
            self.aio = FakeGeminiAsync()

    monkeypatch.setattr("app.ai.AsyncGroq", FakeGroq)
    monkeypatch.setattr("app.ai.genai.Client", FakeGemini)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("app.ai.asyncio.sleep", no_wait)
    return groq_calls, gemini_calls


def groq_judge_response(payload=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload or judge_payload()))
            )
        ]
    )


def run_one_study_judge():
    return asyncio.run(
        run_judging({"study": [study_candidate()], "interview_coach": []})
    )


def test_groq_judge_success_does_not_call_gemini_and_records_telemetry(
    monkeypatch,
) -> None:
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [groq_judge_response()], json.dumps(judge_payload())
    )

    results, failures = run_one_study_judge()
    telemetry = results["study"][0]["judge_provider_telemetry"]

    assert failures == 0
    assert len(groq_calls) == 1
    assert gemini_calls == []
    assert telemetry == {
        "judge_primary_provider": "groq",
        "groq_judge_call_count": 1,
        "groq_final_judge_result": "success",
        "gemini_judge_fallback_used": False,
        "gemini_judge_call_count": 0,
        "final_judge_provider": "groq",
        "final_judge_success": True,
    }


@pytest.mark.parametrize(
    "error",
    [
        provider_error(groq.RateLimitError, 429),
        provider_error(groq.InternalServerError, 500),
    ],
)
def test_transient_groq_judge_failure_recovers_with_one_gemini_call(
    monkeypatch, error
) -> None:
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [error, error], json.dumps(judge_payload())
    )

    results, failures = run_one_study_judge()
    telemetry = results["study"][0]["judge_provider_telemetry"]

    assert failures == 0
    assert results["study"][0]["status"] == "good"
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1
    assert telemetry["gemini_judge_fallback_used"] is True
    assert telemetry["final_judge_provider"] == "gemini"
    assert telemetry["final_judge_success"] is True


def test_structured_output_judge_failure_uses_single_gemini_fallback(
    monkeypatch,
) -> None:
    structured_error = provider_error(
        groq.BadRequestError,
        400,
        {"error": {"message": "Generated JSON does not match the expected schema."}},
    )
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [structured_error], json.dumps(judge_payload())
    )

    results, failures = run_one_study_judge()

    assert failures == 0
    assert len(groq_calls) == 1
    assert len(gemini_calls) == 1
    assert results["study"][0]["judge_provider_telemetry"][
        "groq_final_judge_result"
    ] == "structured_output_rejection"


def test_invalid_gemini_judge_output_remains_judge_failure(monkeypatch) -> None:
    rate_limit = provider_error(groq.RateLimitError, 429)
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [rate_limit, rate_limit], json.dumps({"incomplete": True})
    )

    results, failures = run_one_study_judge()
    result = results["study"][0]

    assert failures == 1
    assert result["status"] == "judge_failure"
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1
    assert result["judge_provider_telemetry"]["final_judge_success"] is False


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (provider_error(groq.AuthenticationError, 401), "authentication"),
        (provider_error(groq.NotFoundError, 404), "invalid_model"),
    ],
)
def test_groq_judge_auth_or_model_failure_does_not_call_gemini(
    monkeypatch, error, category
) -> None:
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [error], json.dumps(judge_payload())
    )

    results, failures = run_one_study_judge()
    telemetry = results["study"][0]["judge_provider_telemetry"]

    assert failures == 1
    assert len(groq_calls) == 1
    assert gemini_calls == []
    assert telemetry["groq_final_judge_result"] == category
    assert telemetry["gemini_judge_fallback_used"] is False


def test_judge_provider_calls_are_bounded_at_three(monkeypatch) -> None:
    rate_limit = provider_error(groq.RateLimitError, 429)
    groq_calls, gemini_calls = install_judge_providers(
        monkeypatch, [rate_limit, rate_limit], "not json"
    )

    _, failures = run_one_study_judge()

    assert failures == 1
    assert len(groq_calls) == 2
    assert len(gemini_calls) == 1
