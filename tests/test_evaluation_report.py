import json
from datetime import datetime, timezone

from evals.interview_checks import load_interview_cases
from evals.report import (
    aggregate_rag_report,
    aggregate_report,
    main,
    render_report,
)
from evals.study_checks import load_study_cases


def complete_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    candidates: dict[str, object] = {"study": [], "interview_coach": []}
    judges: dict[str, object] = {"study": [], "interview_coach": []}
    for area, cases in (
        ("study", load_study_cases()),
        ("interview_coach", load_interview_cases()),
    ):
        output_key = "lesson" if area == "study" else "analysis"
        candidates[area].extend(
            {"id": case["id"], "output": case[output_key], "failures": []}
            for case in cases
        )
        metrics = (
            {
                "topic_relevance": 5,
                "difficulty_alignment": 4,
                "factual_coherence_quality": 5,
                "pedagogical_usefulness": 4,
            }
            if area == "study"
            else {
                "grounding": 5,
                "false_evidence_risk": 1,
                "false_gap_risk": 1,
                "usefulness": 4,
            }
        )
        judges[area].extend(
            {
                "id": case["id"],
                "status": "good",
                "metrics": metrics,
                "concise_notes": ["Synthetic judge note."],
            }
            for case in cases
        )
    return candidates, judges


def rag_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    from evals.rag_checks import load_rag_cases

    rag = {"rag": []}
    judges = {"study": [], "interview_coach": [], "rag": []}
    for case in load_rag_cases():
        rag["rag"].append(
            {
                "id": case["id"],
                "retrieval": {
                    "status": "pass",
                    "retrieved_pages": case["expected_pages"] or [1],
                    "retrieved_chunk_indexes": [0],
                    "checks": {"metadata_preserved": True},
                    "failures": [],
                },
                "generation": {"status": "success", "output": {}, "failures": []},
                "provider_telemetry": {
                    "groq_call_count": 2,
                    "gemini_call_count": 1,
                    "final_provider": "gemini",
                    "elapsed_seconds": 1.25,
                },
            }
        )
        judges["rag"].append(
            {
                "id": case["id"],
                "status": "good",
                "metrics": {
                    "context_relevance": 5,
                    "groundedness": 5,
                    "unsupported_claim_risk": 1,
                    "source_attribution_quality": 4,
                },
                "concise_notes": ["Grounded synthetic result."],
                "judge_provider_telemetry": {
                    "judge_primary_provider": "groq",
                    "groq_judge_call_count": 2,
                    "groq_final_judge_result": "rate_limit",
                    "gemini_judge_fallback_used": True,
                    "gemini_judge_call_count": 1,
                    "final_judge_provider": "gemini",
                    "final_judge_success": True,
                },
            }
        )
    return rag, judges


def test_report_aggregation_combines_all_evaluation_layers() -> None:
    candidates, judges = complete_artifacts()

    views, summary = aggregate_report(candidates, judges)

    assert len(views) == 6
    assert summary["baseline_total"] == 6
    assert summary["live_total"] == 6
    assert summary["judge_good"] == 6


def test_report_totals_include_live_failures() -> None:
    candidates, judges = complete_artifacts()
    candidates["study"][0]["failures"] = ["Missing expected concept"]
    candidates["interview_coach"][-1]["output"] = None
    candidates["interview_coach"][-1]["failures"] = ["Generation failed"]
    judges["interview_coach"][-1].update(
        {"status": "provider_failure", "metrics": None}
    )

    _, summary = aggregate_report(candidates, judges)

    assert summary["live_generated"] == 5
    assert summary["live_deterministic_passed"] == 4
    assert summary["live_deterministic_failed"] == 1
    assert summary["provider_failures"] == 1


