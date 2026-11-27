from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any

from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, get_prompt_registry

if TYPE_CHECKING:
    from app.agents.context import DataAnalysisAgentState


# 中文意图关键词使用 Unicode 转义，避免 Windows 终端或 Git 编码不一致导致乱码。
CN_EAST_CHINA = "\u534e\u4e1c"
CN_TOP_THREE = "\u524d\u4e09"
CN_SALES_VOLUME = "\u9500\u91cf"
CN_MONTH = "\u6708"
CN_CATEGORY_SHARE = "\u5360\u6bd4"
CN_AVG_ORDER_VALUE = "\u5ba2\u5355\u4ef7"
CN_DECLINE = "\u4e0b\u6ed1"
CN_REGION = "\u5730\u533a"
CN_ORDER = "\u8ba2\u5355"
CN_COUNT = "\u6570\u91cf"
CN_INDUSTRY = "\u884c\u4e1a"
CN_CUSTOMER = "\u5ba2\u6237"


@dataclass
class GeneratedSQL:
    """SQL 生成结果。

    used_fallback 用于标记 SQL 是否来自本地演示规则，方便前端展示提示。
    """

    sql: str
    explanation: str
    used_fallback: bool = False
    prompt_id: str | None = None
    prompt_version: str | None = None


class SQLGenerationError(RuntimeError):
    """A SQL generation failure safe to display without provider response details."""


async def generate_sql(
    question: str,
    schema_prompt: str,
    llm: Any,
    metric_context: str = "未检索到相关业务指标口径。",
    prompt_registry: PromptRegistry | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    *,
    allow_demo_fallback: bool = False,
) -> GeneratedSQL:
    """根据自然语言问题和 schema 上下文生成 MySQL SQL。"""

    registry = prompt_registry or get_prompt_registry()
    rendered_prompt = registry.render_messages(
        "sql_generation",
        version=prompt_version,
        variables={
            "schema_prompt": schema_prompt,
            "metric_context": metric_context,
            "question": question,
        },
    )
    try:
        payload = await llm.complete_json(rendered_prompt.messages)
    except JSONDecodeError:
        failure = "模型回复不是有效的 JSON。"
    except APITimeoutError:
        failure = "模型请求超时。请检查中转站是否可用。"
    except APIConnectionError:
        failure = "无法连接模型服务。请检查中转站地址和网络。"
    except APIStatusError as exc:
        failure = f"模型请求失败（HTTP {exc.status_code}）。请检查中转站地址、API Key 和模型名。"
    except Exception:
        failure = "模型调用失败。请检查 SQL 生成 Agent 的中转站配置。"
    else:
        sql = payload.get("sql") if isinstance(payload, dict) else None
        if isinstance(sql, str) and sql.strip():
            return GeneratedSQL(
                sql=sql.strip(),
                explanation=str(payload.get("explanation", "")),
                prompt_id=rendered_prompt.prompt_id,
                prompt_version=rendered_prompt.version,
            )
        if getattr(llm, "enabled", None) is False:
            failure = "SQL 生成 Agent 未配置可用的 API Key。"
        elif payload is None:
            failure = "模型没有返回可用内容。"
        else:
            failure = "模型回复缺少有效的 sql 字符串。"
    if allow_demo_fallback:
        return fallback_sql(question)
    raise SQLGenerationError(f"SQL 生成失败：{failure} 未执行 SQL。")


