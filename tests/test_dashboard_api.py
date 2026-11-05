import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.content import ContentLoadError, load_learning_paths
from app.database import initialize_database


client = TestClient(app_main.app)
SUMMARY_URL = "/api/dashboard/summary"


@pytest.fixture
def dashboard_content(monkeypatch):
    paths = [
        {
            "id": "ai-fundamentals",
            "title": "AI Fundamentals",
            "modules": [
                {
                    "id": "introduction",
                    "lessons": [
                        {"id": "lesson-one", "title": "Lesson One"},
                        {"id": "lesson-two", "title": "Lesson Two"},
                    ],
                }
            ],
        },
        {
            "id": "ai-practice",
            "title": "AI Practice",
            "modules": [
                {"id": "practice", "lessons": [{"id": "lesson-three", "title": "Lesson Three"}]}
            ],
        },
    ]
    monkeypatch.setattr(app_main, "load_learning_paths", lambda: paths)
    return paths


@pytest.fixture
def dashboard_database(tmp_path, monkeypatch):
    database_path = tmp_path / "dashboard" / "asl.db"
    monkeypatch.setattr(app_main, "DATABASE_PATH", database_path)
    return database_path


def add_progress(database_path, lesson_id, completed=0, completed_at=None, last_accessed_at=None):
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO lesson_progress "
            "(lesson_id, completed, completed_at, last_accessed_at) "
            "VALUES (?, ?, ?, ?)",
            (lesson_id, completed, completed_at, last_accessed_at),
        )


def add_attempts(database_path, attempts):
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "INSERT INTO quiz_attempts "
            "(lesson_id, score, total_questions, completed_at) VALUES (?, ?, ?, ?)",
            attempts,
        )


def test_empty_progress_returns_zero_summary_and_path_breakdown(
    dashboard_database, dashboard_content
):
    response = client.get(SUMMARY_URL)

    assert response.status_code == 200
    assert response.json() == {
        "total_lessons": 3,
        "completed_lessons": 0,
        "completion_percentage": 0,
        "most_recently_accessed_lesson": None,
        "learning_paths": [
            {
                "id": "ai-fundamentals",
                "title": "AI Fundamentals",
                "total_lessons": 2,
                "completed_lessons": 0,
                "completion_percentage": 0,
            },
            {
                "id": "ai-practice",
                "title": "AI Practice",
                "total_lessons": 1,
                "completed_lessons": 0,
                "completion_percentage": 0,
            },
        ],
        "recent_quiz_attempts": [],
    }


def test_completion_counts_only_completed_lessons_and_calculates_percentages(
    dashboard_database, dashboard_content
):
    add_progress(
        dashboard_database,
        "lesson-one",
        completed=1,
        completed_at="2026-01-01T00:00:00.000Z",
    )
    add_progress(dashboard_database, "lesson-two")
    add_progress(
        dashboard_database,
        "lesson-three",
        completed=1,
        completed_at="2026-01-01T00:00:00.000Z",
    )

    summary = client.get(SUMMARY_URL).json()

    assert summary["total_lessons"] == 3
    assert summary["completed_lessons"] == 2
    assert summary["completion_percentage"] == 66.67
    assert [path["completion_percentage"] for path in summary["learning_paths"]] == [50.0, 100.0]


def test_most_recent_access_uses_current_lesson_and_returns_path_reference(
    dashboard_database, dashboard_content
):
    add_progress(
        dashboard_database,
        "lesson-one",
        last_accessed_at="2026-01-01T10:00:00.000Z",
    )
    add_progress(
        dashboard_database,
        "lesson-three",
        last_accessed_at="2026-01-02T10:00:00.000Z",
    )
    add_progress(
        dashboard_database,
        "removed-lesson",
        last_accessed_at="2026-01-03T10:00:00.000Z",
    )

    summary = client.get(SUMMARY_URL).json()

    assert summary["most_recently_accessed_lesson"] == {
        "id": "lesson-three",
        "title": "Lesson Three",
        "learning_path_id": "ai-practice",
    }


