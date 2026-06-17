import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.http_headers import content_disposition_attachment
from app.models import KnowledgeDocument, User, UserRole
from app.schemas import KnowledgeDocumentOut
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

router = APIRouter()
rag_service = RagService()
ingestion = IngestionService(rag_service)


def document_out(doc: KnowledgeDocument) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut(
        id=doc.id,
        title=doc.title,
        file_name=doc.file_name or f"{doc.title}.txt",
        source_type=doc.source_type,
        created_at=doc.created_at,
        visible_to_users=doc.visible_to_users,
    )


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
async def list_documents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if user.role != UserRole.admin:
        query = query.where(KnowledgeDocument.visible_to_users.is_(True))
    rows = await db.execute(query)
    docs = rows.scalars().all()
    return [document_out(doc) for doc in docs if doc.file_data is not None]


@router.post("/upload", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Имя файла не указано")
    file_bytes = await file.read()
    doc = await ingestion.upload_file(db=db, file_name=file.filename, file_bytes=file_bytes)
    return document_out(doc)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KnowledgeDocument, document_id)
    if not doc or not doc.file_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    if user.role != UserRole.admin and not doc.visible_to_users:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Файл недоступен")

    file_name = doc.file_name or f"{doc.title}{doc.file_extension or '.txt'}"
    media_type = doc.mime_type or "application/octet-stream"
    headers = {"Content-Disposition": content_disposition_attachment(file_name)}
    return Response(content=doc.file_data, media_type=media_type, headers=headers)


@router.patch("/documents/{document_id}/visibility", response_model=KnowledgeDocumentOut)
async def toggle_document_visibility(
    document_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KnowledgeDocument, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")
    doc.visible_to_users = not doc.visible_to_users
    await db.commit()
    await db.refresh(doc)
    return document_out(doc)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KnowledgeDocument, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")
    await rag_service.delete_document(db, doc)
