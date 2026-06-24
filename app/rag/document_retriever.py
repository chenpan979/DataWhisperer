from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.rag.embeddings import TextEmbedder, create_text_embedder
from app.rag.milvus_document_store import MilvusRagDocumentStore, MilvusRagSearchHit

NO_KNOWLEDGE_CONTEXT = "未检索到相关工作空间知识库资料。"


@dataclass(frozen=True)
class RagKnowledgeScope:
    """当前请求可访问的知识库范围。

    这个对象只保存租户、工作空间和知识库 ID，不保存用户输入。
    后续拆 RAG Agent 时，可以把它作为工具调用上下文传入。
    """

    tenant_id: int | str
    workspace_id: int | str
    knowledge_base_id: int | str | None = None


@dataclass(frozen=True)
class RetrievedKnowledgeChunk:
    """一次检索命中的知识库切片。"""

    source: str
    content: str
    score: float
    file_id: str
    document_id: str
    chunk_index: int


@dataclass(frozen=True)
class RagDocumentRetrievalResult:
    """工作空间知识库检索结果。"""

    chunks: tuple[RetrievedKnowledgeChunk, ...]
    prompt_context: str
    retrieval_mode: str

    @property
    def sources(self) -> list[str]:
        """返回命中的知识来源，方便 API trace 和后续评测使用。"""

        return [f"{item.source}#{item.chunk_index}" for item in self.chunks]


class RagDocumentRetriever:
    """面向上传知识库资料的 Milvus 检索器。

    它只负责检索当前租户/工作空间可见的知识库切片，不负责生成 SQL。
    这样 V4 拆多智能体时，RAG Agent 可以直接复用这一层。
    """

    def __init__(
        self,
        *,
        store: MilvusRagDocumentStore,
        embedder: TextEmbedder,
        auto_fallback: bool = True,
    ):
        self.store = store
        self.embedder = embedder
        self.auto_fallback = auto_fallback

    def retrieve(
        self,
        question: str,
        *,
        scope: RagKnowledgeScope,
        top_k: int = 4,
        min_score: float = 0.12,
    ) -> RagDocumentRetrievalResult:
        """从当前工作空间知识库检索与问题相关的文档片段。"""

        try:
            hits = self.store.search(
                self.embedder.embed(question),
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                knowledge_base_id=scope.knowledge_base_id,
                top_k=top_k,
            )
            selected = tuple(self._to_chunk(hit) for hit in hits if hit.score >= min_score)
            return RagDocumentRetrievalResult(
                chunks=selected,
                prompt_context=_build_prompt_context(selected),
                retrieval_mode="milvus_rag_vector_v1",
            )
        except Exception:
            if not self.auto_fallback:
                raise
            return empty_rag_document_result(retrieval_mode="milvus_rag_vector_v1_fallback")

    def _to_chunk(self, hit: MilvusRagSearchHit) -> RetrievedKnowledgeChunk:
        return RetrievedKnowledgeChunk(
            source=hit.file_name or hit.file_id,
            content=hit.content,
            score=round(hit.score, 4),
            file_id=hit.file_id,
            document_id=hit.document_id,
            chunk_index=hit.chunk_index,
        )


def empty_rag_document_result(*, retrieval_mode: str = "disabled") -> RagDocumentRetrievalResult:
    """返回空知识库检索结果。"""

    return RagDocumentRetrievalResult(
        chunks=(),
        prompt_context=NO_KNOWLEDGE_CONTEXT,
        retrieval_mode=retrieval_mode,
    )


@lru_cache
def get_rag_document_retriever() -> RagDocumentRetriever:
    """创建默认 RAG 文档检索器。"""

    settings = get_settings()
    return create_rag_document_retriever(settings=settings)


def create_rag_document_retriever(*, settings: Settings) -> RagDocumentRetriever:
    """根据运行配置创建 RAG 文档检索器。"""

    return RagDocumentRetriever(
        store=MilvusRagDocumentStore(
            uri=settings.milvus_uri,
            collection_name=settings.milvus_rag_collection,
            dimension=settings.rag_embedding_dimension,
        ),
        embedder=create_text_embedder(settings),
        auto_fallback=settings.milvus_auto_fallback,
    )


def _build_prompt_context(chunks: tuple[RetrievedKnowledgeChunk, ...]) -> str:
    if not chunks:
        return NO_KNOWLEDGE_CONTEXT

    blocks = []
    for item in chunks:
        blocks.append(
            "\n".join(
                [
                    f"### 知识库资料：{item.source}",
                    f"检索分数：{item.score}",
                    f"片段序号：{item.chunk_index}",
                    _clip_content(item.content),
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _clip_content(content: str, *, limit: int = 1200) -> str:
    normalized = content.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."
