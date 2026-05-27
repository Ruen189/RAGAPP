from app.services.rag_service import RagService


def test_should_use_rag_for_factual_query():
    assert RagService.should_use_rag("Объясни Scrum и ссылки на стандарт") is True


def test_should_skip_rag_for_chitchat():
    assert RagService.should_use_rag("Как настроение?") is False


def test_should_use_rag_for_iso_reference():
    assert RagService.should_use_rag("Что говорит ISO по качеству процесса?") is True
