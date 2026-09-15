# Repository Consistency Audit

Audit date: 2026-09-15
Branch reviewed: `dev`
Mode: read-only; this report is the only file created

## Current-state summary

Current architecture observed from implementation and tests:

- FastAPI serves one HTML page with responsive Vanilla JavaScript/CSS workspaces for Home, Study, Interview Coach, and the not-yet-implemented Progress area.
- Study accepts a topic and Basic/Intermediate/Advanced level and returns one strictly validated `Lesson`: 3–4 key points, exactly 5 flashcards, and exactly 4 four-option quiz questions.
- Interview Coach accepts a job description plus pasted CV text or one CV PDF, with optional single LinkedIn and Cover Letter PDFs. Output is qualitative and source-grounded.
- Shared `pypdf` extraction supports text PDFs only. Uploads are limited to 5 MB; Interview Coach directly supplied document text is limited to 15,000 characters.
- Study RAG accepts one PDF, chunks each page deterministically at 180 words with 30-word overlap, embeds with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, retrieves up to 4 passages through an ephemeral Chroma collection, and bounds grounded context to 6,000 characters.
- Grounded lessons reuse the authoritative `Lesson` schema and return short, page-derived source references.
- Groq is primary (`openai/gpt-oss-20b`). Gemini is an optional transparent fallback (`gemini-3.1-flash-lite`) for eligible transient and stochastic structured-output failures. Product Groq attempts are bounded at 2 and Gemini at 1.
- Evaluation v1 provides deterministic Study and Interview Coach checks. Evaluation v2 adds live candidates, RAG retrieval/grounding cases, structured LLM-as-a-judge scoring, provider telemetry, ignored JSON artifacts, and combined HTML reporting.
- The evaluation judge also uses Groq first and eligible Gemini fallback, with the same maximum of 2 Groq calls plus 1 Gemini call per case.
- Minimal `ContextVar`-scoped terminal telemetry covers four generation endpoints and records request/provider metadata without prompts, generated content, or document text.
- Six routes exist: `GET /`, `GET /health`, and four POST routes: `/api/lessons`, `/api/lessons/pdf`, `/api/interview-analysis`, and `/api/interview-analysis/pdf`.
- Runtime dependencies match the implemented stack: FastAPI/Uvicorn, Groq, Google GenAI, Pydantic, pypdf/fontTools, python-multipart, Sentence Transformers, and Chroma. pytest and HTTPX are development dependencies.
- Version `0.1.0` is aligned across `VERSION`, `pyproject.toml`, FastAPI metadata, the launcher output, and README.

Implementation and tests were treated as authoritative when prose disagreed.

## Findings

### CRITICAL-1 — AGENTS.md can regress the implemented provider architecture

- **File:** `AGENTS.md:6`
- **Current text:** “Keep Groq as the only AI provider unless another provider is explicitly requested.”
- **Why inconsistent:** Gemini is already an implemented, configured, tested fallback. A future coding agent following this rule literally could remove, bypass, or fail to preserve the current provider path.
- **Evidence:** `app/ai.py:21,24-33,436-600`; `app/lessons.py:95-114`; `app/interview.py:79-86`; `.env.example:5-7`; provider fallback tests.
- **Recommended correction:** Replace it with: “Keep Groq as the primary provider and Gemini as the optional transparent fallback. Do not add providers or change retry/fallback policy unless explicitly requested.”
- **Correction type:** documentation-only.

### HIGH-1 — README directly describes implemented RAG as future work

- **File:** `README.md:9-33,43-45,47-55,59-75`
- **Current text/behavior:** Current features and architecture omit Study PDF/RAG, while line 45 says vector databases, embeddings, and RAG “will be considered only for a proven retrieval need.”
- **Why inconsistent:** The retrieval need has already been implemented end to end. The statement is now the opposite of repository reality and materially understates the portfolio architecture.
- **Evidence:** `app/main.py:150-178`; `app/rag.py:158-381`; `pyproject.toml:12,20`; `static/app.js:115-176`; `templates/index.html:50-71`; `tests/test_rag.py`, `tests/test_grounded_lessons.py`, and `tests/test_rag_endpoint.py`.
- **Recommended correction:** Add current Study PDF/RAG capability and its local Sentence Transformers/ephemeral Chroma path to Current features, Tech stack, and the architecture diagram; remove the future-only RAG sentence.
- **Correction type:** documentation-only.

