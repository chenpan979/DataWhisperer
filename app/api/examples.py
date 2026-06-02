from fastapi import APIRouter

from app.models.examples import ExampleQuestion, ExamplesResponse

router = APIRouter(tags=["examples"])


EXAMPLE_QUESTIONS = [
    ExampleQuestion(
        question="查询最近 6 个月每月销售额趋势",
        intent="月度销售趋势分析",
        expected_chart="line",
        notes="演示按月份聚合销售额，并推荐折线图。",
    ),
    ExampleQuestion(
        question="查询各商品品类销售额占比",
        intent="品类贡献分析",
        expected_chart="pie",
        notes="演示占比类问题，并推荐饼图。",
    ),
    ExampleQuestion(
        question="哪个地区客单价最高",
        intent="地区客单价对比",
        expected_chart="bar",
        notes="演示按地区比较核心业务指标。",
    ),
    ExampleQuestion(
        question="找出销售额下滑最明显的商品",
        intent="商品销售下滑识别",
        expected_chart="bar",
        notes="演示使用 CTE 做月度对比分析。",
    ),
    ExampleQuestion(
        question="查询华东地区销量前三的商品及其环比增长",
        intent="区域商品排行与增长分析",
        expected_chart="bar",
        notes="演示多表关联和环比计算。",
    ),
    ExampleQuestion(
        question="查询各地区订单数量",
        intent="地区订单量对比",
        expected_chart="bar",
        notes="演示按地区统计订单量。",
    ),
]


@router.get("/examples", response_model=ExamplesResponse)
def list_examples() -> ExamplesResponse:
    """返回适合示例库演示的问题列表。"""

    return ExamplesResponse(examples=EXAMPLE_QUESTIONS)
