import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.content import load_learning_paths


client = TestClient(app_main.app)


def official_path_selection_source() -> str:
    script = client.get("/static/app.js").text
    return script.split("async function selectOfficialPath(", 1)[1].split(
        "async function loadOfficialLearningPaths(", 1
    )[0]


def test_official_paths_navigation_connects_to_listing_api() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    paths = client.get("/api/learning-paths").json()

    assert 'href="#official-learning-paths"' in page
    assert 'data-workspace="official-learning-paths"' in page
    assert 'href="/static/styles.css?v=' in page
    assert 'src="/static/app.js?v=' in page
    assert 'id="official-paths-status" role="status" aria-live="polite"' in page
    assert 'fetch("/api/learning-paths", { signal: controller.signal })' in script
    assert "No official learning paths are available yet." in script
    assert "Learning paths could not be loaded. Please try again." in script
    assert "module.title" in script
    assert 'fetch(\n      `/api/learning-paths/${encodeURIComponent(path.id)}`,' in script
    assert "{ signal: controller.signal }" in script
    assert "renderOfficialModule" in script
    assert "renderOfficialLesson" in script
    assert "All learning paths" in page
    assert "Lesson content is not available yet." in script
    assert "This learning path could not be loaded." in script
    assert paths[0]["modules"][0]["title"] == "Introduction"


def test_rapid_path_switching_invalidates_older_detail_responses() -> None:
    script = client.get("/static/app.js").text
    selection = official_path_selection_source()

    assert "let officialPathRequestId = 0" in script
    assert "const requestId = ++officialPathRequestId" in selection
    assert selection.index("const requestId = ++officialPathRequestId") < selection.index(
        "fetch(\n      `/api/learning-paths/${encodeURIComponent(path.id)}`,"
    )
    assert "officialSelectedPathId = path.id" in selection


def test_path_b_response_wins_when_it_arrives_before_path_a() -> None:
    selection = official_path_selection_source()
    response_read = selection.index("const detail = await response.json()")
    stale_guard = selection.index(
        "if (requestId !== officialPathRequestId || officialSelectedPathId !== path.id)"
    )
    render_modules = selection.index("showOfficialPathModules(detail)")

    assert response_read < stale_guard < render_modules
    assert "renderOfficialLesson(detail, lessonEntry.module, lessonEntry.lesson)" in selection


def test_outdated_path_request_failure_cannot_replace_newer_content() -> None:
    selection = official_path_selection_source()
    error_handler = selection.index("} catch (_error) {")
    stale_guard = selection.index(
        "if (requestId !== officialPathRequestId || officialSelectedPathId !== path.id)",
        error_handler,
    )
    clear_content = selection.index("officialPathContent.replaceChildren()", error_handler)
    show_error = selection.index("This learning path could not be loaded.", error_handler)

    assert error_handler < stale_guard < clear_content < show_error
    assert "button.addEventListener(\"click\", () => selectOfficialPath(path, button))" in client.get(
        "/static/app.js"
    ).text


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


def test_learning_path_detail_timeout_preserves_stale_response_guards() -> None:
    script = client.get("/static/app.js").text
    selection = script.split("async function selectOfficialPath(", 1)[1].split(
        "async function loadOfficialLearningPaths(", 1
    )[0]

    assert "new AbortController()" in selection
    assert "window.setTimeout(() => controller.abort(), 10000)" in selection
    assert "{ signal: controller.signal }" in selection
    assert "window.clearTimeout(timeoutId)" in selection
    assert selection.count(
        "requestId !== officialPathRequestId || officialSelectedPathId !== path.id"
    ) == 2
    assert '"Loading learning path..."' in selection
    assert "This learning path could not be loaded." in selection


def test_official_course_sidebar_uses_dynamic_path_module_and_lesson_data() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    outline = script.split("function renderOfficialPathOutline(", 1)[1].split(
        "function updateOfficialPathProgress(", 1
    )[0]
    module_renderer = script.split("function renderOfficialModule(", 1)[1].split(
        "function renderOfficialPathOutline(", 1
    )[0]

    assert 'id="official-course-sidebar"' in page
    assert 'id="official-course-outline"' in page
    assert "path.modules.forEach((module) =>" in outline
    assert "module.lessons.forEach((lessonItem) =>" in module_renderer
    assert "lessonItem.title" in module_renderer
    assert 'document.createElement("details")' in module_renderer
    assert 'document.createElement("summary")' in module_renderer
    assert 'button.addEventListener("click", () => renderOfficialLesson(path, module, lessonItem))' in module_renderer
    assert 'id="official-course-title"' in page
    assert 'id="official-course-progress-bar"' in page