def test_recent_attempts_are_ordered_with_ties_broken_by_id_and_limited_to_five(
    dashboard_database, dashboard_content
):
    add_attempts(
        dashboard_database,
        [
            ("lesson-one", 1, 4, "2026-01-01T00:00:01.000Z"),
            ("lesson-two", 2, 4, "2026-01-01T00:00:02.000Z"),
            ("lesson-three", 3, 4, "2026-01-01T00:00:03.000Z"),
            ("lesson-one", 4, 4, "2026-01-01T00:00:04.000Z"),
            ("lesson-two", 1, 4, "2026-01-01T00:00:05.000Z"),
            ("lesson-three", 2, 4, "2026-01-01T00:00:05.000Z"),
            ("lesson-one", 3, 4, "2026-01-01T00:00:06.000Z"),
        ],
    )

    recent = client.get(SUMMARY_URL).json()["recent_quiz_attempts"]

    assert len(recent) == 5
    assert [attempt["score"] for attempt in recent] == [3, 2, 1, 4, 3]
    assert [attempt["lesson_title"] for attempt in recent] == [
        "Lesson One",
        "Lesson Three",
        "Lesson Two",
        "Lesson One",
        "Lesson Three",
    ]


def test_multiple_attempts_do_not_double_count_completed_lessons(
    dashboard_database, dashboard_content
):
    add_progress(
        dashboard_database,
        "lesson-one",
        completed=1,
        completed_at="2026-01-01T00:00:00.000Z",
    )
    add_attempts(
        dashboard_database,
        [
            ("lesson-one", 1, 4, "2026-01-01T00:00:01.000Z"),
            ("lesson-one", 2, 4, "2026-01-01T00:00:02.000Z"),
            ("lesson-one", 4, 4, "2026-01-01T00:00:03.000Z"),
        ],
    )

    summary = client.get(SUMMARY_URL).json()

    assert summary["completed_lessons"] == 1
    assert summary["completion_percentage"] == 33.33
    assert len(summary["recent_quiz_attempts"]) == 3


def test_removed_content_ids_are_excluded_from_counts_access_and_recent_activity(
    dashboard_database, dashboard_content
):
    add_progress(
        dashboard_database,
        "removed-lesson",
        completed=1,
        completed_at="2026-01-01T00:00:00.000Z",
        last_accessed_at="2026-01-02T00:00:00.000Z",
    )
    add_attempts(
        dashboard_database,
        [("removed-lesson", 4, 4, "2026-01-03T00:00:00.000Z")],
    )

    summary = client.get(SUMMARY_URL).json()

    assert summary["completed_lessons"] == 0
    assert summary["most_recently_accessed_lesson"] is None
    assert summary["recent_quiz_attempts"] == []


def test_paths_and_modules_with_no_lessons_return_zero_percentage(
    dashboard_database, monkeypatch, tmp_path
):
    content_dir = tmp_path / "empty-content"
    for directory in ("paths", "modules", "lessons"):
        (content_dir / directory).mkdir(parents=True)
    (content_dir / "paths" / "empty-path.json").write_text(
        json.dumps({"id": "empty-path", "title": "Empty Path", "modules": []}),
        encoding="utf-8",
    )
    (content_dir / "paths" / "empty-module-path.json").write_text(
        json.dumps(
            {
                "id": "empty-module-path",
                "title": "Empty Module Path",
                "modules": ["empty-module"],
            }
        ),
        encoding="utf-8",
    )
    (content_dir / "modules" / "empty-module.json").write_text(
        json.dumps(
            {
                "id": "empty-module",
                "path_id": "empty-module-path",
                "title": "Empty Module",
                "lessons": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        app_main, "load_learning_paths", lambda: load_learning_paths(content_dir)
    )

    summary = client.get(SUMMARY_URL).json()

    assert summary["total_lessons"] == 0
    assert summary["completed_lessons"] == 0
    assert summary["completion_percentage"] == 0
    assert summary["learning_paths"] == [
        {
            "id": "empty-module-path",
            "title": "Empty Module Path",
            "total_lessons": 0,
            "completed_lessons": 0,
            "completion_percentage": 0,
        },
        {
            "id": "empty-path",
            "title": "Empty Path",
            "total_lessons": 0,
            "completed_lessons": 0,
            "completion_percentage": 0,
        },
    ]


def test_database_failure_returns_safe_server_error(
    dashboard_database, dashboard_content, monkeypatch
):
    def fail_initialization(_database_path):
        raise sqlite3.OperationalError("private database path")

    monkeypatch.setattr(app_main, "initialize_database", fail_initialization)

    response = client.get(SUMMARY_URL)

    assert response.status_code == 500
    assert response.json() == {"detail": "Progress storage is unavailable."}
    assert "private database path" not in response.text
    assert str(dashboard_database.parent) not in response.text


def test_content_loading_failure_returns_safe_server_error(monkeypatch):
    def fail_loading():
        raise ContentLoadError("private content path")

    monkeypatch.setattr(app_main, "load_learning_paths", fail_loading)

    response = client.get(SUMMARY_URL)

    assert response.status_code == 500
    assert response.json() == {"detail": "Learning content is unavailable."}
    assert "private content path" not in response.text