### HIGH-2 — README activity counts contradict the authoritative schema

- **File:** `README.md:15-16`
- **Current text:** “5–8 generated flashcards” and “4–6 question” quiz.
- **Why inconsistent:** The current Pydantic model and prompt require exactly 5 flashcards and exactly 4 quiz questions. Provider schemas enforce those exact counts.
- **Evidence:** `app/lessons.py:55-56,67-78`; `PROMPTS.md:37`; schema and endpoint tests in `tests/test_lessons.py`.
- **Recommended correction:** State exactly 5 flashcards and exactly 4 multiple-choice questions, or avoid counts in README and defer to `PROMPTS.md`.
- **Correction type:** documentation-only.

### HIGH-3 — README privacy notes omit Study PDF context sent to cloud providers

- **File:** `README.md:162-167`
- **Current text/behavior:** The README says professional documents are sent to Groq/Gemini, but does not say retrieved Study PDF passages are sent for grounded generation.
- **Why inconsistent:** RAG extraction and embeddings are local, but retrieved chunk text is placed in the generation request. This is important user-facing privacy information.
- **Evidence:** `app/rag.py:300-377`; `app/main.py:150-178`; `app/ai.py:252-600`.
- **Recommended correction:** Explicitly state that selected passages from an uploaded Study PDF are sent to Groq and may be sent to Gemini fallback, while the PDF, Chroma collection, and extracted text are not persisted.
- **Correction type:** documentation-only.

### HIGH-4 — README omits the completed evaluation system

- **File:** `README.md:9-33,148-156`
- **Current text/behavior:** Current features and test coverage do not mention deterministic evaluation, live candidates, RAG evaluation, LLM-as-a-judge, artifacts, or the combined report.
- **Why inconsistent:** Evaluation v1/v2 is a substantial implemented developer capability and portfolio feature, not merely planned work. “Deeper Interview Coach evaluation” at line 39 does not describe the current baseline.
- **Evidence:** `evals/run.py`, `evals/run_live.py`, `evals/run_rag.py`, `evals/run_judge.py`, `evals/report.py`, both synthetic fixture sets, RAG fixtures, and evaluation tests.
- **Recommended correction:** Add a concise Evaluation section linking `evals/README.md`, listing the four commands and clarifying deterministic versus live/judge behavior.
- **Correction type:** documentation-only.

### HIGH-5 — PROMPTS.md incorrectly presents both product flows as Groq-only

- **File:** `PROMPTS.md:7,16,64,73`
- **Current text:** The lesson prompt “asks Groq,” “Groq must return,” Interview Coach says “Groq returns,” and both flows share a “Groq structured-output helper.”
- **Why inconsistent:** Groq is primary, but eligible failures transparently use Gemini through a provider-capable shared structured-output helper. The same Pydantic schema remains authoritative for either provider.
- **Evidence:** `app/ai.py:24-33,436-600`; `app/lessons.py:95-114`; `app/interview.py:79-86`; `.env.example:5-7`.
- **Recommended correction:** Use provider-neutral wording for required output and describe `app/ai.py` as the shared structured-generation helper, with Groq primary and Gemini fallback.
- **Correction type:** documentation-only.

### HIGH-6 — diagnose_groq.py can report Groq success when Gemini produced the result

- **File:** `app/diagnose_groq.py:1,13-30`
- **Current text/behavior:** The module calls `POST /api/lessons`, prints the configured Groq model, and labels any HTTP 200 as PASS.
- **Why inconsistent:** `/api/lessons` enables transparent Gemini fallback. A Groq failure followed by Gemini success therefore produces a diagnostic PASS even though the nominal Groq diagnostic failed.
- **Evidence:** `app/lessons.py:105-114`; `app/ai.py:536-600`; `tests/test_provider_fallback.py`.
- **Recommended correction:** Decide whether this is a product-flow smoke test or a Groq-only diagnostic. Rename/reword it for the former, or make provider outcome visible and require Groq final-provider success for the latter. Do not infer provider success only from HTTP 200.
- **Correction type:** requires design decision.

### MEDIUM-1 — PROMPTS.md omits the grounded RAG prompt extension

