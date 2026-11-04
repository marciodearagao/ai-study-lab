"""Explicit initialization for local student-progress persistence."""

from pathlib import Path
import sqlite3


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "asl.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id TEXT PRIMARY KEY CHECK (length(trim(lesson_id)) > 0),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    completed_at TEXT,
    last_accessed_at TEXT,
    CHECK (
        (completed = 0 AND completed_at IS NULL)
        OR (completed = 1 AND completed_at IS NOT NULL)
    ),
    CHECK (
        completed_at IS NULL
        OR (
            strftime('%Y-%m-%dT%H:%M:%fZ', completed_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%fZ', completed_at) = completed_at
        )
    ),
    CHECK (
        last_accessed_at IS NULL
        OR (
            strftime('%Y-%m-%dT%H:%M:%fZ', last_accessed_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%fZ', last_accessed_at) = last_accessed_at
        )
    )
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY,
    lesson_id TEXT NOT NULL CHECK (length(trim(lesson_id)) > 0),
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= total_questions),
    total_questions INTEGER NOT NULL CHECK (total_questions > 0),
    completed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        strftime('%Y-%m-%dT%H:%M:%fZ', completed_at) IS NOT NULL
        AND strftime('%Y-%m-%dT%H:%M:%fZ', completed_at) = completed_at
    )
);
"""


def initialize_database(database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Create the database directory and tables without replacing existing data."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SCHEMA)
    finally:
        connection.close()
