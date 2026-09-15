"""Small request-scoped telemetry for local terminal diagnostics."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
from time import perf_counter
from typing import Iterator, Literal
from uuid import uuid4


ProviderName = Literal["groq", "gemini"]
logger = logging.getLogger("uvicorn.error")


@dataclass
class TelemetryState:
    groq_calls: int = 0
    gemini_calls: int = 0
    groq_final_result: str = "not_run"
    gemini_final_result: str = "not_run"
    final_provider: ProviderName | None = None
    fallback_used: bool = False
    error_category: str | None = None
    retrieved_pages: list[int] = field(default_factory=list)
    retrieved_chunk_count: int = 0


_current_state: ContextVar[TelemetryState | None] = ContextVar(
    "ai_study_lab_telemetry", default=None
)


@contextmanager
def telemetry_scope() -> Iterator[TelemetryState]:
    state = TelemetryState()
    token = _current_state.set(state)
    try:
        yield state
    finally:
        _current_state.reset(token)


def start_request() -> tuple[str, float]:
    return uuid4().hex[:12], perf_counter()


def record_provider_call(provider: ProviderName) -> None:
    state = _current_state.get()
    if state is None:
        return
    if provider == "groq":
        state.groq_calls += 1
    else:
        state.gemini_calls += 1


def record_provider_result(
    provider: ProviderName, *, success: bool, error_category: str | None = None
) -> None:
    state = _current_state.get()
    if state is None:
        return
    if success:
        state.final_provider = provider
    if provider == "groq":
        state.groq_final_result = "success" if success else error_category or "failed"
    else:
        state.gemini_final_result = "success" if success else error_category or "failed"
    if not success and error_category:
        state.error_category = error_category


def record_fallback() -> None:
    state = _current_state.get()
    if state is not None:
        state.fallback_used = True


def record_error_category(category: str) -> None:
    state = _current_state.get()
    if state is not None:
        state.error_category = category


def record_retrieval(page_numbers: list[int], chunk_count: int) -> None:
    state = _current_state.get()
    if state is None:
        return
    state.retrieved_pages = list(dict.fromkeys(page_numbers))
    state.retrieved_chunk_count = chunk_count


def provider_snapshot(state: TelemetryState) -> dict[str, object]:
    return {
        "primary_provider": "groq",
        "final_provider": state.final_provider,
        "fallback_used": state.fallback_used,
        "groq_calls": state.groq_calls,
        "gemini_calls": state.gemini_calls,
        "groq_final_result": state.groq_final_result,
        "gemini_final_result": state.gemini_final_result,
        "error_category": state.error_category,
    }


def emit_request_telemetry(
    *,
    state: TelemetryState,
    endpoint: str,
    started_at: float,
    status_code: int,
    request_id: str | None = None,
) -> None:
    success = status_code < 400
    category = None if success else state.error_category or f"http_{status_code}"
    fields: list[tuple[str, object]] = [
        ("request_id", request_id or uuid4().hex[:12]),
        ("endpoint", endpoint),
        ("duration_ms", max(0, round((perf_counter() - started_at) * 1000))),
        ("success", str(success).lower()),
        ("error_category", category or "none"),
        ("primary_provider", "groq"),
        ("final_provider", state.final_provider or "none"),
        ("fallback_used", str(state.fallback_used).lower()),
        ("groq_calls", state.groq_calls),
        ("gemini_calls", state.gemini_calls),
    ]
    if endpoint == "/api/lessons/pdf":
        fields.extend(
            [
                ("retrieved_pages", json.dumps(state.retrieved_pages, separators=(",", ":"))),
                ("retrieved_chunk_count", state.retrieved_chunk_count),
            ]
        )
    logger.info("telemetry %s", " ".join(f"{key}={value}" for key, value in fields))
