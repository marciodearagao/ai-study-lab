"""Run live RAG retrieval and grounded generation against synthetic fixtures."""

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, cast

from app.ai import AIGenerationError
from app.rag import (
    GroundedLesson,
    RetrievalError,
    RetrievedChunk,
    TextChunk,
    chunk_pages,
    generate_grounded_lesson,
    retrieve_chunks,
)
from evals.rag_checks import evaluate_retrieval, load_rag_cases
from evals.provider_telemetry import ProviderLogCapture
from evals.run_live import has_groq_configuration, load_environment


RAG_RESULTS_PATH = Path(__file__).with_name("results") / "rag_results.json"
Retriever = Callable[[list[TextChunk], str], list[RetrievedChunk]]
Generator = Callable[[str, str, list[RetrievedChunk]], Awaitable[GroundedLesson]]


async def run_rag_evaluations(
    *,
    retriever: Retriever = retrieve_chunks,
    generator: Generator = generate_grounded_lesson,
) -> tuple[dict[str, object], int]:
    artifact: dict[str, object] = {"rag": []}
    failures = 0
    entries = cast(list[dict[str, object]], artifact["rag"])

    for case in load_rag_cases():
        case_id = str(case["id"])
        print(f"Running RAG: {case_id}", flush=True)
        chunks = chunk_pages(
            [
                (int(page["page_number"]), str(page["text"]))
                for page in cast(list[dict[str, object]], case["pages"])
            ]
        )
        try:
            retrieved = retriever(chunks, str(case["query"]))
            retrieval = evaluate_retrieval(case, retrieved)
        except RetrievalError as error:
            entries.append(
                {
                    "id": case_id,
                    "topic": case["topic"],
                    "unsupported": case["unsupported"],
                    "retrieval": {"status": "failure", "checks": {}, "failures": [str(error)]},
                    "generation": {"status": "not_run", "output": None, "failures": []},
                    "provider_telemetry": None,
                }
            )
            failures += 1
            continue

        started = perf_counter()
        grounded: GroundedLesson | None = None
        generation_failures: list[str] = []
        with ProviderLogCapture() as capture:
            try:
                grounded = await generator(
                    str(case["topic"]), str(case["level"]), retrieved
                )
            except (AIGenerationError, RetrievalError) as error:
                generation_failures.append(str(error))
        elapsed = perf_counter() - started

        success = grounded is not None
        telemetry = capture.summary(success=success)
        telemetry["gemini_used"] = telemetry.pop("gemini_fallback_used")
        telemetry["elapsed_seconds"] = round(elapsed, 3)
        entry = {
            "id": case_id,
            "topic": case["topic"],
            "level": case["level"],
            "unsupported": case["unsupported"],
            "retrieval": {
                "status": "pass" if retrieval.passed else "fail",
                "retrieved_pages": list(retrieval.retrieved_pages),
                "retrieved_chunk_indexes": list(retrieval.retrieved_chunk_indexes),
                "checks": retrieval.checks,
                "failures": list(retrieval.failures),
            },
            "generation": {
                "status": "success" if success else "provider_failure",
                "output": grounded.model_dump(mode="json") if grounded else None,
                "failures": generation_failures,
            },
            "provider_telemetry": telemetry,
        }
        entries.append(entry)
        if not retrieval.passed or not success:
            failures += 1

    return artifact, failures


def write_rag_results(
    results: dict[str, object], path: Path = RAG_RESULTS_PATH
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


async def main(*, output_path: Path = RAG_RESULTS_PATH) -> int:
    load_environment()
    if not has_groq_configuration():
        print("RAG evaluation cannot start: AI is not configured. Add GROQ_API_KEY to .env and try again.")
        return 1
    print("Evaluation - live RAG\n")
    results, failures = await run_rag_evaluations()
    written = write_rag_results(results, output_path)
    cases = cast(list[dict[str, object]], results["rag"])
    passed = len(cases) - failures
    print(f"\nSummary\n{passed} passed\n{failures} failed")
    print(f"\nRAG results:\n{written.as_posix()}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
