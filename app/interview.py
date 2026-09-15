from io import BytesIO
from typing import Annotated, Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.ai import generate_structured


RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
BriefItem = Annotated[RequiredText, StringConstraints(max_length=240)]
MAX_DOCUMENT_TEXT = 15_000
# This bounds documents sent directly to the LLM. Page extraction is also reused
# by RAG, which chunks before selecting a much smaller context.
DocumentText = Annotated[RequiredText, StringConstraints(max_length=MAX_DOCUMENT_TEXT)]


class InterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_description: DocumentText
    resume_text: DocumentText
    linkedin_text: DocumentText | None = None
    cover_letter_text: DocumentText | None = None


class InterviewAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fit_level: Literal["Strong fit", "Good fit", "Partial fit", "Weak fit"]
    fit_summary: Annotated[RequiredText, StringConstraints(max_length=400)]
    evidence: list[BriefItem] = Field(max_length=4)
    gaps: list[BriefItem] = Field(max_length=4)
    suggested_study_topics: list[BriefItem] = Field(max_length=4)
    interview_questions: list[BriefItem] = Field(min_length=2, max_length=4)


INTERVIEW_PROMPT = """You are a careful, practical job-interview coach.
Compare the job description with the resume text. Use only these qualitative fit levels: Strong fit,
Good fit, Partial fit, or Weak fit. Never produce a numerical score or match percentage. Every
evidence item must be grounded only in information explicitly present in the provided documents.
Treat the CV as the primary professional document and LinkedIn, when provided, as supporting
professional context. A Cover Letter is supplementary context only: do not use its claims as proof of
professional experience unless they are clearly supported by the CV or LinkedIn. Prefix each evidence
item with "CV:", "LinkedIn:", or "Cover Letter:" to identify its source. Treat job requirements that
are not clearly supported by the provided sources as gaps; do not invent experience or infer missing
qualifications. Keep every section concise, suggest only relevant study topics, and create 2 to 4
focused interview questions."""


def build_interview_messages(request: InterviewRequest) -> list[dict[str, str]]:
    linkedin_context = (
        f"\n\nLINKEDIN PROFILE (OPTIONAL SUPPORTING CONTEXT)\n{request.linkedin_text}"
        if request.linkedin_text
        else ""
    )
    cover_letter_context = (
        f"\n\nCOVER LETTER (OPTIONAL SUPPLEMENTARY CONTEXT)\n{request.cover_letter_text}"
        if request.cover_letter_text
        else ""
    )
    return [
        {"role": "system", "content": INTERVIEW_PROMPT},
        {
            "role": "user",
            "content": (
                "JOB DESCRIPTION\n"
                f"{request.job_description}\n\n"
                "RESUME / CV\n"
                f"{request.resume_text}"
                f"{linkedin_context}"
                f"{cover_letter_context}"
            ),
        },
    ]


async def generate_interview_analysis(request: InterviewRequest) -> InterviewAnalysis:
    return await generate_structured(
        messages=build_interview_messages(request),
        response_model=InterviewAnalysis,
        schema_name="interview_analysis",
        output_label="interview analysis",
        allow_gemini_fallback=True,
    )


class PDFExtractionError(Exception):
    """Raised when a PDF cannot provide usable document text."""


def extract_pdf_pages(pdf_data: bytes, document_name: str) -> list[tuple[int, str]]:
    if not pdf_data:
        raise PDFExtractionError(f"The {document_name} PDF is empty or unreadable.")

    try:
        reader = PdfReader(BytesIO(pdf_data))
        pages = [
            (page_number, text)
            for page_number, page in enumerate(reader.pages, start=1)
            if (text := (page.extract_text() or "").strip())
        ]
    except (PdfReadError, OSError, ValueError, TypeError, KeyError) as error:
        raise PDFExtractionError(f"The {document_name} PDF is empty or unreadable.") from error

    if not pages:
        raise PDFExtractionError(
            f"No readable text was found in the {document_name} PDF. OCR is not supported."
        )
    return pages


def extract_pdf_text(pdf_data: bytes, document_name: str) -> str:
    pages = extract_pdf_pages(pdf_data, document_name)
    text = "\n".join(page_text for _, page_text in pages)
    if len(text) > MAX_DOCUMENT_TEXT:
        raise PDFExtractionError(
            f"The {document_name} PDF contains too much text. Use a shorter PDF."
        )
    return text


def extract_resume_text(pdf_data: bytes) -> str:
    return extract_pdf_text(pdf_data, "resume")
