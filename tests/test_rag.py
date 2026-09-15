from io import BytesIO
import ssl
from types import SimpleNamespace
import sys

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.interview import MAX_DOCUMENT_TEXT, PDFExtractionError, extract_pdf_pages
from app.rag import (
    CHUNK_OVERLAP_WORDS,
    CHUNK_SIZE_WORDS,
    DEFAULT_TOP_K,
    RetrievalError,
    RetrievedChunk,
    TextChunk,
    _embedding_error_category,
    chunk_pages,
    load_embedding_model,
    process_pdf,
    retrieve_chunks,
)


def make_pdf(*page_texts: str | None) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if not text:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_page_extraction_preserves_pdf_page_numbers() -> None:
    pages = extract_pdf_pages(
        make_pdf("First page material", None, "Third page material"),
        "study material",
    )

    assert pages == [(1, "First page material"), (3, "Third page material")]


def test_one_page_pdf_creates_one_chunk_with_metadata() -> None:
    chunks = process_pdf(make_pdf("A concise synthetic lesson source"))

    assert chunks == [
        TextChunk(
            text="A concise synthetic lesson source",
            page_number=1,
            chunk_index=0,
        )
    ]


def test_multi_page_pdf_keeps_chunks_on_their_source_pages() -> None:
    chunks = process_pdf(make_pdf("Page one topic", "Page two topic"))

    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


def test_rag_chunks_text_larger_than_interview_direct_context_limit(monkeypatch) -> None:
    oversized_page = "word " * (MAX_DOCUMENT_TEXT // 5 + 100)
    calls = []

    def shared_page_extraction(pdf_data, document_name):
        calls.append((pdf_data, document_name))
        return [(1, oversized_page)]

    monkeypatch.setattr("app.rag.extract_pdf_pages", shared_page_extraction)

    chunks = process_pdf(b"synthetic PDF")

    assert calls == [(b"synthetic PDF", "study material")]
    assert sum(len(chunk.text) for chunk in chunks) > MAX_DOCUMENT_TEXT
    assert all(chunk.page_number == 1 for chunk in chunks)


def test_chunking_is_deterministic_and_overlaps_words() -> None:
    text = " ".join(f"word{index}" for index in range(CHUNK_SIZE_WORDS + 20))

    first_run = chunk_pages([(4, text)])
    second_run = chunk_pages([(4, text)])

    assert first_run == second_run
    assert len(first_run) == 2
    assert (
        first_run[0].text.split()[-CHUNK_OVERLAP_WORDS:]
        == first_run[1].text.split()[:CHUNK_OVERLAP_WORDS]
    )
    assert all(chunk.page_number == 4 for chunk in first_run)


def test_empty_page_text_does_not_create_empty_chunks() -> None:
    chunks = chunk_pages([(1, "  \n "), (2, "usable material")])

    assert len(chunks) == 1
    assert chunks[0].text == "usable material"
    assert all(chunk.text.strip() for chunk in chunks)


@pytest.mark.parametrize("pdf_data", [b"", b"not a pdf", make_pdf(None)])
def test_unreadable_or_textless_pdf_is_rejected(pdf_data: bytes) -> None:
    with pytest.raises(PDFExtractionError) as error:
        process_pdf(pdf_data)

    assert "PDF" in str(error.value) or "readable text" in str(error.value)


def test_pdf_producing_no_chunks_is_rejected() -> None:
    with pytest.raises(PDFExtractionError, match="No usable text chunks"):
        chunk_pages([(1, "   ")])


def synthetic_embeddings(texts) -> list[list[float]]:
    embeddings = []
    for text in texts:
        normalized = text.casefold()
        embeddings.append(
            [
                float(any(word in normalized for word in ("python", "decorator", "function"))),
                float(any(word in normalized for word in ("passato", "italiano", "italian"))),
                float(any(word in normalized for word in ("football", "stadium", "weather"))),
            ]
        )
    return embeddings


def retrieval_chunks() -> list[TextChunk]:
    return [
        TextChunk("Python decorators wrap a function.", 2, 0),
        TextChunk("Il passato prossimo usa avere o essere.", 5, 1),
        TextChunk("Football supporters filled the stadium.", 8, 2),
        TextChunk("The weather forecast predicts rain.", 9, 3),
        TextChunk("Italiano is spoken throughout Italy.", 10, 4),
    ]


def test_chunks_are_indexed_and_query_returns_internal_top_k() -> None:
    results = retrieve_chunks(
        retrieval_chunks(),
        "How does a Python decorator change a function?",
        embedding_function=synthetic_embeddings,
    )

    assert len(results) == DEFAULT_TOP_K
    assert all(isinstance(result, RetrievedChunk) for result in results)


def test_relevant_chunk_ranks_above_unrelated_content() -> None:
    results = retrieve_chunks(
        retrieval_chunks(),
        "Explain Python function decorators",
        embedding_function=synthetic_embeddings,
    )

    assert results[0].chunk_index == 0
    assert "Python decorators" in results[0].text


def test_retrieval_preserves_page_and_chunk_metadata() -> None:
    results = retrieve_chunks(
        retrieval_chunks(),
        "Italian passato prossimo",
        embedding_function=synthetic_embeddings,
    )

    assert results[0] == RetrievedChunk(
        text="Il passato prossimo usa avere o essere.",
        page_number=5,
        chunk_index=1,
    )


def test_empty_chunks_are_rejected_before_embedding() -> None:
    with pytest.raises(RetrievalError, match="at least one text chunk"):
        retrieve_chunks([], "Python", embedding_function=synthetic_embeddings)


def test_empty_query_is_rejected_before_embedding() -> None:
    with pytest.raises(RetrievalError, match="study topic or question"):
        retrieve_chunks(
            retrieval_chunks(), "   ", embedding_function=synthetic_embeddings
        )


def test_top_k_larger_than_available_chunks_returns_all_available() -> None:
    chunks = retrieval_chunks()[:2]

    results = retrieve_chunks(
        chunks, "Python decorators", embedding_function=synthetic_embeddings
    )

    assert len(results) == 2


def test_ephemeral_retrieval_creates_no_persistent_files(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    retrieve_chunks(
        retrieval_chunks(),
        "Python decorators",
        embedding_function=synthetic_embeddings,
    )

    assert list(tmp_path.iterdir()) == []


def test_embedding_model_load_failure_is_friendly(monkeypatch) -> None:
    def failed_model(_model_name):
        raise OSError("synthetic load failure")

    load_embedding_model.cache_clear()
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=failed_model),
    )

    with pytest.raises(RetrievalError, match="local embedding model could not be loaded"):
        load_embedding_model()

    load_embedding_model.cache_clear()


@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (ModuleNotFoundError("No module named 'torch'"), "missing_dependency"),
        (ssl.SSLCertVerificationError(1, "certificate verify failed"), "tls_certificate"),
        (PermissionError(13, "access denied"), "filesystem_permission"),
        (OSError("offline and no cached files are available"), "offline_cache_miss"),
        (OSError("safetensors cache is corrupt"), "cache_corruption"),
        (ImportError("transformers requires torch 2.x"), "dependency_incompatibility"),
        (RuntimeError("model could not initialize"), "model_initialization"),
    ],
)
def test_embedding_model_failures_are_classified_safely(
    error: Exception, expected_category: str
) -> None:
    assert _embedding_error_category(error) == expected_category
