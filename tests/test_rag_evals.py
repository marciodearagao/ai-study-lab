import asyncio
import json

import pytest
from pydantic import ValidationError

from app.rag import GroundedLesson, RetrievedChunk, SourceReference
from app.lessons import Lesson
from app.telemetry import record_fallback, record_provider_call, record_provider_result
from evals.rag_checks import evaluate_retrieval, load_rag_cases
from evals.run_judge import RagJudgeResult, classify_rag, run_judging
from evals.run_rag import run_rag_evaluations, write_rag_results
from evals.study_checks import load_study_cases


def ranked_chunks(case: dict[str, object]) -> list[RetrievedChunk]:
    pages = {int(page["page_number"]): str(page["text"]) for page in case["pages"]}
    expected = list(case["expected_pages"])
    ordered_pages = expected + [page for page in pages if page not in expected]
    return [
        RetrievedChunk(pages[page], page, index)
        for index, page in enumerate(ordered_pages[:4])
    ]


def grounded_lesson() -> GroundedLesson:
    lesson = Lesson.model_validate(load_study_cases()[0]["lesson"])
    return GroundedLesson(
        lesson=lesson,
        sources=(SourceReference(page_number=1, excerpt="Synthetic source."),),
    )


def test_supported_rag_cases_pass_deterministic_retrieval_checks() -> None:
    for case in load_rag_cases():
        if case["unsupported"]:
            continue
        result = evaluate_retrieval(case, ranked_chunks(case))
        assert result.passed, (case["id"], result.failures)


def test_irrelevant_top_results_are_detected() -> None:
    case = load_rag_cases()[0]
    chunks = ranked_chunks(case)
    result = evaluate_retrieval(case, [chunks[2], chunks[3], chunks[0]])

    assert not result.passed
    assert "Irrelevant passages dominated" in " ".join(result.failures)


def test_unsupported_case_requires_no_known_expected_passage() -> None:
    case = load_rag_cases()[-1]
    result = evaluate_retrieval(case, ranked_chunks(case))

    assert result.passed
    assert result.checks["unsupported_case_recognized"] is True


def test_live_rag_runner_uses_mocked_retrieval_and_generation() -> None:
    retrieval_calls = 0
    generation_calls = 0

    def fake_retriever(chunks, query):
        nonlocal retrieval_calls
        retrieval_calls += 1
        case = next(case for case in load_rag_cases() if case["query"] == query)
        by_page = {chunk.page_number: chunk for chunk in chunks}
        wanted = list(case["expected_pages"]) or list(by_page)
        wanted += [page for page in by_page if page not in wanted]
        return [
            RetrievedChunk(by_page[page].text, page, by_page[page].chunk_index)
            for page in wanted[:4]
        ]

    async def fake_generator(topic, level, retrieved):
        nonlocal generation_calls
        generation_calls += 1
        record_provider_call("groq")
        record_provider_result("groq", success=True)
        return grounded_lesson()

    artifact, failures = asyncio.run(
        run_rag_evaluations(retriever=fake_retriever, generator=fake_generator)
    )

    assert failures == 0
    assert retrieval_calls == generation_calls == 4
    assert len(artifact["rag"]) == 4
    assert artifact["rag"][0]["provider_telemetry"]["groq_call_count"] == 1


def test_live_rag_runner_records_gemini_fallback_telemetry() -> None:
    case_map = {str(case["query"]): case for case in load_rag_cases()}

    def fake_retriever(chunks, query):
        case = case_map[query]
        by_page = {chunk.page_number: chunk for chunk in chunks}
        wanted = list(case["expected_pages"]) or list(by_page)
        wanted += [page for page in by_page if page not in wanted]
        return [
            RetrievedChunk(by_page[page].text, page, by_page[page].chunk_index)
            for page in wanted[:4]
        ]

    async def fallback_generator(topic, level, retrieved):
        record_provider_call("groq")
        record_provider_result("groq", success=False, error_category="provider_error")
        record_provider_call("groq")
        record_provider_result("groq", success=False, error_category="provider_error")
        record_fallback()
        record_provider_call("gemini")
        record_provider_result("gemini", success=True)
        return grounded_lesson()

    artifact, failures = asyncio.run(
        run_rag_evaluations(
            retriever=fake_retriever, generator=fallback_generator
        )
    )
    telemetry = artifact["rag"][0]["provider_telemetry"]

    assert failures == 0
    assert telemetry["groq_call_count"] == 2
    assert telemetry["gemini_used"] is True
    assert telemetry["gemini_call_count"] == 1
    assert telemetry["final_provider"] == "gemini"


