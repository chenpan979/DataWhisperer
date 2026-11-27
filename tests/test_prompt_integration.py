from json import JSONDecodeError

import pytest

from app.tools.insight_tool import generate_insight
from app.agents.sql_repair import repair_sql
from app.agents.sql_generation import SQLGenerationError, generate_sql
from app.agents.query_planning import generate_query_plan


class FakeJsonLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, str]:
        self.messages = messages
        return {"sql": "SELECT 1 AS value", "explanation": "查询固定值。"}



class FakePlanLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        self.messages = messages
        return {
            "objective": "分析月度销售额趋势",
            "candidate_tables": ["orders", "order_items"],
            "steps": [
                "按月份过滤订单日期。",
                "关联订单和订单明细并汇总销售额。",
                "按月份升序排序。",
            ],
            "checks": ["只允许 SELECT/WITH。", "字段必须来自 schema。"],
        }

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
        metric_context="销售额 = SUM(order_items.quantity * order_items.unit_price)",
    )

    assert generated.sql == "SELECT 1 AS value"
    assert generated.prompt_id == "sql_generation"
    assert generated.prompt_version == "v1"
    assert llm.messages[0]["role"] == "system"
    assert "只返回严格 JSON" in llm.messages[0]["content"]
    assert "Table orders(order_id, order_date)" in llm.messages[1]["content"]
    assert "销售额 = SUM(order_items.quantity * order_items.unit_price)" in llm.messages[1]["content"]



@pytest.mark.asyncio
async def test_generate_query_plan_uses_versioned_prompt_template() -> None:
    llm = FakePlanLLM()

    generated = await generate_query_plan(
        question="最近 6 个月每月销售额趋势",
        schema={"tables": [{"name": "orders"}, {"name": "order_items"}]},
        schema_prompt="Table orders(order_id, order_date)\nTable order_items(order_id, quantity)",
        retrieval_context="销售额 = SUM(order_items.quantity * order_items.unit_price)",
        llm=llm,
    )

    assert generated.plan.objective == "分析月度销售额趋势"
    assert generated.plan.candidate_tables == ("orders", "order_items")
    assert generated.prompt_id == "query_planning"
    assert generated.prompt_version == "v1"
    assert llm.messages[0]["role"] == "system"
    assert "不要生成 SQL" in llm.messages[0]["content"]
    assert "Table orders(order_id, order_date)" in llm.messages[1]["content"]
    assert "销售额 = SUM(order_items.quantity * order_items.unit_price)" in llm.messages[1]["content"]


@pytest.mark.asyncio
async def test_demo_question_still_calls_sql_generation_model_first() -> None:
    llm = FakeJsonLLM()

    generated = await generate_sql(
        question="查询最近 6 个月每月销售额趋势",
        schema_prompt="Table orders(order_id, order_date)",
        llm=llm,
        metric_context="销售额 = SUM(order_items.quantity * order_items.unit_price)",
    )

    assert generated.sql == "SELECT 1 AS value"
    assert generated.used_fallback is False
    assert llm.messages

class FailingSqlLLM:
    def __init__(self, result):
        self.result = result

    async def complete_json(self, messages):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "message"),
    [
        (RuntimeError("private provider response"), "模型调用失败"),
        (JSONDecodeError("invalid", "private provider response", 0), "不是有效的 JSON"),
        (None, "没有返回可用内容"),
        (["SELECT 1"], "缺少有效的 sql"),
        ({"sql": 123}, "缺少有效的 sql"),
        ({"sql": "  "}, "缺少有效的 sql"),
    ],
)
async def test_invalid_model_response_does_not_return_demo_sql(result, message) -> None:
    with pytest.raises(SQLGenerationError, match=message) as error:
        await generate_sql("哪个地区客单价最高", "", FailingSqlLLM(result))
    assert "未执行 SQL" in str(error.value)
    assert "private provider response" not in str(error.value)


@pytest.mark.asyncio
async def test_explicit_demo_fallback_can_still_return_demo_sql() -> None:
    generated = await generate_sql(
        "哪个地区客单价最高", "", FailingSqlLLM(None), allow_demo_fallback=True
    )
    assert generated.used_fallback
    assert "avg_order_value" in generated.sql


@pytest.mark.asyncio
async def test_repair_sql_uses_versioned_prompt_template() -> None:
    llm = FakeJsonLLM()

    repaired = await repair_sql(
        question="查询订单数量",
        schema_prompt="Table orders(order_id)",
        failed_sql="SELECT missing_column FROM orders",
        error_message="Unknown column 'missing_column'",
        llm=llm,
        metric_context="订单数 = COUNT(DISTINCT orders.order_id)",
    )

    assert repaired is not None
    assert repaired.sql == "SELECT 1 AS value"
    assert repaired.prompt_id == "sql_repair"
    assert repaired.prompt_version == "v1"
    assert "修复失败的 MySQL 只读查询" in llm.messages[0]["content"]
    assert "Unknown column 'missing_column'" in llm.messages[1]["content"]
    assert "订单数 = COUNT(DISTINCT orders.order_id)" in llm.messages[1]["content"]


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
