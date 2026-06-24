from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MilvusRagDocument:
    """准备写入 Milvus 的 RAG 文档切片。

    一个上传文件会被切成多段，每段单独写入向量库。检索时命中的是 chunk，
    但仍然保留 file_id/file_name，方便前端或后续 Agent 追溯来源。
    """

    chunk_id: str
    tenant_id: str
    workspace_id: str
    knowledge_base_id: str
    document_id: str
    file_id: str
    file_name: str
    chunk_index: int
    content: str
    vector: list[float]


@dataclass(frozen=True)
class MilvusRagSearchHit:
    """Milvus 向量检索命中的 RAG 文档切片。"""

    chunk_id: str
    tenant_id: str
    workspace_id: str
    knowledge_base_id: str
    document_id: str
    file_id: str
    file_name: str
    chunk_index: int
    content: str
    score: float


class MilvusRagDocumentStore:
    """RAG 知识库文件的 Milvus 访问层。

    指标口径索引用 `datawhisperer_metrics`，上传知识库文件使用单独 collection，
    避免把“内置指标定义”和“用户上传资料”混在一起。
    """

    def __init__(self, *, uri: str, collection_name: str, dimension: int):
        self.uri = uri
        self.collection_name = collection_name
        self.dimension = dimension

    def ensure_collection(self) -> None:
        """确保 RAG 文档 collection 存在。"""

        client = self._client()
        self._ensure_collection(client)

    def replace_file_documents(self, file_id: str, documents: list[MilvusRagDocument]) -> int:
        """以文件为粒度重建向量索引。

        同一个文件重新同步时，先删除旧 chunk，再写入新 chunk。
        这样实现简单、可解释，也避免重复上传造成检索结果重复。
        """

        client = self._client()
        self._ensure_collection(client)
        self._delete_file_documents(client, file_id)
        if not documents:
            return 0
        client.insert(
            collection_name=self.collection_name,
            data=[
                {
                    "id": document.chunk_id,
                    "vector": document.vector,
                    "tenant_id": document.tenant_id,
                    "workspace_id": document.workspace_id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "document_id": document.document_id,
                    "file_id": document.file_id,
                    "file_name": document.file_name,
                    "chunk_index": document.chunk_index,
                    "content": document.content,
                }
                for document in documents
            ],
        )
        return len(documents)


    def search(
        self,
        vector: list[float],
        *,
        tenant_id: int | str,
        workspace_id: int | str,
        knowledge_base_id: int | str | None = None,
        top_k: int = 4,
    ) -> list[MilvusRagSearchHit]:
        """按当前租户/工作空间过滤检索 RAG 文档切片。

        多租户场景下，向量库里会同时保存不同工作空间的知识片段。
        这里必须把 tenant_id 和 workspace_id 放进 Milvus filter，避免知识库串租户。
        """

        client = self._client()
        if not client.has_collection(self.collection_name):
            return []
        raw_results = client.search(
            collection_name=self.collection_name,
            data=[vector],
            limit=top_k,
            filter=_build_scope_filter(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
            ),
            output_fields=[
                "id",
                "tenant_id",
                "workspace_id",
                "knowledge_base_id",
                "document_id",
                "file_id",
                "file_name",
                "chunk_index",
                "content",
            ],
        )
        if not raw_results:
            return []

        hits: list[MilvusRagSearchHit] = []
        for item in raw_results[0]:
            entity = _extract_entity(item)
            hits.append(
                MilvusRagSearchHit(
                    chunk_id=str(entity.get("id", "")),
                    tenant_id=str(entity.get("tenant_id", "")),
                    workspace_id=str(entity.get("workspace_id", "")),
                    knowledge_base_id=str(entity.get("knowledge_base_id", "")),
                    document_id=str(entity.get("document_id", "")),
                    file_id=str(entity.get("file_id", "")),
                    file_name=str(entity.get("file_name", "")),
                    chunk_index=int(entity.get("chunk_index", 0) or 0),
                    content=str(entity.get("content", "")),
                    score=float(item.get("distance", item.get("score", 0.0))),
                )
            )
        return hits

    def delete_file_documents(self, file_id: str) -> bool:
        """删除某个上传文件对应的所有向量切片。"""

        client = self._client()
        if not client.has_collection(self.collection_name):
            return False
        self._delete_file_documents(client, file_id)
        return True

    def _ensure_collection(self, client: Any) -> None:
        if client.has_collection(self.collection_name):
            return
        client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dimension,
            primary_field_name="id",
            id_type="string",
            vector_field_name="vector",
            metric_type="COSINE",
            consistency_level="Strong",
            auto_id=False,
            max_length=128,
        )

    def _delete_file_documents(self, client: Any, file_id: str) -> None:
        client.delete(
            collection_name=self.collection_name,
            filter=f'file_id == "{_escape_filter_value(file_id)}"',
        )

    def _client(self) -> Any:
        """延迟创建 MilvusClient，避免基础运行强依赖 pymilvus。"""

        try:
            from pymilvus import MilvusClient
        except ImportError as exc:  # pragma: no cover - environment setup guard
            raise RuntimeError(
                '未安装 pymilvus，无法同步 RAG 文件到 Milvus。请先执行 pip install -e \".[milvus]\"。'
            ) from exc
        return MilvusClient(uri=self.uri)


def _build_scope_filter(
    *,
    tenant_id: int | str,
    workspace_id: int | str,
    knowledge_base_id: int | str | None = None,
) -> str:
    parts = [
        f'tenant_id == "{_escape_filter_value(str(tenant_id))}"',
        f'workspace_id == "{_escape_filter_value(str(workspace_id))}"',
    ]
    if knowledge_base_id is not None:
        parts.append(f'knowledge_base_id == "{_escape_filter_value(str(knowledge_base_id))}"')
    return " and ".join(parts)


def _extract_entity(hit: dict[str, Any]) -> dict[str, Any]:
    """兼容不同 pymilvus 版本的 search 返回结构。"""

    if "entity" in hit and isinstance(hit["entity"], dict):
        return hit["entity"]
    return hit


def _escape_filter_value(value: str) -> str:
    """转义 Milvus filter 字符串中的特殊字符。"""

    return value.replace("\\", "\\\\").replace('"', '\\"')
