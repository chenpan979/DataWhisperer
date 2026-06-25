from app.agents.context import DataAnalysisAgentState
from app.tools.schema_tool import build_schema_overview, schema_to_prompt


class SchemaLinkingAgent:
    """读取并压缩 schema，完成 Text-to-SQL 的 schema linking 前置步骤。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.schema = build_schema_overview(state.engine)
        state.schema_prompt = schema_to_prompt(state.schema)
        state.add_trace(
            "schema",
            "ok",
            f"SchemaLinkingAgent 读取 {state.schema['table_count']} 张表",
        )