def test_course_sidebar_tracks_active_and_persisted_lesson_completion() -> None:
    script = client.get("/static/app.js").text
    indicator_logic = script.split("function updateOfficialLessonIndicators()", 1)[1].split(
        "async function loadOfficialPathProgress(", 1
    )[0]
    progress_logic = script.split("async function loadOfficialPathProgress(", 1)[1].split(
        "function showOfficialPathModules(", 1
    )[0]

    assert 'button.setAttribute("aria-current", String(isActive))' in indicator_logic
    assert 'completion.textContent = "Completed"' in indicator_logic
    assert 'completion.textContent = "Not completed"' in indicator_logic
    assert 'completion.textContent = "Progress unavailable"' in indicator_logic
    assert 'fetch(\n        `/api/progress/lessons/${encodeURIComponent(lesson.id)}`,' in progress_logic
    assert 'Boolean(progress.completed)' in progress_logic
    assert 'controller.abort(), 10000' in progress_logic
    assert "officialLessonProgressVersions.get(lesson.id) !== version" in progress_logic
    assert 'officialLessonCompletion.set(state.lessonId, true)' in script


def test_course_sidebar_path_switch_and_return_invalidate_old_progress() -> None:
    script = client.get("/static/app.js").text
    select = official_path_selection_source()
    return_flow = script.split("function returnToOfficialPathList()", 1)[1].split(
        "officialPathsBack.addEventListener", 1
    )[0]

    assert "officialPathProgressRequestId += 1" in select
    assert "officialPathProgressControllers.forEach((controller) => controller.abort())" in select
    assert "showOfficialPathModules(detail)" in select
    assert "renderOfficialLesson(detail, lessonEntry.module, lessonEntry.lesson)" in select
    assert "targetLessonId = null" in select
    assert "officialPathProgressRequestId += 1" in return_flow
    assert "officialSelectedPath = null" in return_flow
    assert 'officialPathList.hidden = false' in return_flow
    assert "officialCourseSidebar.hidden = true" in return_flow


def test_sidebar_does_not_change_lesson_rendering_or_quiz_persistence() -> None:
    script = client.get("/static/app.js").text
    lesson_renderer = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function loadOfficialLessonProgress(", 1
    )[0]

    assert "renderLessonMarkdown(markdown)" in lesson_renderer
    assert "renderOfficialQuiz(lessonItem.quiz)" in lesson_renderer
    assert "loadOfficialLessonProgress(lessonItem.id, progressStatus, requestId)" in lesson_renderer
    assert 'fetch("/api/progress/quiz-attempts", {' in script
    assert 'state.saveStatus.textContent = "Result saved successfully. Lesson completed."' in script
    assert 'resetOfficialQuizProgress()' in script


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
    assert 'optionKey.textContent = key' in script
    assert 'optionText.textContent = question.options[key]' in script
    assert 'option.append(optionKey, optionText)' in script


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
    for function_name in ("renderOfficialLesson", "showOfficialPathModules"):
        body = script.split(f"function {function_name}(", 1)[1].split("\nfunction ", 1)[0]
        assert "officialQuizState = null" in body
    assert 'selectedWorkspaceName !== "official-learning-paths"' in script
    assert "resetOfficialQuizProgress()" in script


def test_official_quiz_handles_missing_or_empty_questions() -> None:
    script = client.get("/static/app.js").text

    assert "function renderOfficialQuiz(quiz)" in script
    assert "Array.isArray(quiz) && quiz.length > 0" in script
    assert "Quiz questions are not available yet." in script


def test_official_lesson_navigation_reuses_lesson_rendering_and_progress_flow() -> None:
    script = client.get("/static/app.js").text
    navigation = script.split("function renderOfficialLessonNavigation(", 1)[1].split(
        "function renderOfficialModule(", 1
    )[0]
    lesson = script.split("function renderOfficialLesson(", 1)[1].split(
        "function updateOfficialLessonIndicators(", 1
    )[0]

    assert 'navigation.setAttribute("aria-label", "Lesson navigation")' in navigation
    assert "previous.disabled = !neighbors.previous" in navigation
    assert "next.disabled = !neighbors.next" in navigation
    assert "renderOfficialLesson(" in navigation
    assert "neighbors.previous.module" in navigation
    assert "neighbors.next.module" in navigation
    assert "const lessonNavigation = renderOfficialLessonNavigation(path, module, lessonItem)" in lesson
    assert "officialQuizState = null" in lesson
    assert "loadOfficialLessonProgress(lessonItem.id, progressStatus, requestId)" in lesson
    assert "saveOfficialQuizAttempt" not in lesson


