from typing import Any

from app.agents.context import DataAnalysisAgentState, SQLThoughtPlan
from app.agents.retrieval_context import append_plan_context


class QueryPlanningAgent:
    """生成 SQL-of-Thought 查询计划。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.query_plan = build_sql_thought_plan(state)
        state.retrieval_context = append_plan_context(
            state.retrieval_context,
            state.query_plan.to_prompt_context(),
        )
        state.add_trace("query_planning", "ok", state.query_plan.summary)


def build_sql_thought_plan(state: DataAnalysisAgentState) -> SQLThoughtPlan:
    """根据问题、schema 和检索结果生成轻量查询计划。"""

    candidate_tables = pick_candidate_tables(state.schema or {}, state.request.question)
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