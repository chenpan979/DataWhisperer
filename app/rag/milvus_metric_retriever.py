from __future__ import annotations

from pathlib import Path

from app.rag.embeddings import HashingTextEmbedder
from app.rag.metric_retriever import (
    MetricDefinition,
    MetricRetrievalResult,
    MetricRetriever,
    RetrievedMetric,
)
from app.rag.milvus_metric_store import MilvusMetricSearchHit, MilvusMetricStore


class MilvusMetricRetriever:
    """基于 Milvus 的指标口径向量检索器。

    V3.3 把指标口径检索从“本地轻量 hybrid 检索”升级为“可选 Milvus 向量检索”。
    但它仍然保留本地检索兜底，这样项目在没有启动 Milvus、没有安装 pymilvus、
    或者向量库还没同步时，也可以继续正常回答问题。
    """

    def __init__(
        self,
        *,
        store: MilvusMetricStore,
        embedder: HashingTextEmbedder,
        fallback_retriever: MetricRetriever,
        auto_fallback: bool = True,
    ):
        self.store = store
        self.embedder = embedder
        self.fallback_retriever = fallback_retriever
        self.auto_fallback = auto_fallback

    def retrieve(
        self,
        question: str,
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> MetricRetrievalResult:
        """先查 Milvus，失败或无结果时按配置回退到本地检索。"""

        try:
            hits = self.store.search(self.embedder.embed(question), top_k=top_k)
            selected = tuple(
                self._to_retrieved_metric(hit)
                for hit in hits
                if hit.score >= min_score
            )
            if selected:
                return MetricRetrievalResult(
                    metrics=selected,
                    prompt_context=self._build_prompt_context(selected),
                    retrieval_mode="milvus_vector_v1",
                )
            if not self.auto_fallback:
                return MetricRetrievalResult(
                    metrics=(),
                    prompt_context="未检索到相关业务指标口径。",
                    retrieval_mode="milvus_vector_v1",
                )
        except Exception:
            if not self.auto_fallback:
                raise

        return self.fallback_retriever.retrieve(question, top_k=top_k)

    def _to_retrieved_metric(self, hit: MilvusMetricSearchHit) -> RetrievedMetric:
        metric = MetricDefinition(
            name=hit.name,
            path=Path("milvus") / f"{hit.metric_id}.md",
            aliases=_split_csv(hit.aliases),
            keywords=_split_csv(hit.keywords),
            content=hit.content,
        )
        return RetrievedMetric(
            metric=metric,
            score=round(hit.score, 4),
            lexical_score=0,
            semantic_score=round(hit.score, 4),
            matched_terms=(),
        )

    def _build_prompt_context(self, metrics: tuple[RetrievedMetric, ...]) -> str:
        blocks = []
        for item in metrics:
            blocks.append(
                "\n".join(
                    [
                        f"### {item.metric.name}",
                        "匹配词：-",
                        f"检索分数：{item.score}",
                        "检索模式：milvus_vector_v1",
                        item.metric.content,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
