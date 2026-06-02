import json
from collections.abc import Sequence
from typing import Any

from app.core.database import rows_to_preview
from app.core.llm import LLMClient


async def generate_insight(
    question: str,
    sql: str,
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
    llm: LLMClient,
) -> str:
    """基于查询结果生成业务分析结论。

    分析总结必须发生在 SQL 执行之后，这样模型看到的是数据库真实返回的 rows。
    如果没有配置大模型，则返回一个确定性的本地总结，保证系统仍然可演示。
    """

    if not rows:
        return "没有查询到匹配的数据。可以尝试放宽时间范围、地区或其他筛选条件。"

    # 只把前 20 行发给模型，控制 prompt 长度。
    # API 仍然会把完整的、有上限的 rows 返回给前端。
    preview = rows_to_preview(rows, limit=20)
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名谨慎的业务数据分析师。请用简体中文写 3 到 5 句简洁结论。"
                "只能使用查询结果中已经出现的事实，不要编造原因、数字或业务背景。"
                "如果结果里出现 East China、North China、South China、West China，"
                "请分别翻译成华东、华北、华南、西部。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\nSQL: {sql}\nColumns: {list(columns)}\n"
                f"Rows JSON: {json.dumps(preview, ensure_ascii=False)}"
            ),
        },
    ]
    text = await llm.complete_text(messages)
    if text:
        return text.strip()
    return fallback_insight(columns, rows)


def fallback_insight(columns: Sequence[str], rows: Sequence[dict[str, Any]]) -> str:
    """没有大模型时使用的本地总结逻辑。"""

    first = rows[0]
    if len(columns) >= 2:
        leading_value = _translate_value(first.get(columns[0]))
        return (
            f"本次查询返回 {len(rows)} 行结果。排名第一的是 {leading_value}，"
            f"{columns[1]} = {first.get(columns[1])}。"
            "可以结合图表和表格继续比较其他结果。"
        )
    return f"本次查询返回 {len(rows)} 行结果，请查看表格获取详细数据。"


def _translate_value(value: Any) -> Any:
    region_labels = {
        "East China": "\u534e\u4e1c",
        "North China": "\u534e\u5317",
        "South China": "\u534e\u5357",
        "West China": "\u897f\u90e8",
    }
    return region_labels.get(value, value)
