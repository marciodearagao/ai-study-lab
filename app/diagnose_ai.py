"""Run one developer diagnostic through the normal AI lesson flow."""

import argparse
import logging

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app


TELEMETRY_LOGGER = "uvicorn.error"


class _TelemetryHandler(logging.Handler):
    """Capture the final safe telemetry record emitted by the lesson request."""

    def __init__(self) -> None:
        super().__init__()
        self.message: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("telemetry ") and "endpoint=/api/lessons " in message:
            self.message = message


def _request_lesson(topic: str, level: str) -> tuple[object, str | None]:
    logger = logging.getLogger(TELEMETRY_LOGGER)
    handler = _TelemetryHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    if not logger.isEnabledFor(logging.INFO):
        logger.setLevel(logging.INFO)
    try:
        response = TestClient(app).post(
            "/api/lessons",
            json={"topic": topic, "level": level},
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    return response, handler.message


def _provider_fields(message: str | None) -> dict[str, str]:
    if not message:
        return {}
    fields: dict[str, str] = {}
    for item in message.removeprefix("telemetry ").split():
        if "=" in item:
            key, value = item.split("=", 1)
            fields[key] = value
    return fields


def diagnose(topic: str, level: str) -> int:
    load_dotenv()
    print("AI diagnostic")
    print()
    print("Primary provider: Groq")

    response, telemetry_message = _request_lesson(topic, level)
    fields = _provider_fields(telemetry_message)
    final_provider = fields.get("final_provider", "none")
    fallback_used = fields.get("fallback_used", "false")

    print(f"Final provider: {final_provider.title() if final_provider != 'none' else 'none'}")
    print(f"Fallback used: {'yes' if fallback_used == 'true' else 'no'}")

    if response.status_code == 200 and final_provider in {"groq", "gemini"}:
        print("Result: PASS")
        return 0

    print("Result: FAIL")
    if response.status_code == 200:
        reason = "provider outcome telemetry unavailable"
    else:
        category = fields.get("error_category", "none")
        reason = category if category != "none" else f"http_{response.status_code}"
    print(f"Reason: {reason}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", nargs="?", default="Python decorators")
    parser.add_argument(
        "--level",
        choices=("Basic", "Intermediate", "Advanced"),
        default="Basic",
    )
    args = parser.parse_args()
    return diagnose(args.topic, args.level)


if __name__ == "__main__":
    raise SystemExit(main())