def test_deterministic_judge_disagreement_is_visible() -> None:
    candidates, judges = complete_artifacts()
    candidates["study"][0]["failures"] = ["Missing exact phrase"]
    views, summary = aggregate_report(candidates, judges)

    html = render_report(
        views,
        summary,
        generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert views[0].disagreement is True
    assert "Deterministic/judge disagreement" in html
    assert "Missing exact phrase" in html
    assert "GOOD" in html


def test_provider_failure_is_displayed() -> None:
    candidates, judges = complete_artifacts()
    candidates["interview_coach"][-1].update(
        {"output": None, "failures": ["Generation failed: provider unavailable."]}
    )
    judges["interview_coach"][-1].update(
        {
            "status": "provider_failure",
            "metrics": None,
            "concise_notes": ["Generation failed: provider unavailable."],
        }
    )
    views, summary = aggregate_report(candidates, judges)

    html = render_report(views, summary)

    assert "PROVIDER FAILURE" in html
    assert "provider unavailable" in html


def test_missing_artifacts_write_clear_diagnostic_report(tmp_path, capsys) -> None:
    report_path = tmp_path / "report.html"

    exit_code = main(
        candidates_path=tmp_path / "live_candidates.json",
        judge_path=tmp_path / "judge_results.json",
        report_path=report_path,
    )

    assert exit_code == 1
    assert "run_live" in capsys.readouterr().out
    assert "run_judge" in report_path.read_text(encoding="utf-8")


def test_report_contains_expected_metrics_and_legend() -> None:
    candidates, judges = complete_artifacts()
    views, summary = aggregate_report(candidates, judges)

    html = render_report(views, summary)

    assert "Evaluation v2 Report" in html
    assert "Python decorators" in html
    assert "Topic relevance" in html
    assert "False-evidence risk" in html
    assert "PASS / FAIL" in html
    assert "GOOD / REVIEW / POOR" in html
    assert "JUDGE FAILURE" in html


def test_rag_report_aggregation_and_provider_telemetry_are_visible() -> None:
    candidates, judges = complete_artifacts()
    rag, rag_judges = rag_artifacts()
    judges["rag"] = rag_judges["rag"]
    views, summary = aggregate_report(candidates, judges)
    rag_views, rag_summary = aggregate_rag_report(rag, judges)

    html = render_report(
        views, summary, rag_views=rag_views, rag_summary=rag_summary
    )

    assert rag_summary["rag_total"] == 4
    assert rag_summary["rag_retrieval_passed"] == 4
    assert "Context relevance" in html
    assert "Unsupported-claim risk" in html
    assert "Final provider: gemini" in html
    assert "rag-unsupported-french-revolution" in html
    assert "Generator: Gemini · Judge: Gemini fallback" in html
    assert "same-provider generation and judging" in html


def test_combined_report_reads_rag_artifact_without_api_calls(
    monkeypatch, tmp_path
) -> None:
    class UnexpectedGroqClient:
        def __init__(self, **_kwargs):
            raise AssertionError("Report generation attempted an API call.")

    monkeypatch.setattr("app.ai.AsyncGroq", UnexpectedGroqClient)
    candidates, judges = complete_artifacts()
    rag, rag_judges = rag_artifacts()
    judges["rag"] = rag_judges["rag"]
    candidates_path = tmp_path / "live_candidates.json"
    judge_path = tmp_path / "judge_results.json"
    rag_path = tmp_path / "rag_results.json"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    judge_path.write_text(json.dumps(judges), encoding="utf-8")
    rag_path.write_text(json.dumps(rag), encoding="utf-8")

    exit_code = main(
        candidates_path=candidates_path,
        judge_path=judge_path,
        rag_path=rag_path,
        report_path=tmp_path / "report.html",
    )

    assert exit_code == 0
    assert "RAG" in (tmp_path / "report.html").read_text(encoding="utf-8")


def test_report_generation_makes_no_api_calls(monkeypatch, tmp_path) -> None:
    class UnexpectedGroqClient:
        def __init__(self, **_kwargs):
            raise AssertionError("Report generation attempted an API call.")

    monkeypatch.setattr("app.ai.AsyncGroq", UnexpectedGroqClient)
    candidates, judges = complete_artifacts()
    candidates_path = tmp_path / "live_candidates.json"
    judge_path = tmp_path / "judge_results.json"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    judge_path.write_text(json.dumps(judges), encoding="utf-8")

    exit_code = main(
        candidates_path=candidates_path,
        judge_path=judge_path,
        report_path=tmp_path / "report.html",
    )

    assert exit_code == 0
