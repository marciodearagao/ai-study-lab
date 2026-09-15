import asyncio
import json
from copy import deepcopy

from app.ai import AIGenerationError
from app.interview import InterviewAnalysis
from app.lessons import Lesson
from evals.interview_checks import load_interview_cases
from evals.run import run_evaluations
from evals.run_live import main, run_live_evaluations
from evals.study_checks import load_study_cases


def install_mock_generators(monkeypatch, *, invalid_study: bool = False) -> None:
    study_cases = {case["topic"]: case for case in load_study_cases()}
    interview_cases = {
        case["job_description"]: case for case in load_interview_cases()
    }

    async def fake_lesson(request):
        output = deepcopy(study_cases[request.topic]["lesson"])
        if invalid_study and request.topic == "Python decorators":
            output["flashcards"][1]["question"] = output["flashcards"][0]["question"]
        return Lesson.model_validate(output)

    async def fake_interview(request):
        return InterviewAnalysis.model_validate(
            interview_cases[request.job_description]["analysis"]
        )

    monkeypatch.setattr("evals.run_live.generate_lesson", fake_lesson)
    monkeypatch.setattr("evals.run_live.generate_interview_analysis", fake_interview)


def test_live_runner_uses_mocked_ai_calls_and_writes_candidates(
    monkeypatch, tmp_path
) -> None:
    install_mock_generators(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    exit_code = asyncio.run(main(output_path=tmp_path / "candidates.json"))

    assert exit_code == 0
    candidates = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
    assert len(candidates["study"]) == 3
    assert len(candidates["interview_coach"]) == 3


def test_missing_configuration_is_safe(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr("evals.run_live.load_environment", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    exit_code = asyncio.run(main(output_path=tmp_path / "candidates.json"))

    assert exit_code == 1
    assert "AI is not configured" in capsys.readouterr().out
    assert not (tmp_path / "candidates.json").exists()


def test_study_candidates_use_existing_checks(monkeypatch) -> None:
    install_mock_generators(monkeypatch, invalid_study=True)

    results, _ = asyncio.run(run_live_evaluations())

    study_results = [result for result in results if result.area == "Study"]
    assert len(study_results) == 3
    assert "Duplicate flashcard question" in study_results[0].failures[0]


def test_interview_candidates_use_existing_checks(monkeypatch) -> None:
    install_mock_generators(monkeypatch)

    results, _ = asyncio.run(run_live_evaluations())

    interview_results = [
        result for result in results if result.area == "Interview Coach"
    ]
    assert len(interview_results) == 3
    assert all(result.passed for result in interview_results)


def test_live_failure_returns_nonzero(monkeypatch, tmp_path) -> None:
    install_mock_generators(monkeypatch, invalid_study=True)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    exit_code = asyncio.run(main(output_path=tmp_path / "candidates.json"))

    assert exit_code == 1


def test_generation_failure_is_safe(monkeypatch) -> None:
    async def failed_lesson(_request):
        raise AIGenerationError("Groq is temporarily unavailable. Please try again shortly.")

    install_mock_generators(monkeypatch)
    monkeypatch.setattr("evals.run_live.generate_lesson", failed_lesson)

    results, _ = asyncio.run(run_live_evaluations())

    assert results[0].failures == (
        "Generation failed: Groq is temporarily unavailable. Please try again shortly.",
    )


def test_deterministic_runner_makes_no_ai_calls(monkeypatch) -> None:
    async def unexpected_call(_request):
        raise AssertionError("The deterministic runner called AI generation.")

    monkeypatch.setattr("app.lessons.generate_lesson", unexpected_call)
    monkeypatch.setattr("app.interview.generate_interview_analysis", unexpected_call)

    results = run_evaluations()

    assert all(result.passed for result in results)
