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
        min_length=4, max_length=4
    )
    correct_answer: Annotated[ShortText, StringConstraints(max_length=160)]
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
    flashcards: list[Flashcard] = Field(min_length=5, max_length=8)
    quiz_questions: list[QuizQuestion] = Field(min_length=4, max_length=6)


SYSTEM_PROMPT = """You are a clear, practical teacher creating a concise lesson.
Interpret the requested topic in its likely study context. Resolve acronyms from the full topic and
prefer their established meaning in that subject. For technical topics, preserve an acronym when its
meaning remains uncertain instead of inventing or confidently choosing an unrelated expansion.
In an AI or machine-learning topic, RAG normally means Retrieval-Augmented Generation unless the
topic clearly indicates otherwise. Return only the requested lesson structure. Write one short
explanation, then 3 to 4 brief key points that add distinct takeaways without repeating the
explanation. Include 5 to 8 concise flashcards and 4 to 6 multiple-choice quiz questions focused on
the requested topic and learner level. Each quiz question must have exactly four distinct options,
an exact matching correct answer, and a short explanation."""


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


async def generate_lesson(request: LessonRequest) -> Lesson:
    return await generate_structured(
        messages=build_lesson_messages(request),
        response_model=Lesson,
        schema_name="lesson",
        output_label="lesson",
    )
