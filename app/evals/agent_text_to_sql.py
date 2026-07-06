from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from app.agents.orchestrator import DataAnalysisOrchestrator
from app.evals.text_to_sql import (
    TextToSqlEvalCase,
    TextToSqlEvalReport,
    TextToSqlEvalResult,
    build_text_to_sql_report,
)
from app.models.query import QueryRequest
from app.tools.sql_tool import ensure_limit


async def run_agent_text_to_sql_evals(
    cases: list[TextToSqlEvalCase],
    *,
    engine: Engine | None = None,
    llm: Any | None = None,
    orchestrator: Any | None = None,
    max_rows: int = 100,
) -> TextToSqlEvalReport:
    """通过真实多智能体链路运行 Text-to-SQL 评测。

    离线评测只校验本地兜底 SQL，适合快速回归；这个 Runner 会逐条调用
    DataAnalysisOrchestrator.run，也就是和 AI 查数页面一致的链路：
    schema linking、知识检索、SQL 规划、SQL 生成、安全执行、图表推荐和结论生成。
    """

    if orchestrator is None:
        if engine is None or llm is None:
            raise ValueError("agent evaluation requires an orchestrator or both engine and llm.")
        orchestrator = DataAnalysisOrchestrator(engine=engine, llm=llm)

    results: list[TextToSqlEvalResult] = []
    for case in cases:
        results.append(
            await evaluate_agent_case(case, orchestrator=orchestrator, max_rows=max_rows)
        )
    return build_text_to_sql_report(tuple(results))


async def evaluate_agent_case(
    case: TextToSqlEvalCase,
    *,
    orchestrator: Any,
    max_rows: int = 100,
) -> TextToSqlEvalResult:
    """用真实 Orchestrator 评测单条用例。"""

    try:
        response = await orchestrator.run(
            QueryRequest(question=case.question, max_rows=max_rows)
        )
    except Exception as exc:
        return TextToSqlEvalResult(
            case_id=case.id,
            passed=False,
            errors=(f"Agent runner failed: {exc}",),
            generated_sql="",
            chart_type="",
            difficulty=case.difficulty,
            requires_rag=case.requires_rag,
            tags=case.tags,
            ablation_tags=case.ablation_tags,
        )

    errors: list[str] = []
    generated_sql = response.generated_sql.strip()
    chart_type = str((response.chart or {}).get("type", ""))

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

    actual_columns = {column.lower() for column in response.columns}
    for expected_column in case.expected_columns:
        if expected_column.lower() not in actual_columns:
            errors.append(f"Missing expected result column: {expected_column}")

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
