import hashlib
import math
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import KnowledgeChunk, KnowledgeDocument


@dataclass
class RetrievedChunk:
    document_id: str
    chunk_id: str
    score: float
    text: str
    metadata: dict


class HashEmbeddingModel:
    """Small deterministic embedding backend for local Docker runs.

    It avoids pulling PyTorch/CUDA wheels into the API image. The vector is not as
    semantic as a transformer embedding, but it is stable, fast and good enough
    to validate the RAG pipeline end-to-end with Qdrant.
    """

    dimension = 384
    token_pattern = re.compile(r"[\wа-яА-ЯёЁ]+", re.UNICODE)

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self.token_pattern.findall(text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class RagService:
    COLLECTION_NAME = "knowledge_chunks"
    ANCHOR_PATTERNS = (
        re.compile(r"гост(?:\s*[\d.\-]+)?", re.IGNORECASE),
        re.compile(r"iso(?:\s*[\d:]+)?", re.IGNORECASE),
        re.compile(r"pmbok", re.IGNORECASE),
        re.compile(r"scrum", re.IGNORECASE),
        re.compile(r"kanban", re.IGNORECASE),
        re.compile(r"devops", re.IGNORECASE),
    )
    GENERIC_QUERY_TOKENS = frozenset(
        {
            "написано",
            "содержание",
            "расскажи",
            "объясни",
            "стандарт",
            "документ",
            "метод",
            "что",
            "как",
            "какой",
            "какие",
            "про",
            "этом",
            "нем",
            "нём",
            "базе",
            "знаний",
            "вопрос",
            "ответ",
        }
    )

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.encoder: HashEmbeddingModel | None = None
        self.qdrant = None

    def _ensure_ready(self) -> None:
        if self.encoder is None:
            self.encoder = HashEmbeddingModel()
        if self.qdrant is None:
            from qdrant_client import QdrantClient

            self.qdrant = QdrantClient(url=self.settings.qdrant_url)
            self._ensure_collection()

    def _ensure_collection(self) -> None:
        assert self.qdrant is not None
        assert self.encoder is not None
        collections = [item.name for item in self.qdrant.get_collections().collections]
        if self.COLLECTION_NAME in collections:
            return
        from qdrant_client.http.models import Distance, VectorParams

        self.qdrant.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=VectorParams(size=self.encoder.dimension, distance=Distance.COSINE),
        )

    @staticmethod
    def should_use_rag(message: str) -> bool:
        factual_markers = (
            "гост",
            "iso",
            "pmbok",
            "scrum",
            "kanban",
            "devops",
            "метод",
            "стандарт",
            "документ",
            "регламент",
            "требован",
            "оценк",
            "sprint",
            "risk",
            "quality",
            "что написано",
            "что в нем",
            "что в нём",
            "содержание",
            "о чем",
            "о чём",
            "расскажи про",
            "объясни",
        )
        lowered = message.lower()
        return any(marker in lowered for marker in factual_markers)

    @classmethod
    def extract_query_anchors(cls, message: str) -> list[str]:
        lowered = message.lower()
        anchors: list[str] = []
        for pattern in cls.ANCHOR_PATTERNS:
            for match in pattern.finditer(message):
                anchors.append(match.group(0).lower().strip())
        for token in HashEmbeddingModel.token_pattern.findall(lowered):
            if len(token) >= 4 and token not in cls.GENERIC_QUERY_TOKENS:
                anchors.append(token)
        return list(dict.fromkeys(anchors))

    @staticmethod
    def filter_relevant_chunks(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        anchors = RagService.extract_query_anchors(query)
        if not anchors:
            return chunks
        filtered: list[RetrievedChunk] = []
        for chunk in chunks:
            haystack = f"{chunk.text} {chunk.metadata.get('title', '')}".lower()
            if any(anchor in haystack for anchor in anchors):
                filtered.append(chunk)
        return filtered

    @staticmethod
    def chunk_text(content: str, chunk_size: int = 2500, overlap: int = 350) -> list[str]:
        chunks: list[str] = []
        cursor = 0
        while cursor < len(content):
            end = min(len(content), cursor + chunk_size)
            chunks.append(content[cursor:end].strip())
            cursor = max(end - overlap, cursor + 1)
        return [c for c in chunks if c]

    async def ingest_document(
        self,
        db: AsyncSession,
        title: str,
        content: str,
        source_uri: str | None,
        metadata: dict,
        *,
        file_name: str | None = None,
        file_extension: str | None = None,
        mime_type: str | None = None,
        file_data: bytes | None = None,
        visible_to_users: bool = True,
    ) -> KnowledgeDocument:
        self._ensure_ready()
        assert self.qdrant is not None
        assert self.encoder is not None
        from qdrant_client.http.models import PointStruct

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.checksum == checksum))
        doc = existing.scalar_one_or_none()
        if doc:
            updated = False
            if file_name and not doc.file_name:
                doc.file_name = file_name
                updated = True
            if file_extension and not doc.file_extension:
                doc.file_extension = file_extension
                updated = True
            if mime_type and not doc.mime_type:
                doc.mime_type = mime_type
                updated = True
            if file_data and not doc.file_data:
                doc.file_data = file_data
                updated = True
            if updated:
                await db.commit()
                await db.refresh(doc)
            return doc

        doc = KnowledgeDocument(
            title=title,
            source_uri=source_uri,
            checksum=checksum,
            metadata_json=metadata,
            file_name=file_name,
            file_extension=file_extension,
            mime_type=mime_type,
            file_data=file_data,
            visible_to_users=visible_to_users,
        )
        db.add(doc)
        await db.flush()

        points: list[PointStruct] = []
        for idx, chunk in enumerate(self.chunk_text(content)):
            chunk_body = chunk.strip()
            if not chunk_body:
                continue
            chunk_with_title = f"Документ: {title}\n{chunk_body}"
            vector = self.encoder.encode(chunk_with_title)
            point_id = str(uuid.uuid4())
            chunk_row = KnowledgeChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=chunk_with_title,
                metadata_json={"title": title, **metadata},
                qdrant_point_id=point_id,
            )
            db.add(chunk_row)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": str(doc.id),
                        "chunk_index": idx,
                        "text": chunk_with_title,
                        "metadata": chunk_row.metadata_json,
                    },
                )
            )
        self.qdrant.upsert(collection_name=self.COLLECTION_NAME, points=points)
        await db.commit()
        await db.refresh(doc)
        return doc

    async def delete_document(self, db: AsyncSession, document: KnowledgeDocument) -> None:
        self._ensure_ready()
        assert self.qdrant is not None
        from qdrant_client.http.models import FieldCondition, Filter, FilterSelector, MatchValue

        doc_id = str(document.id)
        self.qdrant.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
            ),
        )

        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        await db.delete(document)
        await db.commit()

    async def retrieve_for_query(self, db: AsyncSession, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        raw = self.retrieve(query, top_k=max(top_k * 2, 16))
        if not raw:
            return []

        doc_uuids: list[uuid.UUID] = []
        for doc_id in {chunk.document_id for chunk in raw}:
            try:
                doc_uuids.append(uuid.UUID(doc_id))
            except ValueError:
                continue

        live_ids: set[str] = set()
        if doc_uuids:
            rows = await db.execute(select(KnowledgeDocument.id).where(KnowledgeDocument.id.in_(doc_uuids)))
            live_ids = {str(row[0]) for row in rows.all()}

        live_chunks = [chunk for chunk in raw if chunk.document_id in live_ids]
        return self.filter_relevant_chunks(query, live_chunks)[:top_k]

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        self._ensure_ready()
        assert self.qdrant is not None
        assert self.encoder is not None
        vector = self.encoder.encode(query)
        search_limit = max(top_k * 4, 20)
        hits = self.qdrant.search(collection_name=self.COLLECTION_NAME, query_vector=vector, limit=search_limit)
        query_tokens = [token for token in self.encoder.token_pattern.findall(query.lower()) if len(token) >= 3]

        ranked: list[RetrievedChunk] = []
        for item in hits:
            text = str(item.payload.get("text") or "")
            alpha_chars = sum(1 for ch in text if ch.isalpha())
            if alpha_chars < 30:
                continue
            overlap = sum(1 for token in query_tokens if token in text.lower())
            score = float(item.score) + overlap * 0.08
            ranked.append(
                RetrievedChunk(
                    document_id=item.payload["document_id"],
                    chunk_id=str(item.id),
                    score=score,
                    text=text,
                    metadata=item.payload.get("metadata", {}),
                )
            )

        ranked.sort(key=lambda chunk: chunk.score, reverse=True)
        return ranked[:top_k]
