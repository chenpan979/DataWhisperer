from app.tools.chart_tool import recommend_chart


def test_recommends_line_for_time_series() -> None:
    chart = recommend_chart(
        ["month", "sales_amount"],
        [{"month": "2026-01", "sales_amount": 100.0}],
        "recent 6 months sales trend",
    )
    assert chart["type"] == "line"


def test_recommends_pie_for_share_question() -> None:
    chart = recommend_chart(
        ["category", "sales_amount"],
        [{"category": "Electronics", "sales_amount": 100.0}],
        "category share",
    )
    assert chart["type"] == "pie"


def test_recommends_bar_for_category_metric() -> None:
    chart = recommend_chart(
        ["region_name", "sales_amount"],
        [{"region_name": "East China", "sales_amount": 100.0}],
        "sales by region",
    )
    assert chart["type"] == "bar"


def test_recommends_bar_for_region_order_count() -> None:
    chart = recommend_chart(
        ["region_name", "order_count"],
        [{"region_name": "East China", "order_count": 12}],
        "order count by region",
    )
    assert chart["type"] == "bar"
