from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from app.agents.context import DataAnalysisAgentState, SQLThoughtPlan
from app.core.config import get_settings
from app.core.llm import LLMClient
from app.models.query import QueryRequest, QueryResponse
from app.rag.document_retriever import (
    NO_KNOWLEDGE_CONTEXT,
    RagDocumentRetriever,
    RagKnowledgeScope,
    empty_rag_document_result,
    get_rag_document_retriever,
)
from app.rag.metric_retriever import get_metric_retriever
from app.tools.chart_tool import recommend_chart
from app.tools.insight_tool import generate_insight
from app.tools.query_tool import execute_safe_query
from app.tools.security_policy import QuerySecurityPolicy, default_query_security_policy
from app.tools.schema_tool import build_schema_overview, schema_to_prompt
from app.tools.sql_tool import GeneratedSQL, generate_sql, repair_sql


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


class KnowledgeRetrievalAgent:
    """检索内置指标口径和当前工作空间知识库资料。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.metric_retrieval = get_metric_retriever().retrieve(state.request.question)
        metric_detail = (
            ", ".join(state.metric_retrieval.names)
            if state.metric_retrieval.names
            else "未命中业务指标口径"
        )
        state.add_trace("metric_retrieval", "ok", f"KnowledgeAgent 指标口径：{metric_detail}")

        if state.knowledge_scope is None:
            state.knowledge_retrieval = empty_rag_document_result()
        else:
            retriever = state.rag_retriever or get_rag_document_retriever()
            state.knowledge_retrieval = retriever.retrieve(
                state.request.question,
                scope=state.knowledge_scope,
            )
            knowledge_detail = (
                ", ".join(state.knowledge_retrieval.sources)
                if state.knowledge_retrieval.sources
                else "未命中工作空间知识库"
            )
            state.add_trace(
                "knowledge_retrieval",
                "ok",
                f"KnowledgeAgent 工作空间知识库：{knowledge_detail}（{state.knowledge_retrieval.retrieval_mode}）",
            )

        state.retrieval_context = _combine_retrieval_contexts(
            metric_context=state.metric_retrieval.prompt_context,
            knowledge_context=state.knowledge_retrieval.prompt_context,
        )


class QueryPlanningAgent:
    """生成 SQL-of-Thought 查询计划。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.query_plan = _build_sql_thought_plan(state)
        state.retrieval_context = _append_plan_context(
            state.retrieval_context,
            state.query_plan.to_prompt_context(),
        )
        state.add_trace("query_planning", "ok", state.query_plan.summary)


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
        ) = await _execute_with_optional_repair(
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


class ChartAgent:
    """基于查询结果推荐图表。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.chart = recommend_chart(state.columns, state.rows, question=state.request.question)
        state.add_trace(
            "chart",
            "ok",
            f"ChartAgent: {state.chart.get('type', 'unknown')}; {state.model_trace_detail('chart_agent')}",
        )


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


class DataAnalysisOrchestrator:
    """V4.0 SQL-of-Thought 多智能体编排器。

    这一版仍然保持单库 Text-to-SQL，但把原来的单主控流程拆成多个职责明确的 Agent。
    后续多库路由、MCP 工具调用和多智能体评测都可以继续挂在这条链路上。
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

        return await _execute_with_optional_repair(
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


async def _execute_with_optional_repair(
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


def _build_sql_thought_plan(state: DataAnalysisAgentState) -> SQLThoughtPlan:
    """根据问题、schema 和检索结果生成轻量查询计划。"""

    candidate_tables = _pick_candidate_tables(state.schema or {}, state.request.question)
    metric_hint = ", ".join(state.retrieved_metric_names) or "无明确指标命中"
    knowledge_hint = ", ".join(state.retrieved_knowledge_sources) or "无工作空间知识命中"
    return SQLThoughtPlan(
        objective=state.request.question,
        candidate_tables=tuple(candidate_tables),
        steps=(
            f"结合用户问题识别指标和筛选条件，指标提示：{metric_hint}。",
            f"根据 Schema Linking 在候选表中选择字段和 JOIN 路径，知识库提示：{knowledge_hint}。",
            "生成一条 MySQL 只读 SELECT/WITH 查询，必要时使用聚合、排序和 LIMIT。",
            "执行前通过安全策略、语法结构和行数限制校验。",
        ),
        checks=(
            "只允许 SELECT/WITH，不允许写入、DDL、多语句和危险函数。",
            "字段必须来自 schema；JOIN 条件应优先使用主外键。",
            "聚合查询要检查 GROUP BY、排序方向和时间范围。",
        ),
    )


def _pick_candidate_tables(schema: dict[str, Any], question: str, *, limit: int = 5) -> list[str]:
    """用轻量规则预选候选表，避免 planner 完全空转。"""

    lowered_question = question.casefold()
    scored: list[tuple[int, str]] = []
    for table in schema.get("tables", []):
        table_name = str(table.get("name", ""))
        score = 0
        if table_name.casefold() in lowered_question:
            score += 6
        for column in table.get("columns", []):
            column_name = str(column.get("name", ""))
            if column_name.casefold() in lowered_question:
                score += 3
            score += _business_keyword_score(column_name, lowered_question)
        score += _business_keyword_score(table_name, lowered_question)
        if score > 0:
            scored.append((score, table_name))
    if not scored:
        return [str(table.get("name", "")) for table in schema.get("tables", [])[:limit]]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:limit]]


def _business_keyword_score(name: str, lowered_question: str) -> int:
    mapping = {
        "order": ("订单", "销售", "销量", "金额"),
        "item": ("明细", "商品", "销量", "金额"),
        "product": ("商品", "品类", "产品"),
        "region": ("地区", "区域", "华东", "华北", "华南", "西部"),
        "customer": ("客户", "用户", "行业"),
        "date": ("月", "季度", "年份", "趋势", "时间"),
        "amount": ("金额", "销售额", "gmv", "客单价"),
        "price": ("价格", "金额", "客单价"),
        "quantity": ("数量", "销量", "订单数"),
        "category": ("品类", "分类", "占比"),
    }
    lowered_name = name.casefold()
    score = 0
    for token, words in mapping.items():
        if token in lowered_name and any(word.casefold() in lowered_question for word in words):
            score += 2
    return score


def _combine_retrieval_contexts(*, metric_context: str, knowledge_context: str) -> str:
    """合并内置指标口径和工作空间知识库上下文。"""

    sections = []
    if metric_context:
        sections.append("## 内置业务指标口径\n" + metric_context)
    if knowledge_context and knowledge_context != NO_KNOWLEDGE_CONTEXT:
        sections.append("## 工作空间知识库资料\n" + knowledge_context)
    return "\n\n".join(sections)


def _append_plan_context(context: str, plan_context: str) -> str:
    if not context:
        return plan_context
    return context + "\n\n" + plan_context


def _trace_step(*, name: str, status: str, detail: str | None = None):
    from app.models.query import TraceStep

    return TraceStep(name=name, status=status, detail=detail)
