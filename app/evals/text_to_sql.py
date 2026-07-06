from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from app.agents.sql_generation import fallback_sql
from app.tools.chart_tool import recommend_chart
from app.tools.sql_tool import ensure_limit

DIFFICULTY_ORDER = ("simple", "medium", "complex")


@dataclass(frozen=True)
class EvalBucketSummary:
    """??????????????RAG ??????????"""

    name: str
    total: int
    passed: int
    failed: int
    pass_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
        }


@dataclass(frozen=True)
class TextToSqlEvalCase:
    """?? Text-to-SQL ?????

    difficulty ???????????? SQL?requires_rag ? ablation_tags
    ??????? RAG?SQL-of-Thought??? Agent ??????
    """

    id: str
    question: str
    tags: tuple[str, ...]
    expected_sql_contains: tuple[str, ...]
    forbidden_sql_contains: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_chart_type: str
    must_be_safe: bool = True
    difficulty: str = "medium"
    requires_rag: bool = False
    ablation_tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextToSqlEvalCase":
        """? JSON ????????????????????????"""

        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            tags=tuple(_list_value(data.get("tags"))),
            expected_sql_contains=tuple(_list_value(data.get("expected_sql_contains"))),
            forbidden_sql_contains=tuple(_list_value(data.get("forbidden_sql_contains"))),
            expected_columns=tuple(_list_value(data.get("expected_columns"))),
            expected_chart_type=str(data.get("expected_chart_type", "")),
            must_be_safe=bool(data.get("must_be_safe", True)),
            difficulty=_normalize_difficulty(str(data.get("difficulty", "medium"))),
            requires_rag=bool(data.get("requires_rag", data.get("rag_required", False))),
            ablation_tags=tuple(
                _list_value(data.get("ablation_tags") or data.get("ablation") or [])
            ),
        )


@dataclass(frozen=True)
class TextToSqlEvalResult:
    """???????"""

    case_id: str
    passed: bool
    errors: tuple[str, ...]
    generated_sql: str
    chart_type: str
    difficulty: str
    requires_rag: bool
    tags: tuple[str, ...]
    ablation_tags: tuple[str, ...]


@dataclass(frozen=True)
class TextToSqlEvalReport:
    """?? Text-to-SQL ??????????"""

    total: int
    passed: int
    failed: int
    results: tuple[TextToSqlEvalResult, ...]
    difficulty_breakdown: tuple[EvalBucketSummary, ...]
    rag_breakdown: tuple[EvalBucketSummary, ...]
    ablation_breakdown: tuple[EvalBucketSummary, ...]

    @property
    def pass_rate(self) -> float:
        """??????"""

        if self.total == 0:
            return 0.0
        return round(self.passed / self.total, 4)

    def to_dict(self) -> dict[str, Any]:
        """??????????????????? API ???"""

        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "difficulty_breakdown": [item.to_dict() for item in self.difficulty_breakdown],
            "rag_breakdown": [item.to_dict() for item in self.rag_breakdown],
            "ablation_breakdown": [item.to_dict() for item in self.ablation_breakdown],
            "results": [
                {
                    "case_id": result.case_id,
                    "passed": result.passed,
                    "errors": list(result.errors),
                    "generated_sql": result.generated_sql,
                    "chart_type": result.chart_type,
                    "difficulty": result.difficulty,
                    "requires_rag": result.requires_rag,
                    "tags": list(result.tags),
                    "ablation_tags": list(result.ablation_tags),
                }
                for result in self.results
            ],
        }


def default_eval_cases_path() -> Path:
    """??????????"""

    return Path(__file__).resolve().parents[2] / "evals" / "text_to_sql_cases.json"


def load_eval_cases(path: str | Path | None = None) -> list[TextToSqlEvalCase]:
    """?? Text-to-SQL ??????? JSON ???JSON ??? JSONL?"""

    case_path = Path(path) if path else default_eval_cases_path()
    text = case_path.read_text(encoding="utf-8-sig")
    if case_path.suffix.casefold() == ".jsonl":
        raw_cases = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        raw_payload = json.loads(text)
        raw_cases = _extract_case_items(raw_payload)
    return [TextToSqlEvalCase.from_dict(item) for item in raw_cases]


