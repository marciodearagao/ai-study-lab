# RAG v1

## Problem

Users should be able to study from their own PDF material without understanding chunks, embeddings, vector databases, retrieval scores, or other RAG internals.

## Goal

RAG v1 implements this simple flow:

1 PDF → extract text by page → chunk internally → embed locally → ephemeral Chroma vector search → retrieve top-k passages → generate a grounded lesson → show concise source references

## User Experience

In the Study workspace, the user sees only:

- Topic or question input.
- Optional PDF upload.
- Start learning.

Without a PDF, keep the existing general-model lesson flow. With a PDF, use RAG internally.

Do not expose chunks, embeddings, similarity scores, top-k configuration, vector database details, or manual context selection.

## Portfolio Value

RAG v1 demonstrates RAG, embeddings, Sentence Transformers, Chroma, vector search, retrieval, grounded generation, source attribution, and RAG evaluation.

## Technical Direction

- Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Vector store: ephemeral, in-memory Chroma with no persistent collections.
- Generation: the existing Groq-primary integration with optional transparent Gemini fallback. The same authoritative Pydantic `Lesson` schema applies regardless of provider, and the current retry/fallback policy is unchanged.
- Chunking: deterministic chunks of up to 180 words with a 30-word overlap, never crossing page boundaries.
- Upload boundary: exactly one text-based PDF per request, limited to 5 MB; image-only PDFs are unsupported because v1 does not use OCR.
- PDF preparation: readable pages are chunked without applying the Interview Coach direct-context text limit.
- Retrieval: up to 4 chunks per query using internal-only settings; retrieval details remain hidden from learners.
- Grounded generation: treat retrieved page passages as factual context, reuse the existing `Lesson` schema, bound context to 6,000 characters, and derive short references only from retrieved page metadata. Missing material is not filled with unsupported general knowledge; insufficient context produces a deliberately limited lesson. Irrelevant retrieval may occur, but it does not authorize unsupported claims.

Collections, PDFs, and extracted text are not persisted.

The optional manual embedding smoke test is `python -m app.rag`. Its first run may download the approved model; automated tests use injected embeddings and never download it.

## Scope

RAG v1 includes only:

- Exactly one PDF per Study request.
- Text-based, page-based PDF extraction with a 5 MB upload limit and no OCR.
- Deterministic 180-word chunking with 30-word overlap and no cross-page chunks.
- Local multilingual embeddings using `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Chroma similarity search and top-k retrieval.
- Grounded lesson generation using the existing `Lesson` schema.
- Simple page-derived source references.
- Automated tests.
- RAG evaluation for retrieval and grounding.

## Out of Scope

- Multiple PDFs, DOCX, webpages, or OCR.
- Document libraries or persistent document storage.
- Persistent Chroma collections.
- Topic discovery or study blocks.
- Manual chunk selection.
- Similarity scores or top-k controls in the UI.
- Hybrid search or BM25.
- Reranking.
- Graph RAG, Agentic RAG, or CRAG.
- Knowledge graphs.
- Additional AI providers or OpenRouter.

## Evaluation

Reuse the existing Evaluation framework instead of creating a second system.

Retrieval evaluation checks that expected relevant passages appear in top-k results and irrelevant passages do not dominate retrieval. Grounding evaluation checks that generated lessons are supported by retrieved context, assesses unsupported-claim risk, and assesses source-attribution quality, including an unsupported-context case.

## Success Criteria

RAG v1 meets these criteria:

- One uploaded PDF can ground a lesson.
- Retrieval remains invisible to the user.
- Source references are shown simply.
- Existing Study behavior still works without a PDF.
- RAG retrieval and grounding can be evaluated.

## Anti-overengineering

Do not add infrastructure or UI that exists only to demonstrate RAG architecture.

RAG must improve the learning experience, not become the learning experience.
