from copy import deepcopy

from app.ai import AIGenerationError
from app.diagnose_ai import diagnose
from app.lessons import Lesson
from app.telemetry import record_fallback, record_provider_call, record_provider_result
from evals.study_checks import load_study_cases


def lesson() -> Lesson:
    return Lesson.model_validate(deepcopy(load_study_cases()[0]["lesson"]))


def test_groq_success_reports_groq(monkeypatch, capsys) -> None:
    async def fake_generation(_payload):
        record_provider_call("groq")
        record_provider_result("groq", success=True)
        return lesson()

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)

    assert diagnose("Python decorators", "Basic") == 0
    output = capsys.readouterr().out

    assert "Primary provider: Groq" in output
    assert "Final provider: Groq" in output
    assert "Fallback used: no" in output
    assert "Result: PASS" in output


def test_gemini_fallback_success_reports_gemini(monkeypatch, capsys) -> None:
    async def fake_generation(_payload):
        record_provider_call("groq")
        record_provider_result("groq", success=False, error_category="rate_limit")
        record_fallback()
        record_provider_call("gemini")
        record_provider_result("gemini", success=True)
        return lesson()

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)

    assert diagnose("Python decorators", "Basic") == 0
    output = capsys.readouterr().out

    assert "Final provider: Gemini" in output
    assert "Fallback used: yes" in output
    assert "Result: PASS" in output


def test_failure_does_not_report_false_pass_or_sensitive_content(
    monkeypatch, capsys
) -> None:
    async def fake_generation(_payload):
        record_provider_call("groq")
        record_provider_result("groq", success=False, error_category="authentication")
        raise AIGenerationError(
            "SECRET_KEY provider response", status_code=503, category="authentication"
        )

    monkeypatch.setattr("app.main.generate_lesson", fake_generation)

    assert diagnose("SECRET_PROMPT", "Basic") == 1
    output = capsys.readouterr().out

    assert "Final provider: none" in output
    assert "Fallback used: no" in output
    assert "Result: FAIL" in output
    assert "Reason: authentication" in output
    assert "Result: PASS" not in output
    assert "SECRET_KEY" not in output
    assert "SECRET_PROMPT" not in output
