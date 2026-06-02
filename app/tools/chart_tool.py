from collections.abc import Sequence
from typing import Any

CN_CATEGORY_SHARE = "\u5360\u6bd4"

COLUMN_LABELS = {
    "region_name": "\u5730\u533a",
    "order_count": "\u8ba2\u5355\u6570\u91cf",
    "sales_amount": "\u9500\u552e\u989d",
    "product_name": "\u5546\u54c1",
    "category": "\u54c1\u7c7b",
    "month": "\u6708\u4efd",
    "avg_order_value": "\u5ba2\u5355\u4ef7",
    "growth_rate_percent": "\u73af\u6bd4\u589e\u957f\u7387",
}


def _is_number(value: Any) -> bool:
    """判断一个值是否适合作为图表数值轴。"""

    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_time_column(name: str) -> bool:
    """根据字段名粗略判断是否是时间列，用于推荐折线图。"""

    lowered = name.lower()
    return any(token in lowered for token in ["date", "month", "year", "day", "time"])


def recommend_chart(
    columns: Sequence[str], rows: Sequence[dict[str, Any]], question: str = ""
) -> dict[str, Any]:
    """根据查询结果生成简单的 ECharts 配置。

    V1 阶段不把图表推荐完全交给大模型，而是用稳定规则：
    占比问题 -> 饼图；时间序列 -> 折线图；分类对比 -> 柱状图；
    不适合画图的数据结构 -> 表格兜底。
    """

    if not columns or not rows:
        return {"type": "empty", "title": {"text": "No data"}, "series": []}

    sample = rows[0]
    numeric_columns = [column for column in columns if _is_number(sample.get(column))]
    category_columns = [column for column in columns if column not in numeric_columns]

    if not numeric_columns or not category_columns:
        return {"type": "table", "title": {"text": "Query Result"}, "columns": list(columns)}

    x_col = category_columns[0]
    y_col = numeric_columns[0]
    labels = [row.get(x_col) for row in rows]
    values = [row.get(y_col) for row in rows]
    title = f"\u6309{COLUMN_LABELS.get(x_col, x_col)}\u7edf\u8ba1{COLUMN_LABELS.get(y_col, y_col)}"
    lowered_question = question.lower()

    if CN_CATEGORY_SHARE in question or "share" in lowered_question or "proportion" in lowered_question:
        return {
            "type": "pie",
            "title": {"text": title},
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "pie",
                    "radius": "60%",
                    "data": [{"name": label, "value": value} for label, value in zip(labels, values)],
                }
            ],
        }

    if _is_time_column(x_col):
        return {
            "type": "line",
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": labels},
            "yAxis": {"type": "value"},
            "series": [{"type": "line", "data": values, "smooth": True}],
        }

    return {
        "type": "bar",
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": values}],
    }
