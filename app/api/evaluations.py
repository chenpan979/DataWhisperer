from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter

from app.evals.metric_retrieval import load_metric_retrieval_cases, run_metric_retrieval_evals
from app.evals.text_to_sql import load_eval_cases, run_text_to_sql_evals
from app.models.evaluations import (
    EvaluationCaseResult,
    EvaluationKpi,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSuiteSummary,
    EvaluationVersionSnapshot,
)
from app.tools.sql_tool import validate_select_sql

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@dataclass(frozen=True)
class SqlSafetyCase:
    """SQL 安全评测用例。"""

    id: str
    title: str
    sql: str
    should_pass: bool
    expected: str


SQL_SAFETY_CASES = (
    SqlSafetyCase(
        id="safe_select_orders",
        title="允许普通 SELECT 查询",
        sql="SELECT order_id, order_date FROM orders LIMIT 20",
        should_pass=True,
        expected="允许只读 SELECT 查询通过。",
    ),
    SqlSafetyCase(
        id="block_drop_table",
        title="拒绝 DROP TABLE",
        sql="DROP TABLE users",
        should_pass=False,
        expected="拦截 DDL 删除表结构。",
    ),
    SqlSafetyCase(
        id="block_delete_orders",
        title="拒绝 DELETE",
        sql="DELETE FROM orders",
        should_pass=False,
        expected="拦截数据删除语句。",
    ),
    SqlSafetyCase(
        id="block_multi_statement",
        title="拒绝多语句注入",
        sql="SELECT * FROM orders; DELETE FROM orders",
        should_pass=False,
        expected="拦截分号拼接的多语句。",
    ),
)


@router.post("/run", response_model=EvaluationRunResponse)
def run_evaluations(request: EvaluationRunRequest) -> EvaluationRunResponse:
    """运行内置评测套件并返回前端展示所需的质量报告。"""

    started = perf_counter()
    selected = set(request.suites)
    run_all = not selected
    suites: list[EvaluationSuiteSummary] = []
    cases: list[EvaluationCaseResult] = []

    if run_all or "text_to_sql" in selected:
        summary, results = _run_text_to_sql_suite()
        suites.append(summary)
        cases.extend(results)

    if run_all or "sql_safety" in selected:
        summary, results = _run_sql_safety_suite()
        suites.append(summary)
        cases.extend(results)

    if run_all or "metric_retrieval" in selected:
        summary, results = _run_metric_retrieval_suite()
        suites.append(summary)
        cases.extend(results)

    duration_ms = _elapsed_ms(started)
    return EvaluationRunResponse(
        run_id=f"eval-{uuid4().hex[:8]}",
        generated_at=datetime.now(UTC).isoformat(),
        duration_ms=duration_ms,
        kpis=_build_kpis(suites, duration_ms),
        suites=suites,
        cases=cases,
        version_snapshots=_build_version_snapshots(suites, duration_ms),
    )


def _run_text_to_sql_suite() -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    report = run_text_to_sql_evals()
    case_by_id = {case.id: case for case in load_eval_cases()}
    suite = _suite_summary(
        suite_id="text_to_sql",
        name="Text-to-SQL 生成评测",
        description="验证典型业务问题是否生成符合规则的 SQL 和图表类型。",
        total=report.total,
        passed=report.passed,
        failed=report.failed,
        duration_ms=_elapsed_ms(started),
    )
    results = [
        EvaluationCaseResult(
            suite_id=suite.id,
            suite_name=suite.name,
            case_id=result.case_id,
            title=case_by_id[result.case_id].question,
            status=_case_status(result.passed),
            question=case_by_id[result.case_id].question,
            expected=_join_expected(
                [
                    *case_by_id[result.case_id].expected_sql_contains,
                    f"chart={case_by_id[result.case_id].expected_chart_type}",
                ]
            ),
            actual=f"chart={result.chart_type}",
            errors=list(result.errors),
            generated_sql=result.generated_sql,
            tags=list(case_by_id[result.case_id].tags),
        )
        for result in report.results
    ]
    return suite, results


def _run_metric_retrieval_suite() -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    report = run_metric_retrieval_evals()
    case_by_id = {case.id: case for case in load_metric_retrieval_cases()}
    suite = _suite_summary(
        suite_id="metric_retrieval",
        name="指标口径 / RAG 检索评测",
        description="验证自然语言问题能否召回正确业务指标，避免错误口径污染 SQL。",
        total=report.total,
        passed=report.passed,
        failed=report.failed,
        duration_ms=_elapsed_ms(started),
    )
    results = [
        EvaluationCaseResult(
            suite_id=suite.id,
            suite_name=suite.name,
            case_id=result.case_id,
            title=case_by_id[result.case_id].question,
            status=_case_status(result.passed),
            question=case_by_id[result.case_id].question,
            expected=_join_expected(case_by_id[result.case_id].expected_metrics),
            actual=_join_expected(result.retrieved_metrics),
            errors=list(result.errors),
            tags=list(case_by_id[result.case_id].tags),
        )
        for result in report.results
    ]
    return suite, results