def test_official_lesson_navigation_preserves_dashboard_continue_learning_flow() -> None:
    script = client.get("/static/app.js").text

    assert 'dashboardContinueButton.addEventListener("click"' in script
    assert "navigateToOfficialPath(" in script
    assert "lesson.learning_path_id" in script
    assert "lesson.id" in script
    assert "button.addEventListener(\"click\", () => renderOfficialLesson(" in script


def test_official_learning_paths_resume_recent_lesson_with_safe_fallbacks() -> None:
    script = client.get("/static/app.js").text
    resume = script.split("async function resumeOfficialLearningPath(", 1)[1].split(
        "function startOfficialLessonResume(", 1
    )[0]
    selection = official_path_selection_source()

    assert 'await loadOfficialLearningPaths()' in resume
    assert 'fetch("/api/dashboard/summary", { signal: controller.signal })' in resume
    assert 'controller.abort(), 10000' in resume
    assert 'getOfficialResumeCandidates(paths, lastAccessedLesson)' in resume
    assert 'getOfficialResumeLesson(detail, targetLessonId)' in selection
    assert 'renderOfficialLesson(detail, lessonEntry.module, lessonEntry.lesson)' in selection
    assert 'result?.openedLesson' in resume


def test_manual_official_navigation_cancels_pending_automatic_resume() -> None:
    script = client.get("/static/app.js").text
    selection = official_path_selection_source()
    resume_guard = script.split("function isOfficialResumeCurrent(", 1)[1].split(
        "async function selectOfficialPath(", 1
    )[0]
    return_flow = script.split("function returnToOfficialPathList()", 1)[1].split(
        "officialPathsBack.addEventListener", 1
    )[0]
    workspace_flow = script.split("function showWorkspace(", 1)[1].split(
        "workspaceLinks.forEach", 1
    )[0]

    assert 'if (resumeRequestId === null) {\n    cancelOfficialLessonResume();' in selection
    assert 'requestId === officialResumeRequestId' in resume_guard
    assert 'officialResumeSuppressed' in resume_guard
    assert 'cancelOfficialLessonResume();' in return_flow
    assert 'enteringOfficialPaths' in workspace_flow
    assert '&& officialPathsWorkspace.hidden' in workspace_flow
    assert 'if (!officialPathsWorkspace.hidden' in workspace_flow
    assert 'officialPathRequestId += 1' in return_flow


def test_official_lesson_reading_view_hides_catalog_heading_and_keeps_return_control() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    lesson = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function loadOfficialLessonProgress(", 1
    )[0]
    return_flow = script.split("function returnToOfficialPathList()", 1)[1].split(
        "officialPathsBack.addEventListener", 1
    )[0]

    assert 'id="official-paths-back"' in page
    assert "officialPathsWorkspace.classList.add(\"is-reading\")" in lesson
    assert "officialPathsWorkspace.classList.remove(\"is-reading\")" in return_flow
    assert ".official-paths.is-reading > .section-heading { display: none; }" in styles
    assert ".official-course-sidebar" in styles
    assert ".official-path-detail.is-reading #official-path-content { max-width: 870px; }" in styles


def test_official_quiz_visual_refinement_preserves_accessible_selection_and_feedback() -> None:
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    question_rendering = script.split("function renderOfficialQuizQuestion()", 1)[1].split(
        "function submitOfficialQuizAnswer()", 1
    )[0]
    submit_logic = script.split("function submitOfficialQuizAnswer()", 1)[1].split(
        "function advanceOfficialQuiz()", 1
    )[0]

    assert "Question ${state.questionIndex + 1} of ${state.questions.length}" in question_rendering
    assert 'optionKey.className = "official-quiz-option-key"' in question_rendering
    assert 'option.setAttribute("aria-pressed", "false")' in question_rendering
    assert 'String(button === option)' in question_rendering
    assert "state.selectedKey === question.correct_answer" in submit_logic
    assert "state.feedbackLabel.textContent = isCorrect ? \"Correct!\" : \"Incorrect.\"" in submit_logic
    assert ".official-quiz-options button:focus-visible" in styles
    assert ".official-quiz-options button[aria-pressed=\"true\"]" in styles
    assert ".quiz-feedback.incorrect" in styles


