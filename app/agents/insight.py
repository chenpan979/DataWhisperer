from app.agents.context import DataAnalysisAgentState
from app.tools.insight_tool import generate_insight


class InsightAgent:
    """基于真实查询结果生成业务结论。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.insight_result = await generate_insight(
            state.request.question,
            state.safe_sql,
            state.columns,
            state.rows,
            state.llm_for("insight_agent"),
        )
        state.record_prompt_version(state.insight_result)
        if state.insight_result.prompt_id and state.insight_result.prompt_version:
            detail = f"prompt={state.insight_result.prompt_id}@{state.insight_result.prompt_version}"
        elif state.insight_result.used_fallback:
            detail = "使用本地兜底总结"
        else:
            detail = None
        model_detail = state.model_trace_detail("insight_agent")
        state.add_trace(
            "insight",
            "ok",
            f"InsightAgent: {detail}; {model_detail}" if detail else f"InsightAgent: {model_detail}",
        )