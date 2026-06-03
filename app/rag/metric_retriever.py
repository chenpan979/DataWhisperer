from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class MetricDefinition:
    """业务指标定义。

    当前 V3.0 先使用本地 Markdown 指标库，不接向量数据库。
    每个指标文件包含名称、别名、关键词和完整口径说明。
    """

    name: str
    path: Path
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]
    content: str


@dataclass(frozen=True)
class RetrievedMetric:
    """一次检索命中的指标。"""

    metric: MetricDefinition
    score: int
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class MetricRetrievalResult:
    """指标检索结果。"""

    metrics: tuple[RetrievedMetric, ...]
    prompt_context: str

    @property
    def names(self) -> list[str]:
        """返回命中的指标名称，方便 API 响应和 trace 展示。"""

        return [item.metric.name for item in self.metrics]


class MetricRetriever:
    """本地指标口径检索器。

    V3.0 的目标是先跑通 RAG 的业务闭环：
    用户问题 -> 检索指标口径 -> 注入 SQL prompt -> 生成更懂业务口径的 SQL。

    当前用关键词和别名匹配实现，后续可以把 retrieve 方法升级成 embedding 检索。
    """

    def __init__(self, knowledge_dir: str | Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else project_root / "knowledge"
        self.metrics_dir = self.knowledge_dir / "metrics"

    def load_metrics(self) -> list[MetricDefinition]:
        """读取本地指标 Markdown 文件。"""

        if not self.metrics_dir.exists():
            return []
        return [
            self._load_metric_file(path)
            for path in sorted(self.metrics_dir.glob("*.md"))
        ]

    def retrieve(self, question: str, top_k: int = 3) -> MetricRetrievalResult:
        """根据用户问题检索最相关的指标口径。"""

        retrieved: list[RetrievedMetric] = []
        for metric in self.load_metrics():
            score, matched_terms = self._score(question, metric)
            if score > 0:
                retrieved.append(
                    RetrievedMetric(
                        metric=metric,
                        score=score,
                        matched_terms=tuple(sorted(matched_terms)),
                    )
                )
        retrieved.sort(key=lambda item: (-item.score, item.metric.name))
        selected = tuple(retrieved[:top_k])
        return MetricRetrievalResult(
            metrics=selected,
            prompt_context=self._build_prompt_context(selected),
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

    def _score(self, question: str, metric: MetricDefinition) -> tuple[int, set[str]]:
        normalized_question = question.casefold()
        score = 0
        matched_terms: set[str] = set()

        if metric.name.casefold() in normalized_question:
            score += 5
            matched_terms.add(metric.name)

        for alias in metric.aliases:
            if alias.casefold() in normalized_question:
                score += 4
                matched_terms.add(alias)

        for keyword in metric.keywords:
            if keyword.casefold() in normalized_question:
                score += 3
                matched_terms.add(keyword)

        return score, matched_terms

    def _build_prompt_context(self, metrics: tuple[RetrievedMetric, ...]) -> str:
        if not metrics:
            return "未检索到相关业务指标口径。"

        blocks = []
        for item in metrics:
            blocks.append(
                "\n".join(
                    [
                        f"### {item.metric.name}",
                        f"匹配词：{', '.join(item.matched_terms) or '-'}",
                        item.metric.content,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@lru_cache
def get_metric_retriever() -> MetricRetriever:
    """返回进程内复用的指标检索器。"""

    return MetricRetriever()
