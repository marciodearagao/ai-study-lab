from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai import AIGenerationError
from app.interview import (
    InterviewAnalysis,
    InterviewRequest,
    PDFExtractionError,
    extract_pdf_text,
    generate_interview_analysis,
)
from app.lessons import Lesson, LessonRequest, generate_lesson
from app.rag import (
    GroundedLesson,
    RetrievalError,
    generate_grounded_lesson,
    process_pdf,
    retrieve_chunks,
)
from app.telemetry import (
    emit_request_telemetry,
    record_error_category,
    record_retrieval,
    start_request,
    telemetry_scope,
)


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="AI Study Lab", version="0.1.0")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
MAX_PDF_BYTES = 5 * 1024 * 1024
TELEMETRY_ENDPOINTS = {
    "/api/lessons",
    "/api/lessons/pdf",
    "/api/interview-analysis",
    "/api/interview-analysis/pdf",
}


def is_local_browser_origin(origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {
            "127.0.0.1",
            "localhost",
        }
    except ValueError:
        return False


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and not is_local_browser_origin(origin)
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Cross-origin requests are not allowed."},
        )
    return await call_next(request)


@app.middleware("http")
async def log_generation_telemetry(request: Request, call_next):
    if request.method != "POST" or request.url.path not in TELEMETRY_ENDPOINTS:
        return await call_next(request)

    request_id, started_at = start_request()
    with telemetry_scope() as state:
        try:
            response = await call_next(request)
        except Exception:
            record_error_category("unhandled_error")
            emit_request_telemetry(
                state=state,
                endpoint=request.url.path,
                started_at=started_at,
                status_code=500,
                request_id=request_id,
            )
            raise
        emit_request_telemetry(
            state=state,
            endpoint=request.url.path,
            started_at=started_at,
            status_code=response.status_code,
            request_id=request_id,
        )
        return response


async def read_uploaded_pdf(upload: UploadFile, document_name: str) -> bytes:
    if (
        upload.content_type != "application/pdf"
        or not (upload.filename or "").lower().endswith(".pdf")
    ):
        raise HTTPException(status_code=400, detail=f"Choose one PDF file for {document_name}.")

    pdf_data = await upload.read(MAX_PDF_BYTES + 1)
    if len(pdf_data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"The {document_name} PDF is too large. Choose a file under 5 MB.",
        )
    return pdf_data


async def extract_uploaded_pdf(upload: UploadFile, document_name: str) -> str:
    return extract_pdf_text(await read_uploaded_pdf(upload, document_name), document_name)


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTMLResponse((BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/api/lessons", response_model=Lesson)
async def create_lesson(payload: LessonRequest) -> Lesson:
    try:
        return await generate_lesson(payload)
    except AIGenerationError as error:
        record_error_category(error.category)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/lessons/pdf", response_model=GroundedLesson)
async def create_grounded_lesson(
    topic: Annotated[str, Form(max_length=120)],
    level: Annotated[Literal["Basic", "Intermediate", "Advanced"], Form()],
    study_pdf: Annotated[list[UploadFile] | None, File()] = None,
) -> GroundedLesson:
    if not topic.strip():
        raise HTTPException(status_code=422, detail="Add a topic to begin.")
    if not study_pdf or len(study_pdf) != 1:
        raise HTTPException(status_code=400, detail="Choose exactly one PDF study material file.")

    try:
        pdf_data = await read_uploaded_pdf(study_pdf[0], "study material")
        chunks = await run_in_threadpool(process_pdf, pdf_data)
        retrieved_chunks = await run_in_threadpool(retrieve_chunks, chunks, topic)
        record_retrieval(
            [chunk.page_number for chunk in retrieved_chunks], len(retrieved_chunks)
        )
        return await generate_grounded_lesson(topic, level, retrieved_chunks)
    except PDFExtractionError as error:
        record_error_category("pdf_validation")
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RetrievalError as error:
        record_error_category("retrieval")
        raise HTTPException(status_code=503, detail=str(error)) from error
    except AIGenerationError as error:
        record_error_category(error.category)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/interview-analysis", response_model=InterviewAnalysis)
async def create_interview_analysis(payload: InterviewRequest) -> InterviewAnalysis:
    try:
        return await generate_interview_analysis(payload)
    except AIGenerationError as error:
        record_error_category(error.category)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/interview-analysis/pdf", response_model=InterviewAnalysis)
async def create_interview_analysis_from_pdf(
    job_description: Annotated[str, Form(max_length=15_000)],
    resume_pdf: Annotated[list[UploadFile] | None, File()] = None,
    resume_text: Annotated[str, Form(max_length=15_000)] = "",
    linkedin_pdf: Annotated[list[UploadFile] | None, File()] = None,
    cover_letter_pdf: Annotated[list[UploadFile] | None, File()] = None,
) -> InterviewAnalysis:
    if not job_description.strip():
        raise HTTPException(status_code=422, detail="Add the Job Description to continue.")
    if resume_pdf and len(resume_pdf) != 1:
        raise HTTPException(status_code=400, detail="Choose exactly one PDF resume file.")
    if linkedin_pdf and len(linkedin_pdf) != 1:
        raise HTTPException(status_code=400, detail="Choose at most one LinkedIn Profile PDF.")
    if cover_letter_pdf and len(cover_letter_pdf) != 1:
        raise HTTPException(status_code=400, detail="Choose at most one Cover Letter PDF.")
    if not resume_pdf and not resume_text.strip():
        raise HTTPException(
            status_code=422,
            detail="Choose a resume PDF or add your Resume / CV text to continue.",
        )

    try:
        resolved_resume_text = (
            await extract_uploaded_pdf(resume_pdf[0], "resume")
            if resume_pdf
            else resume_text
        )
        linkedin_text = (
            await extract_uploaded_pdf(linkedin_pdf[0], "LinkedIn Profile")
            if linkedin_pdf
            else None
        )
        cover_letter_text = (
            await extract_uploaded_pdf(cover_letter_pdf[0], "Cover Letter")
            if cover_letter_pdf
            else None
        )
        payload = InterviewRequest(
            job_description=job_description,
            resume_text=resolved_resume_text,
            linkedin_text=linkedin_text,
            cover_letter_text=cover_letter_text,
        )
        return await generate_interview_analysis(payload)
    except PDFExtractionError as error:
        record_error_category("pdf_validation")
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AIGenerationError as error:
        record_error_category(error.category)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
