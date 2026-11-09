# Changelog

## [0.2.0] - 2026-11-08

- Added Study PDF retrieval-augmented generation with local multilingual embeddings, ephemeral ChromaDB retrieval, and page-based sources.
- Added an optional Gemini fallback for eligible Groq failures, plus request/provider telemetry.
- Added deterministic, live, RAG, and LLM-as-a-judge evaluation workflows and a combined report.
- Added Official Learning Paths using Markdown explanations and JSON metadata and quizzes.
- Added content validation and read-only FastAPI endpoints for listing and retrieving learning paths.
- Added frontend navigation through paths, modules, and lessons, safe Markdown display, and interactive lesson quizzes.
- Added local SQLite persistence for official lesson completion, lesson access timestamps, and completed quiz attempt history.
- Added progress API endpoints for recording completed quiz attempts, retrieving lesson progress, and recording lesson access.
- Added the Dashboard Summary API and a basic responsive Home dashboard with Continue Learning, Overall Progress, Official Learning Paths, and Recent Activity.
- Added a persistent Official Learning Paths course sidebar, lesson breadcrumbs, and Previous/Next lesson navigation.
- Added automatic resumption of the most recently accessed official lesson when returning to the workspace.
- Added static asset cache invalidation based on local asset modification times.
- Added stale-response protection and 10-second timeouts for Official Learning Paths requests, plus clearer diagnostics when the local development port is occupied.

## 0.1.0 — Released

- Released the initial local-first Study and Interview Coach application.
- Added topic-based generated lessons, flashcards, and multiple-choice quizzes.
- Added qualitative interview preparation from job descriptions and resume/CV documents.
