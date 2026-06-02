import re
from dataclasses import dataclass
from typing import Any


# 这些关键字不应该出现在本项目的 SQL 中。
# 提示词可以提醒模型“只生成 SELECT”，但真正的安全边界必须靠代码兜住。
FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|call|execute|"
    r"merge|load|outfile|dumpfile)\b",
    re.IGNORECASE,
)

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


def extract_sql(text: str) -> str:
    """从模型输出中提取 SQL。

    模型有时会返回 ```sql ... ``` 代码块，这里统一提取代码块内部内容。
    """

    value = text.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    return value


def validate_select_sql(sql: str) -> str:
    """校验 SQL 是否是单条只读查询。

    在 Text-to-SQL 系统里，模型输出必须当作不可信输入处理：
    模型可能犯错，用户也可能通过 prompt injection 诱导模型生成危险 SQL。
    因此执行前必须在服务端做硬校验。
    """

    cleaned = extract_sql(sql).strip()
    if not cleaned:
        raise ValueError("Generated SQL is empty.")

    cleaned = cleaned.rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Only one SQL statement is allowed.")
    if re.search(r"(--|/\*|\*/|#)", cleaned):
        raise ValueError("SQL comments are not allowed.")
    if not re.match(r"^\s*(select|with)\b", cleaned, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN_SQL_RE.search(cleaned):
        raise ValueError("Unsafe SQL keyword detected.")
    return cleaned


def ensure_limit(sql: str, max_rows: int) -> str:
    """确保查询结果有行数上限。"""

    cleaned = validate_select_sql(sql)
    if re.search(r"\blimit\s+\d+\s*$", cleaned, flags=re.IGNORECASE):
        return cleaned
    return f"{cleaned}\nLIMIT {max_rows}"


async def generate_sql(question: str, schema_prompt: str, llm: Any) -> GeneratedSQL:
    """根据自然语言问题和 schema 上下文生成 MySQL SQL。"""

    deterministic_sql = try_fallback_sql(question)
    if deterministic_sql:
        return deterministic_sql

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior data analyst. Generate safe MySQL SELECT SQL only. "
                "Return strict JSON with keys sql and explanation. Do not return markdown. "
                "Use only the provided schema. Never use write, DDL, or multiple statements. "
                "The explanation must be written in Simplified Chinese."
            ),
        },
        {
            "role": "user",
            "content": f"Schema:\n{schema_prompt}\n\nQuestion:\n{question}",
        },
    ]
    try:
        payload = await llm.complete_json(messages)
    except Exception:
        payload = None
    if payload and payload.get("sql"):
        return GeneratedSQL(sql=str(payload["sql"]), explanation=str(payload.get("explanation", "")))
    return fallback_sql(question)


def try_fallback_sql(question: str) -> GeneratedSQL | None:
    """为已知演示问题返回稳定 SQL。

    示例问题是项目演示入口，应该稳定可控；自由提问才优先交给大模型。
    这种设计可以避免模型偶尔把固定 demo 问偏，影响演示体验。
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
    if CN_AVG_ORDER_VALUE in question or "average order" in q or "avg order" in q:
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
