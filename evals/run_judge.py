"""Judge saved live candidates with the existing structured Groq integration."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from app.ai import AIGenerationError, generate_structured
from evals.interview_checks import load_interview_cases
from evals.provider_telemetry import ProviderLogCapture
from evals.rag_checks import load_rag_cases
from evals.run_rag import RAG_RESULTS_PATH
from evals.run_live import (
    RESULTS_PATH as CANDIDATES_PATH,
    has_groq_configuration,
    load_environment,
)
from evals.study_checks import load_study_cases


JUDGE_RESULTS_PATH = Path(__file__).with_name("results") / "judge_results.json"
Score = Annotated[StrictInt, Field(ge=1, le=5)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StudyJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_relevance: Score
    difficulty_alignment: Score
    factual_coherence_quality: Score
    pedagogical_usefulness: Score
    concise_notes: list[Note] = Field(min_length=1, max_length=3)


class InterviewJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grounding: Score
    false_evidence_risk: Score
    false_gap_risk: Score
    usefulness: Score
    concise_notes: list[Note] = Field(min_length=1, max_length=3)


class RagJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_relevance: Score
    groundedness: Score
    unsupported_claim_risk: Score
    source_attribution_quality: Score
    concise_notes: list[Note] = Field(min_length=1, max_length=3)


STUDY_JUDGE_PROMPT = """You are evaluating learning quality for one generated lesson.
Score only topic relevance, alignment with the requested learner level, factual coherence and
quality, and pedagogical usefulness. Use integer scores from 1 to 5, where 1 is poor and 5 is
excellent. Do not score unrelated style preferences. Return only the requested structure with one
to three concise notes."""

INTERVIEW_JUDGE_PROMPT = """You are evaluating one generated interview-coach analysis against
synthetic source documents. Score grounding and usefulness from 1 (poor) to 5 (excellent). Score
false evidence risk and false gap risk from 1 (very low risk) to 5 (very high risk). Use only
explicit information in the supplied job description and professional sources. Return only the
requested structure with one to three concise notes."""

RAG_JUDGE_PROMPT = """You are evaluating a grounded lesson generated from synthetic retrieved
PDF passages. Score context relevance, groundedness, and source attribution quality from 1 (poor)
to 5 (excellent). Score unsupported claim risk from 1 (very low risk) to 5 (very high risk).
Judge only against the requested topic, retrieved passages, generated lesson, and returned source
references. For an intentionally unsupported query, reward a lesson that clearly limits its claims
instead of inventing an answer. Return only the requested structure with one to three concise
notes."""


class CandidateArtifactError(Exception):
    """Raised when the saved candidate artifact cannot be used."""


def load_candidates(path: Path = CANDIDATES_PATH) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CandidateArtifactError(
            f"Candidate artifact not found: {path.as_posix()}. Run python -m evals.run_live first."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateArtifactError("The candidate artifact is unreadable or invalid.") from error

    if not isinstance(data, dict) or not all(
        isinstance(data.get(area), list) for area in ("study", "interview_coach")
    ):
        raise CandidateArtifactError("The candidate artifact has an invalid structure.")
    return data


def load_rag_candidates(path: Path = RAG_RESULTS_PATH) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CandidateArtifactError(
            f"RAG result artifact not found: {path.as_posix()}. Run python -m evals.run_rag first."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateArtifactError("The RAG result artifact is unreadable or invalid.") from error
    if not isinstance(data, dict) or not isinstance(data.get("rag"), list):
        raise CandidateArtifactError("The RAG result artifact has an invalid structure.")
    return data


def classify_study(metrics: StudyJudgeResult) -> Literal["good", "review", "poor"]:
    scores = (
        metrics.topic_relevance,
        metrics.difficulty_alignment,
        metrics.factual_coherence_quality,
        metrics.pedagogical_usefulness,
    )
    if min(scores) <= 2:
        return "poor"
    if min(scores) == 3:
        return "review"
    return "good"


def classify_interview(
    metrics: InterviewJudgeResult,
) -> Literal["good", "review", "poor"]:
    if (
        min(metrics.grounding, metrics.usefulness) <= 2
        or max(metrics.false_evidence_risk, metrics.false_gap_risk) >= 4
    ):
        return "poor"
    if (
        min(metrics.grounding, metrics.usefulness) == 3
        or max(metrics.false_evidence_risk, metrics.false_gap_risk) == 3
    ):
        return "review"
    return "good"


def classify_rag(
    metrics: RagJudgeResult, *, unsupported: bool = False
) -> Literal["good", "review", "poor"]:
    positive = (
        (metrics.groundedness, metrics.source_attribution_quality)
        if unsupported
        else (
            metrics.context_relevance,
            metrics.groundedness,
            metrics.source_attribution_quality,
        )
    )
    if min(positive) <= 2 or metrics.unsupported_claim_risk >= 4:
        return "poor"
    if min(positive) == 3 or metrics.unsupported_claim_risk == 3:
        return "review"
    return "good"


def _provider_failure(candidate: dict[str, object]) -> dict[str, object] | None:
    if candidate.get("output") is not None:
        return None
    failures = candidate.get("failures")
    if isinstance(failures, list) and failures:
        return {
            "id": str(candidate.get("id", "unknown")),
            "status": "provider_failure",
            "metrics": None,
            "concise_notes": [str(failures[0])],
        }
    return None


async def _judge_study(case: dict[str, object], output: object) -> StudyJudgeResult:
    return await generate_structured(
        messages=[
            {"role": "system", "content": STUDY_JUDGE_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "requested_topic": case["topic"],
                        "requested_level": case["level"],
                        "generated_lesson": output,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_model=StudyJudgeResult,
        schema_name="study_evaluation_judge",
        output_label="Study judge result",
        allow_gemini_fallback=True,
    )


async def _judge_interview(
    case: dict[str, object], output: object
) -> InterviewJudgeResult:
    return await generate_structured(
        messages=[
            {"role": "system", "content": INTERVIEW_JUDGE_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "job_description": case["job_description"],
                        "resume_text": case["resume_text"],
                        "linkedin_text": case["linkedin_text"],
                        "cover_letter_text": case["cover_letter_text"],
                        "generated_analysis": output,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_model=InterviewJudgeResult,
        schema_name="interview_evaluation_judge",
        output_label="Interview Coach judge result",
        allow_gemini_fallback=True,
    )


async def _judge_rag(
    case: dict[str, object], candidate: dict[str, object]
) -> RagJudgeResult:
    retrieval = cast(dict[str, object], candidate["retrieval"])
    generation = cast(dict[str, object], candidate["generation"])
    wanted_indexes = {
        int(value) for value in cast(list[int], retrieval["retrieved_chunk_indexes"])
    }
    from app.rag import chunk_pages

    chunks = chunk_pages(
        [
            (int(page["page_number"]), str(page["text"]))
            for page in cast(list[dict[str, object]], case["pages"])
        ]
    )
    context = [
        {"page_number": chunk.page_number, "text": chunk.text}
        for chunk in chunks
        if chunk.chunk_index in wanted_indexes
    ]
    return await generate_structured(
        messages=[
            {"role": "system", "content": RAG_JUDGE_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "requested_topic": case["topic"],
                        "requested_query": case["query"],
                        "requested_level": case["level"],
                        "intentionally_unsupported": case["unsupported"],
                        "retrieved_context": context,
                        "generated_grounded_result": generation["output"],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_model=RagJudgeResult,
        schema_name="rag_evaluation_judge",
        output_label="RAG judge result",
        allow_gemini_fallback=True,
    )


def _judge_telemetry(
    capture: ProviderLogCapture, *, success: bool
) -> dict[str, object]:
    raw = capture.summary(success=success)
    return {
        "judge_primary_provider": "groq",
        "groq_judge_call_count": raw["groq_call_count"],
        "groq_final_judge_result": raw["groq_final_result"],
        "gemini_judge_fallback_used": raw["gemini_fallback_used"],
        "gemini_judge_call_count": raw["gemini_call_count"],
        "final_judge_provider": raw["final_provider"],
        "final_judge_success": raw["final_success"],
    }


def _judge_not_run_telemetry() -> dict[str, object]:
    return {
        "judge_primary_provider": "groq",
        "groq_judge_call_count": 0,
        "groq_final_judge_result": "not_run",
        "gemini_judge_fallback_used": False,
        "gemini_judge_call_count": 0,
        "final_judge_provider": None,
        "final_judge_success": False,
    }


async def run_judging(
    candidates: dict[str, object],
    rag_candidates: dict[str, object] | None = None,
) -> tuple[dict[str, object], int]:
    results: dict[str, object] = {"study": [], "interview_coach": [], "rag": []}
    processing_failures = 0
    study_cases = {str(case["id"]): case for case in load_study_cases()}
    interview_cases = {str(case["id"]): case for case in load_interview_cases()}

    for area, cases, judge, classifier in (
        ("study", study_cases, _judge_study, classify_study),
        (
            "interview_coach",
            interview_cases,
            _judge_interview,
            classify_interview,
        ),
    ):
        area_results = cast(list[dict[str, object]], results[area])
        area_candidates = cast(list[dict[str, object]], candidates[area])
        for candidate in area_candidates:
            case_id = str(candidate.get("id", "unknown"))
            print(f"Judging {area.replace('_', ' ').title()}: {case_id}", flush=True)
            skipped = _provider_failure(candidate)
            if skipped:
                skipped["judge_provider_telemetry"] = _judge_not_run_telemetry()
                area_results.append(skipped)
                continue
            if case_id not in cases or candidate.get("output") is None:
                area_results.append(
                    {
                        "id": case_id,
                        "status": "judge_failure",
                        "metrics": None,
                        "concise_notes": ["Candidate or matching synthetic case is missing."],
                        "judge_provider_telemetry": _judge_not_run_telemetry(),
                    }
                )
                processing_failures += 1
                continue

            capture = ProviderLogCapture()
            try:
                with capture:
                    metrics = await judge(cases[case_id], candidate["output"])
                status = classifier(metrics)
                area_results.append(
                    {
                        "id": case_id,
                        "status": status,
                        "metrics": metrics.model_dump(mode="json", exclude={"concise_notes"}),
                        "concise_notes": metrics.concise_notes,
                        "deterministic_failures": candidate.get("failures", []),
                        "judge_provider_telemetry": _judge_telemetry(
                            capture, success=True
                        ),
                    }
                )
            except AIGenerationError as error:
                area_results.append(
                    {
                        "id": case_id,
                        "status": "judge_failure",
                        "metrics": None,
                        "concise_notes": [str(error)],
                        "judge_provider_telemetry": _judge_telemetry(
                            capture, success=False
                        ),
                    }
                )
                processing_failures += 1

    if rag_candidates is not None:
        rag_cases = {str(case["id"]): case for case in load_rag_cases()}
        rag_results = cast(list[dict[str, object]], results["rag"])
        for candidate in cast(list[dict[str, object]], rag_candidates["rag"]):
            case_id = str(candidate.get("id", "unknown"))
            print(f"Judging RAG: {case_id}", flush=True)
            generation = candidate.get("generation")
            if not isinstance(generation, dict) or generation.get("output") is None:
                raw_failures = generation.get("failures", []) if isinstance(generation, dict) else []
                retrieval = candidate.get("retrieval")
                if not raw_failures and isinstance(retrieval, dict):
                    raw_failures = retrieval.get("failures", [])
                rag_results.append(
                    {
                        "id": case_id,
                        "status": "provider_failure",
                        "metrics": None,
                        "concise_notes": [str(raw_failures[0]) if raw_failures else "RAG generation did not complete."],
                        "judge_provider_telemetry": _judge_not_run_telemetry(),
                    }
                )
                continue
            if case_id not in rag_cases:
                rag_results.append(
                    {
                        "id": case_id,
                        "status": "judge_failure",
                        "metrics": None,
                        "concise_notes": ["Matching synthetic RAG case is missing."],
                        "judge_provider_telemetry": _judge_not_run_telemetry(),
                    }
                )
                processing_failures += 1
                continue
            capture = ProviderLogCapture()
            try:
                with capture:
                    metrics = await _judge_rag(rag_cases[case_id], candidate)
                rag_results.append(
                    {
                        "id": case_id,
                        "status": classify_rag(
                            metrics, unsupported=bool(rag_cases[case_id]["unsupported"])
                        ),
                        "metrics": metrics.model_dump(mode="json", exclude={"concise_notes"}),
                        "concise_notes": metrics.concise_notes,
                        "retrieval_failures": cast(dict[str, object], candidate["retrieval"]).get("failures", []),
                        "judge_provider_telemetry": _judge_telemetry(
                            capture, success=True
                        ),
                    }
                )
            except (AIGenerationError, KeyError, TypeError, ValueError) as error:
                rag_results.append(
                    {
                        "id": case_id,
                        "status": "judge_failure",
                        "metrics": None,
                        "concise_notes": [str(error)],
                        "judge_provider_telemetry": _judge_telemetry(
                            capture, success=False
                        ),
                    }
                )
                processing_failures += 1

    return results, processing_failures


def write_judge_results(
    results: dict[str, object], path: Path = JUDGE_RESULTS_PATH
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def print_summary(results: dict[str, object], output_path: Path) -> None:
    all_results = cast(list[dict[str, object]], results["study"]) + cast(
        list[dict[str, object]], results["interview_coach"]
    ) + cast(list[dict[str, object]], results.get("rag", []))
    for status in ("good", "review", "poor", "provider_failure", "judge_failure"):
        count = sum(result["status"] == status for result in all_results)
        print(f"{status.replace('_', ' ').title()}: {count}")
    print(f"\nJudge results:\n{output_path.as_posix()}")


async def main(
    *,
    candidates_path: Path = CANDIDATES_PATH,
    output_path: Path = JUDGE_RESULTS_PATH,
    rag_path: Path | None = None,
) -> int:
    try:
        candidates = load_candidates(candidates_path)
    except CandidateArtifactError as error:
        print(f"Judge evaluation cannot start: {error}")
        return 1

    load_environment()
    if not has_groq_configuration():
        print(
            "Judge evaluation cannot start: AI is not configured. "
            "Add GROQ_API_KEY to .env and try again."
        )
        return 1

    rag_candidates = None
    if rag_path is not None:
        try:
            rag_candidates = load_rag_candidates(rag_path)
        except CandidateArtifactError as error:
            print(f"Judge evaluation cannot start: {error}")
            return 1

    print("Evaluation v2 - LLM-as-a-judge\n")
    results, processing_failures = await run_judging(candidates, rag_candidates)
    written_path = write_judge_results(results, output_path)
    print_summary(results, written_path)
    return 1 if processing_failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(rag_path=RAG_RESULTS_PATH)))
