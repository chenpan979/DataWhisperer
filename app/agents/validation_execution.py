from typing import Any

from sqlalchemy.engine import Engine

from app.agents.context import DataAnalysisAgentState
from app.agents.sql_correction_plan import generate_sql_correction_plan
from app.agents.sql_repair import repair_sql
from app.core.llm import LLMClient
from app.tools.query_tool import execute_safe_query
from app.agents.sql_generation import GeneratedSQL


MAX_SQL_REPAIR_ATTEMPTS = 3
SQL_CORRECTION_PLAN_AGENT_KEY = "sql_correction_plan_agent"
SQL_REPAIR_AGENT_KEY = "sql_repair_agent"


class ValidationExecutionAgent:
    """执行 SQL 安全校验、查询执行，并在失败时最多修复三次。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        if state.generated_sql is None:
            raise ValueError("SQL generation must run before validation.")

        max_rows = state.security_policy.effective_limit(
            requested_max_rows=state.request.max_rows,
            system_max_rows=state.settings.max_query_rows,
        )
        if state.security_policy.audit_trace_enabled:
            state.add_trace(
                "security_policy",
                "ok",
                (
                    f"readonly=on, auto_limit={'on' if state.security_policy.auto_limit_enabled else 'off'}, "
                    f"limit={max_rows}, timeout={state.security_policy.query_timeout_seconds}s"
                ),
            )
        if not state.security_policy.auto_limit_enabled:
            state.warnings.append("工作空间已关闭自动补充 LIMIT，请确保生成的 SQL 自带安全 LIMIT。")

        (
            state.safe_sql,
            state.columns,
            state.rows,
            state.final_sql_result,
            state.repair_count,
        ) = await execute_with_optional_repair(
            engine=state.engine,
            llm=state.llm_for("sql_agent"),
            correction_plan_llm=state.llm_for(SQL_CORRECTION_PLAN_AGENT_KEY),
            repair_llm=state.llm_for(SQL_REPAIR_AGENT_KEY),
            correction_plan_model_detail=state.model_trace_detail(SQL_CORRECTION_PLAN_AGENT_KEY),
            repair_model_detail=state.model_trace_detail(SQL_REPAIR_AGENT_KEY),
            question=state.request.question,
            schema_prompt=state.schema_prompt,
            retrieval_context=state.retrieval_context,
            generated=state.generated_sql,
            max_rows=max_rows,
            auto_limit_enabled=state.security_policy.auto_limit_enabled,
            trace=state.trace,
            warnings=state.warnings,
            prompt_versions=state.prompt_versions,
        )
        state.add_trace("execute_sql", "ok", f"ValidationExecutionAgent 返回 {len(state.rows)} 行")


async def execute_with_optional_repair(
    *,
    engine: Engine,
    llm: LLMClient,
    question: str,
    schema_prompt: str,
    retrieval_context: str,
    generated: GeneratedSQL,
    max_rows: int,
    auto_limit_enabled: bool,
    trace: list[Any],
    warnings: list[str],
    prompt_versions: dict[str, str],
    correction_plan_llm: Any | None = None,
    repair_llm: Any | None = None,
    max_repair_attempts: int = MAX_SQL_REPAIR_ATTEMPTS,
    correction_plan_model_detail: str = "model=runtime-default",
    repair_model_detail: str = "model=runtime-default",
) -> tuple[str, list[str], list[dict], GeneratedSQL, int]:
    """执行 SQL；失败时按“诊断计划 -> 按计划重写 -> 再执行”循环修复。

    大模型只负责不确定的诊断和重写；每次重写后的 SQL 仍然必须经过
    ``execute_safe_query`` 的安全校验、LIMIT 处理和数据库执行。
    """

    try:
        safe_sql, columns, rows = execute_safe_query(
            engine,
            generated.sql,
            max_rows,
            auto_limit_enabled=auto_limit_enabled,
        )
        return safe_sql, columns, rows, generated, 0
    except Exception as exc:
        if generated.used_fallback:
            raise
        current_generated = generated
        current_error_message = str(exc)
        repair_history: list[dict[str, str]] = []
        last_exception: Exception = exc

    correction_llm = correction_plan_llm or llm
    rewrite_llm = repair_llm or llm
    attempts = max(1, max_repair_attempts)

    for attempt in range(1, attempts + 1):
        feedback = _format_repair_feedback(
            current_error_message=current_error_message,
            repair_history=repair_history,
        )
        trace.append(
            _trace_step(
                name="sql_repair",
                status="retry",
                detail=f"第 {attempt}/{attempts} 次修复启动：SQL 执行失败，原因：{current_error_message}",
            )
        )
        correction_plan = await generate_sql_correction_plan(
            question=question,
            schema_prompt=schema_prompt,
            metric_context=retrieval_context,
            failed_sql=current_generated.sql,
            error_message=feedback,
            llm=correction_llm,
        )
        if correction_plan.prompt_id and correction_plan.prompt_version:
            prompt_versions[correction_plan.prompt_id] = correction_plan.prompt_version
        trace.append(
            _trace_step(
                name="sql_correction_plan",
                status="ok",
                detail=(
                    f"SQLCorrectionPlanAgent 第 {attempt}/{attempts} 次诊断："
                    f"{correction_plan.to_trace_detail()}; {correction_plan_model_detail}"
                ),
            )
        )
        repaired = await repair_sql(
            question=question,
            schema_prompt=schema_prompt,
            metric_context=retrieval_context,
            failed_sql=current_generated.sql,
            error_message=feedback,
            correction_plan=correction_plan,
            llm=rewrite_llm,
        )
        if not repaired:
            warnings.append(f"第 {attempt} 次 SQL 自动修复未返回可用结果，已停止修复。")
            trace.append(
                _trace_step(
                    name="sql_repair",
                    status="error",
                    detail=f"SQLRepairAgent 第 {attempt}/{attempts} 次未返回可用 SQL；{repair_model_detail}",
                )
            )
            raise last_exception
        if repaired.prompt_id and repaired.prompt_version:
            prompt_versions[repaired.prompt_id] = repaired.prompt_version
        trace.append(
            _trace_step(
                name="sql_repair",
                status="retry",
                detail=(
                    f"SQLRepairAgent 第 {attempt}/{attempts} 次生成修复 SQL：{repaired.explanation}"
                    f"；{repair_model_detail}；prompt={repaired.prompt_id}@{repaired.prompt_version}"
                ),
            )
        )

        try:
            safe_sql, columns, rows = execute_safe_query(
                engine,
                repaired.sql,
                max_rows,
                auto_limit_enabled=auto_limit_enabled,
            )
        except Exception as repair_exc:
            current_error_message = str(repair_exc)
            last_exception = repair_exc
            repair_history.append(
                {
                    "attempt": str(attempt),
                    "failed_sql": repaired.sql,
                    "error_message": current_error_message,
                    "plan": correction_plan.to_trace_detail(),
                }
            )
            if attempt >= attempts:
                warnings.append(f"SQL 自动修复已尝试 {attempts} 次仍失败，已停止继续重写。")
                trace.append(
                    _trace_step(
                        name="sql_repair",
                        status="error",
                        detail=f"第 {attempt}/{attempts} 次修复 SQL 执行仍失败：{current_error_message}",
                    )
                )
                raise last_exception
            trace.append(
                _trace_step(
                    name="sql_repair",
                    status="retry",
                    detail=f"第 {attempt}/{attempts} 次修复 SQL 执行仍失败，将带着失败历史继续修复：{current_error_message}",
                )
            )
            current_generated = repaired
            continue

        trace.append(
            _trace_step(
                name="sql_repair",
                status="ok",
                detail=f"SQLRepairAgent 第 {attempt}/{attempts} 次修复成功并通过安全执行。",
            )
        )
        warnings.append(f"首次 SQL 执行失败，系统已自动修复 {attempt} 次并重新执行。")
        return safe_sql, columns, rows, repaired, attempt

    raise last_exception


def _format_repair_feedback(
    *,
    current_error_message: str,
    repair_history: list[dict[str, str]],
) -> str:
    lines = [f"当前失败原因：{current_error_message}"]
    if repair_history:
        lines.append("历史修复失败：")
        for item in repair_history:
            lines.append(
                f"- 第 {item['attempt']} 次修复 SQL 仍失败：{item['error_message']}；"
                f"上一轮计划：{item['plan']}；上一轮 SQL：{item['failed_sql']}"
            )
    return "\n".join(lines)


def _trace_step(*, name: str, status: str, detail: str | None = None):
    from app.models.query import TraceStep

    return TraceStep(name=name, status=status, detail=detail)