import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.database import rows_to_preview
from app.core.llm import LLMClient
from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, get_prompt_registry


@dataclass
class GeneratedInsight:
    """分析总结生成结果。

    content 是最终展示给用户的中文结论。
    prompt_id 和 prompt_version 用于记录这次总结使用了哪个提示词版本。
    used_fallback 表示是否走了本地兜底总结。
    """

    content: str
    used_fallback: bool = False
    prompt_id: str | None = None
    prompt_version: str | None = None


async def generate_insight(
    question: str,
    sql: str,
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
    llm: LLMClient,
    prompt_registry: PromptRegistry | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> GeneratedInsight:
    """基于查询结果生成业务分析结论。

    分析总结必须发生在 SQL 执行之后，这样模型看到的是数据库真实返回的 rows。
    如果没有配置大模型，则返回一个确定性的本地总结，保证系统仍然可演示。
    """

    if not rows:
        return GeneratedInsight(
            content="没有查询到匹配的数据。可以尝试放宽时间范围、地区或其他筛选条件。",
            used_fallback=True,
        )

    # 只把前 20 行发给模型，控制 prompt 长度。
    # API 仍然会把完整的、有上限的 rows 返回给前端。
    preview = rows_to_preview(rows, limit=20)
    registry = prompt_registry or get_prompt_registry()
    rendered_prompt = registry.render_messages(
        "insight_summary",
        version=prompt_version,
        variables={
            "question": question,
            "sql": sql,
            "columns_json": json.dumps(list(columns), ensure_ascii=False),
            "rows_json": json.dumps(preview, ensure_ascii=False),
        },
    )
    try:
        text = await llm.complete_text(rendered_prompt.messages)
    except Exception:
        text = None
    if text:
        return GeneratedInsight(
            content=text.strip(),
            prompt_id=rendered_prompt.prompt_id,
            prompt_version=rendered_prompt.version,
        )
    return GeneratedInsight(content=fallback_insight(columns, rows), used_fallback=True)


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
