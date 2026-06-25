from typing import Any

from sqlalchemy.engine import Engine

from app.agents.context import DataAnalysisAgentState
from app.core.llm import LLMClient
from app.tools.query_tool import execute_safe_query
from app.tools.sql_tool import GeneratedSQL, repair_sql


class ValidationExecutionAgent:
    """执行 SQL 安全校验、执行查询，并在失败时尝试一次修复。"""

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
) -> tuple[str, list[str], list[dict], GeneratedSQL, int]:
    """执行 SQL；失败时按 SQL-of-Thought 的纠错环节尝试修复一次。"""

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
        error_message = str(exc)
        trace.append(
            _trace_step(
                name="sql_repair",
                status="retry",
                detail=f"CorrectionAgent 收到执行失败原因：{error_message}",
            )
        )
        repaired = await repair_sql(
            question=question,
            schema_prompt=schema_prompt,
            metric_context=retrieval_context,
            failed_sql=generated.sql,
            error_message=error_message,
            llm=llm,
        )
        if not repaired:
            warnings.append("SQL 自动修复未返回可用结果，已保留首次失败信息。")
            raise
        if repaired.prompt_id and repaired.prompt_version:
            prompt_versions[repaired.prompt_id] = repaired.prompt_version
        safe_sql, columns, rows = execute_safe_query(
            engine,
            repaired.sql,
            max_rows,
            auto_limit_enabled=auto_limit_enabled,
        )
        trace.append(
            _trace_step(
                name="sql_repair",
                status="ok",
                detail=(
                    f"{repaired.explanation}"
                    f"（prompt={repaired.prompt_id}@{repaired.prompt_version}）"
                ),
            )
        )
        warnings.append("首次 SQL 执行失败，系统已自动修复并重新执行。")
        return safe_sql, columns, rows, repaired, 1


def _trace_step(*, name: str, status: str, detail: str | None = None):
    from app.models.query import TraceStep

    return TraceStep(name=name, status=status, detail=detail)