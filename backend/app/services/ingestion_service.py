from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag_service import RagService


class IngestionService:
    def __init__(self, rag_service: RagService) -> None:
        self.rag = rag_service

    async def upload_text(
        self,
        db: AsyncSession,
        title: str,
        content: str,
        source_uri: str | None,
        metadata_json: dict,
    ):
        return await self.rag.ingest_document(
            db=db,
            title=title,
            content=content,
            source_uri=source_uri,
            metadata=metadata_json,
        )
