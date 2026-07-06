from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.context import DataAnalysisAgentState, SQLThoughtPlan
from app.agents.retrieval_context import append_plan_context
from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, get_prompt_registry


@dataclass
class GeneratedQueryPlan:
    """Query planning result produced by QueryPlanningAgent.

    The plan itself is injected into the SQL generation prompt. The prompt fields
    are kept for traceability so evaluation can compare model-driven planning
    with rule-based fallback planning later.
    """

    plan: SQLThoughtPlan
    used_fallback: bool = False
    prompt_id: str | None = None
    prompt_version: str | None = None


class QueryPlanningAgent:
    """Generate a SQL-of-Thought query plan before SQL generation.

    This Agent is intentionally model-driven because it is responsible for
    understanding the business question, selecting candidate tables, and turning
    the question into an executable analysis route. If the configured model is
    unavailable, it falls back to a conservative rule-based planner so demos and
    offline tests can still run.
    """

    async def run(self, state: DataAnalysisAgentState) -> None:
        generated = await generate_query_plan(
            question=state.request.question,
            schema=state.schema or {},
            schema_prompt=state.schema_prompt,
            retrieval_context=state.retrieval_context,
            llm=state.llm_for("query_planning_agent"),
            metric_names=state.retrieved_metric_names,
            knowledge_sources=state.retrieved_knowledge_sources,
        )
        state.query_plan = generated.plan
        state.retrieval_context = append_plan_context(
            state.retrieval_context,
            state.query_plan.to_prompt_context(),
        )
        if generated.prompt_id and generated.prompt_version:
            state.prompt_versions[generated.prompt_id] = generated.prompt_version

        mode = "规则兜底" if generated.used_fallback else "LLM 推理"
        state.add_trace(
            "query_planning",
            "ok",
            f"QueryPlanningAgent({mode}): {state.query_plan.summary}; "
            f"{state.model_trace_detail('query_planning_agent')}",
        )


async def generate_query_plan(
    *,
    question: str,
    schema: dict[str, Any],
    schema_prompt: str,
    retrieval_context: str,
    llm: Any,
    metric_names: tuple[str, ...] | list[str] = (),
    knowledge_sources: tuple[str, ...] | list[str] = (),
    prompt_registry: PromptRegistry | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> GeneratedQueryPlan:
    """Ask the model to create a structured SQL-of-Thought plan.

    The model does not generate SQL here. It only returns a compact JSON plan,
    which keeps responsibilities separate: QueryPlanningAgent decides the route,
    SQLGenerationAgent writes SQL, and ValidationExecutionAgent checks safety.
    """

    registry = prompt_registry or get_prompt_registry()
    rendered_prompt = registry.render_messages(
        "query_planning",
        version=prompt_version,
        variables={
            "schema_prompt": schema_prompt,
            "retrieval_context": retrieval_context or "未检索到额外指标或知识库上下文。",
            "question": question,
        },
    )
    try:
        payload = await llm.complete_json(rendered_prompt.messages)
        plan = _plan_from_payload(payload=payload, schema=schema, question=question)
    except Exception:
        plan = None

    if plan is not None:
        return GeneratedQueryPlan(
            plan=plan,
            prompt_id=rendered_prompt.prompt_id,
            prompt_version=rendered_prompt.version,
        )

    return GeneratedQueryPlan(
        plan=build_rule_based_sql_thought_plan(
            schema=schema,
            question=question,
            metric_names=metric_names,
            knowledge_sources=knowledge_sources,
        ),
        used_fallback=True,
    )


def build_sql_thought_plan(state: DataAnalysisAgentState) -> SQLThoughtPlan:
    """Backward-compatible wrapper for older tests and callers."""

    return build_rule_based_sql_thought_plan(
        schema=state.schema or {},
        question=state.request.question,
        metric_names=state.retrieved_metric_names,
        knowledge_sources=state.retrieved_knowledge_sources,
    )


def build_rule_based_sql_thought_plan(
    *,
    schema: dict[str, Any],
    question: str,
    metric_names: tuple[str, ...] | list[str] = (),
    knowledge_sources: tuple[str, ...] | list[str] = (),
) -> SQLThoughtPlan:
    """Create a conservative fallback plan when the LLM planner is unavailable."""

    candidate_tables = pick_candidate_tables(schema or {}, question)
    metric_hint = ", ".join(metric_names) or "无明确指标命中"
    knowledge_hint = ", ".join(knowledge_sources) or "无工作空间知识命中"
    return SQLThoughtPlan(
        objective=question,
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


def _plan_from_payload(
    *,
    payload: Any,
    schema: dict[str, Any],
    question: str,
) -> SQLThoughtPlan | None:
    if not isinstance(payload, dict):
        return None

    available_tables = {
        str(table.get("name", "")).strip()
        for table in (schema or {}).get("tables", [])
        if str(table.get("name", "")).strip()
    }
    raw_tables = payload.get("candidate_tables") or []
    if not isinstance(raw_tables, list | tuple):
        raw_tables = []
    candidate_tables = tuple(
        table
        for table in (str(item).strip() for item in raw_tables)
        if table and (not available_tables or table in available_tables)
    )
    if not candidate_tables:
        candidate_tables = tuple(pick_candidate_tables(schema or {}, question))

    steps = _string_tuple(payload.get("steps"))
    if not steps:
        return None

    checks = _string_tuple(payload.get("checks")) or (
        "只允许 SELECT/WITH，不允许写入、DDL、多语句和危险函数。",
        "字段必须来自 schema，JOIN 条件优先使用主外键。",
    )
    objective = str(payload.get("objective") or question).strip() or question
    return SQLThoughtPlan(
        objective=objective,
        candidate_tables=candidate_tables,
        steps=steps,
        checks=checks,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in (str(item).strip() for item in value) if item)


def pick_candidate_tables(schema: dict[str, Any], question: str, *, limit: int = 5) -> list[str]:
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