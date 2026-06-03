from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from app.rag.metric_retriever import get_metric_retriever


@dataclass(frozen=True)
class MetricRetrievalEvalCase:
    """单条指标检索评测用例。"""

    id: str
    question: str
    expected_metrics: tuple[str, ...]
    forbidden_metrics: tuple[str, ...]
    min_score: float
    tags: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricRetrievalEvalCase":
        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            expected_metrics=tuple(data.get("expected_metrics", [])),
            forbidden_metrics=tuple(data.get("forbidden_metrics", [])),
            min_score=float(data.get("min_score", 1.0)),
            tags=tuple(data.get("tags", [])),
        )


@dataclass(frozen=True)
class MetricRetrievalEvalResult:
    """单条指标检索评测结果。"""

    case_id: str
    passed: bool
    errors: tuple[str, ...]
    retrieved_metrics: tuple[str, ...]
    scores: dict[str, float]


@dataclass(frozen=True)
class MetricRetrievalEvalReport:
    """指标检索评测汇总报告。"""

    total: int
    passed: int
    failed: int
    results: tuple[MetricRetrievalEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "results": [
                {
                    "case_id": result.case_id,
                    "passed": result.passed,
                    "errors": list(result.errors),
                    "retrieved_metrics": list(result.retrieved_metrics),
                    "scores": result.scores,
                }
                for result in self.results
            ],
        }


def default_eval_cases_path() -> Path:
    return Path(__file__).resolve().parents[2] / "evals" / "metric_retrieval_cases.json"


def load_metric_retrieval_cases(
    path: str | Path | None = None,
) -> list[MetricRetrievalEvalCase]:
    case_path = Path(path) if path else default_eval_cases_path()
    raw_cases = json.loads(case_path.read_text(encoding="utf-8"))
    return [MetricRetrievalEvalCase.from_dict(item) for item in raw_cases]


def evaluate_case(case: MetricRetrievalEvalCase) -> MetricRetrievalEvalResult:
    result = get_metric_retriever().retrieve(case.question, min_score=case.min_score)
    retrieved_names = tuple(result.names)
    scores = {item.metric.name: item.score for item in result.metrics}
    errors: list[str] = []

    for metric_name in case.expected_metrics:
        if metric_name not in retrieved_names:
            errors.append(f"Expected metric not retrieved: {metric_name}")

    for metric_name in case.forbidden_metrics:
        if metric_name in retrieved_names:
            errors.append(f"Forbidden metric retrieved: {metric_name}")

    return MetricRetrievalEvalResult(
        case_id=case.id,
        passed=not errors,
        errors=tuple(errors),
        retrieved_metrics=retrieved_names,
        scores=scores,
    )


def run_metric_retrieval_evals(path: str | Path | None = None) -> MetricRetrievalEvalReport:
    cases = load_metric_retrieval_cases(path)
    results = tuple(evaluate_case(case) for case in cases)
    passed = sum(1 for result in results if result.passed)
    return MetricRetrievalEvalReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def main() -> NoReturn:
    report = run_metric_retrieval_evals()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
