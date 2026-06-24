from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.llm import LLMClient
from app.models.query import QueryRequest, QueryResponse, TraceStep
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


class DataAnalysisOrchestrator:
    """DataWhisperer 第一阶段的主控编排器。

    你可以把它理解成 V1 版本的 Agent Harness：
    它本身不直接写 SQL、不直接画图、不直接拼接数据库结果，
    而是把多个职责单一的工具按固定流程串起来。

    当前流程是：
    用户问题 -> 读取数据库结构 -> 生成 SQL -> 校验并执行 SQL -> 生成图表 -> 生成分析结论。

    这样做的好处是 API 层保持很薄，后续要演进多智能体时，
    可以从这里把 SQL Agent、Chart Agent、Insight Agent 逐步拆出去。
    """

    def __init__(
        self,
        engine: Engine,
        llm: LLMClient,
        security_policy: QuerySecurityPolicy | None = None,
        knowledge_scope: RagKnowledgeScope | None = None,
        rag_retriever: RagDocumentRetriever | None = None,
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

    async def _execute_with_optional_repair(
        self,
        *,
        question: str,
        schema_prompt: str,
        metric_context: str,
        generated: GeneratedSQL,
        max_rows: int,
        trace: list[TraceStep],
        warnings: list[str],
        prompt_versions: dict[str, str],
        auto_limit_enabled: bool = True,
    ) -> tuple[str, list[str], list[dict], GeneratedSQL, int]:
        """执行 SQL；失败时尝试一次模型自修复。

        这一步是 V2 的关键增强：模型第一次生成 SQL 后，系统不再“一错就失败”，
        而是把安全校验错误或数据库执行错误反馈给修复 prompt，再重试一次。
        修复后的 SQL 仍然会走 execute_safe_query，所以安全边界没有变弱。
        """

        try:
            safe_sql, columns, rows = execute_safe_query(
                self.engine,
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
                TraceStep(
                    name="sql_repair",
                    status="retry",
                    detail=f"首次 SQL 执行失败，准备修复：{error_message}",
                )
            )
            repaired = await repair_sql(
                question=question,
                schema_prompt=schema_prompt,
                metric_context=metric_context,
                failed_sql=generated.sql,
                error_message=error_message,
                llm=self.llm,
            )
            if not repaired:
                warnings.append("SQL 自动修复未返回可用结果，已保留首次失败信息。")
                raise
            if repaired.prompt_id and repaired.prompt_version:
                prompt_versions[repaired.prompt_id] = repaired.prompt_version
            safe_sql, columns, rows = execute_safe_query(
                self.engine,
                repaired.sql,
                max_rows,
                auto_limit_enabled=auto_limit_enabled,
            )
            trace.append(
                TraceStep(
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


    def _retrieve_workspace_knowledge(self, question: str):
        """检索当前工作空间上传的知识库资料。

        未登录 demo 模式没有租户上下文，因此跳过这一步。登录后必须带 scope 检索，
        保证 Milvus 中不同租户、不同工作空间的知识片段不会互相串用。
        """

        if self.knowledge_scope is None:
            return empty_rag_document_result()
        retriever = self.rag_retriever or get_rag_document_retriever()
        return retriever.retrieve(question, scope=self.knowledge_scope)

    async def run(self, request: QueryRequest) -> QueryResponse:
        """执行一次完整的自然语言数据分析请求。"""

        trace: list[TraceStep] = []
        warnings: list[str] = []
        prompt_versions: dict[str, str] = {}

        # 第一步：读取数据库结构，并压缩成适合放进 prompt 的文本。
        # 大模型需要知道有哪些表、字段、外键关系，但不需要直接看到原始数据。
        schema = build_schema_overview(self.engine)
        schema_prompt = schema_to_prompt(schema)
        trace.append(TraceStep(name="schema", status="ok", detail=f"{schema['table_count']} tables"))

        # V3.0：检索业务指标口径，并注入 SQL 生成 prompt。
        # 这一步是 RAG 的基础形态：先从本地知识库找相关指标，再让模型带着口径写 SQL。
        metric_retrieval = get_metric_retriever().retrieve(request.question)
        trace.append(
            TraceStep(
                name="metric_retrieval",
                status="ok",
                detail=(
                    ", ".join(metric_retrieval.names)
                    if metric_retrieval.names
                    else "未命中业务指标口径"
                ),
            )
        )

        # V3.13.13：检索当前工作空间上传的知识库资料。
        # 这一步为后续 RAG Agent 打底：现在先把命中的知识片段注入 SQL prompt，
        # 后面拆多智能体时可以把它独立成专门的 RAG 检索 Agent。
        knowledge_retrieval = self._retrieve_workspace_knowledge(request.question)
        if self.knowledge_scope is not None:
            knowledge_detail = (
                ", ".join(knowledge_retrieval.sources)
                if knowledge_retrieval.sources
                else "未命中工作空间知识库"
            )
            trace.append(
                TraceStep(
                    name="knowledge_retrieval",
                    status="ok",
                    detail=f"{knowledge_detail}（{knowledge_retrieval.retrieval_mode}）",
                )
            )

        retrieval_context = _combine_retrieval_contexts(
            metric_context=metric_retrieval.prompt_context,
            knowledge_context=knowledge_retrieval.prompt_context,
        )

        # 第二步：生成 SQL。
        # 命中内置示例问题时优先走稳定规则；自由问题则交给大模型生成。
        # 这样既保证演示问题稳定，又保留真实 Text-to-SQL 能力。
        generated = await generate_sql(
            request.question,
            schema_prompt,
            self.llm,
            metric_context=retrieval_context,
        )
        if generated.used_fallback:
            warnings.append("当前 SQL 由本地演示规则生成，用于保证示例问题稳定可运行。")
        if generated.prompt_id and generated.prompt_version:
            prompt_versions[generated.prompt_id] = generated.prompt_version
        sql_trace_detail = generated.explanation
        if generated.prompt_id and generated.prompt_version:
            sql_trace_detail = (
                f"{generated.explanation}（prompt={generated.prompt_id}@{generated.prompt_version}）"
            )
        trace.append(TraceStep(name="generate_sql", status="ok", detail=sql_trace_detail))

        # 第三步：执行 SQL 前再次做安全校验和行数限制。
        # 不能只依赖提示词约束模型，真正的安全边界必须在服务端代码里。
        max_rows = self.security_policy.effective_limit(
            requested_max_rows=request.max_rows,
            system_max_rows=self.settings.max_query_rows,
        )
        if self.security_policy.audit_trace_enabled:
            trace.append(
                TraceStep(
                    name="security_policy",
                    status="ok",
                    detail=(
                        f"readonly=on, auto_limit={'on' if self.security_policy.auto_limit_enabled else 'off'}, "
                        f"limit={max_rows}, timeout={self.security_policy.query_timeout_seconds}s"
                    ),
                )
            )
        if not self.security_policy.auto_limit_enabled:
            warnings.append("工作空间已关闭自动补充 LIMIT，请确保生成的 SQL 自带安全 LIMIT。")
        safe_sql, columns, rows, final_sql_result, repair_count = (
            await self._execute_with_optional_repair(
                question=request.question,
                schema_prompt=schema_prompt,
                metric_context=retrieval_context,
                generated=generated,
                max_rows=max_rows,
                trace=trace,
                warnings=warnings,
                prompt_versions=prompt_versions,
                auto_limit_enabled=self.security_policy.auto_limit_enabled,
            )
        )
        trace.append(TraceStep(name="execute_sql", status="ok", detail=f"{len(rows)} rows"))

        # 第四步：根据真实查询结果生成图表配置。
        # 图表推荐先用确定性规则实现，比完全依赖模型更稳定。
        chart = recommend_chart(columns, rows, question=request.question)
        trace.append(TraceStep(name="chart", status="ok", detail=chart.get("type", "unknown")))

        # 第五步：基于查询结果生成业务结论。
        # 结论必须在 SQL 执行之后生成，避免模型脱离数据凭空分析。
        insight_result = await generate_insight(request.question, safe_sql, columns, rows, self.llm)
        if insight_result.prompt_id and insight_result.prompt_version:
            prompt_versions[insight_result.prompt_id] = insight_result.prompt_version
        insight_trace_detail = None
        if insight_result.prompt_id and insight_result.prompt_version:
            insight_trace_detail = (
                f"prompt={insight_result.prompt_id}@{insight_result.prompt_version}"
            )
        elif insight_result.used_fallback:
            insight_trace_detail = "使用本地兜底总结"
        trace.append(TraceStep(name="insight", status="ok", detail=insight_trace_detail))

        if not self.security_policy.audit_trace_enabled:
            trace = [
                TraceStep(
                    name="security_policy",
                    status="ok",
                    detail="工作空间安全策略已隐藏详细执行轨迹。",
                )
            ]

        return QueryResponse(
            question=request.question,
            generated_sql=safe_sql,
            sql_explanation=final_sql_result.explanation,
            columns=columns,
            rows=rows,
            chart=chart,
            insight=insight_result.content,
            warnings=warnings,
            trace_steps=trace,
            prompt_versions=prompt_versions,
            retrieved_metrics=metric_retrieval.names,
            retrieved_knowledge=knowledge_retrieval.sources,
            repair_count=repair_count,
        )

def _combine_retrieval_contexts(*, metric_context: str, knowledge_context: str) -> str:
    """合并内置指标口径和工作空间知识库上下文。"""

    sections = []
    if metric_context:
        sections.append("## 内置业务指标口径\n" + metric_context)
    if knowledge_context and knowledge_context != NO_KNOWLEDGE_CONTEXT:
        sections.append("## 工作空间知识库资料\n" + knowledge_context)
    return "\n\n".join(sections)
