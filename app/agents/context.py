from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.core.llm import LLMClient
from app.models.query import QueryRequest, TraceStep
from app.rag.document_retriever import (
    RagDocumentRetriever,
    RagDocumentRetrievalResult,
    RagKnowledgeScope,
)
from app.rag.metric_retriever import MetricRetrievalResult
from app.tools.agent_model_router import AgentModelRouter
from app.tools.insight_tool import GeneratedInsight
from app.tools.security_policy import QuerySecurityPolicy
from app.tools.sql_tool import GeneratedSQL


@dataclass(frozen=True)
class SQLThoughtPlan:
    """SQL-of-Thought 查询计划。

    这不是给用户展示的长推理链，而是给 SQL 生成 Agent 使用的结构化计划摘要。
    它把自然语言问题先整理成目标、候选表、执行步骤和校验点，
    让后续 SQL 生成不再直接从原问题跳到 SQL。
    """

    objective: str
    candidate_tables: tuple[str, ...]
    steps: tuple[str, ...]
    checks: tuple[str, ...]

    @property
    def summary(self) -> str:
        tables = ", ".join(self.candidate_tables) if self.candidate_tables else "待模型根据 schema 判断"
        return f"候选表：{tables}；步骤数：{len(self.steps)}"

    def to_prompt_context(self) -> str:
        """转换为可注入 SQL 生成 prompt 的计划文本。"""

        lines = [
            "## SQL-of-Thought 查询计划",
            f"目标：{self.objective}",
            "候选表：" + (", ".join(self.candidate_tables) if self.candidate_tables else "未预判"),
            "执行步骤：",
        ]
        lines.extend(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))
        lines.append("校验要点：")
        lines.extend(f"- {item}" for item in self.checks)
        return "\n".join(lines)


@dataclass
class DataAnalysisAgentState:
    """一次 AI 查数请求在多智能体链路中的共享状态。

    Agent 之间不互相调用对方的私有方法，而是通过这个 state 读写中间结果。
    这样后续拆成真正的异步 Agent、工作流引擎或 MCP Tool 时，边界会更清楚。
    """

    request: QueryRequest
    engine: Engine
    llm: LLMClient
    settings: Settings
    security_policy: QuerySecurityPolicy
    knowledge_scope: RagKnowledgeScope | None = None
    rag_retriever: RagDocumentRetriever | None = None
    agent_model_router: AgentModelRouter | None = None
    trace: list[TraceStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)

    schema: dict[str, Any] | None = None
    schema_prompt: str = ""
    metric_retrieval: MetricRetrievalResult | None = None
    knowledge_retrieval: RagDocumentRetrievalResult | None = None
    retrieval_context: str = ""
    query_plan: SQLThoughtPlan | None = None

    generated_sql: GeneratedSQL | None = None
    final_sql_result: GeneratedSQL | None = None
    safe_sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    repair_count: int = 0

    chart: dict[str, Any] = field(default_factory=dict)
    insight_result: GeneratedInsight | None = None

    def add_trace(self, name: str, status: str, detail: str | None = None) -> None:
        """追加一个可观测步骤。"""

        self.trace.append(TraceStep(name=name, status=status, detail=detail))

    def record_prompt_version(self, result: GeneratedSQL | GeneratedInsight | None) -> None:
        """记录某个 Agent 使用的 prompt 版本。"""

        if result and result.prompt_id and result.prompt_version:
            self.prompt_versions[result.prompt_id] = result.prompt_version

    def llm_for(self, agent_key: str) -> LLMClient:
        """按 Agent key 读取当前工作空间绑定的模型客户端。"""

        if self.agent_model_router is None:
            return self.llm
        return self.agent_model_router.client_for(agent_key)

    def model_trace_detail(self, agent_key: str) -> str:
        """返回可写入执行轨迹的模型绑定摘要。"""

        if self.agent_model_router is None:
            return "model=runtime-default"
        return self.agent_model_router.trace_detail(agent_key)

    @property
    def retrieved_metric_names(self) -> list[str]:
        if self.metric_retrieval is None:
            return []
        return self.metric_retrieval.names

    @property
    def retrieved_knowledge_sources(self) -> list[str]:
        if self.knowledge_retrieval is None:
            return []
        return self.knowledge_retrieval.sources

    @property
    def trace_for_response(self) -> Sequence[TraceStep]:
        """根据安全策略决定是否返回完整执行轨迹。"""

        if self.security_policy.audit_trace_enabled:
            return self.trace
        return [
            TraceStep(
                name="security_policy",
                status="ok",
                detail="工作空间安全策略已隐藏详细执行轨迹。",
            )
        ]
