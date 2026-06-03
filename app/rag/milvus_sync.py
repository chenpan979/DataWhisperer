from __future__ import annotations

from app.core.config import get_settings
from app.rag.embeddings import HashingTextEmbedder
from app.rag.metric_retriever import MetricDefinition, MetricRetriever
from app.rag.milvus_metric_store import MilvusMetricDocument, MilvusMetricStore


def build_metric_documents(
    metrics: list[MetricDefinition],
    embedder: HashingTextEmbedder,
) -> list[MilvusMetricDocument]:
    """把本地指标定义转换成可写入 Milvus 的文档。"""

    documents: list[MilvusMetricDocument] = []
    for metric in metrics:
        documents.append(
            MilvusMetricDocument(
                metric_id=metric.path.stem,
                name=metric.name,
                aliases=", ".join(metric.aliases),
                keywords=", ".join(metric.keywords),
                content=metric.content,
                vector=embedder.embed(metric.search_text),
            )
        )
    return documents


def sync_metrics_to_milvus() -> int:
    """同步本地指标库到 Milvus，返回写入的指标数量。"""

    settings = get_settings()
    embedder = HashingTextEmbedder(dimension=settings.milvus_embedding_dim)
    local_retriever = MetricRetriever()
    store = MilvusMetricStore(
        uri=settings.milvus_uri,
        collection_name=settings.milvus_metric_collection,
        dimension=settings.milvus_embedding_dim,
    )

    documents = build_metric_documents(local_retriever.load_metrics(), embedder)
    store.recreate_collection()
    return store.insert_documents(documents)


def main() -> None:
    """命令行入口：`python -m app.rag.milvus_sync`。"""

    count = sync_metrics_to_milvus()
    print(f"已同步 {count} 个指标口径到 Milvus。")


if __name__ == "__main__":
    main()
