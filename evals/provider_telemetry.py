"""Expose the shared request-scoped provider telemetry to evaluation runners."""

from app.telemetry import provider_snapshot, telemetry_scope


class ProviderLogCapture:
    """Keep the existing evaluation interface over shared provider telemetry."""

    def __init__(self) -> None:
        self._scope = telemetry_scope()
        self._state = None

    def __enter__(self) -> "ProviderLogCapture":
        self._state = self._scope.__enter__()
        return self

    def __exit__(self, *_args: object) -> None:
        self._scope.__exit__(*_args)

    def summary(self, *, success: bool) -> dict[str, object]:
        if self._state is None:
            raise RuntimeError("Provider telemetry capture has not started.")
        raw = provider_snapshot(self._state)
        return {
            "primary_provider_attempted": True,
            "groq_call_count": raw["groq_calls"],
            "groq_final_result": raw["groq_final_result"],
            "gemini_fallback_used": raw["fallback_used"],
            "gemini_call_count": raw["gemini_calls"],
            "final_provider": raw["final_provider"],
            "final_success": success and raw["final_provider"] is not None,
        }
