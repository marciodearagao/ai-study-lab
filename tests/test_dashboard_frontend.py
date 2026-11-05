from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def dashboard_assets():
    return client.get("/").text, client.get("/static/app.js").text


def test_home_contains_accessible_dashboard_sections_and_loading_state():
    page, script = dashboard_assets()

    assert 'id="home" data-workspace="home"' in page
    assert 'id="dashboard-status" role="status" aria-live="polite"' in page
    assert 'id="dashboard-retry" type="button" hidden' in page
    assert 'aria-busy="true" hidden' in page
    for section_id in (
        "continue-title",
        "overall-progress-title",
        "dashboard-paths-title",
        "dashboard-activity-title",
    ):
        assert f'aria-labelledby="{section_id}"' in page
    assert 'id="dashboard-progress-bar" max="100" value="0"' in page
    assert 'fetch("/api/dashboard/summary", { signal: controller.signal })' in script
    assert '"Loading dashboard..."' in script


def test_dashboard_renders_empty_progress_and_starting_point():
    _page, script = dashboard_assets()
    render_flow = script.split("function renderDashboardSummary(", 1)[1].split(
        "function dashboardRequestIsCurrent(", 1
    )[0]

    assert '"No recent lesson yet. Choose an official learning path to get started."' in render_flow
    assert "Explore Official Learning Paths" in _page
    assert '"No official learning paths are available yet."' in render_flow
    assert '"No quiz attempts yet. Complete a lesson quiz to see activity here."' in render_flow
    assert "summary.total_lessons" in render_flow
    assert "summary.completion_percentage" in render_flow
    assert "Math.min(100, summary.completion_percentage)" in render_flow


def test_dashboard_renders_completed_count_and_path_percentages():
    _page, script = dashboard_assets()
    render_flow = script.split("function renderDashboardSummary(", 1)[1].split(
        "function dashboardRequestIsCurrent(", 1
    )[0]

    assert '`${summary.completed_lessons} of ${summary.total_lessons} lessons completed`' in render_flow
    assert "dashboardProgressBar.value" in render_flow
    assert "dashboardProgressPercentage.textContent" in render_flow
    assert "path.completed_lessons" in render_flow
    assert "path.completion_percentage" in render_flow
    assert 'open.textContent = "Open learning path"' in render_flow


def test_recent_activity_renders_titles_scores_and_dates():
    _page, script = dashboard_assets()
    render_flow = script.split("function renderDashboardSummary(", 1)[1].split(
        "function dashboardRequestIsCurrent(", 1
    )[0]

    assert "summary.recent_quiz_attempts.slice(0, 5)" in render_flow
    assert "attempt.lesson_title" in render_flow
    assert "attempt.score" in render_flow
    assert "attempt.total_questions" in render_flow
    assert "date.dateTime = attempt.completed_at" in render_flow
    assert "formatDashboardDate(attempt.completed_at)" in render_flow


def test_continue_learning_routes_to_the_exact_official_lesson():
    _page, script = dashboard_assets()
    continue_flow = script.split("dashboardContinueButton.addEventListener", 1)[1].split(
        "function resetOfficialQuizProgress(", 1
    )[0]
    navigation_flow = script.split("function navigateToOfficialPath(", 1)[1].split(
        "dashboardRetry.addEventListener", 1
    )[0]
    path_selection = script.split("async function selectOfficialPath(", 1)[1].split(
        "async function loadOfficialLearningPaths(", 1
    )[0]

    assert "most_recently_accessed_lesson" in continue_flow
    assert "lesson.learning_path_id" in continue_flow
    assert "lesson.id" in continue_flow
    assert "selectOfficialPath({ id: pathId, title: pathTitle }, null, lessonId)" in navigation_flow
    assert "renderOfficialLesson(detail, module, lesson)" in path_selection


def test_dashboard_path_action_uses_existing_official_path_selection():
    _page, script = dashboard_assets()
    render_flow = script.split("function renderDashboardSummary(", 1)[1].split(
        "function dashboardRequestIsCurrent(", 1
    )[0]
    navigation_flow = script.split("function navigateToOfficialPath(", 1)[1].split(
        "dashboardRetry.addEventListener", 1
    )[0]

    assert "navigateToOfficialPath(path.id, path.title)" in render_flow
    assert 'window.location.hash = "#official-learning-paths"' in navigation_flow
    assert 'showWorkspace("official-learning-paths")' in navigation_flow


def test_dashboard_api_errors_offer_retry_and_loading_has_timeout():
    _page, script = dashboard_assets()
    load_flow = script.split("async function loadDashboardSummary()", 1)[1].split(
        "function navigateToOfficialPath(", 1
    )[0]

    assert '"Dashboard could not be loaded. Please try again."' in load_flow
    assert "dashboardRetry.hidden = false" in load_flow
    assert 'dashboardRetry.addEventListener("click", loadDashboardSummary)' in script
    assert "controller.abort(), 10000" in load_flow
    assert "window.clearTimeout(timeoutId)" in load_flow


def test_dashboard_refreshes_when_home_is_opened_again():
    _page, script = dashboard_assets()
    workspace_flow = script.split("function showWorkspace(name)", 1)[1].split(
        "workspaceLinks.forEach", 1
    )[0]

    assert 'selected.dataset.workspace === "home"' in workspace_flow
    assert "loadDashboardSummary()" in workspace_flow
    assert 'selected.dataset.workspace === "official-learning-paths"' in workspace_flow


def test_stale_dashboard_responses_are_cancelled_or_ignored():
    _page, script = dashboard_assets()
    load_flow = script.split("async function loadDashboardSummary()", 1)[1].split(
        "function navigateToOfficialPath(", 1
    )[0]
    workspace_flow = script.split("function showWorkspace(name)", 1)[1].split(
        "workspaceLinks.forEach", 1
    )[0]

    assert "dashboardRequestId += 1" in load_flow
    assert "dashboardRequestIsCurrent(requestId)" in load_flow
    assert "requestId === dashboardRequestId" in load_flow
    assert "dashboardController.abort()" in workspace_flow


def test_existing_workspace_navigation_and_study_features_remain_available():
    page, script = dashboard_assets()

    for workspace in ("study", "official-learning-paths", "interview-coach", "progress"):
        assert f'href="#{workspace}" data-workspace-link' in page
    study_flow = script.split("const workspaces =", 1)[0]
    assert "function answerQuizQuestion(selectedButton, selectedAnswer)" in study_flow
    assert 'let endpoint = "/api/lessons"' in study_flow
    assert 'endpoint = "/api/lessons/pdf"' in study_flow
