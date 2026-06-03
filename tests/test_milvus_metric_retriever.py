from app.rag.embeddings import HashingTextEmbedder
from app.rag.metric_retriever import MetricRetriever
from app.rag.milvus_metric_retriever import MilvusMetricRetriever
from app.rag.milvus_metric_store import MilvusMetricSearchHit


class FailingStore:
    def search(self, vector: list[float], *, top_k: int = 3) -> list[MilvusMetricSearchHit]:
        raise RuntimeError("Milvus is not available in this test.")


class FakeStore:
    def search(self, vector: list[float], *, top_k: int = 3) -> list[MilvusMetricSearchHit]:
        return [
            MilvusMetricSearchHit(
                metric_id="gmv",
                name="GMV",
                aliases="成交总额, 商品交易总额",
                keywords="销售额, 金额, 趋势",
                content="# GMV\n\n计算口径：SUM(order_items.quantity * order_items.unit_price)",
                score=0.86,
            )
        ]


def test_milvus_metric_retriever_falls_back_to_local_retrieval() -> None:
    retriever = MilvusMetricRetriever(
        store=FailingStore(),
        embedder=HashingTextEmbedder(dimension=16),
        fallback_retriever=MetricRetriever(),
        auto_fallback=True,
    )

    result = retriever.retrieve("最近 6 个月 GMV 趋势")

    assert result.retrieval_mode == "hybrid_lexical_ngram_v1"
    assert result.names[0] == "GMV"


def test_milvus_metric_retriever_returns_vector_hits() -> None:
    retriever = MilvusMetricRetriever(
        store=FakeStore(),
        embedder=HashingTextEmbedder(dimension=16),
        fallback_retriever=MetricRetriever(),
        auto_fallback=True,
    )

    result = retriever.retrieve("最近 6 个月 GMV 趋势")

    assert result.retrieval_mode == "milvus_vector_v1"
    assert result.names == ["GMV"]
    assert "检索模式：milvus_vector_v1" in result.prompt_context
    assert "SUM(order_items.quantity * order_items.unit_price)" in result.prompt_context
