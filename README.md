# AI Study Lab

AI Study Lab is a local-first learning product that turns a topic or PDF into a concise AI-generated lesson and helps job candidates prepare for a specific role. Version 0.1.0 is a focused public MVP built with FastAPI, Groq as its primary AI provider, an optional Gemini fallback, and a framework-free frontend.

## Why it was built

The project explores two practical uses of structured AI output: active study and grounded interview preparation. It favors short, interactive learning activities and evidence-based coaching over long generated pages or opaque match scores.

## Current features

### Study

- Generate a lesson for any topic at Basic, Intermediate, or Advanced level.
- Review a concise explanation and focused key points.
- Study exactly 5 generated flashcards one at a time.
- Take exactly 4 multiple-choice quiz questions with immediate feedback.
- See a quiz score for the current browser session only.
- Optionally ground a lesson in one text-based PDF and review concise page-derived sources.

### Interview Coach

- Compare a job description with pasted CV/resume text or one CV/resume PDF.
- Optionally include one LinkedIn Profile PDF and one Cover Letter PDF.
- Receive a qualitative fit assessment without a fake numerical match score.
- Review evidence labeled by source, unsupported requirements, suggested study topics, and a small set of interview questions.

### Application

- Separate Home, Study, Interview Coach, and Progress workspaces.
- FastAPI REST endpoints backed by provider-independent structured output and Pydantic validation.
- In-memory PDF text extraction with no document persistence.
- Local multilingual embeddings and ephemeral Chroma vector search for Study PDF retrieval.
- Groq primary generation with an optional transparent Gemini fallback and no provider selector.
- Deterministic, live, RAG, and LLM-as-a-judge evaluation with a combined HTML report.
- Minimal terminal-only request/provider telemetry with no persistent history.
- Responsive HTML, CSS, and Vanilla JavaScript interface.
- One-command launcher with `python run.py`.
- Focused pytest coverage for validation, providers, PDFs, RAG, evaluation, telemetry, and API flows.

## Planned next

- Progress and lightweight gamification: username/profile, XP, attempts, history, mastery, weak topics, last studied, and streaks.
- Spaced repetition and small improvements to flashcards, completion states, and examples.
- Additional study activities, introduced and validated one at a time.
- Optional Ollama support if a clear local-model use case is established.

## Not currently planned

The project does not currently need multi-agent workflows, LangGraph, LangChain without a concrete requirement, MCP integration, microservices, plugin systems, enterprise dependency-injection patterns, or unnecessary cloud infrastructure. Persistent document storage, persistent vector collections, OCR, fake ATS scores, and recruitment/ranking-platform features are also outside the current scope.

## Tech stack

- Python 3.11+
- FastAPI, Uvicorn, and REST
- Groq API with optional transparent Google Gemini fallback
- Pydantic structured-output validation
- pypdf and fontTools for text-based PDF extraction
- Sentence Transformers multilingual embeddings
- ephemeral Chroma vector search
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
 Structured generation (Groq primary)
       | eligible failure
       v
 Optional Gemini fallback

Study PDF -> page extraction -> chunks -> local embeddings -> ephemeral Chroma
                                                      |
                                                      v
                              retrieved passages -> grounded lesson + sources

Professional documents -> in-memory text extraction -> Interview Coach analysis
```

> I deliberately started with a small FastAPI application and one well-designed learning flow. I introduced additional infrastructure only when the product required it.

There is no persistent database, background worker, frontend framework, or persistence layer. Request models, AI integration, PDF processing, and retrieval remain small and explicit so the product can evolve from demonstrated needs.

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
GEMINI_API_KEY=your_optional_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
```

Groq remains the primary provider. Gemini is an optional, transparent fallback for eligible provider or structured-output failures and is not user-selectable. If `GEMINI_API_KEY` is empty, requests use Groq without fallback.

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

Tests cover lesson activities, Interview Coach, provider failures and fallback, PDF processing, RAG, evaluation, telemetry, API validation, and practical frontend contracts.

## Evaluation

The repository includes an evaluation harness for deterministic checks, live candidate generation, RAG retrieval and grounding, structured LLM-as-a-judge assessment, provider/fallback telemetry, and a combined HTML report. It is separate from the product UI; see [evals/README.md](evals/README.md) for artifacts and details.

```bash
python -m evals.run
python -m evals.run_live
python -m evals.run_rag
python -m evals.run_judge
python -m evals.report
```

Live and judge commands use configured providers; automated tests mock provider calls.

## Request telemetry

Study, RAG, and Interview Coach requests emit one concise terminal log with request timing and provider/fallback metadata. Telemetry is not persisted, has no dashboard, and excludes prompts, uploaded document content, and generated content.

## Prompt documentation

The current structured-generation behavior is documented in [PROMPTS.md](PROMPTS.md). Executable prompts remain close to their validated models and the shared generation layer in the application code.

## Privacy and document handling

- The application reads uploaded PDFs into memory for the current request and does not persist them. The web framework may use short-lived operating-system temporary buffering while receiving an upload.
- PDFs, extracted text, and ephemeral Chroma collections are not persisted by this application.
- Study PDF embeddings are created locally. Retrieved passages are sent to Groq for grounded lesson generation and may be sent to Gemini if an eligible Groq request fails.
- Job descriptions, resume/CV content, and optional supporting-document text are likewise sent to Groq and may be sent to the optional Gemini fallback.
- API keys remain server-side and belong only in the local `.env` file; never commit `.env`, keys, personal documents, or real candidate data.

## Screenshots

Screenshots will be added after a final public-data UI review. Any future screenshots should use fictional topics, job descriptions, and candidate documents only.

## License

Released under the [MIT License](LICENSE).

## Project status

- Version: `0.1.0`
- Status: early public MVP
- Storage: session-only browser state; no database or saved user content
