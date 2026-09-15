import pytest

from evals import run_all


def test_run_all_executes_steps_in_order_and_returns_zero(capsys) -> None:
    calls: list[str] = []

    def successful_step(name: str):
        def run() -> int:
            calls.append(name)
            return 0

        return run

    steps = tuple(
        (name, successful_step(name))
        for name in ("Deterministic", "Live", "RAG", "Judge", "Report")
    )

    assert run_all.main(steps=steps) == 0
    assert calls == ["Deterministic", "Live", "RAG", "Judge", "Report"]
    output = capsys.readouterr().out
    assert "This evaluation may make live Groq/Gemini API calls." in output
    assert "Evaluation complete." in output
    assert "evaluation_v2_report.html" in output


def test_run_all_stops_on_nonzero_result(capsys) -> None:
    calls: list[str] = []

    def first() -> int:
        calls.append("first")
        return 0

    def failed() -> int:
        calls.append("failed")
        return 2

    def must_not_run() -> int:
        calls.append("later")
        return 0

    assert run_all.main(steps=(("First", first), ("Live", failed), ("Later", must_not_run))) == 2
    assert calls == ["first", "failed"]
    assert "Evaluation stopped: Live failed." in capsys.readouterr().out


def test_run_all_reports_and_preserves_step_exception(capsys) -> None:
    def failed() -> int:
        raise RuntimeError("original step error")

    with pytest.raises(RuntimeError, match="original step error"):
        run_all.main(steps=(("RAG evaluation", failed),))

    assert "Evaluation stopped: RAG evaluation failed." in capsys.readouterr().out
