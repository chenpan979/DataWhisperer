from pathlib import Path

from app.rag.embeddings import HashingTextEmbedder
from app.rag.metric_retriever import MetricDefinition
from app.rag.milvus_sync import build_metric_documents


def test_build_metric_documents_uses_metric_metadata() -> None:
    metric = MetricDefinition(
        name="客单价",
        path=Path("avg_order_value.md"),
        aliases=("AOV", "平均订单金额"),
        keywords=("订单", "金额"),
        content="# 客单价\n\n计算口径：SUM(amount) / COUNT(DISTINCT order_id)",
    )

    documents = build_metric_documents([metric], HashingTextEmbedder(dimension=8))

    assert len(documents) == 1
    assert documents[0].metric_id == "avg_order_value"
    assert documents[0].name == "客单价"
    assert documents[0].aliases == "AOV, 平均订单金额"
    assert len(documents[0].vector) == 8