def test_rag_result_artifact_contains_ids_metadata_and_checks(tmp_path) -> None:
    result = {
        "rag": [
            {
                "id": "synthetic",
                "retrieval": {
                    "retrieved_pages": [2],
                    "retrieved_chunk_indexes": [1],
                    "checks": {"expected_page_in_top_k": True},
                    "failures": [],
                },
            }
        ]
    }
    path = write_rag_results(result, tmp_path / "rag_results.json")
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["rag"][0]["id"] == "synthetic"
    assert saved["rag"][0]["retrieval"]["retrieved_pages"] == [2]


async def fake_rag_judge(**kwargs):
    if kwargs["response_model"] is RagJudgeResult:
        return RagJudgeResult(
            context_relevance=5,
            groundedness=5,
            unsupported_claim_risk=1,
            source_attribution_quality=4,
            concise_notes=["Claims match the retrieved passages."],
        )
    raise AssertionError("Unexpected judge model")


def rag_candidate(*, generated: bool = True) -> dict[str, object]:
    case = load_rag_cases()[0]
    retrieved = ranked_chunks(case)
    return {
        "id": case["id"],
        "retrieval": {
            "status": "pass",
            "retrieved_chunk_indexes": [chunk.chunk_index for chunk in retrieved],
            "failures": [],
        },
        "generation": {
            "status": "success" if generated else "provider_failure",
            "output": grounded_lesson().model_dump(mode="json") if generated else None,
            "failures": [] if generated else ["Temporary provider failure."],
        },
    }


def test_rag_judge_uses_mocked_groq_only(monkeypatch) -> None:
    monkeypatch.setattr("evals.run_judge.generate_structured", fake_rag_judge)
    empty = {"study": [], "interview_coach": []}

    results, failures = asyncio.run(
        run_judging(empty, {"rag": [rag_candidate()]})
    )

    assert failures == 0
    assert results["rag"][0]["status"] == "good"
    assert results["rag"][0]["metrics"]["groundedness"] == 5


def test_rag_judge_skips_provider_failure(monkeypatch) -> None:
    async def unexpected_judge(**_kwargs):
        raise AssertionError("Provider failure was sent to the judge.")

    monkeypatch.setattr("evals.run_judge.generate_structured", unexpected_judge)
    results, failures = asyncio.run(
        run_judging(
            {"study": [], "interview_coach": []},
            {"rag": [rag_candidate(generated=False)]},
        )
    )

    assert failures == 0
    assert results["rag"][0]["status"] == "provider_failure"


@pytest.mark.parametrize("score", [0, 6, 3.5, "5"])
def test_invalid_rag_judge_metric_is_rejected(score) -> None:
    with pytest.raises(ValidationError):
        RagJudgeResult(
            context_relevance=score,
            groundedness=5,
            unsupported_claim_risk=1,
            source_attribution_quality=4,
            concise_notes=["Short note."],
        )


def test_unsupported_case_rewards_safe_limitation() -> None:
    metrics = RagJudgeResult(
        context_relevance=1,
        groundedness=5,
        unsupported_claim_risk=1,
        source_attribution_quality=5,
        concise_notes=["The lesson correctly limits unsupported claims."],
    )

    assert classify_rag(metrics, unsupported=True) == "good"
    assert classify_rag(metrics) == "poor"
