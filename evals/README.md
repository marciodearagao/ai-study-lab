# Evaluations

Evaluation v1 uses fixed synthetic cases and small deterministic check modules:

- [`study_cases.json`](study_cases.json) and [`study_checks.py`](study_checks.py) validate Study structure, duplicates, and concepts.
- [`interview_cases.json`](interview_cases.json) and [`interview_checks.py`](interview_checks.py) validate Interview Coach structure, evidence grounding expectations, gaps, and source labels.

The checks reuse the product's Pydantic models and never call Groq.

Run both evaluation areas from the project root:

```bash
python -m evals.run
```

The command prints Study, Interview Coach, and overall pass/fail totals. It also writes `evals/report.html`; open that file in a browser for the readable technical report.

`report.html` is generated from the committed synthetic fixtures, replaced on every run, and ignored by Git because its timestamp changes. Evaluation v1 is deterministic and makes no LLM or API calls.

## Evaluation v2 live candidates

With valid Groq settings in the root `.env`, run:

```bash
python -m evals.run_live
```

Live mode passes the same synthetic inputs through the production Study and Interview Coach generation functions, then applies the v1 checks. It overwrites `evals/results/live_candidates.json`, which is ignored by Git because it is generated model output. No personal documents are used or stored.

## RAG evaluation

Run the synthetic RAG fixtures through the production chunking, local embedding, ephemeral Chroma retrieval, and grounded lesson path:

```bash
python -m evals.run_rag
```

The four cases cover direct relevance, multilingual retrieval, competing irrelevant passages, and an intentionally unsupported query. Deterministic checks record retrieved page/chunk IDs, expected concepts, ranking, and irrelevant-passage dominance. Live grounded generation also records safe Groq/Gemini call and outcome metadata. The ignored `evals/results/rag_results.json` artifact is overwritten on each run; it contains synthetic material only.

## Evaluation v2 judge

Judge the existing candidates without regenerating them:

```bash
python -m evals.run_judge
```

The structured judge uses Groq first. Eligible transient, provider, structured-output, or stochastic validation failures may use the existing Gemini adapter once; authentication, configuration, invalid-model, malformed-input, and judge-schema errors do not fall back. A case can make at most two Groq calls and one Gemini call. Study scores cover topic relevance, difficulty alignment, factual coherence, and pedagogical usefulness. Interview Coach scoring covers grounding, false-evidence risk, false-gap risk, and usefulness. RAG scoring covers context relevance, groundedness, unsupported-claim risk, and source-attribution quality. Generation provider failures are skipped and labeled separately.

The command overwrites the ignored `evals/results/judge_results.json` artifact. It does not rewrite prompts or regenerate candidates.

## Combined Evaluation v2 report

After live candidates and judge results exist, generate the offline combined report:

```bash
python -m evals.report
```

Open `evals/results/evaluation_v2_report.html`. The report combines the v1 baseline, Study/Interview live checks, RAG retrieval and grounded-generation results, judge scores, provider telemetry, and provider or judge failures. It shows generator and judge providers and flags same-provider generation/judging as a methodological note. Deterministic `PASS`/`FAIL` and judge `GOOD`/`REVIEW`/`POOR` remain separate. Report generation makes no API calls and does not regenerate input artifacts.

See [`docs/specs/evaluation.md`](../docs/specs/evaluation.md) for the broader scope.
