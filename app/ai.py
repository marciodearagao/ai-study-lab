import asyncio
import json
import logging
import os
import ssl
from typing import TypeVar

import groq
from groq import AsyncGroq
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.telemetry import record_fallback, record_provider_call, record_provider_result


ModelT = TypeVar("ModelT", bound=BaseModel)
logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
MAX_PROVIDER_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.25
GEMINI_FALLBACK_CATEGORIES = frozenset(
    {
        "structured_output_rejection",
        "pydantic_validation",
        "rate_limit",
        "timeout",
        "network",
        "provider_error",
    }
)


class AIGenerationError(Exception):
    """A safe categorized error that can be shown to the user."""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        category: str = "other_api_error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category


def _error_body_text(error: Exception) -> str:
    """Return provider error text for classification only; never log this value."""
    body = getattr(error, "body", None)
    return f"{error} {body!r}".casefold()


def _provider_code(error: Exception) -> str | None:
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return None
    details = body.get("error", body)
    if not isinstance(details, dict):
        return None
    code = details.get("code") or details.get("type")
    return str(code)[:80] if code else None


def _request_id(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {})
    return headers.get("x-request-id") or headers.get("request-id")


def _validation_summary(error: ValidationError) -> list[dict[str, object]]:
    return [
        {
            "location": item["loc"],
            "type": item["type"],
            "reason": str(item.get("ctx", {}).get("error", ""))[:120],
        }
        for item in error.errors(include_url=False, include_context=True, include_input=False)
    ]


def _log_failed_generation_validation(
    error: groq.APIError,
    *,
    response_model: type[BaseModel],
    model: str,
) -> None:
    body = getattr(error, "body", None)
    details = body.get("error", body) if isinstance(body, dict) else None
    failed = details.get("failed_generation") if isinstance(details, dict) else None
    if not isinstance(failed, str):
        return
    try:
        parsed = json.loads(failed)
        response_model.model_validate(parsed)
    except json.JSONDecodeError as validation_error:
        logger.error(
            "Groq failed generation diagnostic model=%s result=invalid_json line=%s column=%s",
            model,
            validation_error.lineno,
            validation_error.colno,
        )
    except ValidationError as validation_error:
        logger.error(
            "Groq failed generation diagnostic model=%s result=pydantic_validation errors=%s",
            model,
            _validation_summary(validation_error),
        )


def _is_certificate_failure(error: Exception) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if "certificate_verify_failed" in str(current).casefold():
            return True
        current = current.__cause__ or current.__context__
    return False


def _classify_bad_request(error: groq.BadRequestError, output_label: str) -> AIGenerationError:
    detail = _error_body_text(error)
    model_markers = (
        "model_not_found",
        "model_decommissioned",
        "model does not exist",
        "model is not available",
        "model is unavailable",
        "invalid model",
    )
    schema_markers = (
        "json schema",
        "json_schema",
        "response_format",
        "failed_generation",
        "generated json",
        "structured output",
        "schema validation",
    )
    schema_configuration_markers = (
        "invalid schema for response_format",
        "schema is invalid",
        "schema must",
        "not permitted",
        "unsupported schema",
    )
    if any(marker in detail for marker in model_markers):
        return AIGenerationError(
            "The configured Groq model is invalid or unavailable. Check GROQ_MODEL in .env.",
            category="invalid_model",
        )
    if any(marker in detail for marker in schema_configuration_markers):
        return AIGenerationError(
            "The AI response configuration is invalid. Check the server log.",
            category="schema_configuration",
        )
    if any(marker in detail for marker in schema_markers):
        return AIGenerationError(
            f"The AI returned an invalid {output_label} format. Please try again.",
            category="structured_output_rejection",
        )
    return AIGenerationError(
        "Groq rejected the AI request. Check the server log for the error category.",
        category="request_rejected",
    )


