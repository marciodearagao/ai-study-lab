"""Generate live candidates with production AI and run deterministic checks."""

import asyncio
import json
import os
from pathlib import Path
from typing import cast

from dotenv import load_dotenv
from pydantic import ValidationError

from app.ai import AIGenerationError
from app.interview import (
    InterviewAnalysis,
    InterviewRequest,
    generate_interview_analysis,
)
from app.lessons import Lesson, LessonRequest, generate_lesson
from evals.interview_checks import evaluate_interview_output, load_interview_cases
from evals.run import CaseResult, summarize
from evals.study_checks import evaluate_study_output, load_study_cases


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = Path(__file__).with_name("results") / "live_candidates.json"


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def has_groq_configuration() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


async def run_live_evaluations() -> tuple[list[CaseResult], dict[str, object]]:
    results: list[CaseResult] = []
    candidates: dict[str, object] = {"study": [], "interview_coach": []}

    study_candidates = cast(list[dict[str, object]], candidates["study"])
    for case in load_study_cases():
        case_id = str(case["id"])
        print(f"Running Study: {case_id}", flush=True)
        output: dict[str, object] | None = None
        try:
            lesson = await generate_lesson(
                LessonRequest(topic=case["topic"], level=case["level"])
            )
            output = lesson.model_dump(mode="json")
            failures = evaluate_study_output(
                output,
                expected_concepts=cast(list[str], case["expected_concepts"]),
                forbidden_concepts=cast(list[str], case["forbidden_concepts"]),
            )
        except (AIGenerationError, ValidationError) as error:
            failures = [f"Generation failed: {error}"]
        study_candidates.append(
            {"id": case_id, "output": output, "failures": failures}
        )
        results.append(CaseResult("Study", case_id, tuple(failures)))

    interview_candidates = cast(
        list[dict[str, object]], candidates["interview_coach"]
    )
    for case in load_interview_cases():
        case_id = str(case["id"])
        print(f"Running Interview Coach: {case_id}", flush=True)
        output = None
        try:
            analysis = await generate_interview_analysis(
                InterviewRequest(
                    job_description=case["job_description"],
                    resume_text=case["resume_text"],
                    linkedin_text=case["linkedin_text"],
                    cover_letter_text=case["cover_letter_text"],
                )
            )
            output = analysis.model_dump(mode="json")
            failures = evaluate_interview_output(
                output,
                expected_evidence=cast(list[str], case["expected_evidence"]),
                forbidden_evidence=cast(list[str], case["forbidden_evidence"]),
                expected_gaps=cast(list[str], case["expected_gaps"]),
            )
        except (AIGenerationError, ValidationError) as error:
            failures = [f"Generation failed: {error}"]
        interview_candidates.append(
            {"id": case_id, "output": output, "failures": failures}
        )
        results.append(CaseResult("Interview Coach", case_id, tuple(failures)))

    return results, candidates


def write_candidates(candidates: dict[str, object], path: Path = RESULTS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def print_live_results(results: list[CaseResult], output_path: Path) -> None:
    for area in ("Study", "Interview Coach"):
        print(f"\n{area}")
        for result in (item for item in results if item.area == area):
            status = "PASS" if result.passed else "FAIL"
            print(f"{status}: {result.case_id}")
            for failure in result.failures:
                print(f"  - {failure}")

    totals = summarize(results)
    print(f"\nSummary\n{totals['passed']} passed\n{totals['failed']} failed")
    print(f"\nCandidates:\n{output_path.as_posix()}")


async def main(*, output_path: Path = RESULTS_PATH) -> int:
    load_environment()
    if not has_groq_configuration():
        print(
            "Live evaluation cannot start: AI is not configured. "
            "Add GROQ_API_KEY to .env and try again."
        )
        return 1

    print("Evaluation v2 - live candidates\n")
    results, candidates = await run_live_evaluations()
    written_path = write_candidates(candidates, output_path)
    print_live_results(results, written_path)
    return 1 if summarize(results)["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
