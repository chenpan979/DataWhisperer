from app.agents.context import DataAnalysisAgentState
from app.tools.sql_tool import generate_sql


class SQLGenerationAgent:
    """根据 schema、RAG 上下文和查询计划生成 SQL。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.generated_sql = await generate_sql(
            state.request.question,
            state.schema_prompt,
            state.llm_for("sql_agent"),
            metric_context=state.retrieval_context,
        )
        if state.generated_sql.used_fallback:
            state.warnings.append("当前 SQL 由本地演示规则生成，用于保证示例问题稳定可运行。")
        state.record_prompt_version(state.generated_sql)
        detail = state.generated_sql.explanation
        if state.generated_sql.prompt_id and state.generated_sql.prompt_version:
            detail = f"{detail}（prompt={state.generated_sql.prompt_id}@{state.generated_sql.prompt_version}）"
        state.add_trace(
            "generate_sql",
            "ok",
            f"SQLGenerationAgent: {detail}; {state.model_trace_detail('sql_agent')}",
        )