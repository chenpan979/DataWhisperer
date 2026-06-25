from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from app.agents.charting import ChartAgent
from app.agents.context import DataAnalysisAgentState
from app.agents.insight import InsightAgent
from app.agents.knowledge_retrieval import KnowledgeRetrievalAgent
from app.agents.query_planning import QueryPlanningAgent
from app.agents.schema_linking import SchemaLinkingAgent
from app.agents.sql_generation import SQLGenerationAgent
from app.agents.validation_execution import ValidationExecutionAgent, execute_with_optional_repair
from app.core.config import get_settings
from app.core.llm import LLMClient
from app.models.query import QueryRequest, QueryResponse
from app.rag.document_retriever import RagDocumentRetriever, RagKnowledgeScope
from app.tools.security_policy import QuerySecurityPolicy, default_query_security_policy
from app.tools.sql_tool import GeneratedSQL


class DataAnalysisOrchestrator:
    """SQL-of-Thought 多智能体编排器。

    Orchestrator 只负责确定 Agent 执行顺序和共享状态，具体能力分别放在
    schema_linking、knowledge_retrieval、query_planning、sql_generation、
    validation_execution、charting、insight 等模块中，便于后续独立演进。
    """

    def __init__(
        self,
        engine: Engine,
        llm: LLMClient,
        security_policy: QuerySecurityPolicy | None = None,
        knowledge_scope: RagKnowledgeScope | None = None,
        rag_retriever: RagDocumentRetriever | None = None,
        agent_model_router: Any | None = None,
        agents: list[Any] | None = None,
    ):
        self.engine = engine
        self.llm = llm
        self.settings = get_settings()
        self.security_policy = security_policy or default_query_security_policy(
            system_max_rows=self.settings.max_query_rows,
            query_timeout_seconds=self.settings.query_timeout_seconds,
        )
        self.knowledge_scope = knowledge_scope
        self.rag_retriever = rag_retriever
        self.agent_model_router = agent_model_router
        self.agents = agents or [
            SchemaLinkingAgent(),
            KnowledgeRetrievalAgent(),
            QueryPlanningAgent(),
            SQLGenerationAgent(),
            ValidationExecutionAgent(),
            ChartAgent(),
            InsightAgent(),
        ]

    async def run(self, request: QueryRequest) -> QueryResponse:
        """执行一次完整的 SQL-of-Thought 多智能体查数流程。"""

        state = DataAnalysisAgentState(
            request=request,
            engine=self.engine,
            llm=self.llm,
            settings=self.settings,
            security_policy=self.security_policy,
            knowledge_scope=self.knowledge_scope,
            rag_retriever=self.rag_retriever,
            agent_model_router=self.agent_model_router,
        )
        for agent in self.agents:
            await agent.run(state)

        if state.final_sql_result is None or state.insight_result is None:
            raise ValueError("Agent pipeline finished without final SQL or insight result.")

        return QueryResponse(
            question=request.question,
            generated_sql=state.safe_sql,
            sql_explanation=state.final_sql_result.explanation,
            columns=state.columns,
            rows=state.rows,
            chart=state.chart,
            insight=state.insight_result.content,
            warnings=state.warnings,
            trace_steps=list(state.trace_for_response),
            prompt_versions=state.prompt_versions,
            retrieved_metrics=state.retrieved_metric_names,
            retrieved_knowledge=state.retrieved_knowledge_sources,
            repair_count=state.repair_count,
        )

    async def _execute_with_optional_repair(
        self,
        *,
        question: str,
        schema_prompt: str,
        metric_context: str,
        generated: GeneratedSQL,
        max_rows: int,
        trace: list[Any],
        warnings: list[str],
        prompt_versions: dict[str, str],
        auto_limit_enabled: bool = True,
    ) -> tuple[str, list[str], list[dict], GeneratedSQL, int]:
        """兼容旧测试和旧调用方的 SQL 执行/修复入口。"""

        return await execute_with_optional_repair(
            engine=self.engine,
            llm=self.llm,
            question=question,
            schema_prompt=schema_prompt,
            retrieval_context=metric_context,
            generated=generated,
            max_rows=max_rows,
            auto_limit_enabled=auto_limit_enabled,
            trace=trace,
            warnings=warnings,
            prompt_versions=prompt_versions,
        )