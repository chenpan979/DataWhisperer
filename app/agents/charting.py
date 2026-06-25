from app.agents.context import DataAnalysisAgentState
from app.tools.chart_tool import recommend_chart


class ChartAgent:
    """基于查询结果推荐图表。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.chart = recommend_chart(state.columns, state.rows, question=state.request.question)
        state.add_trace(
            "chart",
            "ok",
            f"ChartAgent: {state.chart.get('type', 'unknown')}; {state.model_trace_detail('chart_agent')}",
        )