def test_official_lesson_breadcrumb_renders_once_above_course_layout() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    template = page.split('id="official-lesson-breadcrumb-container"', 1)[1]
    assert template.index("</div>") < template.index('class="official-path-layout"')
    assert 'id="official-lesson-breadcrumb-container" hidden' in page

    lesson = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function loadOfficialLessonProgress(", 1
    )[0]
    assert "pathName.textContent = path.title" in lesson
    assert "moduleName.textContent = module.title" in lesson
    assert 'lessonName.setAttribute("aria-current", "page")' in lesson
    assert "officialLessonBreadcrumbContainer.replaceChildren(breadcrumb)" in lesson
    assert "officialLessonBreadcrumbContainer.hidden = false" in lesson
    assert "breadcrumb," not in lesson.split("officialPathContent.append(", 1)[1]
    assert ".official-lesson-breadcrumb { margin-bottom: 21px;" in styles

    for flow_name, end_marker in (
        ("function showOfficialPathModules(", "function returnToOfficialPathList("),
        ("function returnToOfficialPathList(", "officialPathsBack.addEventListener"),
    ):
        flow = script.split(flow_name, 1)[1].split(end_marker, 1)[0]
        assert "officialLessonBreadcrumbContainer.replaceChildren()" in flow
        assert "officialLessonBreadcrumbContainer.hidden = true" in flow


def test_official_lesson_fidelity_values_match_prototype_without_changing_quiz_logic() -> None:
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    assert "font-size: clamp(37px, 3.4vw, 48px)" in styles
    assert "font-size: 17px; line-height: 1.78" in styles
    assert "max-width: 74ch" in styles
    assert ".official-course-title" in styles and "font-size: 29px" in styles
    assert "min-height: 44px" in styles
    assert "font-size: 30px" in styles
    assert ".official-quiz-option-key" in styles and "border-radius: 50%" in styles
    assert "margin-top: 34px; padding-top: 19px" in styles
    assert 'state.selectedKey === question.correct_answer' in script
    assert 'fetch("/api/progress/quiz-attempts", {' in script
    navigation = script.split("function renderOfficialLessonNavigation(", 1)[1].split(
        "function renderOfficialModule(", 1
    )[0]
    assert "neighbors.previous.module" in navigation
    assert "neighbors.previous.lesson" in navigation
    assert "neighbors.next.module" in navigation
    assert "neighbors.next.lesson" in navigation


def test_reading_mode_hides_catalog_card_and_markdown_title_duplication() -> None:
    page = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    detail = client.get("/api/learning-paths/ai-fundamentals").json()
    lesson = detail["modules"][0]["lessons"][0]
    assert lesson["title"].strip().lower() == lesson["explanation"].splitlines()[0][2:].strip().lower()
    assert 'id="official-path-list"' in page
    assert ".official-path-list[hidden] { display: none; }" in styles
    assert "officialPathList.hidden = true" in script
    assert "officialPathList.hidden = false" in script

    renderer = script.split("function stripDuplicateLeadingLessonHeading(", 1)[1].split(
        "function getOrderedOfficialLessons(", 1
    )[0]
    assert "normalize(match[1]) === normalize(lessonTitle)" in renderer
    lesson_render = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function loadOfficialLessonProgress(", 1
    )[0]
    assert "stripDuplicateLeadingLessonHeading(lessonItem.explanation, lessonItem.title)" in lesson_render
    assert 'heading.textContent = lessonItem.title' in lesson_render
    assert "  heading,\n    progressStatus" not in lesson_render
    assert "progressStatus,\n    heading,\n    explanation" in lesson_render


def test_lesson_catalog_sidebar_and_quiz_behaviors_remain_connected() -> None:
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text
    show_path = script.split("function showOfficialPathModules(", 1)[1].split(
        "function returnToOfficialPathList(", 1
    )[0]
    return_to_catalog = script.split("function returnToOfficialPathList(", 1)[1].split(
        "officialPathsBack.addEventListener", 1
    )[0]
    lesson_render = script.split("function renderOfficialLesson(", 1)[1].split(
        "async function loadOfficialLessonProgress(", 1
    )[0]
    assert "officialCourseSidebar.hidden = false" in show_path
    assert "officialPathList.hidden = true" in show_path
    assert 'class="official-course-heading">Course Content</p>' in client.get("/").text
    assert "officialCourseProgressPercent.textContent = `${completionPercent}%`" in script
    assert 'officialCourseOutline.querySelectorAll(".official-course-module")' in lesson_render
    assert "activeModule.open = true" in lesson_render
    assert "updateOfficialLessonIndicators()" in lesson_render
    assert "officialPathList.hidden = false" in return_to_catalog
    assert 'fetch("/api/progress/quiz-attempts", {' in script
    assert "state.selectedKey === question.correct_answer" in script
    assert "neighbors.previous.module" in script and "neighbors.next.module" in script
    assert "getOfficialResumeLesson(detail, targetLessonId)" in script
    assert ".official-quiz-controls { margin-top: 19px; display: flex; justify-content: flex-start;" in styles


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
