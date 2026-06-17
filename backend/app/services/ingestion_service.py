from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_parser import UnsupportedDocumentError, extract_text, guess_mime_type, validate_extension
from app.services.rag_service import RagService


class IngestionService:
    def __init__(self, rag_service: RagService) -> None:
        self.rag = rag_service

    async def upload_file(
        self,
        db: AsyncSession,
        file_name: str,
        file_bytes: bytes,
        metadata_json: dict | None = None,
        visible_to_users: bool = True,
    ):
        safe_name = Path(file_name).name
        try:
            extension = validate_extension(safe_name)
            content = extract_text(safe_name, file_bytes)
        except UnsupportedDocumentError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        title = Path(safe_name).stem.replace("_", " ").strip() or safe_name
        return await self.rag.ingest_document(
            db=db,
            title=title,
            content=content,
            source_uri=f"upload://{safe_name}",
            metadata=metadata_json or {"domain": "project-management"},
            file_name=safe_name,
            file_extension=extension,
            mime_type=guess_mime_type(extension),
            file_data=file_bytes,
            visible_to_users=visible_to_users,
        )
