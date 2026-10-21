"""Project memory: past features, code and learned instructions, searchable by meaning.

Each project gets its own ChromaDB collection. Text is turned into vectors
with a small local model (all-MiniLM-L6-v2), so no API call is needed.

The database client and the model are created the first time they are
needed, not when this module is imported. Loading the model takes a few
seconds and pulls in PyTorch, so the server and the tests start faster
this way.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import TYPE_CHECKING

import chromadb

from app.config import settings
from app.schemas.core import MemoryEntry
from app.utils.logging import log_structured

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class VectorStore:
    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None
        self._embedder: SentenceTransformer | None = None
        # Two requests may arrive at the same time. The lock makes sure
        # only one of them loads the model.
        self._load_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Created on first use
    # ------------------------------------------------------------------

    @property
    def client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        return self._client

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Turn texts into vectors. Runs in a worker thread."""
        with self._load_lock:
            if self._embedder is None:
                from sentence_transformers import SentenceTransformer  # slow import, so done here

                self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedder.encode(texts, show_progress_bar=False).tolist()

    def _collection(self, project_id: int):
        return self.client.get_or_create_collection(f"project_{project_id}_memory")

    # ------------------------------------------------------------------
    # Public API. Memory is a helper, not a must, so these log errors
    # instead of raising them: a broken memory store never fails a run.
    # ------------------------------------------------------------------

    async def add_documents(
        self,
        project_id: int,
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        try:
            embeddings = await asyncio.to_thread(self._embed, documents)
            await asyncio.to_thread(
                self._collection(project_id).add,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
                ids=[f"doc_{uuid.uuid4().hex[:12]}" for _ in documents],
            )
            log_structured("vector_store_add", project_id=project_id, doc_count=len(documents))
        except Exception as exc:
            log_structured("vector_store_add_error", project_id=project_id, error=str(exc))

    async def query(self, project_id: int, query_text: str, top_k: int = 5) -> list[tuple[str, dict]]:
        """The `top_k` stored documents closest in meaning to `query_text`."""
        try:
            embedding = await asyncio.to_thread(self._embed, [query_text])
            result = await asyncio.to_thread(
                self._collection(project_id).query, query_embeddings=embedding, n_results=top_k
            )
            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0] or [{}] * len(documents)
            return list(zip(documents, metadatas, strict=True))
        except Exception as exc:
            log_structured("vector_store_query_error", project_id=project_id, error=str(exc))
            return []

    async def list_documents(self, project_id: int) -> list[MemoryEntry]:
        try:
            result = await asyncio.to_thread(self._collection(project_id).get)
        except Exception as exc:
            log_structured("vector_store_list_error", project_id=project_id, error=str(exc))
            return []
        ids = result.get("ids", [])
        documents = result.get("documents") or [""] * len(ids)
        metadatas = result.get("metadatas") or [{}] * len(ids)
        return [
            MemoryEntry(id=doc_id, document=document or "", metadata=metadata or {})
            for doc_id, document, metadata in zip(ids, documents, metadatas, strict=True)
        ]

    async def add_learned_instruction(self, project_id: int, task_type: str, instruction: str) -> None:
        """Store an instruction the self-evolve agent learned, for later runs to find."""
        await self.add_documents(
            project_id=project_id,
            documents=[instruction],
            metadatas=[{"type": "learned_instruction", "task_type": task_type}],
        )

    def health_check(self) -> bool:
        """True if ChromaDB answers. Does not load the embedding model."""
        try:
            self.client.heartbeat()
        except Exception:
            return False
        return True


vector_store = VectorStore()
