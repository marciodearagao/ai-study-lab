"""Run the complete Evaluation workflow in sequence."""

import asyncio
from collections.abc import Callable, Sequence

from evals import report, run, run_judge, run_live, run_rag


Step = tuple[str, Callable[[], int]]


def _run_live() -> int:
    return asyncio.run(run_live.main())


def _run_rag() -> int:
    return asyncio.run(run_rag.main())


def _run_judge() -> int:
    return asyncio.run(run_judge.main(rag_path=run_judge.RAG_RESULTS_PATH))


def _build_report() -> int:
    return report.main(rag_path=report.RAG_RESULTS_PATH)


STEPS: tuple[Step, ...] = (
    ("Deterministic evaluation", run.main),
    ("Live evaluation", _run_live),
    ("RAG evaluation", _run_rag),
    ("LLM judge", _run_judge),
    ("Building report", _build_report),
)


def main(*, steps: Sequence[Step] = STEPS) -> int:
    print("Evaluation suite")
    print("This evaluation may make live Groq/Gemini API calls.")

    total = len(steps)
    for index, (name, action) in enumerate(steps, start=1):
        print(f"\n[{index}/{total}] {name}...")
        try:
            result = action()
        except Exception:
            print(f"Evaluation stopped: {name} failed.")
            raise
        if result != 0:
            print(f"Evaluation stopped: {name} failed.")
            return result if result > 0 else 1

    print("\nEvaluation complete.")
    print(f"Report: {report.REPORT_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
