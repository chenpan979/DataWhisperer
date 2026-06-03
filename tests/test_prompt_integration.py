import pytest

from app.tools.insight_tool import generate_insight
from app.tools.sql_tool import generate_sql, repair_sql


class FakeJsonLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, str]:
        self.messages = messages
        return {"sql": "SELECT 1 AS value", "explanation": "查询固定值。"}


class FakeTextLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def complete_text(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return "本次查询返回 1 行结果，可以结合表格继续查看。"


@pytest.mark.asyncio
async def test_generate_sql_uses_versioned_prompt_template() -> None:
    llm = FakeJsonLLM()

    generated = await generate_sql(
        question="Please calculate weekday revenue.",
        schema_prompt="Table orders(order_id, order_date)",
        llm=llm,
    )

    assert generated.sql == "SELECT 1 AS value"
    assert generated.prompt_id == "sql_generation"
    assert generated.prompt_version == "v1"
    assert llm.messages[0]["role"] == "system"
    assert "只返回严格 JSON" in llm.messages[0]["content"]
    assert "Table orders(order_id, order_date)" in llm.messages[1]["content"]


@pytest.mark.asyncio
async def test_repair_sql_uses_versioned_prompt_template() -> None:
    llm = FakeJsonLLM()

    repaired = await repair_sql(
        question="查询订单数量",
        schema_prompt="Table orders(order_id)",
        failed_sql="SELECT missing_column FROM orders",
        error_message="Unknown column 'missing_column'",
        llm=llm,
    )

    assert repaired is not None
    assert repaired.sql == "SELECT 1 AS value"
    assert repaired.prompt_id == "sql_repair"
    assert repaired.prompt_version == "v1"
    assert "修复失败的 MySQL 只读查询" in llm.messages[0]["content"]
    assert "Unknown column 'missing_column'" in llm.messages[1]["content"]


@pytest.mark.asyncio
async def test_generate_insight_uses_versioned_prompt_template() -> None:
    llm = FakeTextLLM()

    generated = await generate_insight(
        question="哪个地区销售额最高？",
        sql="SELECT region_name, sales_amount FROM region_sales",
        columns=["region_name", "sales_amount"],
        rows=[{"region_name": "East China", "sales_amount": 1000}],
        llm=llm,  # type: ignore[arg-type]
    )

    assert generated.content == "本次查询返回 1 行结果，可以结合表格继续查看。"
    assert generated.prompt_id == "insight_summary"
    assert generated.prompt_version == "v1"
    assert llm.messages[0]["role"] == "system"
    assert "只基于查询结果中已经出现的事实" in llm.messages[0]["content"]
    assert "East China" in llm.messages[1]["content"]
