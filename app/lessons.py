from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.ai import generate_structured


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LessonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Annotated[ShortText, StringConstraints(max_length=120)]
    level: Literal["Basic", "Intermediate", "Advanced"]


class Flashcard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[ShortText, StringConstraints(max_length=200)]
    answer: Annotated[ShortText, StringConstraints(max_length=300)]


class QuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[ShortText, StringConstraints(max_length=240)]
    options: list[Annotated[ShortText, StringConstraints(max_length=160)]] = Field(
        min_length=4,
        max_length=4,
    )
    correct_answer: Annotated[ShortText, StringConstraints(max_length=160)] = Field(
        description="Copy one complete option exactly, character for character."
    )
    explanation: Annotated[ShortText, StringConstraints(max_length=300)]

    @model_validator(mode="after")
    def validate_options_and_answer(self) -> "QuizQuestion":
        if len({option.casefold() for option in self.options}) != 4:
            raise ValueError("quiz options must be distinct")
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer must exactly match one option")
        return self


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[ShortText, StringConstraints(max_length=100)]
    short_explanation: Annotated[ShortText, StringConstraints(max_length=400)]
    key_concepts: list[Annotated[ShortText, StringConstraints(max_length=120)]] = Field(
        min_length=3, max_length=4
    )
    flashcards: list[Flashcard] = Field(min_length=5, max_length=5)
    quiz_questions: list[QuizQuestion] = Field(min_length=4, max_length=4)


SYSTEM_PROMPT = """You are a clear, practical teacher creating a concise lesson.
Interpret the requested topic in its likely study context. Resolve acronyms from the full topic and
prefer their established meaning in that subject. For technical topics, preserve an acronym when its
meaning remains uncertain instead of inventing or confidently choosing an unrelated expansion.
In an AI or machine-learning topic, RAG normally means Retrieval-Augmented Generation unless the
topic clearly indicates otherwise. Return only the requested lesson structure. Write one short
explanation, then 3 to 4 brief key points that add distinct takeaways without repetition.
Activity rules:
- Generate exactly 5 concise flashcards.
- Generate exactly 4 multiple-choice quiz questions.
- Give every quiz question exactly 4 distinct, non-near-duplicate option strings; never repeat an option.
- Copy one complete option exactly, character for character, into correct_answer.
- Keep every quiz explanation short.
Adhere exactly to the structured schema. Before returning, verify all counts, distinct options, and
exact answer matches."""

LESSON_RETRY_PROMPT = """Regenerate the entire lesson because the previous candidate did not satisfy
the structured schema. Return exactly 5 flashcards and exactly 4 quiz questions. Every quiz question
must contain exactly 4 distinct option strings with no repeated option, and correct_answer must copy
one option exactly. Return only the complete structured lesson."""


def build_lesson_messages(request: LessonRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f'Requested topic: "{request.topic}"\n'
                f"Learner level: {request.level}\n"
                "Create the lesson without broadening it into an unrelated subject."
            ),
        },
    ]


async def generate_lesson_from_messages(messages: list[dict[str, str]]) -> Lesson:
    return await generate_structured(
        messages=messages,
        response_model=Lesson,
        schema_name="lesson",
        output_label="lesson",
        allow_gemini_fallback=True,
    )


async def generate_lesson(request: LessonRequest) -> Lesson:
    return await generate_structured(
        messages=build_lesson_messages(request),
        response_model=Lesson,
        schema_name="lesson",
        output_label="lesson",
        retry_structured_output=True,
        structured_retry_message=LESSON_RETRY_PROMPT,
        allow_gemini_fallback=True,
    )