- **File:** `PROMPTS.md` (missing section after Lesson generation)
- **Current text/behavior:** Only general lessons and Interview Coach prompts are documented.
- **Why inconsistent:** Grounded Study materially extends the lesson system prompt with context-only factual grounding, insufficient-context limitation, and source-material-as-data instructions.
- **Evidence:** `app/rag.py:300-377`.
- **Recommended correction:** Add a short Grounded lesson/RAG subsection covering retrieved page context, no unsupported filling, unchanged `Lesson` schema, and page-derived references.
- **Correction type:** documentation-only.

### MEDIUM-2 — RAG spec retains pre-implementation/provider wording

- **File:** `docs/specs/rag.md:11,15-21,32-33`
- **Current text:** The UI “should eventually” expose the optional PDF flow, and generation is described only as Groq.
- **Why inconsistent:** The UI and endpoint are implemented. Generation uses Groq primary with eligible Gemini fallback. “Initially ephemeral” is also less precise than the current fixed v1 implementation, which creates `chromadb.EphemeralClient` for each retrieval session.
- **Evidence:** `templates/index.html:50-56`; `static/app.js:115-176`; `app/main.py:150-178`; `app/rag.py:220-283`; `app/lessons.py:95-102`.
- **Recommended correction:** Change future tense to current-state language and describe generation as the existing Groq-primary/Gemini-fallback integration. State that Chroma is ephemeral in v1.
- **Correction type:** documentation-only.

### MEDIUM-3 — Evaluation spec calls implemented checks “future” and live generation “Groq”

- **File:** `docs/specs/evaluation.md:14-35,43-48`
- **Current text:** Study and Interview checks are introduced as future checks; live v2 says it uses production Groq generation functions.
- **Why inconsistent:** Those checks are implemented, and production generation can finish through Gemini fallback. Later lines correctly describe judge fallback, leaving the document internally uneven.
- **Evidence:** `evals/study_checks.py`; `evals/interview_checks.py`; `evals/run.py`; `evals/run_live.py`; `app/lessons.py:105-114`; `app/interview.py:79-86`.
- **Recommended correction:** Use present tense for implemented v1 checks and “production generation paths (Groq primary, eligible Gemini fallback)” for live v2.
- **Correction type:** documentation-only.

### MEDIUM-4 — Groq diagnostic has a development-only dependency boundary

- **File:** `app/diagnose_groq.py:7,19`; `pyproject.toml:24-28`
- **Current text/behavior:** A module shipped under `app` imports FastAPI `TestClient`, which relies on HTTPX, while HTTPX is declared only in the `dev` extra.
- **Why inconsistent:** The diagnostic may fail after a runtime-only installation even though the application itself is correctly installed. The documented setup installs `[dev]`, so impact is limited, but packaging intent is unclear.
- **Evidence:** `httpx` appears only in the development dependency group; application runtime modules otherwise avoid `TestClient`.
- **Recommended correction:** If the diagnostic is a developer tool, move/label it as such and document that `[dev]` is required. If it is intended for runtime installations, avoid `TestClient` or promote the required dependency only after a deliberate packaging decision.
- **Correction type:** requires design decision.

### MEDIUM-5 — Minimal request telemetry is absent from architecture documentation

- **File:** `README.md:26-33,57-79,148-156`; no dedicated current-state note elsewhere
- **Current text/behavior:** The repository now emits one structured terminal record for Study, RAG, and Interview Coach requests, but README architecture/testing descriptions omit it.
- **Why inconsistent:** This does not need to be marketed as an observability platform, but it is a current operational behavior with explicit privacy boundaries and focused tests.
- **Evidence:** `app/telemetry.py`; `app/main.py:48-53,82-108`; `app/ai.py:14,263-565`; `tests/test_telemetry.py`.
- **Recommended correction:** Add one sentence describing local terminal-only request/provider metadata and explicitly distinguish it from persistent monitoring or an observability platform.
- **Correction type:** documentation-only.

### LOW-1 — extract_resume_text appears to be a legacy compatibility wrapper