def _classify_provider_error(error: groq.APIError, output_label: str) -> AIGenerationError:
    if isinstance(error, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return AIGenerationError(
            "Groq authentication failed. Check GROQ_API_KEY in .env and restart the app.",
            category="authentication",
        )
    if isinstance(error, groq.NotFoundError):
        return AIGenerationError(
            "The configured Groq model is invalid or unavailable. Check GROQ_MODEL in .env.",
            category="invalid_model",
        )
    if isinstance(error, groq.RateLimitError):
        return AIGenerationError(
            "Groq is rate-limited. Please try again shortly.",
            status_code=429,
            category="rate_limit",
        )
    if isinstance(error, groq.InternalServerError) or (
        getattr(error, "status_code", 0) and getattr(error, "status_code", 0) >= 500
    ):
        return AIGenerationError(
            "Groq is temporarily unavailable. Please try again shortly.",
            status_code=503,
            category="provider_error",
        )
    if isinstance(error, groq.APITimeoutError):
        return AIGenerationError(
            "The AI request timed out. Please try again shortly.",
            status_code=503,
            category="timeout",
        )
    if isinstance(error, groq.APIConnectionError):
        return AIGenerationError(
            "The AI service could not be reached. Check your connection and try again.",
            status_code=503,
            category="network",
        )
    if isinstance(error, groq.BadRequestError):
        return _classify_bad_request(error, output_label)
    return AIGenerationError(
        "Groq could not complete the request. Please try again.",
        category="other_api_error",
    )


def _is_transient(error: groq.APIError) -> bool:
    if isinstance(error, groq.APIConnectionError) and _is_certificate_failure(error):
        return False
    status_code = getattr(error, "status_code", 0) or 0
    return isinstance(
        error,
        (
            groq.APITimeoutError,
            groq.APIConnectionError,
            groq.RateLimitError,
            groq.InternalServerError,
        ),
    ) or status_code >= 500


def _log_provider_error(
    error: groq.APIError,
    *,
    category: str,
    model: str,
    attempt: int,
) -> None:
    logger.error(
        "Groq request failed category=%s model=%s exception=%s status=%s "
        "provider_code=%s request_id=%s attempt=%s/%s",
        category,
        model,
        type(error).__name__,
        getattr(error, "status_code", None),
        _provider_code(error),
        _request_id(error),
        attempt,
        MAX_PROVIDER_ATTEMPTS,
    )


async def _generate_with_groq(
    *,
    messages: list[dict[str, str]],
    response_model: type[ModelT],
    schema_name: str,
    output_label: str,
    retry_structured_output: bool = False,
    structured_retry_message: str | None = None,
) -> ModelT:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        record_provider_result("groq", success=False, error_category="configuration")
        raise AIGenerationError(
            "AI is not configured yet. Add GROQ_API_KEY to .env and restart the app.",
            status_code=503,
            category="configuration",
        )

    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    client = AsyncGroq(api_key=api_key, timeout=30, max_retries=0)
    structured_retry_used = False
    for attempt in range(1, MAX_PROVIDER_ATTEMPTS + 1):
        attempt_messages = messages
        if structured_retry_used and structured_retry_message:
            attempt_messages = [
                *messages,
                {"role": "system", "content": structured_retry_message},
            ]
        try:
            record_provider_call("groq")
            response = await client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=attempt_messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": response_model.model_json_schema(),
                    },
                },
            )
        except groq.APIError as error:
            classified = _classify_provider_error(error, output_label)
            record_provider_result(
                "groq", success=False, error_category=classified.category
            )
            _log_provider_error(error, category=classified.category, model=model, attempt=attempt)
            if classified.category == "structured_output_rejection":
                _log_failed_generation_validation(
                    error,
                    response_model=response_model,
                    model=model,
                )
            should_retry_structure = (
                retry_structured_output
                and classified.category == "structured_output_rejection"
            )
            if (_is_transient(error) or should_retry_structure) and attempt < MAX_PROVIDER_ATTEMPTS:
                if should_retry_structure:
                    structured_retry_used = True
                    logger.warning(
                        "Groq structured output retry scheduled category=%s model=%s "
                        "attempt=%s/%s",
                        classified.category,
                        model,
                        attempt,
                        MAX_PROVIDER_ATTEMPTS,
                    )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            if should_retry_structure:
                logger.error(
                    "Groq structured output retry exhausted category=%s model=%s "
                    "attempt=%s/%s",
                    classified.category,
                    model,
                    attempt,
                    MAX_PROVIDER_ATTEMPTS,
                )
            raise classified from error

        try:
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty structured response")
        except (IndexError, AttributeError, TypeError, ValueError) as error:
            record_provider_result(
                "groq", success=False, error_category="response_parsing"
            )
            logger.error(
                "Groq response parsing failed category=response_parsing model=%s exception=%s",
                model,
                type(error).__name__,
            )
            raise AIGenerationError(
                f"The AI returned an invalid {output_label} format. Please try again.",
                category="response_parsing",
            ) from error

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            record_provider_result("groq", success=False, error_category="invalid_json")
            logger.error(
                "Groq response parsing failed category=invalid_json model=%s line=%s column=%s",
                model,
                error.lineno,
                error.colno,
            )
            raise AIGenerationError(
                f"The AI returned an invalid {output_label} format. Please try again.",
                category="invalid_json",
            ) from error

        try:
            result = response_model.model_validate(parsed)
        except ValidationError as error:
            record_provider_result(
                "groq", success=False, error_category="pydantic_validation"
            )
            logger.error(
                "Groq response validation failed category=pydantic_validation model=%s "
                "attempt=%s/%s errors=%s",
                model,
                attempt,
                MAX_PROVIDER_ATTEMPTS,
                _validation_summary(error),
            )
            if retry_structured_output and attempt < MAX_PROVIDER_ATTEMPTS:
                structured_retry_used = True
                logger.warning(
                    "Groq structured output retry scheduled category=pydantic_validation "
                    "model=%s attempt=%s/%s",
                    model,
                    attempt,
                    MAX_PROVIDER_ATTEMPTS,
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            if retry_structured_output:
                logger.error(
                    "Groq structured output retry exhausted category=pydantic_validation "
                    "model=%s attempt=%s/%s",
                    model,
                    attempt,
                    MAX_PROVIDER_ATTEMPTS,
                )
            raise AIGenerationError(
                f"The AI returned an invalid {output_label} format. Please try again.",
                category="pydantic_validation",
            ) from error

        if structured_retry_used:
            logger.info(
                "Groq structured output retry succeeded model=%s attempt=%s/%s",
                model,
                attempt,
                MAX_PROVIDER_ATTEMPTS,
            )
        record_provider_result("groq", success=True)
        return result

    raise RuntimeError("structured generation attempt loop ended unexpectedly")


def _gemini_request_parts(
    messages: list[dict[str, str]],
) -> tuple[str | None, list[dict[str, object]]]:
    system_instruction = "\n\n".join(
        message["content"] for message in messages if message["role"] == "system"
    ) or None
    contents = [
        {
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        }
        for message in messages
        if message["role"] != "system"
    ]
    return system_instruction, contents


async def _generate_with_gemini(
    *,
    messages: list[dict[str, str]],
    response_model: type[ModelT],
    output_label: str,
) -> ModelT:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        record_provider_result(
            "gemini", success=False, error_category="gemini_configuration"
        )
        raise AIGenerationError(
            "The optional Gemini fallback is not configured.",
            status_code=503,
            category="gemini_configuration",
        )

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    system_instruction, contents = _gemini_request_parts(messages)
    async_client = None
    try:
        async_client = genai.Client(api_key=api_key).aio
        record_provider_call("gemini")
        response = await async_client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_json_schema=response_model.model_json_schema(),
            ),
        )
    except Exception as error:
        record_provider_result(
            "gemini", success=False, error_category="gemini_provider_error"
        )
        logger.error(
            "fallback_provider=gemini fallback_result=provider_error model=%s "
            "exception=%s status=%s",
            model,
            type(error).__name__,
            getattr(error, "status_code", getattr(error, "code", None)),
        )
        raise AIGenerationError(
            "The AI services could not complete the request. Please try again.",
            category="gemini_provider_error",
        ) from error
    finally:
        if async_client is not None:
            try:
                await async_client.aclose()
            except Exception as error:
                logger.warning(
                    "fallback_provider=gemini client_close=failed exception=%s",
                    type(error).__name__,
                )

    try:
        content = response.text
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty structured response")
        parsed = json.loads(content)
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        record_provider_result(
            "gemini", success=False, error_category="gemini_invalid_json"
        )
        logger.error(
            "fallback_provider=gemini fallback_result=invalid_json model=%s exception=%s",
            model,
            type(error).__name__,
        )
        raise AIGenerationError(
            f"The AI returned an invalid {output_label} format. Please try again.",
            category="gemini_invalid_json",
        ) from error

    try:
        result = response_model.model_validate(parsed)
    except ValidationError as error:
        record_provider_result(
            "gemini", success=False, error_category="gemini_pydantic_validation"
        )
        logger.error(
            "fallback_provider=gemini fallback_result=pydantic_validation model=%s errors=%s",
            model,
            _validation_summary(error),
        )
        raise AIGenerationError(
            f"The AI returned an invalid {output_label} format. Please try again.",
            category="gemini_pydantic_validation",
        ) from error
    record_provider_result("gemini", success=True)
    return result


