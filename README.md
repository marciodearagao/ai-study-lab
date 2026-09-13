# AI Study Lab

AI Study Lab is a local-first learning product that turns a topic into a concise AI-generated lesson and helps job candidates prepare for a specific role. Version 0.1.0 is a focused public MVP built with FastAPI, Groq, and a framework-free frontend.

## Why it was built

The project explores two practical uses of structured AI output: active study and grounded interview preparation. It favors short, interactive learning activities and evidence-based coaching over long generated pages or opaque match scores.

## Current features

### Study

- Generate a lesson for any topic at Basic, Intermediate, or Advanced level.
- Review a concise explanation and focused key points.
- Study 5–8 generated flashcards one at a time.
- Take a 4–6 question multiple-choice quiz with immediate feedback.
- See a quiz score for the current browser session only.

### Interview Coach

- Compare a job description with pasted CV/resume text or one CV/resume PDF.
- Optionally include one LinkedIn Profile PDF and one Cover Letter PDF.
- Receive a qualitative fit assessment without a fake numerical match score.
- Review evidence labeled by source, unsupported requirements, suggested study topics, and a small set of interview questions.

### Application

- Separate Home, Study, Interview Coach, and Progress workspaces.
- FastAPI REST endpoints backed by Groq structured output and Pydantic validation.
- In-memory PDF text extraction with no document persistence.
- Responsive HTML, CSS, and Vanilla JavaScript interface.
- One-command launcher with `python run.py`.
- Focused pytest coverage for validation, provider failures, PDF handling, and API flows.

## Planned next

- Progress and lightweight gamification: username/profile, XP, attempts, history, mastery, weak topics, last studied, and streaks.
- Spaced repetition and small improvements to flashcards, completion states, and examples.
- Deeper Interview Coach evaluation while preserving evidence-grounded results.
- Additional study activities, introduced and validated one at a time.
- Optional Ollama support if a clear local-model use case is established.

## Not currently planned

The project does not currently need multi-agent workflows, LangGraph, LangChain without a concrete requirement, MCP integration, microservices, plugin systems, enterprise dependency-injection patterns, or unnecessary cloud infrastructure. Vector databases, embeddings, and RAG will be considered only for a proven retrieval need. OCR, fake ATS scores, and recruitment/ranking-platform features are also outside the current scope.

## Tech stack

- Python 3.11+
- FastAPI and Uvicorn
- Groq API
- Pydantic structured-output validation
- pypdf for text-based PDF extraction
- HTML, CSS, and Vanilla JavaScript
- pytest and HTTPX

## Architecture and design philosophy

```text
Browser (HTML/CSS/JavaScript)
              |
              v
       FastAPI REST API
              |
              v
    Small application modules
              |
              v
 Groq structured generation

PDF upload -> in-memory text extraction -> Interview Coach analysis
```

> I deliberately started with a small FastAPI application and one well-designed learning flow. I introduced additional infrastructure only when the product required it.

There is no database, background worker, frontend framework, or persistence layer. Request models, AI integration, and PDF extraction remain small and explicit so the product can evolve from demonstrated needs.

## Installation

Install [Python 3.11 or newer](https://www.python.org/downloads/), then clone or download this repository and open a terminal in the project directory.

Create a virtual environment. A `.venv` is an isolated Python environment for this project, so its packages do not affect other Python projects:

```bash
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or activate it in Bash on Windows:

```bash
source .venv/Scripts/activate
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Configuration

Create a local `.env` file from the safe example.

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

Set the following values in `.env`:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
```

The `.env` file stores local configuration and secrets. It is ignored by Git and must never be committed. Restart the app after changing `.env`; settings are loaded when the application starts.

## Running

With the virtual environment active, start the app with:

```bash
python run.py
```

The launcher prints the local address and normally opens the app in your default browser. Press `Ctrl+C` in the terminal to stop it.

## Tests

Run the full suite with:

```bash
pytest
```

Tests cover structured lesson, flashcard, and quiz validation; lesson and interview endpoints; safe provider error handling; PDF validation and extraction; optional supporting documents; and practical frontend contracts.

## Prompt documentation

The current structured-generation behavior is documented in [PROMPTS.md](PROMPTS.md). The executable prompt definitions remain close to the Groq integration in the application code.

## Privacy and document handling

- The application reads uploaded PDFs into memory for the current request and does not persist them. The web framework may use short-lived operating-system temporary buffering while receiving an upload.
- Extracted document text is not stored by this application.
- Job descriptions, resume/CV content, and optional supporting-document text are sent to the configured AI provider to generate the analysis.
- API keys belong only in the local `.env` file; never commit `.env`, keys, personal documents, or real candidate data.

## Screenshots

Screenshots will be added after a final public-data UI review. Any future screenshots should use fictional topics, job descriptions, and candidate documents only.

## License

Released under the [MIT License](LICENSE).

## Project status

- Version: `0.1.0`
- Status: early public MVP
- Storage: session-only browser state; no database or saved user content
