"""Regenerate DataWhisperer Text-to-SQL evaluation datasets.

这个脚本只负责生成评测数据，不依赖数据库和大模型，便于在任何机器上复现。

数据集分层：
- text_to_sql_cases.json：离线稳定回归集，覆盖当前本地 fallback 能稳定生成的 7 类问题。
- text_to_sql_18_table_cases.jsonl：真实 Agent Runner 默认集，每类问题覆盖产品库 18 张业务表。
- text_to_sql_upload_100_cases.jsonl：测试集管理页面可上传的 100 条演示集。
- text_to_sql_product_240_cases.jsonl / text_to_sql_product_360_cases.jsonl：
  产品级大样本 benchmark，用于后续 Agent、RAG、SQL 修复和消融实验。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals"

FORBIDDEN_SQL = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE")


@dataclass(frozen=True)
class Scenario:
    """一类可复用的评测问题模板。"""

    slug: str
    difficulty: str
    chart_type: str
    tags: tuple[str, ...]
    expected_sql_contains: tuple[str, ...]
    expected_columns: tuple[str, ...]
    requires_rag: bool
    ablation_tags: tuple[str, ...]
    questions: tuple[str, ...]


def make_case(
    *,
    case_id: str,
    question: str,
    scenario: Scenario,
) -> dict[str, object]:
    """生成统一格式的 Text-to-SQL 评测用例。"""

    return {
        "id": case_id,
        "question": question,
        "difficulty": scenario.difficulty,
        "requires_rag": scenario.requires_rag,
        "ablation_tags": list(scenario.ablation_tags),
        "tags": list(scenario.tags),
        "expected_sql_contains": list(scenario.expected_sql_contains),
        "forbidden_sql_contains": list(FORBIDDEN_SQL),
        "expected_columns": list(scenario.expected_columns),
        "expected_chart_type": scenario.chart_type,
        "must_be_safe": True,
    }


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(text + "\n", encoding="utf-8")


OFFLINE_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        slug="monthly_sales_trend",
        difficulty="simple",
        chart_type="line",
        tags=("orders", "order_items", "time_series", "fallback"),
        expected_sql_contains=(
            "DATE_FORMAT(o.order_date, '%Y-%m') AS month",
            "SUM(oi.quantity * oi.unit_price)",
            "INTERVAL 6 MONTH",
            "GROUP BY DATE_FORMAT",
        ),
        expected_columns=("month", "sales_amount"),
        requires_rag=True,
        ablation_tags=("metric_rag", "chart_recommendation"),
        questions=(
            "查询最近 6 个月每月销售额趋势",
            "最近 6 个月的月度销售额变化如何",
            "帮我看最近 6 个月每月销售额走势",
            "统计最近 6 个月按月销售额趋势",
            "最近 6 个月销售额按月份怎么变化",
            "查询最近 6 个月销售额月度趋势",
            "最近 6 个月每个月销售金额是多少",
            "看一下最近 6 个月月销售额折线趋势",
            "最近 6 个月销售额有没有持续增长",
            "统计最近 6 个月每月销售额并按月份排序",
        ),
    ),
    Scenario(
        slug="category_sales_share",
        difficulty="simple",
        chart_type="pie",
        tags=("products", "order_items", "category", "fallback"),
        expected_sql_contains=(
            "p.category",
            "SUM(oi.quantity * oi.unit_price)",
            "GROUP BY p.category",
        ),
        expected_columns=("category", "sales_amount"),
        requires_rag=True,
        ablation_tags=("metric_rag", "chart_recommendation"),
        questions=(
            "查询各商品品类销售额占比",
            "各商品品类的销售额占比是多少",
            "帮我看商品品类销售额占比",
            "统计不同商品品类销售额占比",
            "各品类销售额占比情况",
            "查询商品品类贡献占比",
            "看一下各品类销售金额占比",
            "不同商品品类销售占比如何",
            "统计商品品类销售额并计算占比",
            "商品品类销售额占比排名",
        ),
    ),
    Scenario(
        slug="region_avg_order_value",
        difficulty="medium",
        chart_type="bar",
        tags=("orders", "order_items", "regions", "fallback"),
        expected_sql_contains=(
            "avg_order_value",
            "COUNT(DISTINCT o.order_id)",
            "GROUP BY r.region_name",
        ),
        expected_columns=("region_name", "avg_order_value"),
        requires_rag=True,
        ablation_tags=("metric_rag", "schema_linking"),
        questions=(
            "哪个地区客单价最高",
            "查询各地区客单价排名",
            "帮我比较不同地区客单价",
            "各地区客单价从高到低排序",
            "统计地区客单价表现",
            "哪个地区客单价也就是平均每单金额最高",
            "看一下地区维度的客单价",
            "查询地区客单价 Top 排名",
            "比较各地区订单客单价",
            "不同地区客单价差异如何",
        ),
    ),
    Scenario(
        slug="product_sales_decline",
        difficulty="medium",
        chart_type="bar",
        tags=("orders", "order_items", "products", "fallback"),
        expected_sql_contains=(
            "WITH last_month AS",
            "WITH last_month AS",
            "previous_month",
            "amount_change",
        ),
        expected_columns=("product_name", "previous_amount", "last_amount", "amount_change"),
        requires_rag=True,
        ablation_tags=("metric_rag", "sql_of_thought", "chart_recommendation"),
        questions=(
            "找出销售额下滑最明显的商品",
            "哪些商品销售额下滑最明显",
            "帮我看最近销售额下滑最多的商品",
            "查询销售额下滑幅度最大的商品",
            "找出环比销售额下滑的商品",
            "最近一个月销售额下滑最严重的商品有哪些",
            "对比最近两个月找出销售额下滑商品",
            "商品销售额下滑排行榜",
            "看一下哪些商品销售额出现明显下滑",
            "统计销售额下滑最突出的商品",
        ),
    ),
    Scenario(
        slug="region_order_count",
        difficulty="simple",
        chart_type="bar",
        tags=("orders", "regions", "fallback"),
        expected_sql_contains=(
            "COUNT(DISTINCT o.order_id) AS order_count",
            "JOIN regions r",
            "GROUP BY r.region_name",
        ),
        expected_columns=("region_name", "order_count"),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "查询各地区订单数量",
            "统计每个地区订单数量",
            "各地区订单数量是多少",
            "帮我看地区订单数量排名",
            "按地区统计订单数量",
            "不同地区订单数量对比",
            "查询地区维度订单数量",
            "统计各地区订单数量",
            "各地区订单数量从高到低排序",
            "看一下订单数量最多的地区",
        ),
    ),
    Scenario(
        slug="east_top_growth",
        difficulty="complex",
        chart_type="bar",
        tags=("orders", "order_items", "products", "regions", "fallback"),
        expected_sql_contains=(
            "WITH current_q AS",
            "previous_q",
            "growth_rate_percent",
            "East China",
        ),
        expected_columns=("product_name", "current_quantity", "previous_quantity", "growth_rate_percent"),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "查询华东地区销量前三的商品及其环比增长",
            "华东地区销量前三商品环比增长是多少",
            "帮我看华东销量前三商品和上一季度对比",
            "统计华东地区销量 Top3 商品及环比增长",
            "华东地区最近销量前三的商品表现如何",
            "查询华东销量前三商品的增长率",
            "华东地区商品销量前三及环比",
            "找出华东地区销量前三商品并计算环比增长",
            "华东销量 Top3 商品与上一周期相比如何",
            "分析华东地区销量最高的前三个商品及增长",
        ),
    ),
    Scenario(
        slug="industry_customer_count",
        difficulty="simple",
        chart_type="bar",
        tags=("customers", "industry", "fallback"),
        expected_sql_contains=(
            "c.industry",
            "COUNT(DISTINCT c.customer_id) AS customer_count",
            "GROUP BY c.industry",
        ),
        expected_columns=("industry", "customer_count"),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "按行业统计客户数量",
            "查询各行业客户数量",
            "各行业客户数量是多少",
            "帮我看行业客户数量分布",
            "统计不同行业客户数量",
            "行业维度客户数量排名",
            "查询客户所属行业数量",
            "各行业客户数量从高到低排序",
            "看一下哪个行业客户数量最多",
            "统计行业客户数量并排序",
        ),
    ),
)


PRODUCT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        slug="region_gmv",
        difficulty="simple",
        chart_type="bar",
        tags=("regions", "orders", "order_items", "metric_gmv"),
        expected_sql_contains=("regions", "orders", "order_items"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "chart_recommendation"),
        questions=(
            "按地区统计最近 30 天 GMV 和订单数量",
            "各地区本季度销售额和订单数表现如何",
            "查询不同区域的 GMV 排名",
            "对比华东、华北、华南和西部的销售额",
            "按地区查看销售额、订单量和客单价",
        ),
    ),
    Scenario(
        slug="segment_repurchase",
        difficulty="medium",
        chart_type="bar",
        tags=("customer_segments", "customers", "orders", "metric_repurchase"),
        expected_sql_contains=("customer_segments", "customers", "orders"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "不同客户分层的复购率和客单价分别是多少",
            "按客户等级统计订单数和复购表现",
            "比较 VIP、成长客户和普通客户的销售贡献",
            "不同客户分层最近 90 天的复购差异",
            "客户分层维度下 GMV 和订单量如何",
        ),
    ),
    Scenario(
        slug="customer_industry",
        difficulty="simple",
        chart_type="bar",
        tags=("customers", "orders"),
        expected_sql_contains=("customers", "orders"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "按客户行业统计订单数量和销售额",
            "哪个行业客户贡献的销售额最高",
            "不同行业客户最近 6 个月订单数对比",
            "查询各行业客户的平均订单金额",
            "行业维度客户销售贡献排名",
        ),
    ),
    Scenario(
        slug="category_hierarchy",
        difficulty="medium",
        chart_type="pie",
        tags=("categories", "products", "order_items"),
        expected_sql_contains=("categories", "products", "order_items"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "按一级品类统计销售额占比",
            "不同商品分类的销量和销售额排名",
            "查询父品类下各子品类销售贡献",
            "品类结构里哪个分类增长最快",
            "按商品分类查看近 30 天销售额",
        ),
    ),
    Scenario(
        slug="supplier_sales",
        difficulty="medium",
        chart_type="bar",
        tags=("suppliers", "products", "order_items"),
        expected_sql_contains=("suppliers", "products", "order_items"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "sql_of_thought"),
        questions=(
            "按供应商统计商品销售额和销量",
            "哪个供应商贡献的销售额最高",
            "供应商维度下商品动销情况如何",
            "查询各供应商关联商品的平均售价",
            "找出销售额最高的供应商及其商品数",
        ),
    ),
    Scenario(
        slug="warehouse_inventory",
        difficulty="complex",
        chart_type="bar",
        tags=("warehouses", "products", "inventory_snapshots"),
        expected_sql_contains=("warehouses", "inventory_snapshots", "products"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "各仓库当前库存金额和缺货 SKU 数量是多少",
            "按仓库统计库存覆盖天数和库存件数",
            "找出库存低于安全线的仓库和商品",
            "仓库维度下哪些商品库存压力最大",
            "比较不同仓库的库存周转风险",
        ),
    ),
    Scenario(
        slug="product_price_band",
        difficulty="medium",
        chart_type="bar",
        tags=("products", "order_items", "categories"),
        expected_sql_contains=("products", "order_items"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "按商品价格带统计销售额和销量",
            "不同价格区间商品的销售表现如何",
            "查询高价商品和低价商品的销售贡献",
            "商品价格带与销量之间有什么关系",
            "找出销量最高的商品及其品类和价格",
        ),
    ),
    Scenario(
        slug="channel_aov",
        difficulty="medium",
        chart_type="bar",
        tags=("sales_channels", "orders", "order_items", "metric_aov"),
        expected_sql_contains=("sales_channels", "orders", "order_items"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "chart_recommendation"),
        questions=(
            "各销售渠道的客单价和订单数是多少",
            "哪个渠道 GMV 最高且客单价最高",
            "按渠道比较销售额、订单量和客单价",
            "最近 6 个月各渠道销售趋势如何",
            "线上渠道和线下渠道的订单表现差异",
        ),
    ),
    Scenario(
        slug="campaign_roi",
        difficulty="complex",
        chart_type="bar",
        tags=("campaigns", "orders", "order_items", "metric_roi"),
        expected_sql_contains=("campaigns", "orders", "order_items"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "各营销活动的 GMV、订单数和 ROI 如何",
            "活动期间销售额最高的是哪个 campaign",
            "比较不同营销活动带来的订单转化",
            "找出 ROI 低但销售额高的活动",
            "按活动统计投入产出和销售贡献",
        ),
    ),
    Scenario(
        slug="coupon_effect",
        difficulty="complex",
        chart_type="bar",
        tags=("coupons", "orders", "order_items"),
        expected_sql_contains=("coupons", "orders", "order_items"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "不同优惠券的使用率和拉动销售额是多少",
            "优惠券订单和非优惠券订单客单价差异",
            "找出核销金额最高的优惠券",
            "按优惠券类型统计订单数和销售额",
            "分析优惠券对复购订单的影响",
        ),
    ),
    Scenario(
        slug="order_trend",
        difficulty="simple",
        chart_type="line",
        tags=("orders", "time_series"),
        expected_sql_contains=("orders",),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "最近 12 个月每月订单数量趋势",
            "按月统计订单数和支付订单数",
            "查询最近 90 天每日订单趋势",
            "本季度订单量相比上季度变化如何",
            "按订单状态统计订单数量",
        ),
    ),
    Scenario(
        slug="order_item_top_products",
        difficulty="simple",
        chart_type="bar",
        tags=("order_items", "products"),
        expected_sql_contains=("order_items", "products"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "销量最高的 Top10 商品有哪些",
            "按商品统计销售数量和销售额",
            "查询单品销售额排行榜",
            "找出件单价最高的商品明细",
            "各商品 SKU 的销量表现如何",
        ),
    ),
    Scenario(
        slug="inventory_risk",
        difficulty="complex",
        chart_type="bar",
        tags=("inventory_snapshots", "warehouses", "products"),
        expected_sql_contains=("inventory_snapshots", "warehouses", "products"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "哪些商品连续两周库存下降且销量上升",
            "按仓库找出库存周转风险最高的商品",
            "查询库存快耗尽但最近销量高的商品",
            "库存金额最高的仓库和品类是什么",
            "结合库存和销量识别补货优先级",
        ),
    ),
    Scenario(
        slug="payment_success",
        difficulty="medium",
        chart_type="pie",
        tags=("payments", "orders"),
        expected_sql_contains=("payments", "orders"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "不同支付方式的支付成功率是多少",
            "按支付渠道统计支付金额和失败订单数",
            "查询支付失败率最高的支付方式",
            "每月支付成功率趋势如何",
            "支付方式维度下 GMV 占比是多少",
        ),
    ),
    Scenario(
        slug="shipment_delay",
        difficulty="medium",
        chart_type="bar",
        tags=("shipments", "orders", "regions"),
        expected_sql_contains=("shipments", "orders"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "sql_of_thought"),
        questions=(
            "各地区平均发货时长和签收时长是多少",
            "哪个物流承运商延迟率最高",
            "查询超时发货订单数量",
            "按区域统计配送时效表现",
            "最近 30 天物流延迟订单趋势",
        ),
    ),
    Scenario(
        slug="return_reason",
        difficulty="medium",
        chart_type="pie",
        tags=("returns", "orders", "products", "metric_return_rate"),
        expected_sql_contains=("returns", "orders"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "chart_recommendation"),
        questions=(
            "各退货原因的退货率和退款金额是多少",
            "按品类统计退货订单数量",
            "找出退货率最高的商品",
            "最近 6 个月退货金额趋势",
            "不同地区退货率差异如何",
        ),
    ),
    Scenario(
        slug="review_score",
        difficulty="medium",
        chart_type="bar",
        tags=("product_reviews", "products", "customers"),
        expected_sql_contains=("product_reviews", "products"),
        expected_columns=(),
        requires_rag=False,
        ablation_tags=("schema_linking", "chart_recommendation"),
        questions=(
            "各商品平均评分和差评数量是多少",
            "评分最低的商品及其销售额如何",
            "按品类统计平均评价分",
            "最近 90 天差评率趋势",
            "找出评价数量最多且评分较低的商品",
        ),
    ),
    Scenario(
        slug="support_ticket",
        difficulty="complex",
        chart_type="bar",
        tags=("support_tickets", "customers", "orders"),
        expected_sql_contains=("support_tickets", "customers"),
        expected_columns=(),
        requires_rag=True,
        ablation_tags=("schema_linking", "metric_rag", "sql_of_thought"),
        questions=(
            "各问题类型的客服工单数量和平均响应时长",
            "哪些客户分层提交的工单最多",
            "查询售后工单与退货订单的关联情况",
            "最近 30 天客服工单处理时长趋势",
            "找出高价值客户中未解决工单数量",
        ),
    ),
)


def build_offline_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for scenario in OFFLINE_SCENARIOS:
        for index, question in enumerate(scenario.questions, start=1):
            cases.append(
                make_case(
                    case_id=f"offline_{scenario.slug}_{index:02d}",
                    question=question,
                    scenario=scenario,
                )
            )
    return cases


def build_product_cases(total: int) -> list[dict[str, object]]:
    """按 18 类业务问题均匀扩展产品级 benchmark。"""

    cases: list[dict[str, object]] = []
    per_scenario = total // len(PRODUCT_SCENARIOS)
    remainder = total % len(PRODUCT_SCENARIOS)
    for scenario_index, scenario in enumerate(PRODUCT_SCENARIOS, start=1):
        scenario_total = per_scenario + (1 if scenario_index <= remainder else 0)
        for index in range(1, scenario_total + 1):
            base_question = scenario.questions[(index - 1) % len(scenario.questions)]
            round_label = (index - 1) // len(scenario.questions) + 1
            if round_label == 1:
                question = base_question
            else:
                question = f"{base_question}，并按结果从高到低排序（口径版本 {round_label}）"
            cases.append(
                make_case(
                    case_id=f"product_{scenario.slug}_{index:03d}",
                    question=question,
                    scenario=scenario,
                )
            )
    return cases


def main() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    offline_cases = build_offline_cases()
    product_240_cases = build_product_cases(240)
    product_360_cases = build_product_cases(360)
    agent_18_cases = [
        make_case(
            case_id=f"agent18_{scenario.slug}",
            question=scenario.questions[0],
            scenario=scenario,
        )
        for scenario in PRODUCT_SCENARIOS
    ]
    upload_100_cases = product_360_cases[:100]

    write_json(
        EVAL_DIR / "text_to_sql_cases.json",
        {
            "version": "v4.2.1",
            "description": "DataWhisperer 离线稳定 Text-to-SQL 回归集，覆盖当前 fallback 能稳定生成的 7 类问题。",
            "cases": offline_cases,
        },
    )
    write_jsonl(EVAL_DIR / "text_to_sql_18_table_cases.jsonl", agent_18_cases)
    write_jsonl(EVAL_DIR / "text_to_sql_upload_100_cases.jsonl", upload_100_cases)
    write_jsonl(EVAL_DIR / "text_to_sql_product_240_cases.jsonl", product_240_cases)
    write_jsonl(EVAL_DIR / "text_to_sql_product_360_cases.jsonl", product_360_cases)

    print("Regenerated evaluation datasets:")
    print(f"- text_to_sql_cases.json: {len(offline_cases)} cases")
    print(f"- text_to_sql_18_table_cases.jsonl: {len(agent_18_cases)} cases")
    print(f"- text_to_sql_upload_100_cases.jsonl: {len(upload_100_cases)} cases")
    print(f"- text_to_sql_product_240_cases.jsonl: {len(product_240_cases)} cases")
    print(f"- text_to_sql_product_360_cases.jsonl: {len(product_360_cases)} cases")


if __name__ == "__main__":
    main()