- **File:** `app/interview.py:124-125`
- **Current text/behavior:** `extract_resume_text` delegates directly to `extract_pdf_text(..., "resume")`.
- **Why suspicious:** Production code calls `extract_pdf_text` through `app/main.py`; the wrapper is referenced only by `tests/test_interview.py`.
- **Evidence:** Repository-wide symbol search found no production caller.
- **Recommended correction:** Confirm no external use, then either remove the wrapper and update its test or document it as a supported convenience API.
- **Correction type:** code cleanup.

### LOW-2 — ProviderLogCapture no longer captures logs

- **File:** `evals/provider_telemetry.py:1-34`
- **Current text/behavior:** `ProviderLogCapture` now opens the shared `ContextVar` telemetry scope and reads a snapshot; it does not attach a logging handler or capture log records.
- **Why suspicious:** The stale class name reflects the superseded implementation and can mislead maintainers about how evaluator telemetry works.
- **Evidence:** The module imports only `provider_snapshot` and `telemetry_scope` from `app.telemetry`.
- **Recommended correction:** Rename it to something such as `ProviderTelemetryCapture` when a small cleanup is convenient.
- **Correction type:** code cleanup.

### LOW-3 — Combined-report aggregation calculates counters that are not rendered

- **File:** `evals/report.py:165-177,269-285`
- **Current text/behavior:** Standard judge provider counts/fallback recoveries and RAG fallback recoveries are added to summary dictionaries. Only RAG Groq/Gemini provider counts are rendered; the other calculated counters have no report or terminal consumer.
- **Why suspicious:** These values appear intended for visibility but currently add silent, untested aggregation surface.
- **Evidence:** Repository-wide references occur only at their definitions, except `rag_judge_provider_groq` and `rag_judge_provider_gemini`, which are rendered.
- **Recommended correction:** Either render the useful totals concisely or remove calculations that have no consumer.
- **Correction type:** code cleanup.

### LOW-4 — The test client stack emits dependency deprecation warnings

- **Files:** `pyproject.toml:10-27`; test modules importing `fastapi.testclient.TestClient`
- **Current text/behavior:** The full suite passes, but importing the test client emits a Starlette warning that the current HTTPX integration is deprecated and an AnyIO warning for the deprecated `BlockingPortal` alias.
- **Why noteworthy:** This is not a current product defect, but it is concrete toolchain drift that may become a compatibility failure during a future dependency update.
- **Evidence:** `pytest -p no:cacheprovider` completed with 219 passing tests and these 2 dependency deprecation warnings.
- **Recommended correction:** Address the compatible FastAPI/Starlette/test-client/AnyIO upgrade path in one dependency-maintenance change; do not merely suppress the warnings.
- **Correction type:** dependency/tooling cleanup.

## API consistency

The frontend routes and FastAPI routes agree:

| Route | Request | Current use |
|---|---|---|
| `GET /` | none | Main workspace HTML |
| `GET /health` | none | Launcher readiness/version |
| `POST /api/lessons` | JSON `LessonRequest` | General lesson |
| `POST /api/lessons/pdf` | multipart topic, level, one PDF | RAG-grounded lesson |
| `POST /api/interview-analysis` | JSON `InterviewRequest` | Pasted-text coaching |
| `POST /api/interview-analysis/pdf` | multipart job/CV text and optional PDFs | PDF-capable coaching |

No contradictory documented endpoint path or request shape was found. README lacks an explicit endpoint reference, but its non-RAG capability prose generally matches the current routes.

## Dependency consistency

- All declared runtime dependencies have concrete implementation justification.
- `fonttools` is not directly imported but is intentionally available to pypdf for CFF/Type1 font parsing; this is not evidence for removal.
- `python-multipart` is required indirectly by FastAPI form/file endpoints.
- `chromadb` and `sentence-transformers` are used by RAG; their presence contradicts README’s future-only RAG statement, not the dependency configuration.
- Two dependency/tooling concerns were found: `app/diagnose_groq.py` depends on development-only HTTPX through `TestClient` (MEDIUM-4), and the current test-client stack emits two deprecation warnings (LOW-4).
- No `gemini-2.5` reference, extra hosted embedding provider, OpenAI API client, Ollama implementation, or undeclared runtime import was found. `openai/gpt-oss-20b` is the configured Groq-hosted model identifier, not an OpenAI provider integration.

## Version and status consistency

