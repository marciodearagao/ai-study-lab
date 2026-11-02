import json
from shutil import copytree
from pathlib import Path

import pytest

from app.content import ContentLoadError, load_learning_paths


CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"


def load_json(directory: str, identifier: str) -> dict:
    path = CONTENT_DIR / directory / f"{identifier}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def copy_content(tmp_path: Path) -> Path:
    return copytree(CONTENT_DIR, tmp_path / "content")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_sample_path_module_and_lesson_references_resolve() -> None:
    path_files = list((CONTENT_DIR / "paths").glob("*.json"))
    assert len(path_files) == 1

    path = json.loads(path_files[0].read_text(encoding="utf-8"))
    assert path["id"] == path_files[0].stem
    assert path["modules"] == ["introduction"]

    for module_id in path["modules"]:
        module = load_json("modules", module_id)
        assert module["id"] == module_id
        assert module["path_id"] == path["id"]

        for lesson_id in module["lessons"]:
            lesson = load_json("lessons", lesson_id)
            assert lesson["id"] == lesson_id
            assert lesson["module_id"] == module_id
            explanation = CONTENT_DIR / "lessons" / lesson["explanation_file"]
            assert explanation.is_file()
            assert explanation.read_text(encoding="utf-8").strip()


def test_sample_lesson_has_four_valid_quiz_questions() -> None:
    lesson = load_json("lessons", "what-is-artificial-intelligence")
    questions = lesson["quiz"]
    expected_option_keys = ["A", "B", "C", "D"]

    assert len(questions) == 4
    assert len({question["id"] for question in questions}) == 4
    for question in questions:
        options = question["options"]
        assert list(options) == expected_option_keys
        option_texts = list(options.values())
        assert all(option.strip() for option in option_texts)
        assert len(set(option_texts)) == 4
        assert question["correct_answer"] in options


def test_loader_returns_nested_sample_content() -> None:
    paths = load_learning_paths(CONTENT_DIR)

    assert len(paths) == 1
    path = paths[0]
    assert path["id"] == "ai-fundamentals"
    module = path["modules"][0]
    lesson = module["lessons"][0]
    assert lesson["id"] == "what-is-artificial-intelligence"
    assert lesson["explanation"] == (
        CONTENT_DIR / "lessons" / "what-is-artificial-intelligence.md"
    ).read_text(encoding="utf-8")
    assert len(lesson["quiz"]) == 4


def test_loader_reports_missing_module_file(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    (content_dir / "modules" / "introduction.json").unlink()

    with pytest.raises(ContentLoadError, match="Missing module file"):
        load_learning_paths(content_dir)


def test_loader_reports_malformed_json(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    (content_dir / "paths" / "ai-fundamentals.json").write_text("{", encoding="utf-8")

    with pytest.raises(ContentLoadError, match="Could not read learning path file"):
        load_learning_paths(content_dir)


def test_loader_reports_broken_module_path_reference(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    module_path = content_dir / "modules" / "introduction.json"
    module = json.loads(module_path.read_text(encoding="utf-8"))
    module["path_id"] = "another-path"
    write_json(module_path, module)

    with pytest.raises(ContentLoadError, match="references path"):
        load_learning_paths(content_dir)


def test_loader_rejects_invalid_quiz_answer_key(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    lesson_path = content_dir / "lessons" / "what-is-artificial-intelligence.json"
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    lesson["quiz"][0]["correct_answer"] = "E"
    write_json(lesson_path, lesson)

    with pytest.raises(ContentLoadError, match="correct_answer must reference"):
        load_learning_paths(content_dir)


@pytest.mark.parametrize(
    "options",
    [
        {"A": "One", "B": "Two", "C": "Three"},
        {"A": "One", "B": "Two", "C": "Three", "D": " "},
        {"A": "Same", "B": "Same", "C": "Three", "D": "Four"},
    ],
)
def test_loader_rejects_invalid_quiz_options(tmp_path: Path, options: dict) -> None:
    content_dir = copy_content(tmp_path)
    lesson_path = content_dir / "lessons" / "what-is-artificial-intelligence.json"
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    lesson["quiz"][0]["options"] = options
    write_json(lesson_path, lesson)

    with pytest.raises(ContentLoadError, match="option"):
        load_learning_paths(content_dir)


def test_loader_rejects_invalid_identifier_before_file_access(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    path_file = content_dir / "paths" / "ai-fundamentals.json"
    path = json.loads(path_file.read_text(encoding="utf-8"))
    path["modules"] = ["../outside"]
    write_json(path_file, path)

    with pytest.raises(ContentLoadError, match="Invalid .* modules identifier"):
        load_learning_paths(content_dir)


def test_loader_rejects_explanation_path_traversal(tmp_path: Path) -> None:
    content_dir = copy_content(tmp_path)
    lesson_path = content_dir / "lessons" / "what-is-artificial-intelligence.json"
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    lesson["explanation_file"] = "../outside.md"
    write_json(lesson_path, lesson)

    with pytest.raises(ContentLoadError, match="invalid explanation_file path"):
        load_learning_paths(content_dir)
