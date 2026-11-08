from pathlib import Path
from datetime import datetime, timezone
import sqlite3
from typing import Annotated, Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai import AIGenerationError
from app.content import ContentLoadError, load_learning_paths
from app.database import DEFAULT_DATABASE_PATH, initialize_database
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


def static_asset_version(asset_name: str) -> str:
    """Return a cache key that changes when a local static asset changes."""

    return str((BASE_DIR / "static" / asset_name).stat().st_mtime_ns)


app = FastAPI(title="AI Study Lab", version="0.1.0")
DATABASE_PATH = DEFAULT_DATABASE_PATH
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
    page = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    page = page.replace("__STYLES_VERSION__", static_asset_version("styles.css"))
    page = page.replace("__APP_VERSION__", static_asset_version("app.js"))
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/api/learning-paths")
def list_learning_paths() -> list[dict[str, object]]:
    try:
        paths = load_learning_paths()
    except ContentLoadError as error:
        raise HTTPException(
            status_code=500, detail="Learning content is unavailable."
        ) from error

    return [
        {
            "id": path["id"],
            "title": path["title"],
            "modules": [
                {"id": module["id"], "title": module["title"]}
                for module in path["modules"]
            ],
        }
        for path in paths
    ]


@app.get("/api/learning-paths/{path_id}")
def get_learning_path(path_id: str) -> dict[str, object]:
    try:
        paths = load_learning_paths()
    except ContentLoadError as error:
        raise HTTPException(
            status_code=500, detail="Learning content is unavailable."
        ) from error

    for path in paths:
        if path["id"] == path_id:
            return path
    raise HTTPException(status_code=404, detail="Learning path not found.")


class QuizAttemptRequest(BaseModel):
    lesson_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    total_questions: int = Field(gt=0)


def find_official_lesson(lesson_id: str) -> dict[str, object]:
    try:
        paths = load_learning_paths()
    except ContentLoadError as error:
        raise HTTPException(
            status_code=500, detail="Learning content is unavailable."
        ) from error

    for path in paths:
        for module in path["modules"]:
            for lesson in module["lessons"]:
                if lesson["id"] == lesson_id:
                    return lesson
    raise HTTPException(status_code=404, detail="Lesson not found.")


def progress_database_connection() -> sqlite3.Connection:
    initialize_database(DATABASE_PATH)
    return sqlite3.connect(DATABASE_PATH)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


@app.post("/api/progress/quiz-attempts")
def record_quiz_attempt(payload: QuizAttemptRequest) -> dict[str, object]:
    lesson = find_official_lesson(payload.lesson_id)
    total_questions = len(lesson["quiz"])
    if payload.total_questions != total_questions or payload.score > total_questions:
        raise HTTPException(status_code=422, detail="Invalid quiz score or question count.")

    completed_at = utc_timestamp()
    connection = None
    try:
        connection = progress_database_connection()
        with connection:
            connection.execute(
                "INSERT INTO lesson_progress (lesson_id, completed, completed_at) "
                "VALUES (?, 1, ?) "
                "ON CONFLICT(lesson_id) DO UPDATE SET completed = 1, "
                "completed_at = COALESCE(lesson_progress.completed_at, excluded.completed_at)",
                (payload.lesson_id, completed_at),
            )
            cursor = connection.execute(
                "INSERT INTO quiz_attempts "
                "(lesson_id, score, total_questions, completed_at) VALUES (?, ?, ?, ?)",
                (payload.lesson_id, payload.score, payload.total_questions, completed_at),
            )
            attempt_id = cursor.lastrowid
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(
            status_code=500, detail="Progress storage is unavailable."
        ) from error
    finally:
        if connection is not None:
            connection.close()

    return {
        "id": attempt_id,
        "lesson_id": payload.lesson_id,
        "score": payload.score,
        "total_questions": payload.total_questions,
        "completed_at": completed_at,
    }


