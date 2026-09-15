"""Build one offline HTML report from Evaluation v1 and v2 artifacts."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import cast

from evals.interview_checks import load_interview_cases
from evals.rag_checks import load_rag_cases
from evals.run import run_evaluations, summarize
from evals.run_judge import JUDGE_RESULTS_PATH
from evals.run_live import RESULTS_PATH as CANDIDATES_PATH
from evals.run_rag import RAG_RESULTS_PATH
from evals.study_checks import load_study_cases


REPORT_PATH = Path(__file__).with_name("results") / "evaluation_v2_report.html"
AREAS = ("study", "interview_coach")


class ReportArtifactError(Exception):
    """Raised when an Evaluation v2 artifact cannot be read."""


@dataclass(frozen=True)
class CaseView:
    area: str
    case_id: str
    label: str
    generation_status: str
    deterministic_status: str
    deterministic_failures: tuple[str, ...]
    judge_status: str
    metrics: dict[str, int]
    notes: tuple[str, ...]
    judge_provider_telemetry: dict[str, object]

    @property
    def disagreement(self) -> bool:
        return self.deterministic_status == "fail" and self.judge_status in {
            "good",
            "review",
        }


@dataclass(frozen=True)
class RagCaseView:
    case_id: str
    label: str
    unsupported: bool
    retrieval_status: str
    retrieval_checks: dict[str, bool]
    retrieval_failures: tuple[str, ...]
    retrieved_pages: tuple[int, ...]
    retrieved_chunk_indexes: tuple[int, ...]
    generation_status: str
    generation_title: str
    source_pages: tuple[int, ...]
    judge_status: str
    metrics: dict[str, int]
    notes: tuple[str, ...]
    provider_telemetry: dict[str, object]
    judge_provider_telemetry: dict[str, object]


def load_artifact(
    path: Path, label: str, *, required_areas: tuple[str, ...] = AREAS
) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportArtifactError(f"{label} is unreadable or invalid: {path.as_posix()}") from error
    if not isinstance(data, dict) or not all(
        isinstance(data.get(area), list) for area in required_areas
    ):
        raise ReportArtifactError(f"{label} has an invalid structure: {path.as_posix()}")
    return data


def _case_definitions() -> dict[str, list[dict[str, object]]]:
    return {
        "study": load_study_cases(),
        "interview_coach": load_interview_cases(),
    }


def aggregate_report(
    candidates: dict[str, object], judge_results: dict[str, object]
) -> tuple[list[CaseView], dict[str, int]]:
    views: list[CaseView] = []
    for area, definitions in _case_definitions().items():
        candidate_map = {
            str(item.get("id")): item
            for item in cast(list[dict[str, object]], candidates[area])
        }
        judge_map = {
            str(item.get("id")): item
            for item in cast(list[dict[str, object]], judge_results[area])
        }
        for definition in definitions:
            case_id = str(definition["id"])
            candidate = candidate_map.get(case_id, {})
            judge = judge_map.get(case_id, {})
            output = candidate.get("output")
            failures = tuple(str(item) for item in candidate.get("failures", []))
            if output is not None:
                generation_status = "generated"
                deterministic_status = "fail" if failures else "pass"
            elif failures:
                generation_status = "provider_failure"
                deterministic_status = "not_run"
            else:
                generation_status = "missing"
                deterministic_status = "not_run"

            judge_status = str(judge.get("status", "judge_failure"))
            raw_metrics = judge.get("metrics")
            metrics = (
                {str(key): int(value) for key, value in raw_metrics.items()}
                if isinstance(raw_metrics, dict)
                else {}
            )
            notes = tuple(str(item) for item in judge.get("concise_notes", []))
            judge_telemetry = judge.get("judge_provider_telemetry")
            label = str(definition["topic"] if area == "study" else case_id)
            views.append(
                CaseView(
                    area=area,
                    case_id=case_id,
                    label=label,
                    generation_status=generation_status,
                    deterministic_status=deterministic_status,
                    deterministic_failures=failures,
                    judge_status=judge_status,
                    metrics=metrics,
                    notes=notes,
                    judge_provider_telemetry=(
                        judge_telemetry if isinstance(judge_telemetry, dict) else {}
                    ),
                )
            )

    baseline = summarize(run_evaluations())
    summary = {
        "baseline_total": baseline["total"],
        "baseline_passed": baseline["passed"],
        "baseline_failed": baseline["failed"],
        "live_total": len(views),
        "live_generated": sum(view.generation_status == "generated" for view in views),
        "live_deterministic_passed": sum(
            view.deterministic_status == "pass" for view in views
        ),
        "live_deterministic_failed": sum(
            view.deterministic_status == "fail" for view in views
        ),
        "judge_good": sum(view.judge_status == "good" for view in views),
        "judge_review": sum(view.judge_status == "review" for view in views),
        "judge_poor": sum(view.judge_status == "poor" for view in views),
        "provider_failures": sum(
            view.generation_status == "provider_failure" for view in views
        ),
        "judge_failures": sum(view.judge_status == "judge_failure" for view in views),
        "judge_provider_groq": sum(
            view.judge_provider_telemetry.get("final_judge_provider") == "groq"
            for view in views
        ),
        "judge_provider_gemini": sum(
            view.judge_provider_telemetry.get("final_judge_provider") == "gemini"
            for view in views
        ),
        "judge_fallback_recoveries": sum(
            view.judge_provider_telemetry.get("gemini_judge_fallback_used") is True
            and view.judge_provider_telemetry.get("final_judge_success") is True
            for view in views
        ),
    }
    return views, summary


def aggregate_rag_report(
    rag_results: dict[str, object], judge_results: dict[str, object]
) -> tuple[list[RagCaseView], dict[str, int]]:
    candidate_map = {
        str(item.get("id")): item
        for item in cast(list[dict[str, object]], rag_results["rag"])
    }
    judge_map = {
        str(item.get("id")): item
        for item in cast(list[dict[str, object]], judge_results.get("rag", []))
    }
    views: list[RagCaseView] = []
    for case in load_rag_cases():
        case_id = str(case["id"])
        candidate = candidate_map.get(case_id, {})
        retrieval = candidate.get("retrieval")
        generation = candidate.get("generation")
        retrieval = retrieval if isinstance(retrieval, dict) else {}
        generation = generation if isinstance(generation, dict) else {}
        judge = judge_map.get(case_id, {})
        raw_metrics = judge.get("metrics")
        metrics = (
            {str(key): int(value) for key, value in raw_metrics.items()}
            if isinstance(raw_metrics, dict)
            else {}
        )
        telemetry = candidate.get("provider_telemetry")
        judge_telemetry = judge.get("judge_provider_telemetry")
        output = generation.get("output")
        output = output if isinstance(output, dict) else {}
        lesson = output.get("lesson")
        lesson = lesson if isinstance(lesson, dict) else {}
        sources = output.get("sources")
        sources = sources if isinstance(sources, list) else []
        views.append(
            RagCaseView(
                case_id=case_id,
                label=str(case["topic"]),
                unsupported=bool(case["unsupported"]),
                retrieval_status=str(retrieval.get("status", "missing")),
                retrieval_checks={
                    str(key): bool(value)
                    for key, value in cast(
                        dict[str, object], retrieval.get("checks", {})
                    ).items()
                },
                retrieval_failures=tuple(
                    str(value) for value in retrieval.get("failures", [])
                ),
                retrieved_pages=tuple(
                    int(value) for value in retrieval.get("retrieved_pages", [])
                ),
                retrieved_chunk_indexes=tuple(
                    int(value)
                    for value in retrieval.get("retrieved_chunk_indexes", [])
                ),
                generation_status=str(generation.get("status", "missing")),
                generation_title=str(lesson.get("title", "")),
                source_pages=tuple(
                    int(source["page_number"])
                    for source in sources
                    if isinstance(source, dict)
                    and isinstance(source.get("page_number"), int)
                ),
                judge_status=str(judge.get("status", "judge_failure")),
                metrics=metrics,
                notes=tuple(str(value) for value in judge.get("concise_notes", [])),
                provider_telemetry=telemetry if isinstance(telemetry, dict) else {},
                judge_provider_telemetry=(
                    judge_telemetry if isinstance(judge_telemetry, dict) else {}
                ),
            )
        )
    summary = {
        "rag_total": len(views),
        "rag_retrieval_passed": sum(view.retrieval_status == "pass" for view in views),
        "rag_retrieval_failed": sum(view.retrieval_status == "fail" for view in views),
        "rag_generated": sum(view.generation_status == "success" for view in views),
        "rag_provider_failures": sum(
            view.generation_status == "provider_failure" for view in views
        ),
        "rag_judge_good": sum(view.judge_status == "good" for view in views),
        "rag_judge_review": sum(view.judge_status == "review" for view in views),
        "rag_judge_poor": sum(view.judge_status == "poor" for view in views),
        "rag_judge_failures": sum(
            view.judge_status == "judge_failure" for view in views
        ),
        "rag_judge_provider_groq": sum(
            view.judge_provider_telemetry.get("final_judge_provider") == "groq"
            for view in views
        ),
        "rag_judge_provider_gemini": sum(
            view.judge_provider_telemetry.get("final_judge_provider") == "gemini"
            for view in views
        ),
        "rag_judge_fallback_recoveries": sum(
            view.judge_provider_telemetry.get("gemini_judge_fallback_used") is True
            and view.judge_provider_telemetry.get("final_judge_success") is True
            for view in views
        ),
        "rag_same_provider_cases": sum(
            bool(view.provider_telemetry.get("final_provider"))
            and view.provider_telemetry.get("final_provider")
            == view.judge_provider_telemetry.get("final_judge_provider")
            for view in views
        ),
    }
    return views, summary


def _badge(value: str) -> str:
    label = value.replace("_", " ").upper()
    return f'<span class="badge {escape(value)}">{escape(label)}</span>'


def _metric(label: str, value: int | None) -> str:
    shown = str(value) if value is not None else "—"
    return f'<div class="metric"><span>{escape(label)}</span><strong>{shown}</strong></div>'


def _render_case(view: CaseView) -> str:
    study_metrics = (
        ("Topic relevance", "topic_relevance"),
        ("Difficulty alignment", "difficulty_alignment"),
        ("Factual coherence", "factual_coherence_quality"),
        ("Pedagogical usefulness", "pedagogical_usefulness"),
    )
    interview_metrics = (
        ("Grounding", "grounding"),
        ("False-evidence risk", "false_evidence_risk"),
        ("False-gap risk", "false_gap_risk"),
        ("Usefulness", "usefulness"),
    )
    metric_rows = study_metrics if view.area == "study" else interview_metrics
    metrics = "".join(_metric(label, view.metrics.get(key)) for label, key in metric_rows)
    failures = "".join(f"<li>{escape(item)}</li>" for item in view.deterministic_failures)
    notes = "".join(f"<li>{escape(item)}</li>" for item in view.notes)
    judge_provider = view.judge_provider_telemetry.get("final_judge_provider")
    judge_provider_text = (
        f"Judge provider: {str(judge_provider).title()}"
        + (
            " fallback"
            if view.judge_provider_telemetry.get("gemini_judge_fallback_used")
            else ""
        )
        if judge_provider
        else "Judge provider: not available"
    )
    disagreement = (
        '<p class="disagreement">Deterministic/judge disagreement — review the fixed rule before treating this as an overall quality failure.</p>'
        if view.disagreement
        else ""
    )
    return f"""
      <article class="case">
        <div class="case-title"><div><h3>{escape(view.label)}</h3><code>{escape(view.case_id)}</code></div>{_badge(view.judge_status)}</div>
        <div class="statuses">
          <span>Generation {_badge(view.generation_status)}</span>
          <span>Deterministic {_badge(view.deterministic_status)}</span>
          <span>Judge {_badge(view.judge_status)}</span>
        </div>
        <p class="muted">{escape(judge_provider_text)}</p>
        {disagreement}
        <div class="metrics">{metrics}</div>
        {f'<div class="details"><strong>Deterministic findings</strong><ul>{failures}</ul></div>' if failures else ''}
        {f'<div class="details"><strong>Judge notes</strong><ul>{notes}</ul></div>' if notes else ''}
      </article>"""


def _render_rag_case(view: RagCaseView) -> str:
    metric_rows = (
        ("Context relevance", "context_relevance"),
        ("Groundedness", "groundedness"),
        ("Unsupported-claim risk", "unsupported_claim_risk"),
        ("Source attribution", "source_attribution_quality"),
    )
    metrics = "".join(_metric(label, view.metrics.get(key)) for label, key in metric_rows)
    findings = "".join(f"<li>{escape(item)}</li>" for item in view.retrieval_failures)
    checks = "".join(
        f"<li>{_badge('pass' if passed else 'fail')} {escape(name.replace('_', ' '))}</li>"
        for name, passed in view.retrieval_checks.items()
    )
    notes = "".join(f"<li>{escape(item)}</li>" for item in view.notes)
    pages = ", ".join(str(value) for value in view.retrieved_pages) or "none"
    indexes = ", ".join(str(value) for value in view.retrieved_chunk_indexes) or "none"
    source_pages = ", ".join(str(value) for value in view.source_pages) or "none"
    telemetry = view.provider_telemetry
    judge_telemetry = view.judge_provider_telemetry
    generator_provider = telemetry.get("final_provider")
    judge_provider = judge_telemetry.get("final_judge_provider")
    same_provider = bool(generator_provider) and generator_provider == judge_provider
    provider_line = (
        f"Groq calls: {escape(str(telemetry.get('groq_call_count', 'unknown')))} · "
        f"Gemini calls: {escape(str(telemetry.get('gemini_call_count', 'unknown')))} · "
        f"Final provider: {escape(str(telemetry.get('final_provider') or 'none'))} · "
        f"Elapsed: {escape(str(telemetry.get('elapsed_seconds', 'unknown')))}s"
    )
    return f"""
      <article class="case">
        <div class="case-title"><div><h3>{escape(view.label)}</h3><code>{escape(view.case_id)}</code></div>{_badge(view.judge_status)}</div>
        <div class="statuses">
          <span>Retrieval {_badge(view.retrieval_status)}</span>
          <span>Generation {_badge(view.generation_status)}</span>
          <span>Judge {_badge(view.judge_status)}</span>
          {f'<span>{_badge("unsupported")} fixture</span>' if view.unsupported else ''}
        </div>
        <p class="muted">Retrieved pages: {escape(pages)} · chunk indexes: {escape(indexes)}</p>
        <p><strong>Generated lesson:</strong> {escape(view.generation_title or 'not available')} <span class="muted">· source pages: {escape(source_pages)}</span></p>
        <p class="muted">{provider_line}</p>
        <p class="muted">Generator: {escape(str(generator_provider or 'none').title())} · Judge: {escape(str(judge_provider or 'none').title())}{' fallback' if judge_telemetry.get('gemini_judge_fallback_used') else ''}</p>
        {f'<p class="method-note">Method note: same-provider generation and judging.</p>' if same_provider else ''}
        <div class="metrics">{metrics}</div>
        {f'<div class="details"><strong>Retrieval checks</strong><ul>{checks}</ul></div>' if checks else ''}
        {f'<div class="details"><strong>Retrieval findings</strong><ul>{findings}</ul></div>' if findings else ''}
        {f'<div class="details"><strong>Judge notes</strong><ul>{notes}</ul></div>' if notes else ''}
      </article>"""


def render_report(
    views: list[CaseView],
    summary: dict[str, int],
    *,
    rag_views: list[RagCaseView] | None = None,
    rag_summary: dict[str, int] | None = None,
    generated_at: datetime | None = None,
) -> str:
    timestamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp_text = timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    study = "".join(_render_case(view) for view in views if view.area == "study")
    interview = "".join(
        _render_case(view) for view in views if view.area == "interview_coach"
    )
    rag_views = rag_views or []
    rag = "".join(_render_rag_case(view) for view in rag_views)
    rag_summary_html = ""
    rag_section = ""
    if rag_summary is not None:
        rag_summary_html = f"""
    <div class="summary-card"><strong>{rag_summary['rag_retrieval_passed']} / {rag_summary['rag_total']}</strong>RAG retrieval passed</div>
    <div class="summary-card"><strong>{rag_summary['rag_generated']} / {rag_summary['rag_total']}</strong>Grounded lessons generated</div>
    <div class="summary-card"><strong>{rag_summary['rag_judge_good']} / {rag_summary['rag_judge_review']} / {rag_summary['rag_judge_poor']}</strong>RAG Good / Review / Poor</div>
    <div class="summary-card"><strong>{rag_summary['rag_provider_failures']} / {rag_summary['rag_judge_failures']}</strong>RAG provider / judge failures</div>
    <div class="summary-card"><strong>{rag_summary['rag_judge_provider_groq']} / {rag_summary['rag_judge_provider_gemini']}</strong>RAG judges: Groq / Gemini</div>
    <div class="summary-card"><strong>{rag_summary['rag_same_provider_cases']}</strong>Same-provider RAG cases</div>"""
        rag_section = f"<h2>RAG</h2>{rag}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Evaluation v2 Report</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #24312c; background: #f3f2ec; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; }} main {{ width: min(1040px, calc(100% - 2rem)); margin: 3rem auto; }}
    h1, h2, h3, p {{ margin-top: 0; }} h1 {{ margin-bottom: .35rem; }} h2 {{ margin-top: 2.5rem; }} code, .muted {{ color: #6b746f; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: .8rem; margin: 1.5rem 0; }}
    .summary-card, .legend, .case {{ background: #fff; border: 1px solid #dce1dc; border-radius: 14px; box-shadow: 0 8px 30px rgba(36,49,44,.04); }}
    .summary-card {{ padding: 1rem; }} .summary-card strong {{ display: block; font-size: 1.55rem; margin-bottom: .2rem; }}
    .legend {{ padding: 1rem 1.2rem; line-height: 1.65; }} .legend p {{ margin: .15rem 0; }}
    .case {{ padding: 1.25rem; margin: .9rem 0; }} .case-title, .statuses {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }}
    .case-title h3 {{ margin-bottom: .25rem; }} .statuses {{ justify-content: flex-start; flex-wrap: wrap; margin: 1rem 0; }}
    .statuses > span {{ color: #66706b; font-size: .86rem; }} .badge {{ display: inline-block; margin-left: .3rem; padding: .24rem .48rem; border-radius: 999px; background: #edf0ed; color: #52605a; font-size: .72rem; font-weight: 750; letter-spacing: .04em; }}
    .pass, .good, .generated {{ background: #e5f3e9; color: #21633d; }} .fail, .poor, .provider_failure, .judge_failure {{ background: #fae8e5; color: #923b32; }} .review {{ background: #fff1cc; color: #7b5a12; }} .not_run, .missing {{ background: #eceeef; color: #5f686b; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .65rem; }} .metric {{ padding: .75rem; background: #f7f7f3; border-radius: 9px; }}
    .metric span {{ display: block; min-height: 2.2em; color: #66706b; font-size: .8rem; }} .metric strong {{ font-size: 1.25rem; }}
    .details {{ margin-top: 1rem; }} .details ul {{ margin: .4rem 0 0; padding-left: 1.25rem; }} .disagreement, .method-note {{ padding: .75rem; border-left: 3px solid #bf8b20; background: #fff8e5; color: #684c13; }}
    @media (max-width: 620px) {{ main {{ margin: 1.5rem auto; }} .case-title {{ display: block; }} .case-title > .badge {{ margin: .8rem 0 0; }} }}
  </style>
</head>
<body><main>
  <h1>Evaluation v2 Report</h1><p class="muted">Generated {escape(timestamp_text)}</p>
  <div class="summary">
    <div class="summary-card"><strong>{summary['baseline_passed']} pass &middot; {summary['baseline_failed']} fail</strong>Baseline deterministic ({summary['baseline_total']} cases)</div>
    <div class="summary-card"><strong>{summary['live_generated']} / {summary['live_total']}</strong>Live candidates generated</div>
    <div class="summary-card"><strong>{summary['live_deterministic_passed']} pass &middot; {summary['live_deterministic_failed']} fail</strong>Live deterministic checks</div>
    <div class="summary-card"><strong>{summary['judge_good']} / {summary['judge_review']} / {summary['judge_poor']}</strong>Good / Review / Poor</div>
    <div class="summary-card"><strong>{summary['provider_failures']}</strong>Provider failures</div>
    <div class="summary-card"><strong>{summary['judge_failures']}</strong>Judge failures</div>
    {rag_summary_html}
  </div>
  <div class="legend"><strong>Legend</strong><p><b>PASS / FAIL</b> = deterministic checks. <b>GOOD / REVIEW / POOR</b> = LLM-as-a-judge quality assessment.</p><p><b>PROVIDER FAILURE</b> = provider or infrastructure failure, not a quality judgment. <b>JUDGE FAILURE</b> = judge-processing failure.</p></div>
  <h2>Study</h2>{study}
  <h2>Interview Coach</h2>{interview}
  {rag_section}
</main></body></html>
"""


