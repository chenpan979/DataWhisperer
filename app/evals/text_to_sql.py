from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from typing import Any

from app.tools.chart_tool import recommend_chart
from app.tools.sql_tool import ensure_limit, fallback_sql


@dataclass(frozen=True)
class TextToSqlEvalCase:
    """单条 Text-to-SQL 评测用例。"""

    id: str
    question: str
    tags: tuple[str, ...]
    expected_sql_contains: tuple[str, ...]
    forbidden_sql_contains: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_chart_type: str
    must_be_safe: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextToSqlEvalCase":
        """从 JSON 字典构造评测用例。"""

        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            tags=tuple(data.get("tags", [])),
            expected_sql_contains=tuple(data.get("expected_sql_contains", [])),
            forbidden_sql_contains=tuple(data.get("forbidden_sql_contains", [])),
            expected_columns=tuple(data.get("expected_columns", [])),
            expected_chart_type=str(data.get("expected_chart_type", "")),
            must_be_safe=bool(data.get("must_be_safe", True)),
        )


@dataclass(frozen=True)
class TextToSqlEvalResult:
    """单条评测结果。"""

    case_id: str
    passed: bool
    errors: tuple[str, ...]
    generated_sql: str
    chart_type: str


@dataclass(frozen=True)
class TextToSqlEvalReport:
    """一组评测用例的汇总结果。"""

    total: int
    passed: int
    failed: int
    results: tuple[TextToSqlEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        """通过率。"""

        if self.total == 0:
            return 0.0
        return round(self.passed / self.total, 4)

    def to_dict(self) -> dict[str, Any]:
        """转换成可序列化字典，方便后续写入报告文件或 API 返回。"""

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
                    "generated_sql": result.generated_sql,
                    "chart_type": result.chart_type,
                }
                for result in self.results
            ],
        }


def default_eval_cases_path() -> Path:
    """返回默认评测集路径。"""

    return Path(__file__).resolve().parents[2] / "evals" / "text_to_sql_cases.json"


def load_eval_cases(path: str | Path | None = None) -> list[TextToSqlEvalCase]:
    """读取 Text-to-SQL 评测用例。"""

    case_path = Path(path) if path else default_eval_cases_path()
    raw_cases = json.loads(case_path.read_text(encoding="utf-8"))
    return [TextToSqlEvalCase.from_dict(item) for item in raw_cases]


def evaluate_case(case: TextToSqlEvalCase, max_rows: int = 100) -> TextToSqlEvalResult:
    """评测单个用例。

    当前 runner 使用项目内置 fallback SQL 作为被测 SQL 生成器。
    这样可以在不启动数据库、不调用真实大模型的情况下验证：
    SQL 安全规则、典型问题覆盖、字段约定和图表推荐是否稳定。
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
    )


def run_text_to_sql_evals(path: str | Path | None = None) -> TextToSqlEvalReport:
    """运行完整 Text-to-SQL 评测集。"""

    cases = load_eval_cases(path)
    results = tuple(evaluate_case(case) for case in cases)
    passed = sum(1 for result in results if result.passed)
    return TextToSqlEvalReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def _sample_row_for_columns(columns: tuple[str, ...]) -> dict[str, Any]:
    """为图表推荐构造一行最小样例数据。"""

    row: dict[str, Any] = {}
    for index, column in enumerate(columns):
        if index == 0:
            row[column] = _sample_category_value(column)
        else:
            row[column] = 100
    return row


def _sample_category_value(column: str) -> str:
    """根据字段名给出适合图表推荐的样例分类值。"""

    lowered = column.lower()
    if "month" in lowered or "date" in lowered:
        return "2026-01"
    if "region" in lowered:
        return "East China"
    if "category" in lowered:
        return "Electronics"
    if "product" in lowered:
        return "Aurora Laptop"
    return "sample"


def main() -> NoReturn:
    """命令行入口。

    用法：
        python -m app.evals.text_to_sql
    """

    report = run_text_to_sql_evals()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
