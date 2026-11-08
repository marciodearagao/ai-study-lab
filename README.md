# AI Study Lab

AI Study Lab (ASL) is a local-first, single-user learning application focused on practical AI-assisted study. Version **0.1.0** is the current released version. The `dev` branch contains additional work for **v0.2.0, which is unreleased**; see [CHANGELOG.md](CHANGELOG.md) for the development changes.

## Released in v0.1.0

The v0.1.0 release includes topic-based Study lessons, flashcards and quizzes, and the Interview Coach.

## Features in the current development branch

The features below are available on `dev`. Additions after v0.1.0 are part of unreleased v0.2.0 development.

### Study

- Generate a lesson for a learner-selected topic and Basic, Intermediate, or Advanced level.
- Review a short explanation and key concepts, study five flashcards, and answer four multiple-choice questions with feedback and a session-only score.
- Optionally provide one text-based PDF. ASL extracts pages, creates local multilingual embeddings, retrieves relevant passages using an ephemeral ChromaDB collection, and generates a grounded lesson with page-based sources.

### Official Learning Paths

- Browse file-based official learning content in the hierarchy **Learning Path → Module → Lesson → Quiz**.
- The current sample is AI Fundamentals, with an Introduction module and a lesson about artificial intelligence.
- Lesson explanations are Markdown files. Path, module, lesson metadata, and quiz data are JSON files under `content/`; the current sample quiz has four questions.
- Lesson quizzes present one question at a time, provide answer feedback, calculate a score, and can be restarted. Official lesson quiz attempts and completion are saved locally in SQLite; unfinished attempts are not saved.
- Content is loaded and validated by `app/content.py` and served through `GET /api/learning-paths` and `GET /api/learning-paths/{path_id}`. New content that follows the existing schema can be added as files without changing application code.
- Lesson access and completion are available through the progress API. The dashboard summary API combines current official content with locally stored progress.

### Dashboard and progress

- The Home workspace is a basic dashboard with Continue Learning, Overall Progress, Official Learning Paths, and Recent Activity.
- SQLite stores local, single-user progress for official lessons: completion, first completion time, last access time, and completed quiz attempts. It does not store educational content or require an account.
- The progress and dashboard APIs expose lesson status, quiz history, and aggregate progress. Learners can review their progress through the Home Dashboard and Official Learning Paths; there is no separate Progress workspace.

### Interview Coach

- Compare a job description with pasted CV/resume text or one CV/resume PDF. Optional LinkedIn Profile and Cover Letter PDFs provide additional context.
- Review a qualitative, source-grounded assessment, evidence, gaps, suggested study topics, and interview questions. ASL does not calculate an ATS score or match percentage.

### Application and developer tools

- Home (Dashboard), Study, Official Learning Paths, and Interview Coach are available workspaces.
- FastAPI provides the web page, health check, learning-path endpoints, progress endpoints, dashboard summary, Study endpoints, and Interview Coach endpoints.
- Groq is the primary structured-generation provider; Gemini is an optional transparent fallback for eligible failures.
- Deterministic, live, RAG, and LLM-as-a-judge evaluations are available separately from the learner interface. Live generation and judge commands can call configured AI providers; the pytest suite mocks provider calls.
- Request/provider telemetry is written to the server terminal and is not persisted.

## Content structure

```text
content/
├── paths/       # Learning path JSON files
├── modules/     # Module JSON files
└── lessons/     # Lesson JSON metadata, Markdown explanations, and quiz data
```

IDs use lowercase letters, digits, and hyphens. JSON references connect paths to modules and modules to lessons. Lesson quiz options use stable `A`, `B`, `C`, and `D` keys. The loader validates identifiers, references, quiz answers, and that explanation files remain inside the lessons directory.

## Technology and architecture

- Python 3.11+, FastAPI, and Uvicorn.
- Pydantic for request and generated-output validation.
- Groq with optional Google Gemini fallback.
- `pypdf` and fontTools for text-based PDF handling.
- Sentence Transformers for local multilingual embeddings and ChromaDB for ephemeral RAG retrieval.
- Markdown and JSON files for Official Learning Paths content.
- HTML, CSS, and Vanilla JavaScript; pytest and HTTPX for tests.

```text
Browser (HTML / CSS / Vanilla JavaScript)
  └── FastAPI
      ├── Study → app/lessons.py → app/ai.py → Groq / optional Gemini
      ├── Study PDF → app/rag.py → local embeddings → ephemeral ChromaDB
      │                              └── retrieved sources → app/ai.py
      ├── Official Learning Paths → app/content.py → JSON / Markdown files
      ├── Progress and Dashboard APIs → SQLite (local lesson progress and quiz history)
      └── Interview Coach → app/interview.py → app/ai.py
```

SQLite is used only for local, single-user official lesson progress and completed quiz attempts. Official educational content remains in Markdown/JSON files; ChromaDB is used separately for ephemeral document-based RAG retrieval. Uploaded documents are processed for the current request and are not persisted by ASL. Study PDF passages selected for generation, and Interview Coach document text, are sent to Groq and may be sent to Gemini when eligible fallback is used. See [`.env.example`](.env.example) for configuration names; keep API keys in the ignored local `.env` file.

## Planned work

The following items are **not implemented**:

- My Learning Studio for learner-created study experiences.
- A contextual AI mentor that offers hints.
- A hybrid navigation redesign with a collapsible sidebar.

These plans do not change the current file-based Official Learning Paths content or the existing Study, RAG, and Interview Coach features.

## Setup and running

Install Python 3.11 or newer, then create and activate a virtual environment.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
cp .env.example .env
```

Activate the environment in Git Bash on Windows:

```bash
source .venv/Scripts/activate
```

In Bash on macOS or Linux, use `source .venv/bin/activate` instead.

Set `GROQ_API_KEY` in `.env`. `GEMINI_API_KEY` is optional. Then start ASL:

```bash
python run.py
```

The launcher runs the app at `http://127.0.0.1:8000` and normally opens a browser. Keep the terminal open while using the app; press `Ctrl+C` to stop it.

## Tests and evaluations

Run the automated test suite without writing bytecode or pytest cache files:

```bash
python -B -m pytest -p no:cacheprovider
```

Evaluation commands are documented in [evals/README.md](evals/README.md). Deterministic checks and report generation do not require live model calls; live candidate generation, RAG generation, and judge evaluations use configured providers.

## Documentation

- [PROMPTS.md](PROMPTS.md) describes dynamic Study lessons, Study PDF grounding, and Interview Coach prompts.
- [docs/specs/rag.md](docs/specs/rag.md) and [docs/specs/evaluation.md](docs/specs/evaluation.md) describe the RAG and evaluation scope.
- [CHANGELOG.md](CHANGELOG.md) distinguishes the released baseline from unreleased development.

## License

Released under the [MIT License](LICENSE).
