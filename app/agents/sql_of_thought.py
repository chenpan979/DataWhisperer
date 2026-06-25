"""SQL-of-Thought 多智能体兼容导出模块。

V4.1.1 之后，每个 Agent 已拆到独立文件中。本模块保留旧导入路径，
避免历史测试、脚本或外部调用方从 `app.agents.sql_of_thought` 导入时报错。
新代码建议直接从 `app.agents.orchestrator` 或具体 Agent 模块导入。
"""

from app.agents.charting import ChartAgent
from app.agents.context import DataAnalysisAgentState, SQLThoughtPlan
from app.agents.insight import InsightAgent
from app.agents.knowledge_retrieval import KnowledgeRetrievalAgent
from app.agents.orchestrator import DataAnalysisOrchestrator
from app.agents.query_planning import (
    QueryPlanningAgent,
    build_sql_thought_plan as _build_sql_thought_plan,
    pick_candidate_tables as _pick_candidate_tables,
)
from app.agents.retrieval_context import (
    append_plan_context as _append_plan_context,
    combine_retrieval_contexts as _combine_retrieval_contexts,
)
from app.agents.schema_linking import SchemaLinkingAgent
from app.agents.sql_generation import SQLGenerationAgent
from app.agents.validation_execution import (
    ValidationExecutionAgent,
    _trace_step,
    execute_safe_query,
    execute_with_optional_repair as _execute_with_optional_repair,
)
from app.tools.schema_tool import build_schema_overview, schema_to_prompt

__all__ = [
    "ChartAgent",
    "DataAnalysisAgentState",
    "DataAnalysisOrchestrator",
    "InsightAgent",
    "KnowledgeRetrievalAgent",
    "QueryPlanningAgent",
    "SQLGenerationAgent",
    "SQLThoughtPlan",
    "SchemaLinkingAgent",
    "ValidationExecutionAgent",
    "_append_plan_context",
    "_build_sql_thought_plan",
    "_combine_retrieval_contexts",
    "_execute_with_optional_repair",
    "_pick_candidate_tables",
    "_trace_step",
    "build_schema_overview",
    "execute_safe_query",
    "schema_to_prompt",
]