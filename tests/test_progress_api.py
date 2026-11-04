import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main as app_main


client = TestClient(app_main.app)
LESSON_ID = "what-is-artificial-intelligence"


@pytest.fixture
def progress_database(tmp_path, monkeypatch):
    database_path = tmp_path / "isolated" / "asl.db"
    monkeypatch.setattr(app_main, "DATABASE_PATH", database_path)
    return database_path


def submit_attempt(score, total_questions=4):
    return client.post(
        "/api/progress/quiz-attempts",
        json={
            "lesson_id": LESSON_ID,
            "score": score,
            "total_questions": total_questions,
        },
    )


def test_completed_attempt_records_progress_and_attempt(progress_database):
    response = submit_attempt(3)

    assert response.status_code == 200
    attempt = response.json()
    assert attempt["id"] == 1
    assert attempt["lesson_id"] == LESSON_ID
    assert (attempt["score"], attempt["total_questions"]) == (3, 4)
    assert attempt["completed_at"].endswith("Z")
    progress = client.get(f"/api/progress/lessons/{LESSON_ID}").json()
    assert progress["completed"] is True
    assert progress["completed_at"] == attempt["completed_at"]


def test_zero_score_still_completes_the_lesson(progress_database):
    assert submit_attempt(0).status_code == 200
    progress = client.get(f"/api/progress/lessons/{LESSON_ID}").json()

    assert progress["completed"] is True
    assert progress["latest_quiz_score"] == 0


def test_multiple_attempts_preserve_first_completion_and_report_scores(progress_database):
    first_attempt = submit_attempt(1).json()
    first_completion = "2025-01-02T03:04:05.000Z"
    with sqlite3.connect(progress_database) as connection:
        connection.execute(
            "UPDATE lesson_progress SET completed_at = ? WHERE lesson_id = ?",
            (first_completion, LESSON_ID),
        )

    second_attempt = submit_attempt(4).json()
    third_attempt = submit_attempt(2).json()
    progress = client.get(f"/api/progress/lessons/{LESSON_ID}").json()

    assert second_attempt["id"] == first_attempt["id"] + 1
    assert third_attempt["id"] == second_attempt["id"] + 1
    assert progress["completed_at"] == first_completion
    assert progress["latest_quiz_score"] == 2
    assert progress["best_quiz_score"] == 4
    assert [item["score"] for item in progress["quiz_attempts"]] == [1, 4, 2]
    assert [item["completed_at"] for item in progress["quiz_attempts"]] == sorted(
        item["completed_at"] for item in progress["quiz_attempts"]
    )


def test_empty_progress_has_null_timestamps_scores_and_no_attempts(progress_database):
    response = client.get(f"/api/progress/lessons/{LESSON_ID}")

    assert response.status_code == 200
    assert response.json() == {
        "lesson_id": LESSON_ID,
        "completed": False,
        "completed_at": None,
        "last_accessed_at": None,
        "latest_quiz_score": None,
        "best_quiz_score": None,
        "quiz_attempts": [],
    }


def test_access_records_timestamp_without_completing_lesson(progress_database):
    response = client.post(f"/api/progress/lessons/{LESSON_ID}/access")
    progress = client.get(f"/api/progress/lessons/{LESSON_ID}").json()

    assert response.status_code == 200
    assert response.json()["last_accessed_at"].endswith("Z")
    assert progress["completed"] is False
    assert progress["completed_at"] is None
    assert progress["last_accessed_at"] == response.json()["last_accessed_at"]


def test_access_update_preserves_existing_completion(progress_database):
    attempt = submit_attempt(2).json()
    response = client.post(f"/api/progress/lessons/{LESSON_ID}/access")
    progress = client.get(f"/api/progress/lessons/{LESSON_ID}").json()

    assert response.status_code == 200
    assert progress["completed"] is True
    assert progress["completed_at"] == attempt["completed_at"]
    assert progress["last_accessed_at"] == response.json()["last_accessed_at"]


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", "/api/progress/lessons/unknown-lesson", None),
        ("post", "/api/progress/lessons/unknown-lesson/access", None),
        (
            "post",
            "/api/progress/quiz-attempts",
            {"lesson_id": "unknown-lesson", "score": 1, "total_questions": 4},
        ),
    ],
)
def test_unknown_lessons_return_404(progress_database, method, url, body):
    response = client.request(method, url, json=body)

    assert response.status_code == 404
    assert response.json() == {"detail": "Lesson not found."}


@pytest.mark.parametrize(
    ("score", "total_questions"),
    [(-1, 4), (5, 4), (0, 0), (0, 3)],
)
def test_invalid_attempt_scores_or_question_counts_return_422(
    progress_database, score, total_questions
):
    response = submit_attempt(score, total_questions)

    assert response.status_code == 422


def test_progress_persists_across_separate_requests(progress_database):
    submitted = submit_attempt(3)
    fetched = client.get(f"/api/progress/lessons/{LESSON_ID}")

    assert submitted.status_code == fetched.status_code == 200
    assert fetched.json()["quiz_attempts"][0]["id"] == submitted.json()["id"]


def test_database_failures_return_safe_server_error(tmp_path, monkeypatch):
    def fail_initialization(_database_path):
        raise sqlite3.OperationalError("private database path")

    monkeypatch.setattr(app_main, "DATABASE_PATH", tmp_path / "isolated" / "asl.db")
    monkeypatch.setattr(app_main, "initialize_database", fail_initialization)

    response = submit_attempt(2)

    assert response.status_code == 500
    assert response.json() == {"detail": "Progress storage is unavailable."}
    assert "private database path" not in response.text
    assert str(tmp_path) not in response.text