- `VERSION`, `pyproject.toml`, FastAPI metadata, launcher behavior, and README all report `0.1.0`.
- Progress is labeled “Coming later” in both UI and tests and has no backend implementation, so that status is consistent.
- Database/persistence exclusions remain accurate: uploads, extracted text, Chroma collections, browser study scores, and telemetry are not persisted by the application.
- No version bump is implied by this audit.

## Files/areas that appear consistent with the current implementation

- `.env.example` has current Groq/Gemini keys and model defaults.
- `pyproject.toml` represents the implemented runtime and test stack with compatible ranges.
- `.gitignore` excludes `.env`, `.venv`, PDFs/documents, v1 report output, and all generated v2 evaluation artifacts.
- `app/lessons.py` and the activity/schema details in `PROMPTS.md:37-41` agree on concise output, acronym handling, exact activity counts, option uniqueness, and answer matching.
- `app/interview.py` and the Interview Coach schema/prompt details in `PROMPTS.md:49-75` agree apart from provider-only wording.
- Core RAG constants and behavior agree with `docs/specs/rag.md:31-41`: approved model, ephemeral Chroma, top-k 4, 180/30 chunking, 6,000-character context, and no Interview direct-context limit.
- `evals/README.md` accurately documents commands, artifacts, deterministic/live separation, RAG cases, judge fallback limits, and report behavior.
- `templates/index.html`, `static/app.js`, and `static/styles.css` consistently implement the workspace navigation, RAG upload/source display, flashcards, quiz, Interview Coach documents, and Progress placeholder.
- `run.py` matches README setup: fixed local address, readiness check, browser opening, clear startup/stopping messages, and version read from `VERSION`.
- Tests consistently mock provider/model calls where required and cover current schemas, routes, PDFs, RAG, evaluation, provider fallback, and telemetry.
- `LICENSE` is a complete MIT license and README links it correctly.

## Statistics

- Files reviewed: **53**
- Findings: **16 total**
  - CRITICAL: **1**
  - HIGH: **6**
  - MEDIUM: **5**
  - LOW: **4**
- Stale model/provider prose: **9 occurrences across 5 documentation files**, plus **1 misleading provider diagnostic behavior**
- Obsolete Gemini model references (`gemini-2.5`): **0**
- Stale roadmap/status statements: **4 concrete occurrences across 3 files**
- Suspicious/dead-code candidates: **4** (diagnostic semantics, one wrapper, one stale class name, unused report counters)
- Dependency drift findings: **2 boundary/tooling concerns; 0 clearly unused dependencies**
- Files with no identified issue: **43**
- TODO/FIXME markers: **0**

Severity counts overlap neither files nor findings. A file may contain multiple findings; “files with no identified issue” counts distinct reviewed files not named by a finding.

## Cleanup plan — not executed

### Batch A — critical instructions

1. Correct the provider rule in `AGENTS.md`.
2. Review that replacement against provider fallback tests before merging.

### Batch B — public README and prompt documentation

1. Correct exact flashcard/quiz counts.
2. Document implemented RAG, Evaluation v1/v2, and minimal terminal telemetry.
3. Update architecture/stack and Study PDF privacy disclosure.
4. Make `PROMPTS.md` provider-neutral and add the grounded RAG prompt extension.

### Batch C — specs

1. Convert completed RAG and deterministic-evaluation sections from future to current tense.
2. Align provider wording with Groq-primary/Gemini-fallback reality.
3. Preserve current boundaries: one PDF, ephemeral Chroma, top-k 4, no persistence or observability platform.

### Batch D — small code decisions/cleanup

1. Decide whether `diagnose_groq.py` is Groq-specific or a full product-flow smoke test, then align behavior, name, and dependency expectations.
2. Confirm whether `extract_resume_text` has any external consumer before removal.
3. Rename `ProviderLogCapture` to match its ContextVar-based implementation.
4. Render or remove unused evaluation report counters.
5. Plan a compatible test-client dependency refresh to resolve the two deprecation warnings without suppressing them.

Each batch is independently reviewable; no repository rewrite is warranted.

## Verification

The audit used static inspection, targeted repository searches, OpenAPI route extraction, dependency/import comparison, Git ignore checks, and a fresh full-suite run: **219 passed, 2 dependency deprecation warnings in 8.98 seconds**. No secrets or `.env` values were inspected. Existing files were not modified.