def write_report(html: str, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def _missing_report(messages: list[str]) -> str:
    items = "".join(f"<li>{escape(message)}</li>" for message in messages)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Evaluation v2 Report</title></head><body><main><h1>Evaluation v2 Report unavailable</h1><ul>{items}</ul></main></body></html>"""


def main(
    *,
    candidates_path: Path = CANDIDATES_PATH,
    judge_path: Path = JUDGE_RESULTS_PATH,
    report_path: Path = REPORT_PATH,
    rag_path: Path | None = None,
) -> int:
    missing: list[str] = []
    if not candidates_path.exists():
        missing.append(
            f"Missing {candidates_path.as_posix()}. Run python -m evals.run_live first."
        )
    if not judge_path.exists():
        missing.append(
            f"Missing {judge_path.as_posix()}. Run python -m evals.run_judge first."
        )
    if rag_path is not None and not rag_path.exists():
        missing.append(
            f"Missing {rag_path.as_posix()}. Run python -m evals.run_rag first."
        )
    if missing:
        write_report(_missing_report(missing), report_path)
        print("Evaluation v2 report could not be completed:")
        for message in missing:
            print(f"- {message}")
        print(f"\nDiagnostic report:\n{report_path.as_posix()}")
        return 1

    try:
        candidates = load_artifact(candidates_path, "Live candidate artifact")
        judge_results = load_artifact(judge_path, "Judge result artifact")
        rag_results = (
            load_artifact(rag_path, "RAG result artifact", required_areas=("rag",))
            if rag_path is not None
            else None
        )
    except ReportArtifactError as error:
        message = str(error)
        write_report(_missing_report([message]), report_path)
        print(f"Evaluation v2 report could not be completed: {message}")
        return 1

    views, summary = aggregate_report(candidates, judge_results)
    rag_views = None
    rag_summary = None
    if rag_results is not None:
        rag_views, rag_summary = aggregate_rag_report(rag_results, judge_results)
    written_path = write_report(
        render_report(views, summary, rag_views=rag_views, rag_summary=rag_summary),
        report_path,
    )
    print("Evaluation v2 combined report")
    print(f"Baseline: {summary['baseline_passed']} / {summary['baseline_total']} passed")
    print(
        "Live deterministic: "
        f"{summary['live_deterministic_passed']} passed, "
        f"{summary['live_deterministic_failed']} failed"
    )
    print(
        "Judge: "
        f"{summary['judge_good']} good, {summary['judge_review']} review, "
        f"{summary['judge_poor']} poor"
    )
    print(
        f"Provider failures: {summary['provider_failures']}, "
        f"Judge failures: {summary['judge_failures']}"
    )
    if rag_summary is not None:
        print(
            "RAG: "
            f"{rag_summary['rag_retrieval_passed']} retrieval passes, "
            f"{rag_summary['rag_generated']} generated, "
            f"{rag_summary['rag_judge_good']} good, "
            f"{rag_summary['rag_judge_review']} review, "
            f"{rag_summary['rag_judge_poor']} poor, "
            f"{rag_summary['rag_provider_failures']} provider failures, "
            f"{rag_summary['rag_judge_failures']} judge failures"
        )
    print(f"\nReport:\n{written_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(rag_path=RAG_RESULTS_PATH))
