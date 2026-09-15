# Evaluation

## Problem

We need repeatable checks for LLM-generated study content and Interview Coach analysis so prompt/model changes do not silently reduce quality.

## Goals

- Detect obvious regressions.
- Validate generated structures and content constraints.
- Test Study and Interview Coach independently.
- Keep evaluation simple and reproducible.

## Study Evaluation Scope

Deterministic Study checks cover:

- Valid structured lesson output.
- Expected flashcard and quiz structure.
- No empty values.
- Duplicate flashcards or questions.
- Quiz correct answer exists in its options.
- Expected or forbidden concepts for selected fixed test cases.
- Concise output limits.

## Interview Coach Evaluation Scope

Deterministic Interview Coach checks cover:

- Evidence grounded in supplied professional documents.
- Expected evidence for fixed synthetic cases.
- Forbidden or unsupported evidence.
- Expected job gaps.
- Valid source labels.
- Valid structured output.

## Test Data

Use small synthetic fixtures only. Do not use the user's real CV, LinkedIn profile, cover letter, or personal information.

## Evaluation Versions

- Evaluation v1 runs deterministic Study and Interview Coach checks against fixed synthetic outputs without API calls.
- Evaluation v2 live mode sends the same synthetic inputs through the production generation paths—Groq primary with eligible Gemini fallback—and applies the v1 deterministic checks to saved candidates. Live mode requires valid Groq configuration.
- The Evaluation v2 judge reads saved candidates without regenerating them. Study metrics are topic relevance, difficulty alignment, factual coherence, and pedagogical usefulness. Interview Coach metrics are grounding, false-evidence risk, false-gap risk, and usefulness.
- RAG evaluation uses four synthetic cases with production chunking, local embeddings, ephemeral retrieval, and grounded lesson generation. It checks retrieval relevance and ranking, multilingual retrieval, irrelevant-result dominance, grounded generation, and an explicitly unsupported-context query. Its judge metrics are context relevance, groundedness, unsupported-claim risk, and source-attribution quality; this is focused regression coverage, not exhaustive RAG benchmarking.
- Groq is the primary judge. Eligible transient, provider, or stochastic structured-output failures may use Gemini once, with at most two Groq attempts plus one Gemini attempt per case. Missing configuration, authentication, invalid models, malformed evaluation input, and local schema/programming errors do not fall back.
- Provider telemetry records provider attempts, call counts, outcomes, fallback use, and the final generation/judge provider. The report makes generator/judge combinations visible, including the same-provider methodological limitation.
- Live candidates, judge output, and RAG output are overwritten at `evals/results/live_candidates.json`, `evals/results/judge_results.json`, and `evals/results/rag_results.json`. Generated results are ignored by Git. The combined offline report at `evals/results/evaluation_v2_report.html` presents the v1 baseline, live deterministic results, RAG results, judge classifications, disagreements, and infrastructure failures without making API calls.

## Out of Scope

- RAGAS.
- DeepEval.
- LangSmith.
- Observability platforms.
- Production monitoring.
- UI dashboard.
- Persistence or database.
- Model benchmarking across multiple providers.

## Success Criteria

The local flow is `python -m evals.run`, `python -m evals.run_live`, `python -m evals.run_rag`, `python -m evals.run_judge`, then `python -m evals.report`. Deterministic failures and judge quality classifications remain separate signals. Evaluation thresholds remain diagnostic and do not tune production retrieval automatically.

## Anti-overengineering

Keep evaluation independent from the product UI and avoid frameworks unless a concrete need appears.
