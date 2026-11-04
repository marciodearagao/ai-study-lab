from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_official_lesson_registers_access_and_loads_progress():
    script = client.get("/static/app.js").text
    lesson_flow = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function selectOfficialPath(", 1
    )[0]

    assert '"Checking lesson progress..."' in lesson_flow
    assert "loadOfficialLessonProgress(lessonItem.id, progressStatus, requestId)" in lesson_flow
    assert '{ method: "POST" }' in lesson_flow
    assert '`/api/progress/lessons/${encodeURIComponent(lessonId)}/access`' in lesson_flow
    assert '`/api/progress/lessons/${encodeURIComponent(lessonId)}`' in lesson_flow
    assert 'progressResult.value.completed' in lesson_flow
    assert '"Lesson completed previously."' in lesson_flow


def test_completed_official_quiz_saves_one_attempt_with_existing_score():
    script = client.get("/static/app.js").text
    submit_flow = script.split("function advanceOfficialQuiz()", 1)[1].split(
        "function renderOfficialQuiz(", 1
    )[0]

    assert "!state.submitted || state.finished" in submit_flow
    assert "state.finished = true" in submit_flow
    assert '"/api/progress/quiz-attempts"' in submit_flow
    assert "lesson_id: state.lessonId" in submit_flow
    assert "score: state.correctCount" in submit_flow
    assert "total_questions: state.questions.length" in submit_flow
    assert '"Saving your result..."' in submit_flow
    assert '"Result saved successfully. Lesson completed."' in submit_flow


def test_restart_resets_in_memory_only_without_saving_incomplete_attempt():
    script = client.get("/static/app.js").text
    reset_flow = script.split("function resetOfficialQuizProgress()", 1)[1].split(
        "function renderOfficialQuizQuestion()", 1
    )[0]

    assert "function resetOfficialQuizProgress()" not in reset_flow
    assert '"/api/progress/quiz-attempts"' not in reset_flow
    assert "officialQuizState.questionIndex = 0" in reset_flow
    assert "officialQuizState.correctCount = 0" in reset_flow
    assert "officialQuizState.finished = false" in reset_flow
    assert "officialQuizState.persisting" in reset_flow


def test_repeated_attempts_keep_completed_indicator_and_report_save_failure():
    script = client.get("/static/app.js").text
    completion_flow = script.split("function advanceOfficialQuiz()", 1)[1].split(
        "async function saveOfficialQuizAttempt(", 1
    )[0]
    save_flow = script.split("async function saveOfficialQuizAttempt(", 1)[1].split(
        "function renderOfficialQuiz(", 1
    )[0]

    assert 'state.progressStatus.dataset.completed = "true"' in save_flow
    assert '"Your score is shown, but the result could not be saved."' in save_flow
    assert '"Quiz result"' in script
    assert "state.restart.disabled = true" in completion_flow
    assert "state.restart.disabled = false" in save_flow


def test_old_lesson_progress_responses_are_ignored_after_navigation():
    script = client.get("/static/app.js").text
    load_flow = script.split("async function loadOfficialLessonProgress(", 1)[1].split(
        "async function selectOfficialPath(", 1
    )[0]

    assert "requestId !== officialLessonRequestId" in load_flow
    assert "!statusElement.isConnected" in load_flow
    assert "Promise.allSettled" in load_flow
    assert "officialLessonRequestId += 1" in script


def test_official_progress_calls_do_not_change_the_study_quiz():
    script = client.get("/static/app.js").text
    study_flow = script.split("const workspaces =", 1)[0]

    assert "function renderQuizQuestion()" in study_flow
    assert "function answerQuizQuestion(selectedButton, selectedAnswer)" in study_flow
    assert "function answerQuizQuestion" in study_flow
    assert "/api/progress/" not in study_flow
