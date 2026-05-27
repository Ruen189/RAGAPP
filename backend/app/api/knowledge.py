from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import KnowledgeDocument, User
from app.schemas import KnowledgeDocumentOut, KnowledgeUploadRequest
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

router = APIRouter()
rag_service = RagService()
ingestion = IngestionService(rag_service)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
async def list_documents(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    docs = query.scalars().all()
    return [
        KnowledgeDocumentOut(
            id=doc.id,
            title=doc.title,
            source_type=doc.source_type,
            source_uri=doc.source_uri,
            created_at=doc.created_at,
        )
        for doc in docs
    ]


@router.post("/upload", response_model=KnowledgeDocumentOut)
async def upload_document(payload: KnowledgeUploadRequest, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    doc = await ingestion.upload_text(
        db=db,
        title=payload.title,
        content=payload.content,
        source_uri=payload.source_uri,
        metadata_json=payload.metadata_json,
    )
    return KnowledgeDocumentOut(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        source_uri=doc.source_uri,
        created_at=doc.created_at,
    )
