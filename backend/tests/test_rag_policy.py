from app.services.rag_service import RagService, RetrievedChunk


def test_should_use_rag_for_factual_query():
    assert RagService.should_use_rag("Объясни Scrum и ссылки на стандарт") is True


def test_should_skip_rag_for_chitchat():
    assert RagService.should_use_rag("Как настроение?") is False


def test_should_use_rag_for_iso_reference():
    assert RagService.should_use_rag("Что говорит ISO по качеству процесса?") is True


def test_should_use_rag_for_document_content_question():
    assert RagService.should_use_rag("Что написано в ГОСТ 7.32?") is True
    assert RagService.should_use_rag("Расскажи про содержание документа") is True


def test_extract_query_anchors_for_gost():
    anchors = RagService.extract_query_anchors("Что написано в ГОСТ 7.32?")
    assert "гост 7.32" in anchors


def test_filter_relevant_chunks_drops_unrelated_docs():
    chunks = [
        RetrievedChunk(
            document_id="doc-1",
            chunk_id="chunk-1",
            score=0.9,
            text="Документ: Учебный проект\nЦель, scope, риски и журнал решений.",
            metadata={"title": "Учебный проект"},
        )
    ]
    filtered = RagService.filter_relevant_chunks("Что написано в ГОСТ 7.32?", chunks)
    assert filtered == []
