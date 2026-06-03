from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


NO_METRIC_CONTEXT = "未检索到相关业务指标口径。"


@dataclass(frozen=True)
class MetricDefinition:
    """业务指标定义。

    V3.0 使用本地 Markdown 指标库。
    V3.1 在此基础上加入轻量语义相似度检索，形成 hybrid retrieval。
    """

    name: str
    path: Path
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]
    content: str

    @property
    def search_text(self) -> str:
        """用于相似度检索的指标文本。"""

        return " ".join([self.name, *self.aliases, *self.keywords, self.content])


@dataclass(frozen=True)
class RetrievedMetric:
    """一次检索命中的指标。"""

    metric: MetricDefinition
    score: float
    lexical_score: int
    semantic_score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class MetricRetrievalResult:
    """指标检索结果。"""

    metrics: tuple[RetrievedMetric, ...]
    prompt_context: str
    retrieval_mode: str

    @property
    def names(self) -> list[str]:
        """返回命中的指标名称，方便 API 响应和 trace 展示。"""

        return [item.metric.name for item in self.metrics]


class MetricRetriever:
    """本地指标口径检索器。

    V3.1 采用 hybrid 检索：
    1. 关键词/别名精确匹配，保证强业务词稳定命中；
    2. 字符 n-gram cosine 相似度，补充同义表达和不完全匹配。

    这不是最终的向量数据库方案，但已经具备 RAG 检索增强的完整工程骨架。
    后续接 embedding 时，可以替换 _semantic_score，不需要改变主控流程。
    """

    def __init__(self, knowledge_dir: str | Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else project_root / "knowledge"
        self.metrics_dir = self.knowledge_dir / "metrics"

    def load_metrics(self) -> list[MetricDefinition]:
        """读取本地指标 Markdown 文件。"""

        if not self.metrics_dir.exists():
            return []
        return [self._load_metric_file(path) for path in sorted(self.metrics_dir.glob("*.md"))]

    def retrieve(
        self,
        question: str,
        top_k: int = 3,
        min_score: float = 1.0,
    ) -> MetricRetrievalResult:
        """根据用户问题检索最相关的指标口径。"""

        retrieved: list[RetrievedMetric] = []
        for metric in self.load_metrics():
            lexical_score, matched_terms = self._lexical_score(question, metric)
            semantic_score = self._semantic_score(question, metric.search_text)
            # lexical 负责强命中，semantic 负责弱相关补充。
            # 如果没有任何关键词/别名命中，纯语义召回必须超过更高门槛，避免把
            # “订单数量”这种问题误召回到“客单价”等相邻但不同的指标。
            if lexical_score == 0 and semantic_score < 0.30:
                score = 0.0
            else:
                score = lexical_score + semantic_score * 4
            if score >= min_score:
                retrieved.append(
                    RetrievedMetric(
                        metric=metric,
                        score=round(score, 4),
                        lexical_score=lexical_score,
                        semantic_score=round(semantic_score, 4),
                        matched_terms=tuple(sorted(matched_terms)),
                    )
                )
        retrieved.sort(key=lambda item: (-item.score, item.metric.name))
        selected = tuple(retrieved[:top_k])
        return MetricRetrievalResult(
            metrics=selected,
            prompt_context=self._build_prompt_context(selected),
            retrieval_mode="hybrid_lexical_ngram_v1",
        )

    def _load_metric_file(self, path: Path) -> MetricDefinition:
        content = path.read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        name = path.stem
        aliases: tuple[str, ...] = ()
        keywords: tuple[str, ...] = ()

        for line in lines:
            if line.startswith("# "):
                name = line.removeprefix("# ").strip()
            elif line.startswith("aliases:"):
                aliases = _split_csv(line.removeprefix("aliases:"))
            elif line.startswith("keywords:"):
                keywords = _split_csv(line.removeprefix("keywords:"))

        return MetricDefinition(
            name=name,
            path=path,
            aliases=aliases,
            keywords=keywords,
            content=content,
        )

    def _lexical_score(self, question: str, metric: MetricDefinition) -> tuple[int, set[str]]:
        normalized_question = question.casefold()
        score = 0
        matched_terms: set[str] = set()

        if metric.name.casefold() in normalized_question:
            score += 6
            matched_terms.add(metric.name)

        for alias in metric.aliases:
            if alias.casefold() in normalized_question:
                score += 5
                matched_terms.add(alias)

        for keyword in metric.keywords:
            if keyword.casefold() in normalized_question:
                score += 3
                matched_terms.add(keyword)

        return score, matched_terms

    def _semantic_score(self, question: str, metric_text: str) -> float:
        question_vector = _to_ngram_vector(question)
        metric_vector = _to_ngram_vector(metric_text)
        return _cosine_similarity(question_vector, metric_vector)

    def _build_prompt_context(self, metrics: tuple[RetrievedMetric, ...]) -> str:
        if not metrics:
            return NO_METRIC_CONTEXT

        blocks = []
        for item in metrics:
            blocks.append(
                "\n".join(
                    [
                        f"### {item.metric.name}",
                        f"匹配词：{', '.join(item.matched_terms) or '-'}",
                        f"检索分数：{item.score}",
                        "检索模式：hybrid_lexical_ngram_v1",
                        item.metric.content,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _to_ngram_vector(text: str) -> Counter[str]:
    """把中英文混合文本转换成轻量 n-gram 向量。

    中文没有分词器时，用字符 bigram 能覆盖一部分语义相似表达；
    英文和数字用 token，适合识别 GMV、AOV、order_count 等术语。
    """

    normalized = text.casefold()
    vector: Counter[str] = Counter()
    ascii_tokens = re.findall(r"[a-z0-9_]+", normalized)
    vector.update(ascii_tokens)

    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    vector.update(cjk_chars)
    vector.update("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
    return vector


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0

    common = set(left) & set(right)
    dot_product = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


@lru_cache
def get_metric_retriever() -> MetricRetriever:
    """返回进程内复用的指标检索器。"""

    return MetricRetriever()
