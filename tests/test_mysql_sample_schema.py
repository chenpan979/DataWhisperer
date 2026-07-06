from pathlib import Path


def test_mysql_sample_schema_is_product_like() -> None:
    script = Path("scripts/mysql_sample.sql").read_text(encoding="utf-8")

    assert script.count("CREATE TABLE") >= 18
    for table_name in [
        "customer_segments",
        "categories",
        "suppliers",
        "warehouses",
        "sales_channels",
        "campaigns",
        "coupons",
        "payments",
        "shipments",
        "returns",
        "product_reviews",
        "support_tickets",
    ]:
        assert f"CREATE TABLE {table_name}" in script

    assert "WHILE i <= 5000 DO" in script
    assert "FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)" in script
    assert "FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)" in script
