import sqlite3
from datetime import datetime, timezone

import pytest

from app.database import initialize_database


def connect(database_path):
    return sqlite3.connect(database_path)


def add_incomplete_progress(connection, lesson_id="intro-to-ai"):
    connection.execute(
        "INSERT INTO lesson_progress (lesson_id) VALUES (?)",
        (lesson_id,),
    )


def test_initialization_creates_expected_tables_and_columns(tmp_path) -> None:
    database_path = tmp_path / "nested" / "asl.db"

    initialize_database(database_path)

    with connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        progress_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(lesson_progress)")
        }
        attempt_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(quiz_attempts)")
        }

    assert tables == {"lesson_progress", "quiz_attempts"}
    assert progress_columns == {
        "lesson_id", "completed", "completed_at", "last_accessed_at"
    }
    assert attempt_columns == {
        "id", "lesson_id", "score", "total_questions", "completed_at"
    }


def test_repeated_initialization_preserves_existing_records(tmp_path) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)
    with connect(database_path) as connection:
        connection.execute(
            "INSERT INTO lesson_progress (lesson_id) VALUES (?)", ("intro-to-ai",)
        )
        connection.execute(
            "INSERT INTO quiz_attempts (lesson_id, score, total_questions) "
            "VALUES (?, ?, ?)",
            ("intro-to-ai", 3, 4),
        )

    initialize_database(database_path)

    with connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM lesson_progress").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 1


def test_one_lesson_can_have_multiple_completed_quiz_attempts(tmp_path) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)
    with connect(database_path) as connection:
        add_incomplete_progress(connection)
        connection.executemany(
            "INSERT INTO quiz_attempts (lesson_id, score, total_questions) "
            "VALUES (?, ?, ?)",
            [
                ("intro-to-ai", 2, 4),
                ("intro-to-ai", 4, 4),
            ],
        )
        attempts = connection.execute(
            "SELECT id, score, total_questions, completed_at "
            "FROM quiz_attempts WHERE lesson_id = ? ORDER BY id",
            ("intro-to-ai",),
        ).fetchall()

    assert len(attempts) == 2
    assert attempts[0][0] != attempts[1][0]
    assert [(attempt[1], attempt[2]) for attempt in attempts] == [(2, 4), (4, 4)]
    for attempt in attempts:
        assert attempt[3].endswith("Z")
        assert datetime.fromisoformat(attempt[3].replace("Z", "+00:00")).utcoffset() == timezone.utc.utcoffset(None)


@pytest.mark.parametrize(
    ("score", "total_questions"),
    [(-1, 4), (5, 4), (0, 0), (0, -1)],
)
def test_invalid_quiz_scores_and_question_counts_are_rejected(
    tmp_path, score, total_questions
) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)

    with connect(database_path) as connection:
        add_incomplete_progress(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO quiz_attempts (lesson_id, score, total_questions) "
                "VALUES (?, ?, ?)",
                ("intro-to-ai", score, total_questions),
            )


@pytest.mark.parametrize(
    ("completed", "completed_at"),
    [(2, None), (0, "2026-01-01T00:00:00.000Z"), (1, None)],
)
def test_progress_completion_constraints_are_enforced(
    tmp_path, completed, completed_at
) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)

    with connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO lesson_progress (lesson_id, completed, completed_at) "
                "VALUES (?, ?, ?)",
                ("intro-to-ai", completed, completed_at),
            )


def test_progress_timestamps_require_utc_z_format(tmp_path) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)

    with connect(database_path) as connection:
        connection.execute(
            "INSERT INTO lesson_progress (lesson_id, completed, completed_at, last_accessed_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "valid-lesson",
                1,
                "2026-11-02T12:30:00.000Z",
                "2026-11-02T12:30:00.000Z",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO lesson_progress (lesson_id, completed, completed_at) "
                "VALUES (?, ?, ?)",
                ("offset-lesson", 1, "2026-11-02T12:30:00.000+00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO lesson_progress (lesson_id, last_accessed_at) "
                "VALUES (?, ?)",
                ("naive-lesson", "2026-11-02T12:30:00.000"),
            )


def test_quiz_attempt_persists_between_separate_connections(tmp_path) -> None:
    database_path = tmp_path / "asl.db"
    initialize_database(database_path)
    with connect(database_path) as first_connection:
        add_incomplete_progress(first_connection)
        first_connection.execute(
            "INSERT INTO quiz_attempts (lesson_id, score, total_questions) "
            "VALUES (?, ?, ?)",
            ("intro-to-ai", 3, 4),
        )

    with connect(database_path) as second_connection:
        stored_attempt = second_connection.execute(
            "SELECT score, total_questions FROM quiz_attempts WHERE lesson_id = ?",
            ("intro-to-ai",),
        ).fetchone()

    assert stored_attempt == (3, 4)


def test_temporary_databases_are_isolated(tmp_path) -> None:
    first_database = tmp_path / "first" / "asl.db"
    second_database = tmp_path / "second" / "asl.db"
    initialize_database(first_database)
    initialize_database(second_database)

    with connect(first_database) as connection:
        add_incomplete_progress(connection)
    with connect(second_database) as connection:
        progress_count = connection.execute(
            "SELECT COUNT(*) FROM lesson_progress"
        ).fetchone()[0]

    assert progress_count == 0
