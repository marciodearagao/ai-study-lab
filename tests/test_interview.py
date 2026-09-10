from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pydantic import ValidationError

from app.ai import AIGenerationError
from app.interview import (
    InterviewAnalysis,
    InterviewRequest,
    build_interview_messages,
    extract_resume_text,
)
from app.main import app


client = TestClient(app)


def make_pdf(text: str | None = None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def sample_analysis() -> InterviewAnalysis:
    return InterviewAnalysis(
        fit_level="Good fit",
        fit_summary="The resume supports the core Python requirements, with one notable platform gap.",
        evidence=["Built production Python APIs", "Used pytest for automated testing"],
        gaps=["No Kubernetes experience is stated"],
        suggested_study_topics=["Kubernetes fundamentals"],
        interview_questions=[
            "How did you design your production APIs?",
            "How would you deploy a service to Kubernetes?",
        ],
    )


def test_valid_interview_analysis_request(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert payload.job_description == "Python and Kubernetes required"
        assert payload.resume_text == "Built production Python APIs"
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis",
        json={
            "job_description": "Python and Kubernetes required",
            "resume_text": "Built production Python APIs",
        },
    )

    assert response.status_code == 200
    assert response.json()["fit_level"] == "Good fit"
    assert len(response.json()["interview_questions"]) == 2


def test_valid_pdf_is_extracted_and_analyzed(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert payload.job_description == "Python role"
        assert "Built Python APIs" in payload.resume_text
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={"resume_pdf": ("resume.pdf", make_pdf("Built Python APIs"), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["fit_level"] == "Good fit"
    assert "Built Python APIs" in extract_resume_text(make_pdf("Built Python APIs"))


def test_cv_and_linkedin_pdfs_are_extracted_and_analyzed(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert "Built Python APIs" in payload.resume_text
        assert "AWS certification" in payload.linkedin_text
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python and cloud experience required"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Built Python APIs"), "application/pdf"),
            "linkedin_pdf": (
                "linkedin-profile.pdf",
                make_pdf("AWS certification"),
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 200


def test_cv_and_cover_letter_pdfs_are_extracted_and_analyzed(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert "Built Python APIs" in payload.resume_text
        assert "Interested in the platform mission" in payload.cover_letter_text
        assert payload.linkedin_text is None
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python experience required"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Built Python APIs"), "application/pdf"),
            "cover_letter_pdf": (
                "cover-letter.pdf",
                make_pdf("Interested in the platform mission"),
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 200


def test_cv_linkedin_and_cover_letter_are_analyzed_together(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert "Python APIs" in payload.resume_text
        assert "AWS certification" in payload.linkedin_text
        assert "Customer focus" in payload.cover_letter_text
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python cloud role"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Python APIs"), "application/pdf"),
            "linkedin_pdf": ("linkedin.pdf", make_pdf("AWS certification"), "application/pdf"),
            "cover_letter_pdf": (
                "cover-letter.pdf",
                make_pdf("Customer focus"),
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 200


def test_pdf_endpoint_rejects_non_pdf_file() -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={"resume_pdf": ("resume.txt", b"Python developer", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Choose one PDF file for resume."}


@pytest.mark.parametrize("pdf_data", [b"", b"not a pdf", make_pdf()])
def test_pdf_endpoint_rejects_unreadable_or_textless_pdf(pdf_data: bytes) -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={"resume_pdf": ("resume.pdf", pdf_data, "application/pdf")},
    )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"] or "readable text" in response.json()["detail"]


def test_pdf_endpoint_rejects_invalid_linkedin_file_type() -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Python developer"), "application/pdf"),
            "linkedin_pdf": ("linkedin.txt", b"Profile text", "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Choose one PDF file for LinkedIn Profile."}


@pytest.mark.parametrize("pdf_data", [b"not a pdf", make_pdf()])
def test_pdf_endpoint_rejects_unreadable_or_textless_linkedin_pdf(pdf_data: bytes) -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Python developer"), "application/pdf"),
            "linkedin_pdf": ("linkedin.pdf", pdf_data, "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert "LinkedIn Profile PDF" in response.json()["detail"]


def test_pdf_endpoint_rejects_invalid_cover_letter_file_type() -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Python developer"), "application/pdf"),
            "cover_letter_pdf": ("cover-letter.txt", b"Letter text", "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Choose one PDF file for Cover Letter."}


@pytest.mark.parametrize("pdf_data", [b"not a pdf", make_pdf()])
def test_pdf_endpoint_rejects_unreadable_or_textless_cover_letter(pdf_data: bytes) -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        data={"job_description": "Python role"},
        files={
            "resume_pdf": ("resume.pdf", make_pdf("Python developer"), "application/pdf"),
            "cover_letter_pdf": ("cover-letter.pdf", pdf_data, "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert "Cover Letter PDF" in response.json()["detail"]


def test_existing_pasted_resume_flow_still_works(monkeypatch) -> None:
    async def fake_analysis(payload):
        assert payload.resume_text == "Pasted Python experience"
        return sample_analysis()

    monkeypatch.setattr("app.main.generate_interview_analysis", fake_analysis)

    response = client.post(
        "/api/interview-analysis",
        json={"job_description": "Python role", "resume_text": "Pasted Python experience"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    [("job_description", "   "), ("resume_text", "")],
)
def test_interview_analysis_requires_both_inputs(field: str, value: str) -> None:
    payload = {"job_description": "Python role", "resume_text": "Python developer"}
    payload[field] = value

    response = client.post("/api/interview-analysis", json=payload)

    assert response.status_code == 422


def test_interview_analysis_structured_output_validation() -> None:
    with pytest.raises(ValidationError):
        InterviewAnalysis(
            fit_level="87% match",
            fit_summary="A numerical score is not allowed.",
            evidence=[],
            gaps=[],
            suggested_study_topics=[],
            interview_questions=["Only one question"],
        )


def test_interview_prompt_requires_grounded_evidence_and_no_score() -> None:
    messages = build_interview_messages(
        InterviewRequest(
            job_description="Needs Kubernetes",
            resume_text="Python developer",
            linkedin_text="Cloud certification",
            cover_letter_text="Motivated to join the team",
        )
    )

    assert "grounded only" in messages[0]["content"]
    assert "Never produce a numerical score" in messages[0]["content"]
    assert "CV as the primary" in messages[0]["content"]
    assert '"CV:", "LinkedIn:", or "Cover Letter:"' in messages[0]["content"]
    assert "supplementary context only" in messages[0]["content"]
    assert "unless they are clearly supported" in messages[0]["content"]
    assert "Needs Kubernetes" in messages[1]["content"]
    assert "Python developer" in messages[1]["content"]
    assert "Cloud certification" in messages[1]["content"]
    assert "Motivated to join the team" in messages[1]["content"]


def test_interview_ai_failure_is_handled_safely(monkeypatch) -> None:
    async def failed_analysis(_payload):
        raise AIGenerationError("Groq is temporarily unavailable. Please try again shortly.", 503)

    monkeypatch.setattr("app.main.generate_interview_analysis", failed_analysis)

    response = client.post(
        "/api/interview-analysis",
        json={"job_description": "Python role", "resume_text": "Python developer"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Groq is temporarily unavailable. Please try again shortly."
    }
