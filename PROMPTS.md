# AI prompts

## Lesson generation

### Purpose

The current prompt asks the structured generation provider to act as a clear, practical teacher and create one concise lesson for the learner’s chosen subject and experience level.

### Inputs

- `topic`: the subject the learner wants to study, up to 120 characters
- `level`: `Basic`, `Intermediate`, or `Advanced`

### Structured output

The model must return a JSON object that is validated before it reaches the UI:

```json
{
  "title": "Lesson title",
  "short_explanation": "One short explanatory paragraph.",
  "key_concepts": ["Three to four", "brief, distinct points", "without repetition"],
  "flashcards": [
    {"question": "A concise question", "answer": "A concise answer"}
  ],
  "quiz_questions": [
    {
      "question": "A focused multiple-choice question",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option A",
      "explanation": "A concise explanation"
    }
  ]
}
```

The explanation is followed by 3–4 concise key points that add information without repeating it. The validated schema requires exactly 5 flashcards and exactly 4 multiple-choice quiz questions. Every quiz question has exactly four distinct, non-near-duplicate options, a character-for-character matching correct answer, and a short explanation. Extra fields are rejected, and all content must be non-empty and stay within the limits defined by the Pydantic models.

### Ambiguous acronyms

The prompt resolves acronyms from the full topic and likely study context. It prefers an established technical meaning when the context supports one. If the meaning remains uncertain, it preserves the acronym rather than inventing or confidently choosing an unrelated expansion. For example, in an AI or machine-learning topic, RAG normally means Retrieval-Augmented Generation.

### Source of truth

The real prompt and structured lesson model are currently defined directly in [`app/lessons.py`](app/lessons.py), keeping the lesson behavior close to its validated output contract.

Prompts may evolve as the product is tested and lesson quality is evaluated.

## Grounded Study from PDF

When a Study PDF is supplied, the lesson prompt receives only retrieved passages with their page labels. Factual claims must stay within that context; insufficient material must not be filled with unsupported general knowledge. The result still uses the authoritative `Lesson` schema, so key points, flashcards, and quiz questions follow the same validation rules. Source references contain short excerpts and page numbers derived only from retrieved passages. The grounded extension is defined in [`app/rag.py`](app/rag.py).

## Interview Coach analysis

### Purpose

The Interview Coach prompt compares a Job Description with Resume / CV text and, when supplied, optional LinkedIn Profile and Cover Letter context. It produces a concise, qualitative assessment grounded in those supplied sources; it does not calculate an ATS score or match percentage.

### Inputs

- `job_description`: the role’s responsibilities and requirements
- `resume_text`: the candidate’s stated experience and skills
- `linkedin_text`: optional supporting context extracted from a LinkedIn Profile PDF
- `cover_letter_text`: optional supplementary context extracted from a Cover Letter PDF

### Structured output

The model returns a validated JSON object with:

- `fit_level`: `Strong fit`, `Good fit`, `Partial fit`, or `Weak fit`
- `fit_summary`: a brief overall assessment
- `evidence`: up to four source-labeled points grounded only in the provided documents
- `gaps`: up to four job requirements not clearly supported by the provided sources
- `suggested_study_topics`: up to four relevant preparation topics
- `interview_questions`: two to four focused questions

The CV remains the primary professional document, while an optional LinkedIn Profile PDF provides supporting professional context. A Cover Letter PDF is supplementary only: its claims are not treated as stronger evidence than the CV unless clearly supported. Evidence is labeled `CV:`, `LinkedIn:`, or `Cover Letter:`. The prompt explicitly prohibits numerical match scores and invented experience. The real prompt and output model are defined in [`app/interview.py`](app/interview.py).

Product generation uses the small shared structured-output layer in [`app/ai.py`](app/ai.py). Groq is primary and Gemini may transparently handle eligible failures; the same Pydantic output schema remains authoritative regardless of provider.

Prompts may evolve as the product is tested and coaching quality is evaluated.
