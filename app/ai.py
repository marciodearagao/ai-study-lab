import os
from typing import TypeVar

import groq
from groq import AsyncGroq
from pydantic import BaseModel, ValidationError


ModelT = TypeVar("ModelT", bound=BaseModel)


class AIGenerationError(Exception):
    """A safe error that can be shown to the user."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


async def generate_structured(
    *,
    messages: list[dict[str, str]],
    response_model: type[ModelT],
    schema_name: str,
    output_label: str,
) -> ModelT:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise AIGenerationError(
            "AI is not configured yet. Add GROQ_API_KEY to .env and restart the app.",
            status_code=503,
        )

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    try:
        response = await AsyncGroq(api_key=api_key, timeout=30, max_retries=0).chat.completions.create(
            model=model,
            temperature=0.2,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content or ""
    except (groq.AuthenticationError, groq.PermissionDeniedError) as error:
        raise AIGenerationError(
            "Groq authentication failed. Check GROQ_API_KEY in .env and restart the app."
        ) from error
    except (groq.NotFoundError, groq.BadRequestError) as error:
        raise AIGenerationError(
            "The configured Groq model is invalid or unavailable. Check GROQ_MODEL in .env."
        ) from error
    except (
        groq.APITimeoutError,
        groq.APIConnectionError,
        groq.RateLimitError,
        groq.InternalServerError,
    ) as error:
        raise AIGenerationError(
            "Groq is temporarily unavailable. Please try again shortly.", status_code=503
        ) from error
    except groq.APIError as error:
        raise AIGenerationError(
            "Groq could not complete the request. Please try again."
        ) from error
    except (IndexError, AttributeError, TypeError) as error:
        raise AIGenerationError(
            f"The AI returned an invalid {output_label} format. Please try again."
        ) from error

    try:
        return response_model.model_validate_json(content)
    except (ValidationError, ValueError, TypeError) as error:
        raise AIGenerationError(
            f"The AI returned an invalid {output_label} format. Please try again."
        ) from error
