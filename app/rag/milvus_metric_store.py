from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MilvusMetricDocument:
    """准备写入 Milvus 的指标文档。"""

    metric_id: str
    name: str
    aliases: str
    keywords: str
    content: str
    vector: list[float]


@dataclass(frozen=True)
class MilvusMetricSearchHit:
    """Milvus 向量检索命中的指标文档。"""

    metric_id: str
    name: str
    aliases: str
    keywords: str
    content: str
    score: float


class MilvusMetricStore:
    """Milvus 指标向量库访问层。

    这个类只负责和 Milvus 交互，不负责读取 Markdown、不负责生成向量、
    也不负责把结果拼成 prompt。职责拆开以后，单元测试和后续替换都更容易。
    """

    def __init__(self, *, uri: str, collection_name: str, dimension: int):
        self.uri = uri
        self.collection_name = collection_name
        self.dimension = dimension

    def recreate_collection(self) -> None:
        """重建指标 collection。

        指标口径库当前规模很小，V3.3 采用“全量重建索引”的方式最清晰。
        真实生产环境可以进一步升级成按文件 hash 增量 upsert。
        """

        client = self._client()
        if client.has_collection(self.collection_name):
            client.drop_collection(self.collection_name)
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

    def insert_documents(self, documents: list[MilvusMetricDocument]) -> int:
        """批量写入指标文档，返回写入数量。"""

        if not documents:
            return 0

        client = self._client()
        client.insert(
            collection_name=self.collection_name,
            data=[
                {
                    "id": document.metric_id,
                    "vector": document.vector,
                    "name": document.name,
                    "aliases": document.aliases,
                    "keywords": document.keywords,
                    "content": document.content,
                }
                for document in documents
            ],
        )
        return len(documents)

    def search(self, vector: list[float], *, top_k: int = 3) -> list[MilvusMetricSearchHit]:
        """按向量相似度检索指标文档。"""

        client = self._client()
        raw_results = client.search(
            collection_name=self.collection_name,
            data=[vector],
            limit=top_k,
            output_fields=["id", "name", "aliases", "keywords", "content"],
        )
        if not raw_results:
            return []

        hits: list[MilvusMetricSearchHit] = []
        for item in raw_results[0]:
            entity = _extract_entity(item)
            hits.append(
                MilvusMetricSearchHit(
                    metric_id=str(entity.get("id", "")),
                    name=str(entity.get("name", "")),
                    aliases=str(entity.get("aliases", "")),
                    keywords=str(entity.get("keywords", "")),
                    content=str(entity.get("content", "")),
                    score=float(item.get("distance", item.get("score", 0.0))),
                )
            )
        return hits

    def _client(self) -> Any:
        """创建 MilvusClient。

        这里使用延迟导入：只有真正选择 Milvus 检索时才需要安装 `pymilvus`。
        这样本地开发者不启动 Milvus、不安装客户端，也不会影响基础测试。
        """

        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pymilvus，无法使用 Milvus 检索。请先执行 pip install pymilvus。"
            ) from exc
        return MilvusClient(uri=self.uri)


def _extract_entity(hit: dict[str, Any]) -> dict[str, Any]:
    """兼容不同 pymilvus 版本的 search 返回结构。"""

    if "entity" in hit and isinstance(hit["entity"], dict):
        return hit["entity"]
    return hit
