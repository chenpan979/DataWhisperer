from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.rag.embeddings import TextEmbedder, create_text_embedder
from app.rag.milvus_document_store import MilvusRagDocument, MilvusRagDocumentStore
from app.tools.file_store import ManagedFileStore, get_rag_file_store


@dataclass(frozen=True)
class RagFileSyncResult:
    """RAG 文件同步结果。

    这个结果会被写回文件元数据，也会直接返回给前端。
    status 只用少量固定值，方便 UI 显示：
    - synced：已完成切片和 Milvus 写入；
    - skipped：文件存在，但当前类型不适合自动切片；
    - failed：文件已保存，但向量同步失败，可手动重试。
    """

    status: str
    message: str
    collection: str | None = None
    chunk_count: int = 0
    synced_at: str | None = None

    def to_metadata(self) -> dict[str, object | None]:
        """转换成 ManagedFile 元数据字段。"""

        return {
            "sync_status": self.status,
            "sync_message": self.message,
            "sync_collection": self.collection,
            "sync_chunk_count": self.chunk_count,
            "synced_at": self.synced_at,
        }


def split_text_into_chunks(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """把知识库文本切成适合 embedding 的片段。

    这里不做复杂 NLP 分句，先采用“固定窗口 + 尽量按自然换行/句号截断”的方式。
    这样实现稳定、可测试，后续如果接文档解析器或专门的 chunker，可以替换此函数。
    """

    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []

    chunk_size = max(100, int(chunk_size or 800))
    overlap = max(0, min(int(overlap or 0), chunk_size // 2))
    chunks: list[str] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(text_length, start + chunk_size)
        if end < text_length:
            window = normalized[start:end]
            split_at = max(
                window.rfind("\n\n"),
                window.rfind("\n"),
                window.rfind("。"),
                window.rfind(". "),
            )
            if split_at >= max(80, chunk_size // 3):
                end = start + split_at + 1

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)

    return chunks


def sync_rag_file_to_milvus(
    file_id: str,
    *,
    file_store: ManagedFileStore | None = None,
    settings: Settings | None = None,
    embedder: TextEmbedder | None = None,
    vector_store: MilvusRagDocumentStore | None = None,
) -> RagFileSyncResult:
    """把一个已上传 RAG 文件切片并同步到 Milvus。

    注意：同步失败只影响向量检索，不应该回滚文件上传。调用方会把 failed 状态写回元数据，
    让用户在页面上看到原因并可以点击“同步”重试。
    """

    file_store = file_store or get_rag_file_store()
    loaded = file_store.read_text_file(file_id)
    settings = settings or get_settings()
    attempted_at = datetime.now(UTC).isoformat()

    if loaded is None:
        return RagFileSyncResult(
            status="skipped",
            message="当前文件类型暂不支持自动切片，文件已保留在知识库资料中。",
            collection=settings.milvus_rag_collection,
            synced_at=attempted_at,
        )

    file, text = loaded
    chunks = split_text_into_chunks(
        text,
        chunk_size=settings.rag_chunk_size,
        overlap=settings.rag_chunk_overlap,
    )
    if not chunks:
        return RagFileSyncResult(
            status="skipped",
            message="文件没有可索引的文本内容。",
            collection=settings.milvus_rag_collection,
            synced_at=attempted_at,
        )

    try:
        vector_store = vector_store or MilvusRagDocumentStore(
            uri=settings.milvus_uri,
            collection_name=settings.milvus_rag_collection,
            dimension=settings.rag_embedding_dimension,
        )
        ensure_collection = getattr(vector_store, "ensure_collection", None)
        if callable(ensure_collection):
            ensure_collection()

        embedder = embedder or create_text_embedder(settings)
        vectors = _embed_chunks(embedder, chunks)
        documents = [
            MilvusRagDocument(
                chunk_id=_chunk_id(file.id, index, chunk),
                file_id=file.id,
                file_name=file.name,
                chunk_index=index,
                content=chunk,
                vector=vectors[index],
            )
            for index, chunk in enumerate(chunks)
        ]
        written = vector_store.replace_file_documents(file.id, documents)
    except Exception as exc:  # pragma: no cover - concrete failures depend on local Milvus/DashScope
        return RagFileSyncResult(
            status="failed",
            message=str(exc),
            collection=settings.milvus_rag_collection,
            chunk_count=len(chunks),
            synced_at=attempted_at,
        )

    return RagFileSyncResult(
        status="synced",
        message=f"已切分 {written} 个片段并同步到 Milvus。",
        collection=settings.milvus_rag_collection,
        chunk_count=written,
        synced_at=attempted_at,
    )


def delete_rag_file_vectors(
    file_id: str,
    *,
    settings: Settings | None = None,
    vector_store: MilvusRagDocumentStore | None = None,
) -> bool:
    """删除文件时同步清理 Milvus 中的向量切片。

    清理失败不阻塞本地文件删除，避免 Milvus 临时不可用时影响资料管理。
    """

    settings = settings or get_settings()
    try:
        vector_store = vector_store or MilvusRagDocumentStore(
            uri=settings.milvus_uri,
            collection_name=settings.milvus_rag_collection,
            dimension=settings.rag_embedding_dimension,
        )
        return vector_store.delete_file_documents(file_id)
    except Exception:
        return False


def _embed_chunks(embedder: TextEmbedder, chunks: list[str]) -> list[list[float]]:
    batch_embed = getattr(embedder, "embed_batch", None)
    if callable(batch_embed):
        return batch_embed(chunks)
    return [embedder.embed(chunk) for chunk in chunks]


def _chunk_id(file_id: str, index: int, content: str) -> str:
    digest = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"{file_id}_{index}_{digest}"