def try_fallback_sql(question: str) -> GeneratedSQL | None:
    """为已知演示问题返回稳定 SQL。

    示例问题只作为大模型不可用时的兜底路径，避免演示和离线测试完全失败。
    """

    q = question.lower()
    if ("huadong" in q or "east" in q or CN_EAST_CHINA in question) and (
        "top" in q or CN_TOP_THREE in question or CN_SALES_VOLUME in question
    ):
        return GeneratedSQL(
            sql="""
WITH current_q AS (
    SELECT p.product_name, SUM(oi.quantity) AS current_quantity
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    JOIN regions r ON o.region_id = r.region_id
    WHERE r.region_name = 'East China'
      AND o.order_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
    GROUP BY p.product_name
),
previous_q AS (
    SELECT p.product_name, SUM(oi.quantity) AS previous_quantity
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    JOIN regions r ON o.region_id = r.region_id
    WHERE r.region_name = 'East China'
      AND o.order_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
      AND o.order_date < DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
    GROUP BY p.product_name
)
SELECT
    current_q.product_name,
    current_q.current_quantity,
    COALESCE(previous_q.previous_quantity, 0) AS previous_quantity,
    CASE
        WHEN COALESCE(previous_q.previous_quantity, 0) = 0 THEN NULL
        ELSE ROUND((current_q.current_quantity - previous_q.previous_quantity)
            / previous_q.previous_quantity * 100, 2)
    END AS growth_rate_percent
FROM current_q
LEFT JOIN previous_q ON current_q.product_name = previous_q.product_name
ORDER BY current_q.current_quantity DESC
LIMIT 3
""",
            explanation="查询华东地区近三个月销量前三的商品，并与上一季度销量做环比对比。",
            used_fallback=True,
        )
    if "6" in q and ("month" in q or CN_MONTH in question):
        return GeneratedSQL(
            sql="""
SELECT
    DATE_FORMAT(o.order_date, '%Y-%m') AS month,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS sales_amount
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
ORDER BY month
""",
            explanation="按月份汇总最近六个月的销售额，用于观察销售趋势。",
            used_fallback=True,
        )
    if CN_CATEGORY_SHARE in question or "share" in q or "proportion" in q or "category" in q:
        return GeneratedSQL(
            sql="""
SELECT
    p.category,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS sales_amount
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
GROUP BY p.category
ORDER BY sales_amount DESC
""",
            explanation="按商品品类汇总销售额，用于分析各品类销售占比。",
            used_fallback=True,
        )
    if CN_AVG_ORDER_VALUE in question or "average order" in q or "avg order" in q or "aov" in q:
        return GeneratedSQL(
            sql="""
SELECT
    r.region_name,
    ROUND(SUM(oi.quantity * oi.unit_price) / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN regions r ON o.region_id = r.region_id
GROUP BY r.region_name
ORDER BY avg_order_value DESC
""",
            explanation="按地区计算客单价，并按客单价从高到低排序。",
            used_fallback=True,
        )
    if CN_DECLINE in question or "decline" in q or "drop" in q:
        return GeneratedSQL(
            sql="""
WITH last_month AS (
    SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS amount
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
    GROUP BY p.product_name
),
previous_month AS (
    SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS amount
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 2 MONTH)
      AND o.order_date < DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
    GROUP BY p.product_name
)
SELECT
    previous_month.product_name,
    ROUND(previous_month.amount, 2) AS previous_amount,
    ROUND(COALESCE(last_month.amount, 0), 2) AS last_amount,
    ROUND(COALESCE(last_month.amount, 0) - previous_month.amount, 2) AS amount_change
FROM previous_month
LEFT JOIN last_month ON previous_month.product_name = last_month.product_name
ORDER BY amount_change ASC
LIMIT 10
""",
            explanation="对比最近一个月和上一个月的商品销售额，找出下滑最明显的商品。",
            used_fallback=True,
        )
    if (CN_REGION in question or "region" in q) and (
        CN_ORDER in question or "order" in q
    ) and (CN_COUNT in question or "count" in q):
        return GeneratedSQL(
            sql="""
SELECT
    r.region_name,
    COUNT(DISTINCT o.order_id) AS order_count
FROM orders o
JOIN regions r ON o.region_id = r.region_id
GROUP BY r.region_name
ORDER BY order_count DESC
""",
            explanation="按地区统计订单数量，并按订单量从高到低排序。",
            used_fallback=True,
        )
    if (CN_INDUSTRY in question or "industry" in q) and (
        CN_CUSTOMER in question or "customer" in q
    ) and (CN_COUNT in question or "count" in q):
        return GeneratedSQL(
            sql="""
SELECT
    c.industry,
    COUNT(DISTINCT c.customer_id) AS customer_count
FROM customers c
GROUP BY c.industry
ORDER BY customer_count DESC
""",
            explanation="按行业统计客户数量，并按客户数量从高到低排序。",
            used_fallback=True,
        )
    return None


def fallback_sql(question: str) -> GeneratedSQL:
    """当大模型不可用或没有返回 SQL 时的兜底逻辑。"""

    deterministic_sql = try_fallback_sql(question)
    if deterministic_sql:
        return deterministic_sql

    return GeneratedSQL(
        sql="""
SELECT
    r.region_name,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS sales_amount
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN regions r ON o.region_id = r.region_id
GROUP BY r.region_name
ORDER BY sales_amount DESC
""",
        explanation="默认分析：按地区汇总销售额，并按销售额从高到低排序。",
        used_fallback=True,
    )


class SQLGenerationAgent:
    """?? schema?RAG ?????????? SQL?"""

    async def run(self, state: "DataAnalysisAgentState") -> None:
        state.generated_sql = await generate_sql(
            state.request.question,
            state.schema_prompt,
            state.llm_for("sql_agent"),
            metric_context=state.retrieval_context,
            allow_demo_fallback=(
                state.settings.enable_demo_sql_fallback
                and state.engine.url.get_backend_name() == "mysql"
                and state.engine.url.database == "datawhisperer_demo"
            ),
        )
        if state.generated_sql.used_fallback:
            state.warnings.append("模型未生成 SQL，已在演示库中使用演示查询。")
        state.record_prompt_version(state.generated_sql)
        detail = state.generated_sql.explanation
        if state.generated_sql.prompt_id and state.generated_sql.prompt_version:
            detail = f"{detail}?prompt={state.generated_sql.prompt_id}@{state.generated_sql.prompt_version}?"
        state.add_trace(
            "generate_sql",
            "ok",
            f"SQLGenerationAgent: {detail}; {state.model_trace_detail('sql_agent')}",
        )
