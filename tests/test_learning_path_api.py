import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.content import load_learning_paths


client = TestClient(app_main.app)


def test_official_paths_navigation_connects_to_listing_api() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    paths = client.get("/api/learning-paths").json()

    assert 'href="#official-learning-paths"' in page
    assert 'data-workspace="official-learning-paths"' in page
    assert 'src="/static/app.js?v=step4c-progress"' in page
    assert 'id="official-paths-status" role="status" aria-live="polite"' in page
    assert 'fetch("/api/learning-paths", { signal: controller.signal })' in script
    assert "No official learning paths are available yet." in script
    assert "Learning paths could not be loaded. Please try again." in script
    assert "module.title" in script
    assert 'fetch(`/api/learning-paths/${encodeURIComponent(path.id)}`)' in script
    assert "renderOfficialModule" in script
    assert "renderOfficialLesson" in script
    assert "Back to modules" in script
    assert "Lesson content is not available yet." in script
    assert "This learning path could not be loaded." in script
    assert paths[0]["modules"][0]["title"] == "Introduction"


def test_pending_learning_path_request_times_out_and_unlocks_retry() -> None:
    script = client.get("/static/app.js").text

    assert "new AbortController()" in script
    assert "controller.abort(), 10000" in script
    assert "window.clearTimeout(timeoutId)" in script
    assert 'officialPathRetry.addEventListener("click"' in script
    assert "officialPathsLoading = false" in script


def test_learning_paths_listing_is_compact() -> None:
    response = client.get("/api/learning-paths")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "ai-fundamentals",
            "title": "AI Fundamentals",
            "modules": [{"id": "introduction", "title": "Introduction"}],
        }
    ]


def test_learning_path_detail_includes_explanation_and_quiz() -> None:
    response = client.get("/api/learning-paths/ai-fundamentals")

    assert response.status_code == 200
    path = response.json()
    lesson = path["modules"][0]["lessons"][0]
    assert path["id"] == "ai-fundamentals"
    assert lesson["title"] == "What Is Artificial Intelligence?"
    assert lesson["explanation"].startswith("# What Is Artificial Intelligence?")
    assert len(lesson["quiz"]) == 4
    assert list(lesson["quiz"][0]["options"]) == ["A", "B", "C", "D"]
    assert lesson["quiz"][0]["correct_answer"] == "A"


def test_official_lesson_markdown_renderer_uses_safe_dom_nodes() -> None:
    script = client.get("/static/app.js").text
    renderer = script.split("function renderInlineMarkdown", 1)[1].split(
        "function renderOfficialModule", 1
    )[0]

    assert "document.createTextNode" in renderer
    assert "code.textContent = match[1]" in renderer
    assert "code.textContent = codeLines.join(\"\\n\")" in renderer
    assert "innerHTML" not in renderer


def test_official_lesson_markdown_supports_requested_blocks() -> None:
    script = client.get("/static/app.js").text

    assert '/^(#{1,6})\\s+(.+?)\\s*#*\\s*$/' in script
    assert '/^\\s*(?:[-*+]\\s+|(\\d+)\\.\\s+)(.+)$/' in script
    assert 'document.createElement("pre")' in script
    assert 'document.createElement(tag)' in script
    assert 'const tag = item[1] ? "ol" : "ul"' in script


def test_official_lesson_quiz_loads_keyed_sample_questions() -> None:
    lesson = client.get("/api/learning-paths/ai-fundamentals").json()["modules"][0]["lessons"][0]

    assert len(lesson["quiz"]) == 4
    for question in lesson["quiz"]:
        assert list(question["options"]) == ["A", "B", "C", "D"]
        assert question["correct_answer"] in question["options"]

    script = client.get("/static/app.js").text
    assert "renderOfficialQuiz(lessonItem.quiz)" in script
    assert 'option.textContent = `${key}. ${question.options[key]}`' in script


def test_official_quiz_supports_answers_and_prevents_duplicate_submissions() -> None:
    script = client.get("/static/app.js").text
    submit_logic = script.split("function submitOfficialQuizAnswer()", 1)[1].split(
        "function advanceOfficialQuiz()", 1
    )[0]

    assert "state.submitted || !state.selectedKey" in submit_logic
    assert "state.selectedKey === question.correct_answer" in submit_logic
    assert "state.correctCount += 1" in submit_logic
    assert 'question.options[question.correct_answer]' in submit_logic
    assert 'state.feedbackLabel.textContent = isCorrect ? "Correct!" : "Incorrect."' in submit_logic


def test_official_quiz_navigation_score_restart_and_lesson_reset() -> None:
    script = client.get("/static/app.js").text
    advance_logic = script.split("function advanceOfficialQuiz()", 1)[1].split(
        "function renderOfficialQuiz(", 1
    )[0]
    reset_logic = script.split("function resetOfficialQuizProgress()", 1)[1].split(
        "function renderOfficialQuizQuestion()", 1
    )[0]

    assert "state.questionIndex += 1" in advance_logic
    assert "${state.correctCount} / ${state.questions.length} correct" in advance_logic
    assert 'restart.textContent = "Restart quiz"' in script
    assert "officialQuizState.questionIndex = 0" in reset_logic
    assert "officialQuizState.correctCount = 0" in reset_logic
    for function_name in ("renderOfficialLesson", "renderOfficialModule", "showOfficialPathModules"):
        body = script.split(f"function {function_name}(", 1)[1].split("\nfunction ", 1)[0]
        assert "officialQuizState = null" in body
    assert 'selected.dataset.workspace !== "official-learning-paths"' in script
    assert "resetOfficialQuizProgress()" in script


def test_official_quiz_handles_missing_or_empty_questions() -> None:
    script = client.get("/static/app.js").text

    assert "function renderOfficialQuiz(quiz)" in script
    assert "Array.isArray(quiz) && quiz.length > 0" in script
    assert "Quiz questions are not available yet." in script


def test_unknown_learning_path_returns_404() -> None:
    response = client.get("/api/learning-paths/not-a-learning-path")

    assert response.status_code == 404
    assert response.json() == {"detail": "Learning path not found."}


@pytest.mark.parametrize("endpoint", ["/api/learning-paths", "/api/learning-paths/ai-fundamentals"])
@pytest.mark.parametrize("invalid_content", [False, True])
def test_invalid_content_returns_safe_500(
    endpoint: str, invalid_content: bool, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    content_dir = tmp_path / "content"
    (content_dir / "paths").mkdir(parents=True)
    if invalid_content:
        (content_dir / "modules").mkdir()
        (content_dir / "lessons").mkdir()
        (content_dir / "paths" / "broken.json").write_text("{", encoding="utf-8")

    def fail_to_load():
        return load_learning_paths(content_dir)

    monkeypatch.setattr(app_main, "load_learning_paths", fail_to_load)

    response = client.get(endpoint)

    assert response.status_code == 500
    assert response.json() == {"detail": "Learning content is unavailable."}
    assert "private" not in response.text
    assert "Traceback" not in response.text


def test_existing_api_endpoints_remain_available() -> None:
    assert client.get("/health").status_code == 200
    assert client.post("/api/lessons", json={}).status_code == 422
    assert client.post("/api/lessons/pdf").status_code == 422
    assert client.post("/api/interview-analysis", json={}).status_code == 422
    assert client.post("/api/interview-analysis/pdf").status_code == 422
