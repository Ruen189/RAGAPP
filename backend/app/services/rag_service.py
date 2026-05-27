import hashlib
import math
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
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
        )
        lowered = message.lower()
        return any(marker in lowered for marker in factual_markers)

    @staticmethod
    def chunk_text(content: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
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
    ) -> KnowledgeDocument:
        self._ensure_ready()
        assert self.qdrant is not None
        assert self.encoder is not None
        from qdrant_client.http.models import PointStruct

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.checksum == checksum))
        doc = existing.scalar_one_or_none()
        if doc:
            return doc

        doc = KnowledgeDocument(
            title=title,
            source_uri=source_uri,
            checksum=checksum,
            metadata_json=metadata,
        )
        db.add(doc)
        await db.flush()

        points: list[PointStruct] = []
        for idx, chunk in enumerate(self.chunk_text(content)):
            vector = self.encoder.encode(chunk)
            point_id = str(uuid.uuid4())
            chunk_row = KnowledgeChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=chunk,
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
                        "text": chunk,
                        "metadata": chunk_row.metadata_json,
                    },
                )
            )
        self.qdrant.upsert(collection_name=self.COLLECTION_NAME, points=points)
        await db.commit()
        await db.refresh(doc)
        return doc

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        self._ensure_ready()
        assert self.qdrant is not None
        assert self.encoder is not None
        vector = self.encoder.encode(query)
        hits = self.qdrant.search(collection_name=self.COLLECTION_NAME, query_vector=vector, limit=top_k)
        return [
            RetrievedChunk(
                document_id=item.payload["document_id"],
                chunk_id=str(item.id),
                score=float(item.score),
                text=item.payload["text"],
                metadata=item.payload.get("metadata", {}),
            )
            for item in hits
        ]