async def generate_structured(
    *,
    messages: list[dict[str, str]],
    response_model: type[ModelT],
    schema_name: str,
    output_label: str,
    retry_structured_output: bool = False,
    structured_retry_message: str | None = None,
    allow_gemini_fallback: bool = False,
) -> ModelT:
    try:
        result = await _generate_with_groq(
            messages=messages,
            response_model=response_model,
            schema_name=schema_name,
            output_label=output_label,
            retry_structured_output=retry_structured_output,
            structured_retry_message=structured_retry_message,
        )
    except AIGenerationError as groq_error:
        if (
            not allow_gemini_fallback
            or groq_error.category not in GEMINI_FALLBACK_CATEGORIES
        ):
            raise
        if not os.getenv("GEMINI_API_KEY", "").strip():
            logger.warning(
                "primary_provider=groq groq_result=%s fallback_provider=gemini "
                "fallback_result=not_configured",
                groq_error.category,
            )
            raise

        record_fallback()
        logger.warning(
            "primary_provider=groq groq_result=%s fallback_provider=gemini fallback_result=started",
            groq_error.category,
        )
        fallback_messages = messages
        if structured_retry_message and groq_error.category in {
            "structured_output_rejection",
            "pydantic_validation",
        }:
            fallback_messages = [
                *messages,
                {"role": "system", "content": structured_retry_message},
            ]
        try:
            result = await _generate_with_gemini(
                messages=fallback_messages,
                response_model=response_model,
                output_label=output_label,
            )
        except AIGenerationError as gemini_error:
            logger.error(
                "fallback_provider=gemini fallback_result=%s",
                gemini_error.category,
            )
            raise groq_error from gemini_error

        logger.info(
            "fallback_provider=gemini fallback_result=success model=%s",
            os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        )
        return result

    logger.info(
        "primary_provider=groq groq_result=success model=%s",
        os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
    )
    return result
