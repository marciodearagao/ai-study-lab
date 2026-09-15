from datetime import datetime, timezone

from evals.run import (
    CaseResult,
    main,
    run_evaluations,
    summarize,
    write_html_report,
)


def test_runner_aggregates_study_and_interview_cases() -> None:
    results = run_evaluations()

    assert sum(result.area == "Study" for result in results) == 3
    assert sum(result.area == "Interview Coach" for result in results) == 3
    assert all(result.passed for result in results)


def test_summary_counts_passes_and_failures() -> None:
    results = [
        CaseResult("Study", "passing"),
        CaseResult("Study", "failing", ("Example failure",)),
    ]

    assert summarize(results) == {"passed": 1, "failed": 1, "total": 2}


def test_main_returns_nonzero_when_a_case_fails(tmp_path) -> None:
    results = [CaseResult("Study", "failing", ("Example failure",))]

    exit_code = main(results=results, report_path=tmp_path / "report.html")

    assert exit_code == 1


def test_html_report_is_generated(tmp_path) -> None:
    report_path = tmp_path / "report.html"

    written_path = write_html_report(
        [CaseResult("Study", "passing")],
        report_path,
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )

    assert written_path == report_path
    assert report_path.exists()


def test_html_report_contains_expected_summary_and_failures(tmp_path) -> None:
    report_path = tmp_path / "report.html"
    write_html_report(
        [
            CaseResult("Study", "study-pass"),
            CaseResult("Interview Coach", "coach-fail", ("Missing evidence",)),
        ],
        report_path,
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )

    report = report_path.read_text(encoding="utf-8")
    assert "<title>Evaluation Report</title>" in report
    assert "Generated 2026-01-02T03:04:05Z" in report
    assert "1 passed &middot; 1 failed &middot; 2 total" in report
    assert "Study" in report
    assert "Interview Coach" in report
    assert "coach-fail" in report
    assert "Missing evidence" in report
