import pytest

from app.tools.sql_tool import ensure_limit, fallback_sql, validate_select_sql


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM orders",
        "SELECT * FROM orders; DELETE FROM orders",
        "UPDATE orders SET status = 'paid'",
        "SELECT * FROM orders INTO OUTFILE '/tmp/orders.csv'",
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(ValueError):
        validate_select_sql(sql)


def test_allows_select_sql() -> None:
    assert validate_select_sql("SELECT * FROM orders") == "SELECT * FROM orders"


def test_adds_limit_when_missing() -> None:
    assert ensure_limit("SELECT * FROM orders", 50).endswith("LIMIT 50")


def test_keeps_existing_limit() -> None:
    assert ensure_limit("SELECT * FROM orders LIMIT 10", 50).endswith("LIMIT 10")


def test_region_order_count_fallback() -> None:
    generated = fallback_sql("\u67e5\u8be2\u5404\u5730\u533a\u8ba2\u5355\u6570\u91cf")

    assert generated.used_fallback is True
    assert "COUNT(DISTINCT o.order_id) AS order_count" in generated.sql
    assert "GROUP BY r.region_name" in generated.sql


def test_industry_customer_count_fallback() -> None:
    generated = fallback_sql("\u7edf\u8ba1\u6bcf\u4e2a\u884c\u4e1a\u7684\u5ba2\u6237\u6570\u91cf")

    assert generated.used_fallback is True
    assert "COUNT(DISTINCT c.customer_id) AS customer_count" in generated.sql
    assert "GROUP BY c.industry" in generated.sql