def evaluate_case(case: TextToSqlEvalCase, max_rows: int = 100) -> TextToSqlEvalResult:
    """???????

    ?? runner ?????? fallback SQL ??????????
    ???????????????????????????????
    SQL ?????????????????????
    """

    errors: list[str] = []
    generated = fallback_sql(case.question)
    generated_sql = generated.sql.strip()

    if case.must_be_safe:
        try:
            ensure_limit(generated_sql, max_rows)
        except ValueError as exc:
            errors.append(f"SQL safety check failed: {exc}")

    lowered_sql = generated_sql.lower()
    for expected in case.expected_sql_contains:
        if expected.lower() not in lowered_sql:
            errors.append(f"SQL does not contain expected fragment: {expected}")

    for forbidden in case.forbidden_sql_contains:
        if forbidden.lower() in lowered_sql:
            errors.append(f"SQL contains forbidden fragment: {forbidden}")

    chart_type = ""
    if case.expected_columns or case.expected_chart_type:
        rows = [_sample_row_for_columns(case.expected_columns)]
        chart = recommend_chart(case.expected_columns, rows, question=case.question)
        chart_type = str(chart.get("type", ""))
    if case.expected_chart_type and chart_type != case.expected_chart_type:
        errors.append(
            f"Chart type mismatch: expected {case.expected_chart_type}, got {chart_type}"
        )

    return TextToSqlEvalResult(
        case_id=case.id,
        passed=not errors,
        errors=tuple(errors),
        generated_sql=generated_sql,
        chart_type=chart_type,
        difficulty=case.difficulty,
        requires_rag=case.requires_rag,
        tags=case.tags,
        ablation_tags=case.ablation_tags,
    )


def build_text_to_sql_report(
    results: tuple[TextToSqlEvalResult, ...]
) -> TextToSqlEvalReport:
    """?????????????API ?????????????????"""

    passed = sum(1 for result in results if result.passed)
    return TextToSqlEvalReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
        difficulty_breakdown=_summarize_difficulty(results),
        rag_breakdown=_summarize_rag(results),
        ablation_breakdown=_summarize_ablation(results),
    )


def run_text_to_sql_evals(path: str | Path | None = None) -> TextToSqlEvalReport:
    """???? Text-to-SQL ?????????????????"""

    cases = load_eval_cases(path)
    results = tuple(evaluate_case(case) for case in cases)
    return build_text_to_sql_report(results)


def _extract_case_items(raw: Any) -> list[dict[str, Any]]:
    """?? {cases: [...]}?{items: [...]}?{data: [...]} ??????"""

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("cases", "items", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw]
    raise ValueError("Text-to-SQL eval cases must be a JSON object, array, or JSONL file.")


def _summarize_difficulty(results: tuple[TextToSqlEvalResult, ...]) -> tuple[EvalBucketSummary, ...]:
    summaries = []
    for difficulty in DIFFICULTY_ORDER:
        bucket = [result for result in results if result.difficulty == difficulty]
        summaries.append(_bucket_summary(difficulty, bucket))
    return tuple(summaries)


def _summarize_rag(results: tuple[TextToSqlEvalResult, ...]) -> tuple[EvalBucketSummary, ...]:
    return (
        _bucket_summary("rag_required", [result for result in results if result.requires_rag]),
        _bucket_summary("no_rag_required", [result for result in results if not result.requires_rag]),
    )


def _summarize_ablation(results: tuple[TextToSqlEvalResult, ...]) -> tuple[EvalBucketSummary, ...]:
    names = sorted({tag for result in results for tag in result.ablation_tags})
    if not names:
        return ()
    return tuple(
        _bucket_summary(name, [result for result in results if name in result.ablation_tags])
        for name in names
    )


def _bucket_summary(name: str, bucket: list[TextToSqlEvalResult]) -> EvalBucketSummary:
    total = len(bucket)
    passed = sum(1 for result in bucket if result.passed)
    failed = total - passed
    pass_rate = round(passed / total, 4) if total else 0.0
    return EvalBucketSummary(
        name=name,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
    )


def _sample_row_for_columns(columns: tuple[str, ...]) -> dict[str, Any]:
    """????????????????"""

    row: dict[str, Any] = {}
    for index, column in enumerate(columns):
        if index == 0:
            row[column] = _sample_category_value(column)
        else:
            row[column] = 100
    return row


def _sample_category_value(column: str) -> str:
    """????????????????????"""

    lowered = column.lower()
    if "month" in lowered or "date" in lowered:
        return "2026-01"
    if "region" in lowered:
        return "East China"
    if "category" in lowered:
        return "Electronics"
    if "product" in lowered:
        return "Aurora Laptop"
    if "industry" in lowered:
        return "Retail"
    return "sample"


def _normalize_difficulty(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in DIFFICULTY_ORDER:
        return lowered
    if lowered in {"easy", "basic", "??"}:
        return "simple"
    if lowered in {"normal", "intermediate", "??"}:
        return "medium"
    if lowered in {"hard", "advanced", "??"}:
        return "complex"
    return "medium"


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            return _list_value(json.loads(text))
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.split("|") if part.strip()]


def main() -> NoReturn:
    """??????

    ???
        python -m app.evals.text_to_sql
    """

    report = run_text_to_sql_evals()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
