"""Load and validate the file-based learning content."""

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any


DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OPTION_KEYS = ("A", "B", "C", "D")
_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class ContentLoadError(ValueError):
    """Raised when learning content is missing or invalid."""


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContentLoadError(f"Invalid {label} identifier: {value!r}.")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentLoadError(f"{label} must be a nonempty string.")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContentLoadError(f"{label} must contain a JSON object.")
    return value


def _identifier_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ContentLoadError(f"{label} must be a list of identifiers.")
    identifiers = [_identifier(item, label) for item in value]
    if len(set(identifiers)) != len(identifiers):
        raise ContentLoadError(f"{label} contains duplicate identifiers.")
    return identifiers


def _read_json_file(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContentLoadError(f"Missing {kind} file: {path}.") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContentLoadError(f"Could not read {kind} file {path}: {error}.") from error
    return _object(value, f"{kind.title()} file {path}")


def _read_record(directory: Path, identifier: str, kind: str) -> dict[str, Any]:
    identifier = _identifier(identifier, kind)
    path = directory / f"{identifier}.json"
    record = _read_json_file(path, kind)
    record_id = _identifier(record.get("id"), f"{kind} in {path}")
    if record_id != identifier:
        raise ContentLoadError(
            f"{kind.title()} identifier {record_id!r} does not match filename {path.name!r}."
        )
    return record


def _load_explanation(lessons_dir: Path, filename: Any, lesson_id: str) -> str:
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or PurePosixPath(filename).name != filename
        or PureWindowsPath(filename).name != filename
        or Path(filename).suffix.lower() != ".md"
    ):
        raise ContentLoadError(
            f"Lesson {lesson_id!r} has an invalid explanation_file path."
        )

    lesson_dir = lessons_dir.resolve()
    explanation_path = (lessons_dir / filename).resolve()
    try:
        explanation_path.relative_to(lesson_dir)
    except ValueError as error:
        raise ContentLoadError(
            f"Lesson {lesson_id!r} explanation_file must stay inside {lessons_dir}."
        ) from error

    try:
        explanation = explanation_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ContentLoadError(
            f"Missing explanation file for lesson {lesson_id!r}: {filename}."
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise ContentLoadError(
            f"Could not read explanation for lesson {lesson_id!r}: {error}."
        ) from error
    return _text(explanation, f"Explanation for lesson {lesson_id!r}")


def _load_quiz(quiz: Any, lesson_id: str) -> list[dict[str, Any]]:
    if not isinstance(quiz, list) or not quiz:
        raise ContentLoadError(f"Lesson {lesson_id!r} quiz must be a nonempty list.")

    questions: list[dict[str, Any]] = []
    question_ids: set[str] = set()
    for index, value in enumerate(quiz, start=1):
        label = f"Lesson {lesson_id!r} quiz question {index}"
        question = _object(value, label)
        question_id = _identifier(question.get("id"), f"{label} question")
        if question_id in question_ids:
            raise ContentLoadError(f"{label} has duplicate identifier {question_id!r}.")
        question_ids.add(question_id)

        options = _object(question.get("options"), f"{label} options")
        if set(options) != set(OPTION_KEYS) or len(options) != len(OPTION_KEYS):
            raise ContentLoadError(
                f"{label} options must have exactly the keys A, B, C, and D."
            )
        option_texts = [_text(options[key], f"{label} option {key}") for key in OPTION_KEYS]
        if len({text.strip().casefold() for text in option_texts}) != len(OPTION_KEYS):
            raise ContentLoadError(f"{label} options must be distinct.")

        correct_answer = question.get("correct_answer")
        if not isinstance(correct_answer, str) or correct_answer not in options:
            raise ContentLoadError(
                f"{label} correct_answer must reference an option key A, B, C, or D."
            )
        questions.append(
            {
                "id": question_id,
                "question": _text(question.get("question"), f"{label} question"),
                "options": {key: options[key] for key in OPTION_KEYS},
                "correct_answer": correct_answer,
            }
        )
    return questions


def load_learning_paths(
    content_dir: str | Path = DEFAULT_CONTENT_DIR,
) -> list[dict[str, Any]]:
    """Load all paths with nested modules, lessons, Markdown, and quizzes.

    Returned dictionaries contain only JSON-compatible values and are suitable
    for later serialization by an API.
    """

    root = Path(content_dir).resolve()
    paths_dir = root / "paths"
    modules_dir = root / "modules"
    lessons_dir = root / "lessons"
    for directory, label in (
        (paths_dir, "paths"),
        (modules_dir, "modules"),
        (lessons_dir, "lessons"),
    ):
        if not directory.is_dir():
            raise ContentLoadError(f"Missing {label} directory: {directory}.")

    path_files = sorted(paths_dir.glob("*.json"))
    if not path_files:
        raise ContentLoadError(f"No learning path JSON files found in {paths_dir}.")

    result: list[dict[str, Any]] = []
    referenced_modules: set[str] = set()
    referenced_lessons: set[str] = set()

    for path_file in path_files:
        path_id = _identifier(path_file.stem, "learning path file")
        path = _read_record(paths_dir, path_id, "learning path")
        path_title = _text(path.get("title"), f"Learning path {path_id!r} title")
        module_ids = _identifier_list(
            path.get("modules"), f"Learning path {path_id!r} modules"
        )
        modules: list[dict[str, Any]] = []

        for module_id in module_ids:
            if module_id in referenced_modules:
                raise ContentLoadError(f"Module {module_id!r} is referenced more than once.")
            referenced_modules.add(module_id)
            module = _read_record(modules_dir, module_id, "module")
            module_path_id = _identifier(
                module.get("path_id"), f"module {module_id} path"
            )
            if module_path_id != path_id:
                raise ContentLoadError(
                    f"Module {module_id!r} references path {module_path_id!r}; "
                    f"expected {path_id!r}."
                )
            module_title = _text(module.get("title"), f"Module {module_id!r} title")
            lesson_ids = _identifier_list(
                module.get("lessons"), f"Module {module_id!r} lessons"
            )
            lessons: list[dict[str, Any]] = []

            for lesson_id in lesson_ids:
                if lesson_id in referenced_lessons:
                    raise ContentLoadError(f"Lesson {lesson_id!r} is referenced more than once.")
                referenced_lessons.add(lesson_id)
                lesson = _read_record(lessons_dir, lesson_id, "lesson")
                lesson_module_id = _identifier(
                    lesson.get("module_id"), f"lesson {lesson_id} module"
                )
                if lesson_module_id != module_id:
                    raise ContentLoadError(
                        f"Lesson {lesson_id!r} references module {lesson_module_id!r}; "
                        f"expected {module_id!r}."
                    )
                lessons.append(
                    {
                        "id": lesson_id,
                        "title": _text(lesson.get("title"), f"Lesson {lesson_id!r} title"),
                        "explanation": _load_explanation(
                            lessons_dir, lesson.get("explanation_file"), lesson_id
                        ),
                        "quiz": _load_quiz(lesson.get("quiz"), lesson_id),
                    }
                )

            modules.append(
                {"id": module_id, "title": module_title, "lessons": lessons}
            )
        result.append({"id": path_id, "title": path_title, "modules": modules})

    for directory, kind, referenced in (
        (modules_dir, "module", referenced_modules),
        (lessons_dir, "lesson", referenced_lessons),
    ):
        for file_path in directory.glob("*.json"):
            identifier = _identifier(file_path.stem, f"{kind} file")
            if identifier not in referenced:
                raise ContentLoadError(
                    f"Unreferenced {kind} file: {file_path.name}."
                )

    return result
