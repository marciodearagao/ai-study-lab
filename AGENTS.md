# Project rules

- Make small, incremental changes that are easy to review and understand. Build only the approved current scope; do not scaffold roadmap features.
- Use Python, FastAPI, HTML, CSS, Vanilla JavaScript, and pytest. Keep functions and modules direct; avoid unnecessary frameworks, agents, abstraction layers, or infrastructure.
- Store Official Learning Paths content in Markdown and JSON files using the existing path, module, lesson, and quiz hierarchy.
- Keep Groq as the primary provider and Gemini as the optional transparent fallback. Do not add providers or change retry/fallback policy unless explicitly requested.
- Use ChromaDB exclusively for the existing ephemeral, document-based RAG retrieval. SQLite is implemented for local, single-user Official Learning Paths progress, including lesson completion, access timestamps, and completed quiz attempts. Keep educational content in Markdown/JSON files; do not store it in SQLite.
- The progress APIs, Dashboard Summary API, and basic Home dashboard are implemented. Preserve the local-first, single-user scope; do not add accounts or authentication unless explicitly requested.
- Keep code, comments, documentation, and user-facing application text in English.
- Keep UI copy concise and preserve responsive, accessible workspace flows.
- Add tests for meaningful behavior and prefer behavioral assertions over tests coupled to implementation details.
- Keep `VERSION` and project metadata in sync when the released version changes.
- Never commit `.env`, API keys, uploaded documents, or real personal data.
