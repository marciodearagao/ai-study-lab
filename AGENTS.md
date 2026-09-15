# Project rules

- Keep the codebase small, direct, and easy to understand.
- Build only the current scope; do not scaffold roadmap features.
- Use Python, FastAPI, HTML, CSS, Vanilla JavaScript, and pytest.
- Keep Groq as the primary provider and Gemini as the optional transparent fallback. Do not add providers or change retry/fallback policy unless explicitly requested.
- Do not add databases, frontend frameworks, orchestration tools, or infrastructure without a current product requirement.
- Prefer plain functions and small modules over abstraction layers.
- Keep UI copy concise and preserve the responsive, accessible workspace flows.
- Add tests for behavior that matters; avoid tests tied to implementation details.
- Keep `VERSION` and project metadata in sync when the version changes.
- Never commit `.env`, API keys, uploaded documents, or real personal data.