@app.get("/api/progress/lessons/{lesson_id}")
def get_lesson_progress(lesson_id: str) -> dict[str, object]:
    find_official_lesson(lesson_id)
    connection = None
    try:
        connection = progress_database_connection()
        progress = connection.execute(
            "SELECT completed, completed_at, last_accessed_at "
            "FROM lesson_progress WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
        rows = connection.execute(
            "SELECT id, score, total_questions, completed_at FROM quiz_attempts "
            "WHERE lesson_id = ? ORDER BY completed_at ASC, id ASC",
            (lesson_id,),
        ).fetchall()
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(
            status_code=500, detail="Progress storage is unavailable."
        ) from error
    finally:
        if connection is not None:
            connection.close()

    attempts = [
        {
            "id": row[0],
            "score": row[1],
            "total_questions": row[2],
            "completed_at": row[3],
        }
        for row in rows
    ]
    return {
        "lesson_id": lesson_id,
        "completed": bool(progress[0]) if progress else False,
        "completed_at": progress[1] if progress else None,
        "last_accessed_at": progress[2] if progress else None,
        "latest_quiz_score": attempts[-1]["score"] if attempts else None,
        "best_quiz_score": max((attempt["score"] for attempt in attempts), default=None),
        "quiz_attempts": attempts,
    }


@app.post("/api/progress/lessons/{lesson_id}/access")
def record_lesson_access(lesson_id: str) -> dict[str, str]:
    find_official_lesson(lesson_id)
    last_accessed_at = utc_timestamp()
    connection = None
    try:
        connection = progress_database_connection()
        with connection:
            connection.execute(
                "INSERT INTO lesson_progress "
                "(lesson_id, completed, completed_at, last_accessed_at) "
                "VALUES (?, 0, NULL, ?) "
                "ON CONFLICT(lesson_id) DO UPDATE SET "
                "last_accessed_at = excluded.last_accessed_at",
                (lesson_id, last_accessed_at),
            )
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(
            status_code=500, detail="Progress storage is unavailable."
        ) from error
    finally:
        if connection is not None:
            connection.close()

    return {"lesson_id": lesson_id, "last_accessed_at": last_accessed_at}


@app.get("/api/dashboard/summary")
def get_dashboard_summary() -> dict[str, object]:
    try:
        paths = load_learning_paths()
    except ContentLoadError as error:
        raise HTTPException(
            status_code=500, detail="Learning content is unavailable."
        ) from error

    lesson_details: dict[str, dict[str, str]] = {}
    path_lessons: dict[str, list[str]] = {}
    for path in paths:
        lessons = [
            lesson
            for module in path["modules"]
            for lesson in module["lessons"]
        ]
        path_lessons[path["id"]] = [lesson["id"] for lesson in lessons]
        for lesson in lessons:
            lesson_details[lesson["id"]] = {
                "title": lesson["title"],
                "learning_path_id": path["id"],
            }

    connection = None
    try:
        connection = progress_database_connection()
        completed_rows = connection.execute(
            "SELECT lesson_id FROM lesson_progress WHERE completed = ?", (1,)
        ).fetchall()
        access_rows = connection.execute(
            "SELECT lesson_id, last_accessed_at FROM lesson_progress "
            "WHERE last_accessed_at IS NOT NULL "
            "ORDER BY last_accessed_at DESC, lesson_id ASC"
        ).fetchall()
        attempt_rows = connection.execute(
            "SELECT lesson_id, score, total_questions, completed_at "
            "FROM quiz_attempts ORDER BY completed_at DESC, id DESC"
        ).fetchall()
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(
            status_code=500, detail="Progress storage is unavailable."
        ) from error
    finally:
        if connection is not None:
            connection.close()

    lesson_ids = set(lesson_details)
    completed_ids = {row[0] for row in completed_rows if row[0] in lesson_ids}
    total_lessons = len(lesson_details)
    completed_lessons = len(completed_ids)
    most_recent_lesson = next(
        (row[0] for row in access_rows if row[0] in lesson_ids), None
    )

    path_summaries = []
    for path in paths:
        lesson_ids_for_path = path_lessons[path["id"]]
        path_total = len(lesson_ids_for_path)
        path_completed = sum(lesson_id in completed_ids for lesson_id in lesson_ids_for_path)
        path_summaries.append(
            {
                "id": path["id"],
                "title": path["title"],
                "total_lessons": path_total,
                "completed_lessons": path_completed,
                "completion_percentage": (
                    round(path_completed * 100 / path_total, 2) if path_total else 0
                ),
            }
        )

    recent_attempts = []
    for lesson_id, score, total_questions, completed_at in attempt_rows:
        lesson = lesson_details.get(lesson_id)
        if lesson is None:
            continue
        recent_attempts.append(
            {
                "lesson_id": lesson_id,
                "lesson_title": lesson["title"],
                "score": score,
                "total_questions": total_questions,
                "completed_at": completed_at,
            }
        )
        if len(recent_attempts) == 5:
            break

    return {
        "total_lessons": total_lessons,
        "completed_lessons": completed_lessons,
        "completion_percentage": (
            round(completed_lessons * 100 / total_lessons, 2) if total_lessons else 0
        ),
        "most_recently_accessed_lesson": (
            {
                "id": most_recent_lesson,
                "title": lesson_details[most_recent_lesson]["title"],
                "learning_path_id": lesson_details[most_recent_lesson]["learning_path_id"],
            }
            if most_recent_lesson
            else None
        ),
        "learning_paths": path_summaries,
        "recent_quiz_attempts": recent_attempts,
    }


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
