import os

from fastapi.testclient import TestClient

from app import main as app_main
from app.main import app


client = TestClient(app)


def test_home_page_loads_learning_interface() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "What do you want to" in response.text
    assert 'id="study-form"' in response.text
    assert "Start learning" in response.text
    assert 'id="study-pdf"' in response.text
    assert "Study material <small>Optional</small>" in response.text
    assert 'id="flashcard-mode"' in response.text
    assert "Reveal answer" in response.text
    assert 'id="quiz-mode"' in response.text
    assert "Take quiz" in response.text
    assert "Quiz complete" in response.text
    assert '<h3 class="key-points-heading">Key points</h3>' in response.text
    assert "Based on your uploaded material" in response.text
    assert 'id="source-references"' in response.text
    assert "key-concepts" not in response.text
    assert 'id="interview-form"' in response.text
    assert "Job Description" in response.text
    assert "Resume / CV text" in response.text
    assert 'id="resume-pdf"' in response.text
    assert "No PDF selected" in response.text
    assert 'id="linkedin-pdf"' in response.text
    assert "No LinkedIn PDF selected" in response.text
    assert 'id="cover-letter-pdf"' in response.text
    assert "No Cover Letter PDF selected" in response.text
    assert 'id="dashboard-progress-bar"' in response.text
    assert 'data-workspace="study"' in response.text
    assert 'data-workspace="interview-coach"' in response.text
    assert 'data-workspace="progress"' not in response.text
    assert 'data-workspace="home"' in response.text


def test_static_assets_are_served() -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "--green" in response.text


def test_home_asset_urls_follow_static_file_modification_times(monkeypatch, tmp_path) -> None:
    templates_dir = tmp_path / "templates"
    static_dir = tmp_path / "static"
    templates_dir.mkdir()
    static_dir.mkdir()
    (templates_dir / "index.html").write_text(
        '<link href="/static/styles.css?v=__STYLES_VERSION__">'
        '<script src="/static/app.js?v=__APP_VERSION__"></script>',
        encoding="utf-8",
    )
    css_path = static_dir / "styles.css"
    js_path = static_dir / "app.js"
    css_path.write_text("body {}", encoding="utf-8")
    js_path.write_text("void 0;", encoding="utf-8")
    monkeypatch.setattr(app_main, "BASE_DIR", tmp_path)

    first_response = client.get("/")
    first_css_version = str(css_path.stat().st_mtime_ns)
    first_js_version = str(js_path.stat().st_mtime_ns)
    assert first_response.headers["cache-control"] == "no-cache"
    assert f"/static/styles.css?v={first_css_version}" in first_response.text
    assert f"/static/app.js?v={first_js_version}" in first_response.text
    assert "__STYLES_VERSION__" not in first_response.text
    assert "__APP_VERSION__" not in first_response.text

    original_stat = css_path.stat()
    os.utime(
        css_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000),
    )
    second_response = client.get("/")

    assert f"/static/styles.css?v={css_path.stat().st_mtime_ns}" in second_response.text
    assert f"/static/styles.css?v={first_css_version}" not in second_response.text
    assert f"/static/app.js?v={first_js_version}" in second_response.text


def test_frontend_resets_hidden_answer_when_cards_change() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "function renderFlashcard()" in response.text
    assert "flashcardAnswer.hidden = true" in response.text
    assert 'classList.add("activity-active")' in response.text
    assert 'classList.remove("activity-active")' in response.text


def test_frontend_quiz_locks_answers_and_tracks_session_score() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "if (quizAnswered)" in response.text
    assert "button.disabled = true" in response.text
    assert 'isCorrect ? "Correct" : "Incorrect"' in response.text
    assert "quizCorrectCount += 1" in response.text
    assert "`${quizCorrectCount} / ${quizQuestions.length} correct`" in response.text


def test_frontend_switches_one_workspace_at_a_time() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "function showWorkspace(name)" in response.text
    assert "workspace.hidden = workspace !== selected" in response.text
    assert 'link.setAttribute("aria-current", "page")' in response.text


def test_frontend_uses_pdf_endpoint_and_shows_filename() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert 'endpoint = "/api/interview-analysis/pdf"' in response.text
    assert "`Selected: ${file.name}`" in response.text
    assert 'formData.append("linkedin_pdf", linkedinPdf)' in response.text
    assert 'formData.append("cover_letter_pdf", coverLetterPdf)' in response.text


def test_study_frontend_selects_standard_or_grounded_request() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert 'let endpoint = "/api/lessons"' in response.text
    assert 'endpoint = "/api/lessons/pdf"' in response.text
    assert 'formData.append("study_pdf", studyPdf)' in response.text
    assert 'const lessonResult = studyPdf ? result.lesson : result' in response.text
    assert "Preparing your study material..." in response.text


def test_grounded_frontend_keeps_activities_and_renders_safe_sources() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "flashcards = lessonResult.flashcards" in response.text
    assert "quizQuestions = lessonResult.quiz_questions" in response.text
    assert "groundedIndicator.hidden = !result.used_uploaded_material" in response.text
    assert "page.textContent = `Page ${source.page_number}`" in response.text
    assert "item.append(page, source.excerpt)" in response.text


def test_health_reports_version() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}


def test_cross_origin_write_is_rejected() -> None:
    response = client.post(
        "/api/interview-analysis/pdf",
        headers={"Origin": "https://untrusted.example"},
        data={"job_description": "Role", "resume_text": "Experience"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-origin requests are not allowed."}


def test_local_origin_write_reaches_endpoint_validation() -> None:
    response = client.post(
        "/api/lessons",
        headers={"Origin": "http://127.0.0.1:8000"},
        json={},
    )

    assert response.status_code == 422


def test_untrusted_host_is_rejected() -> None:
    response = client.get("/", headers={"Host": "untrusted.example"})

    assert response.status_code == 400
