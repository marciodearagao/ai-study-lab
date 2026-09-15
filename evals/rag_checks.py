"""Deterministic checks for RAG retrieval results."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.rag import DEFAULT_TOP_K, RetrievedChunk


CASES_PATH = Path(__file__).with_name("rag_cases.json")


@dataclass(frozen=True)
class RetrievalCheckResult:
    case_id: str
    retrieved_pages: tuple[int, ...]
    retrieved_chunk_indexes: tuple[int, ...]
    checks: dict[str, bool]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def load_rag_cases(path: Path = CASES_PATH) -> list[dict[str, object]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("RAG evaluation cases must be a list.")
    return cast(list[dict[str, object]], cases)


def evaluate_retrieval(
    case: dict[str, object], retrieved: list[RetrievedChunk]
) -> RetrievalCheckResult:
    expected_pages = {int(page) for page in cast(list[int], case["expected_pages"])}
    irrelevant_pages = {
        int(page) for page in cast(list[int], case["irrelevant_pages"])
    }
    expected_concepts = [
        str(value).casefold()
        for value in cast(list[str], case["expected_concepts"])
    ]
    unsupported = bool(case["unsupported"])
    retrieved_pages = tuple(chunk.page_number for chunk in retrieved)
    retrieved_indexes = tuple(chunk.chunk_index for chunk in retrieved)
    combined_text = " ".join(chunk.text for chunk in retrieved).casefold()
    top_window = retrieved_pages[: min(2, len(retrieved_pages))]

    checks: dict[str, bool] = {
        "result_count_within_top_k": 0 < len(retrieved) <= DEFAULT_TOP_K,
        "metadata_preserved": all(
            chunk.page_number >= 1 and chunk.chunk_index >= 0 for chunk in retrieved
        ),
    }
    if unsupported:
        checks.update(
            {
                "unsupported_case_recognized": not expected_pages
                and not expected_concepts,
                "no_known_relevant_passage_claimed": not expected_pages,
            }
        )
    else:
        checks.update(
            {
                "expected_page_in_top_k": bool(expected_pages & set(retrieved_pages)),
                "expected_concepts_in_top_k": all(
                    concept in combined_text for concept in expected_concepts
                ),
                "relevant_passage_ranked_first": bool(retrieved_pages)
                and retrieved_pages[0] in expected_pages,
                "irrelevant_passages_do_not_dominate_top_results": sum(
                    page in irrelevant_pages for page in top_window
                )
                <= len(top_window) // 2,
            }
        )

    messages = {
        "result_count_within_top_k": "Retrieval returned no results or exceeded the internal top-k.",
        "metadata_preserved": "Retrieved page or chunk metadata is invalid.",
        "unsupported_case_recognized": "The unsupported fixture has an invalid expectation.",
        "no_known_relevant_passage_claimed": "An unsupported fixture declared a relevant passage.",
        "expected_page_in_top_k": "No expected relevant page appeared in top-k.",
        "expected_concepts_in_top_k": "Expected concepts were absent from retrieved passages.",
        "relevant_passage_ranked_first": "The expected relevant passage was not ranked first.",
        "irrelevant_passages_do_not_dominate_top_results": "Irrelevant passages dominated the highest-ranked results.",
    }
    failures = tuple(messages[name] for name, passed in checks.items() if not passed)
    return RetrievalCheckResult(
        case_id=str(case["id"]),
        retrieved_pages=retrieved_pages,
        retrieved_chunk_indexes=retrieved_indexes,
        checks=checks,
        failures=failures,
    )
