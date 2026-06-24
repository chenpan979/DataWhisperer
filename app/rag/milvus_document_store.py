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
    file_id: str
    file_name: str
    chunk_index: int
    content: str
    vector: list[float]


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
                    "file_id": document.file_id,
                    "file_name": document.file_name,
                    "chunk_index": document.chunk_index,
                    "content": document.content,
                }
                for document in documents
            ],
        )
        return len(documents)

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


def _escape_filter_value(value: str) -> str:
    """转义 Milvus filter 字符串中的特殊字符。"""

    return value.replace("\\", "\\\\").replace('"', '\\"')