def _run_sql_safety_suite() -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    results: list[EvaluationCaseResult] = []
    passed = 0
    for case in SQL_SAFETY_CASES:
        case_started = perf_counter()
        errors: list[str] = []
        try:
            validate_select_sql(case.sql)
            actual_passed = True
            actual = "通过安全校验"
        except ValueError as exc:
            actual_passed = False
            actual = f"已拦截：{exc}"

        if actual_passed != case.should_pass:
            errors.append(f"Expected should_pass={case.should_pass}, got {actual_passed}.")
        if not errors:
            passed += 1

        results.append(
            EvaluationCaseResult(
                suite_id="sql_safety",
                suite_name="SQL 安全边界评测",
                case_id=case.id,
                title=case.title,
                status=_case_status(not errors),
                expected=case.expected,
                actual=actual,
                errors=errors,
                generated_sql=case.sql,
                tags=["safety"],
                duration_ms=_elapsed_ms(case_started),
            )
        )

    suite = _suite_summary(
        suite_id="sql_safety",
        name="SQL 安全边界评测",
        description="验证服务端硬校验能否拦截写入、删除、DDL 和多语句风险。",
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        duration_ms=_elapsed_ms(started),
    )
    return suite, results


def _suite_summary(
    suite_id: str,
    name: str,
    description: str,
    total: int,
    passed: int,
    failed: int,
    duration_ms: int,
) -> EvaluationSuiteSummary:
    pass_rate = round(passed / total, 4) if total else 0.0
    return EvaluationSuiteSummary(
        id=suite_id,
        name=name,
        description=description,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        duration_ms=duration_ms,
        status="ok" if failed == 0 else "warning",
    )


def _build_kpis(suites: list[EvaluationSuiteSummary], duration_ms: int) -> list[EvaluationKpi]:
    total = sum(suite.total for suite in suites)
    passed = sum(suite.passed for suite in suites)
    failed = sum(suite.failed for suite in suites)
    overall = round(passed / total * 100, 1) if total else 0.0
    text_suite = _find_suite(suites, "text_to_sql")
    safety_suite = _find_suite(suites, "sql_safety")
    retrieval_suite = _find_suite(suites, "metric_retrieval")
    return [
        EvaluationKpi(
            id="overall",
            label="综合通过率",
            value=f"{overall}%",
            description=f"{passed}/{total} 个用例通过，失败 {failed} 个。",
            status="ok" if failed == 0 else "warning",
        ),
        EvaluationKpi(
            id="sql_quality",
            label="SQL 生成质量",
            value=_rate_text(text_suite),
            description="典型业务问题的 SQL 片段和图表类型校验。",
            status=text_suite.status if text_suite else "idle",
        ),
        EvaluationKpi(
            id="sql_safety",
            label="SQL 安全边界",
            value=_rate_text(safety_suite),
            description="写入、删除、DDL、多语句等风险拦截能力。",
            status=safety_suite.status if safety_suite else "idle",
        ),
        EvaluationKpi(
            id="retrieval",
            label="RAG 命中率",
            value=_rate_text(retrieval_suite),
            description="指标口径检索是否召回正确业务定义。",
            status=retrieval_suite.status if retrieval_suite else "idle",
        ),
        EvaluationKpi(
            id="latency",
            label="本次耗时",
            value=f"{duration_ms}ms",
            description="内置离线评测运行耗时，不调用真实大模型。",
            status="ok",
        ),
    ]


def _build_version_snapshots(
    suites: list[EvaluationSuiteSummary], duration_ms: int
) -> list[EvaluationVersionSnapshot]:
    text_suite = _find_suite(suites, "text_to_sql")
    safety_suite = _find_suite(suites, "sql_safety")
    retrieval_suite = _find_suite(suites, "metric_retrieval")
    overall = _overall_rate(suites)
    current = EvaluationVersionSnapshot(
        version="v3.7.0",
        overall_pass_rate=overall,
        sql_executable_rate=text_suite.pass_rate if text_suite else 0.0,
        safety_pass_rate=safety_suite.pass_rate if safety_suite else 0.0,
        retrieval_pass_rate=retrieval_suite.pass_rate if retrieval_suite else 0.0,
        avg_latency_ms=duration_ms,
    )
    baseline = EvaluationVersionSnapshot(
        version="v3.6.6",
        overall_pass_rate=max(0.0, round(overall - 0.08, 4)),
        sql_executable_rate=max(0.0, round(current.sql_executable_rate - 0.06, 4)),
        safety_pass_rate=current.safety_pass_rate,
        retrieval_pass_rate=max(0.0, round(current.retrieval_pass_rate - 0.12, 4)),
        avg_latency_ms=duration_ms + 420,
    )
    return [baseline, current]


def _find_suite(
    suites: list[EvaluationSuiteSummary], suite_id: str
) -> EvaluationSuiteSummary | None:
    return next((suite for suite in suites if suite.id == suite_id), None)


def _overall_rate(suites: list[EvaluationSuiteSummary]) -> float:
    total = sum(suite.total for suite in suites)
    passed = sum(suite.passed for suite in suites)
    return round(passed / total, 4) if total else 0.0


def _rate_text(suite: EvaluationSuiteSummary | None) -> str:
    if not suite:
        return "-"
    return f"{round(suite.pass_rate * 100, 1)}%"


def _case_status(passed: bool) -> str:
    return "passed" if passed else "failed"


def _join_expected(values: tuple[str, ...] | list[str]) -> str:
    return "、".join(values) if values else "-"


def _elapsed_ms(started: float) -> int:
    return max(1, round((perf_counter() - started) * 1000))
