"""Run Evaluation v1 and write a small local HTML report."""

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import cast

from evals.interview_checks import evaluate_interview_output, load_interview_cases
from evals.study_checks import evaluate_study_output, load_study_cases


REPORT_PATH = Path(__file__).with_name("report.html")


@dataclass(frozen=True)
class CaseResult:
    area: str
    case_id: str
    failures: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


def run_evaluations() -> list[CaseResult]:
    results: list[CaseResult] = []

    for case in load_study_cases():
        failures = evaluate_study_output(
            cast(dict[str, object], case["lesson"]),
            expected_concepts=cast(list[str], case["expected_concepts"]),
            forbidden_concepts=cast(list[str], case["forbidden_concepts"]),
        )
        results.append(
            CaseResult("Study", str(case["id"]), tuple(failures))
        )

    for case in load_interview_cases():
        failures = evaluate_interview_output(
            cast(dict[str, object], case["analysis"]),
            expected_evidence=cast(list[str], case["expected_evidence"]),
            forbidden_evidence=cast(list[str], case["forbidden_evidence"]),
            expected_gaps=cast(list[str], case["expected_gaps"]),
        )
        results.append(
            CaseResult("Interview Coach", str(case["id"]), tuple(failures))
        )

    return results


def summarize(results: list[CaseResult]) -> dict[str, int]:
    passed = sum(result.passed for result in results)
    return {"passed": passed, "failed": len(results) - passed, "total": len(results)}


def _render_result(result: CaseResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    details = ""
    if result.failures:
        messages = "".join(f"<li>{escape(message)}</li>" for message in result.failures)
        details = f'<ul class="failures">{messages}</ul>'
    return (
        '<li class="case-result">'
        f'<span class="status {status.lower()}">{status}</span>'
        f"<code>{escape(result.case_id)}</code>{details}</li>"
    )


def _render_area(area: str, results: list[CaseResult]) -> str:
    area_results = [result for result in results if result.area == area]
    totals = summarize(area_results)
    rows = "".join(_render_result(result) for result in area_results)
    return f"""
      <section>
        <div class="section-heading">
          <h2>{escape(area)}</h2>
          <span>{totals['passed']} passed &middot; {totals['failed']} failed</span>
        </div>
        <ul class="results">{rows}</ul>
      </section>"""


def write_html_report(
    results: list[CaseResult],
    path: Path = REPORT_PATH,
    *,
    generated_at: datetime | None = None,
) -> Path:
    timestamp = generated_at or datetime.now(timezone.utc)
    timestamp_text = timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    totals = summarize(results)
    overall_status = "PASS" if totals["failed"] == 0 else "FAIL"
    report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Evaluation Report</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #24312c; background: #f4f3ed; }}
    body {{ margin: 0; }}
    main {{ width: min(880px, calc(100% - 2rem)); margin: 3rem auto; }}
    h1, h2, p {{ margin-top: 0; }}
    .timestamp {{ color: #68736e; }}
    .summary, section {{ margin: 1.25rem 0; padding: 1.25rem; background: #fff; border: 1px solid #dfe3df; border-radius: 12px; }}
    .summary strong {{ font-size: 1.35rem; }}
    .section-heading {{ display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }}
    .results, .failures {{ list-style: none; padding: 0; margin: 0; }}
    .case-result {{ padding: .8rem 0; border-top: 1px solid #edf0ed; }}
    .status {{ display: inline-block; min-width: 3.3rem; margin-right: .65rem; font-size: .78rem; font-weight: 700; letter-spacing: .06em; }}
    .pass {{ color: #287548; }}
    .fail {{ color: #a33a32; }}
    .failures {{ margin: .55rem 0 0 4rem; color: #7c302b; }}
    .failures li {{ margin-top: .25rem; }}
    code {{ font-size: .95rem; }}
  </style>
</head>
<body>
  <main>
    <h1>Evaluation Report</h1>
    <p class="timestamp">Generated {escape(timestamp_text)}</p>
    <div class="summary">
      <strong class="{overall_status.lower()}">{overall_status}</strong>
      <p>{totals['passed']} passed &middot; {totals['failed']} failed &middot; {totals['total']} total</p>
    </div>
    {_render_area('Study', results)}
    {_render_area('Interview Coach', results)}
  </main>
</body>
</html>
"""
    path.write_text(report, encoding="utf-8")
    return path


def print_terminal_report(results: list[CaseResult], report_path: Path) -> None:
    print("Evaluation v1")
    for area in ("Study", "Interview Coach"):
        print(f"\n{area}")
        for result in (item for item in results if item.area == area):
            status = "PASS" if result.passed else "FAIL"
            print(f"{status}: {result.case_id}")
            for failure in result.failures:
                print(f"  - {failure}")

    totals = summarize(results)
    print("\nSummary")
    print(f"{totals['passed']} passed")
    print(f"{totals['failed']} failed")
    print(f"\nReport:\n{report_path.as_posix()}")


def main(
    *,
    results: list[CaseResult] | None = None,
    report_path: Path = REPORT_PATH,
) -> int:
    resolved_results = results if results is not None else run_evaluations()
    written_report = write_html_report(resolved_results, report_path)
    print_terminal_report(resolved_results, written_report)
    return 1 if summarize(resolved_results)["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
