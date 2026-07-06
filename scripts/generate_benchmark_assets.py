from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """生成复杂样例库脚本和产品级评测集。

    这个脚本不是运行时依赖，而是给开发阶段使用的资产生成器：
    - scripts/mysql_sample.sql：多表、多关系、大样本 MySQL 示例库。
    - evals/text_to_sql_product_360_cases.jsonl：产品级 Text-to-SQL benchmark。
    - docs/v4-evaluation-benchmark-design.md：评测体系说明文档。
    """

    (ROOT / "scripts" / "mysql_sample.sql").write_text(
        _build_mysql_sample_sql(),
        encoding="utf-8",
    )
    stable_cases = _make_cases(
        [
            ("region_order_count", 9),
            ("industry_customer_count", 9),
            ("monthly_sales_trend", 9),
            ("category_sales_share", 9),
            ("region_avg_order_value", 9),
            ("product_sales_decline", 8),
            ("east_top_growth", 7),
        ],
        prefix="stable",
    )
    (ROOT / "evals" / "text_to_sql_cases.json").write_text(
        json.dumps(stable_cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    product_cases = _make_cases(
        [
            ("region_order_count", 72),
            ("industry_customer_count", 72),
            ("monthly_sales_trend", 48),
            ("category_sales_share", 48),
            ("region_avg_order_value", 48),
            ("product_sales_decline", 36),
            ("east_top_growth", 36),
        ],
        prefix="product",
    )
    (ROOT / "evals" / "text_to_sql_product_360_cases.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in product_cases),
        encoding="utf-8",
    )
    (ROOT / "docs" / "v4-evaluation-benchmark-design.md").write_text(
        _benchmark_doc(),
        encoding="utf-8",
    )
    print("generated mysql_sample.sql and 360 product benchmark cases")


def _build_mysql_sample_sql() -> str:
    lines: list[str] = []
    lines.extend(
        [
            "CREATE DATABASE IF NOT EXISTS datawhisperer_demo",
            "  DEFAULT CHARACTER SET utf8mb4",
            "  COLLATE utf8mb4_unicode_ci;",
            "",
            "USE datawhisperer_demo;",
            "",
        ]
    )
    lines.extend(_drop_tables())
    lines.extend(_create_tables())
    lines.extend(_create_indexes())
    lines.extend(_seed_dimensions())
    lines.extend(_seed_fact_procedure())
    return "\n".join(lines) + "\n"


def _drop_tables() -> list[str]:
    tables = [
        "support_tickets",
        "product_reviews",
        "returns",
        "shipments",
        "payments",
        "inventory_snapshots",
        "order_items",
        "orders",
        "coupons",
        "campaigns",
        "sales_channels",
        "products",
        "warehouses",
        "suppliers",
        "categories",
        "customers",
        "customer_segments",
        "regions",
    ]
    return [*(f"DROP TABLE IF EXISTS {table};" for table in tables), ""]


def _create_tables() -> list[str]:
    return [
        """CREATE TABLE regions (
    region_id INT PRIMARY KEY AUTO_INCREMENT,
    region_name VARCHAR(64) NOT NULL UNIQUE,
    region_tier VARCHAR(32) NOT NULL,
    manager_name VARCHAR(64) NOT NULL
);""",
        """CREATE TABLE customer_segments (
    segment_id INT PRIMARY KEY AUTO_INCREMENT,
    segment_name VARCHAR(64) NOT NULL UNIQUE,
    min_lifetime_value DECIMAL(12, 2) NOT NULL,
    description VARCHAR(255) NOT NULL
);""",
        """CREATE TABLE customers (
    customer_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_name VARCHAR(128) NOT NULL,
    industry VARCHAR(64) NOT NULL,
    region_id INT NOT NULL,
    segment_id INT NOT NULL,
    created_at DATE NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id),
    FOREIGN KEY (segment_id) REFERENCES customer_segments(segment_id)
);""",
        """CREATE TABLE categories (
    category_id INT PRIMARY KEY AUTO_INCREMENT,
    parent_category_id INT NULL,
    category_name VARCHAR(64) NOT NULL UNIQUE,
    category_level INT NOT NULL,
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);""",
        """CREATE TABLE suppliers (
    supplier_id INT PRIMARY KEY AUTO_INCREMENT,
    supplier_name VARCHAR(128) NOT NULL,
    region_id INT NOT NULL,
    rating DECIMAL(3, 2) NOT NULL,
    lead_time_days INT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);""",
        """CREATE TABLE warehouses (
    warehouse_id INT PRIMARY KEY AUTO_INCREMENT,
    warehouse_name VARCHAR(128) NOT NULL,
    region_id INT NOT NULL,
    capacity INT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);""",
        """CREATE TABLE products (
    product_id INT PRIMARY KEY AUTO_INCREMENT,
    product_name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    category_id INT NOT NULL,
    supplier_id INT NOT NULL,
    list_price DECIMAL(12, 2) NOT NULL,
    cost_price DECIMAL(12, 2) NOT NULL,
    launch_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);""",
        """CREATE TABLE sales_channels (
    channel_id INT PRIMARY KEY AUTO_INCREMENT,
    channel_name VARCHAR(64) NOT NULL UNIQUE,
    channel_type VARCHAR(32) NOT NULL,
    commission_rate DECIMAL(5, 4) NOT NULL
);""",
        """CREATE TABLE campaigns (
    campaign_id INT PRIMARY KEY AUTO_INCREMENT,
    campaign_name VARCHAR(128) NOT NULL,
    channel_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    budget DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (channel_id) REFERENCES sales_channels(channel_id)
);""",
        """CREATE TABLE coupons (
    coupon_id INT PRIMARY KEY AUTO_INCREMENT,
    coupon_code VARCHAR(64) NOT NULL UNIQUE,
    discount_type VARCHAR(32) NOT NULL,
    discount_value DECIMAL(12, 2) NOT NULL,
    min_order_amount DECIMAL(12, 2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);""",
        """CREATE TABLE orders (
    order_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT NOT NULL,
    region_id INT NOT NULL,
    channel_id INT NOT NULL,
    campaign_id INT NULL,
    coupon_id INT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (region_id) REFERENCES regions(region_id),
    FOREIGN KEY (channel_id) REFERENCES sales_channels(channel_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id),
    FOREIGN KEY (coupon_id) REFERENCES coupons(coupon_id)
);""",
        """CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    discount_rate DECIMAL(5, 4) NOT NULL DEFAULT 0,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
);""",
        """CREATE TABLE inventory_snapshots (
    snapshot_id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    snapshot_date DATE NOT NULL,
    stock_quantity INT NOT NULL,
    reserved_quantity INT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
);""",
        """CREATE TABLE payments (
    payment_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL UNIQUE,
    payment_method VARCHAR(32) NOT NULL,
    payment_status VARCHAR(32) NOT NULL,
    paid_amount DECIMAL(12, 2) NOT NULL,
    paid_at DATETIME NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);""",
        """CREATE TABLE shipments (
    shipment_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL UNIQUE,
    warehouse_id INT NOT NULL,
    carrier VARCHAR(64) NOT NULL,
    shipped_at DATETIME NULL,
    delivered_at DATETIME NULL,
    delivery_status VARCHAR(32) NOT NULL,
    shipping_fee DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
);""",
        """CREATE TABLE returns (
    return_id INT PRIMARY KEY AUTO_INCREMENT,
    order_item_id INT NOT NULL,
    return_date DATE NOT NULL,
    reason VARCHAR(128) NOT NULL,
    return_quantity INT NOT NULL,
    refund_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)
);""",
        """CREATE TABLE product_reviews (
    review_id INT PRIMARY KEY AUTO_INCREMENT,
    order_item_id INT NOT NULL,
    product_id INT NOT NULL,
    customer_id INT NOT NULL,
    rating INT NOT NULL,
    review_date DATE NOT NULL,
    sentiment VARCHAR(32) NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);""",
        """CREATE TABLE support_tickets (
    ticket_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT NOT NULL,
    order_id INT NULL,
    ticket_type VARCHAR(64) NOT NULL,
    priority VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    resolved_at DATETIME NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);""",
        "",
    ]


def _create_indexes() -> list[str]:
    indexes = [
        "CREATE INDEX idx_customers_region ON customers(region_id);",
        "CREATE INDEX idx_customers_segment ON customers(segment_id);",
        "CREATE INDEX idx_products_category ON products(category_id);",
        "CREATE INDEX idx_products_supplier ON products(supplier_id);",
        "CREATE INDEX idx_orders_customer ON orders(customer_id);",
        "CREATE INDEX idx_orders_region ON orders(region_id);",
        "CREATE INDEX idx_orders_channel ON orders(channel_id);",
        "CREATE INDEX idx_orders_campaign ON orders(campaign_id);",
        "CREATE INDEX idx_orders_date ON orders(order_date);",
        "CREATE INDEX idx_order_items_order ON order_items(order_id);",
        "CREATE INDEX idx_order_items_product ON order_items(product_id);",
        "CREATE INDEX idx_order_items_warehouse ON order_items(warehouse_id);",
        "CREATE INDEX idx_inventory_product_warehouse ON inventory_snapshots(product_id, warehouse_id);",
        "CREATE INDEX idx_returns_order_item ON returns(order_item_id);",
        "CREATE INDEX idx_reviews_product ON product_reviews(product_id);",
        "CREATE INDEX idx_tickets_customer ON support_tickets(customer_id);",
    ]
    return [*indexes, ""]


def _seed_dimensions() -> list[str]:
    return [
        """INSERT INTO regions (region_name, region_tier, manager_name) VALUES
('East China', 'tier_1', 'Lin Chen'),
('North China', 'tier_1', 'Wei Zhang'),
('South China', 'tier_1', 'Yun Li'),
('West China', 'tier_2', 'Qiang Zhou'),
('Central China', 'tier_2', 'Min Zhao'),
('Northeast China', 'tier_3', 'Han Wu');""",
        """INSERT INTO customer_segments (segment_name, min_lifetime_value, description) VALUES
('New', 0.00, 'Newly acquired customers'),
('Growth', 10000.00, 'Customers with growing order value'),
('Loyal', 50000.00, 'Repeat customers with stable demand'),
('VIP', 150000.00, 'High value customers'),
('At Risk', 20000.00, 'Customers with recent activity decline');""",
        """INSERT INTO categories (parent_category_id, category_name, category_level) VALUES
(NULL, 'Electronics', 1),
(NULL, 'Home Appliance', 1),
(NULL, 'Office', 1),
(NULL, 'Sports', 1),
(NULL, 'Outdoor', 1),
(NULL, 'Beauty', 1),
(NULL, 'Mother Baby', 1),
(1, 'Computer', 2),
(1, 'Mobile Device', 2),
(2, 'Kitchen Appliance', 2),
(2, 'Cleaning Appliance', 2),
(3, 'Office Furniture', 2),
(4, 'Fitness Gear', 2),
(5, 'Travel Gear', 2),
(6, 'Personal Care', 2),
(7, 'Kids Furniture', 2);""",
        """INSERT INTO suppliers (supplier_name, region_id, rating, lead_time_days) VALUES
('Orion Supply', 1, 4.80, 5),
('Harbor Electronics', 1, 4.65, 7),
('North Star Manufacturing', 2, 4.52, 9),
('South Home Factory', 3, 4.40, 8),
('West Outdoor Group', 4, 4.35, 10),
('Central Office Works', 5, 4.58, 6),
('Northeast Beauty Lab', 6, 4.20, 12),
('Aurora Kids Co', 3, 4.46, 11);""",
        """INSERT INTO warehouses (warehouse_name, region_id, capacity) VALUES
('Shanghai Main Warehouse', 1, 120000),
('Beijing North Warehouse', 2, 90000),
('Guangzhou South Warehouse', 3, 100000),
('Chengdu West Warehouse', 4, 70000),
('Wuhan Central Warehouse', 5, 85000),
('Shenyang Northeast Warehouse', 6, 65000),
('Hangzhou Fast Fulfillment', 1, 75000),
('Shenzhen Cross-border Warehouse', 3, 60000);""",
        """INSERT INTO sales_channels (channel_name, channel_type, commission_rate) VALUES
('Official Store', 'owned', 0.0000),
('Tmall Flagship', 'marketplace', 0.0450),
('JD Flagship', 'marketplace', 0.0400),
('Douyin Shop', 'content', 0.0550),
('WeChat Mini Program', 'private_domain', 0.0150),
('Offline Key Account', 'offline', 0.0200);""",
        """INSERT INTO campaigns (campaign_name, channel_id, start_date, end_date, budget) VALUES
('618 Mega Sale', 2, DATE_SUB(CURDATE(), INTERVAL 40 DAY), DATE_SUB(CURDATE(), INTERVAL 15 DAY), 300000.00),
('Back To School', 3, DATE_SUB(CURDATE(), INTERVAL 120 DAY), DATE_SUB(CURDATE(), INTERVAL 80 DAY), 180000.00),
('Winter Home Upgrade', 1, DATE_SUB(CURDATE(), INTERVAL 220 DAY), DATE_SUB(CURDATE(), INTERVAL 180 DAY), 160000.00),
('Private Domain Member Day', 5, DATE_SUB(CURDATE(), INTERVAL 70 DAY), DATE_SUB(CURDATE(), INTERVAL 65 DAY), 80000.00),
('Outdoor Spring Trip', 4, DATE_SUB(CURDATE(), INTERVAL 150 DAY), DATE_SUB(CURDATE(), INTERVAL 110 DAY), 120000.00),
('Office Refresh', 6, DATE_SUB(CURDATE(), INTERVAL 260 DAY), DATE_SUB(CURDATE(), INTERVAL 230 DAY), 90000.00),
('Beauty New Arrival', 4, DATE_SUB(CURDATE(), INTERVAL 95 DAY), DATE_SUB(CURDATE(), INTERVAL 50 DAY), 110000.00),
('VIP Appreciation', 5, DATE_SUB(CURDATE(), INTERVAL 25 DAY), DATE_ADD(CURDATE(), INTERVAL 5 DAY), 70000.00);""",
        """INSERT INTO coupons (coupon_code, discount_type, discount_value, min_order_amount, start_date, end_date) VALUES
('NEW50', 'amount', 50.00, 299.00, DATE_SUB(CURDATE(), INTERVAL 365 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY)),
('VIP200', 'amount', 200.00, 2999.00, DATE_SUB(CURDATE(), INTERVAL 365 DAY), DATE_ADD(CURDATE(), INTERVAL 120 DAY)),
('HOME8', 'percent', 0.08, 999.00, DATE_SUB(CURDATE(), INTERVAL 240 DAY), DATE_ADD(CURDATE(), INTERVAL 60 DAY)),
('OFFICE100', 'amount', 100.00, 1299.00, DATE_SUB(CURDATE(), INTERVAL 240 DAY), DATE_ADD(CURDATE(), INTERVAL 60 DAY)),
('SPORTS30', 'amount', 30.00, 199.00, DATE_SUB(CURDATE(), INTERVAL 180 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY)),
('BEAUTY20', 'amount', 20.00, 159.00, DATE_SUB(CURDATE(), INTERVAL 180 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY));""",
        _products_sql(),
        "",
    ]


def _products_sql() -> str:
    products = [
        ("Aurora Laptop", "Electronics", 8, 1, 6999, 5100),
        ("Breeze Phone", "Electronics", 9, 2, 3999, 2780),
        ("Cipher Tablet", "Electronics", 9, 2, 2999, 2100),
        ("Dynamo Monitor", "Electronics", 8, 3, 1599, 980),
        ("Echo Earbuds", "Electronics", 9, 2, 699, 390),
        ("Nova Smart Watch", "Electronics", 9, 2, 1299, 760),
        ("Comet Coffee Maker", "Home Appliance", 10, 4, 899, 520),
        ("Dawn Air Purifier", "Home Appliance", 11, 4, 1299, 810),
        ("Ember Oven", "Home Appliance", 10, 4, 2399, 1510),
        ("Frost Mini Fridge", "Home Appliance", 10, 4, 1899, 1210),
        ("Halo Vacuum", "Home Appliance", 11, 4, 1699, 1030),
        ("Iris Humidifier", "Home Appliance", 11, 4, 499, 260),
        ("Echo Office Chair", "Office", 12, 6, 599, 310),
        ("Flux Standing Desk", "Office", 12, 6, 1899, 1180),
        ("Graph Notebook Pack", "Office", 3, 6, 99, 38),
        ("Helix Desk Lamp", "Office", 3, 6, 269, 128),
        ("Ink Printer", "Office", 3, 6, 1199, 760),
        ("Jade Storage Cabinet", "Office", 12, 6, 799, 450),
        ("Kite Running Shoes", "Sports", 13, 5, 499, 230),
        ("Lumen Yoga Mat", "Sports", 13, 5, 159, 65),
        ("Motion Bike Helmet", "Sports", 13, 5, 329, 150),
        ("Pulse Dumbbell Set", "Sports", 13, 5, 459, 220),
        ("Quartz Camping Tent", "Outdoor", 14, 5, 899, 490),
        ("River Backpack", "Outdoor", 14, 5, 399, 180),
        ("Solar Hiking Jacket", "Outdoor", 14, 5, 699, 350),
        ("Terra Travel Bottle", "Outdoor", 14, 5, 129, 52),
        ("Umber Skin Care Set", "Beauty", 15, 7, 299, 128),
        ("Velvet Hair Dryer", "Beauty", 15, 7, 399, 205),
        ("Willow Baby Stroller", "Mother Baby", 16, 8, 1499, 870),
        ("Zen Kids Desk", "Mother Baby", 16, 8, 899, 510),
    ]
    values = []
    for index, (name, category, category_id, supplier_id, list_price, cost_price) in enumerate(products):
        launch = f"DATE_SUB(CURDATE(), INTERVAL {420 - index * 9} DAY)"
        values.append(
            f"('{name}', '{category}', {category_id}, {supplier_id}, "
            f"{list_price:.2f}, {cost_price:.2f}, {launch}, 'active')"
        )
    return "INSERT INTO products (product_name, category, category_id, supplier_id, list_price, cost_price, launch_date, status) VALUES\n" + ",\n".join(values) + ";"


def _seed_fact_procedure() -> list[str]:
    return [
        """DROP PROCEDURE IF EXISTS seed_datawhisperer_demo;
DELIMITER $$
CREATE PROCEDURE seed_datawhisperer_demo()
BEGIN
    DECLARE i INT DEFAULT 1;
    DECLARE current_order_id INT;
    DECLARE first_order_item_id INT;
    DECLARE first_product_id INT;
    DECLARE second_product_id INT;
    DECLARE third_product_id INT;
    DECLARE current_customer_id INT;
    DECLARE current_region_id INT;
    DECLARE current_channel_id INT;
    DECLARE current_warehouse_id INT;
    DECLARE current_status VARCHAR(32);
    DECLARE current_order_total DECIMAL(12, 2);

    WHILE i <= 500 DO
        INSERT INTO customers (customer_name, industry, region_id, segment_id, created_at)
        VALUES (
            CONCAT('Customer ', LPAD(i, 4, '0')),
            ELT(1 + MOD(i, 8), 'Retail', 'Technology', 'Food', 'Trading', 'Finance', 'Manufacturing', 'Education', 'Healthcare'),
            1 + MOD(i * 5, 6),
            1 + MOD(i * 3, 5),
            DATE_SUB(CURDATE(), INTERVAL MOD(i * 11, 900) DAY)
        );
        SET i = i + 1;
    END WHILE;

    SET i = 1;
    WHILE i <= 2400 DO
        SET first_product_id = 1 + MOD(i * 5, 30);
        SET second_product_id = 1 + MOD(i * 7 + 3, 30);
        INSERT INTO inventory_snapshots (product_id, warehouse_id, snapshot_date, stock_quantity, reserved_quantity)
        VALUES (
            first_product_id,
            1 + MOD(i * 3, 8),
            DATE_SUB(CURDATE(), INTERVAL MOD(i * 2, 180) DAY),
            50 + MOD(i * 17, 950),
            MOD(i * 7, 80)
        );
        IF MOD(i, 2) = 0 THEN
            INSERT INTO inventory_snapshots (product_id, warehouse_id, snapshot_date, stock_quantity, reserved_quantity)
            VALUES (
                second_product_id,
                1 + MOD(i * 5, 8),
                DATE_SUB(CURDATE(), INTERVAL MOD(i * 3, 180) DAY),
                30 + MOD(i * 13, 700),
                MOD(i * 5, 70)
            );
        END IF;
        SET i = i + 1;
    END WHILE;

    SET i = 1;
    WHILE i <= 5000 DO
        SET current_customer_id = 1 + MOD(i * 7, 500);
        SET current_region_id = 1 + MOD(i * 5, 6);
        SET current_channel_id = 1 + MOD(i * 3, 6);
        SET current_status = ELT(1 + MOD(i, 12), 'paid', 'paid', 'paid', 'paid', 'paid', 'completed', 'completed', 'shipped', 'refunded', 'cancelled', 'paid', 'completed');

        INSERT INTO orders (customer_id, region_id, channel_id, campaign_id, coupon_id, order_date, status)
        VALUES (
            current_customer_id,
            current_region_id,
            current_channel_id,
            CASE WHEN MOD(i, 4) = 0 THEN 1 + MOD(i, 8) ELSE NULL END,
            CASE WHEN MOD(i, 5) = 0 THEN 1 + MOD(i, 6) ELSE NULL END,
            DATE_SUB(CURDATE(), INTERVAL MOD(i * 7, 720) DAY),
            current_status
        );

        SET current_order_id = LAST_INSERT_ID();
        SET first_product_id = 1 + MOD(i * 5, 30);
        SET second_product_id = 1 + MOD(i * 7 + 3, 30);
        SET third_product_id = 1 + MOD(i * 11 + 5, 30);
        SET current_warehouse_id = 1 + MOD(i * 3, 8);

        INSERT INTO order_items (order_id, product_id, warehouse_id, quantity, unit_price, discount_rate)
        VALUES (
            current_order_id,
            first_product_id,
            current_warehouse_id,
            1 + MOD(i * 3, 24),
            ROUND((SELECT list_price FROM products WHERE product_id = first_product_id) * (0.88 + MOD(i, 9) / 100), 2),
            ROUND(MOD(i, 6) / 100, 4)
        );
        SET first_order_item_id = LAST_INSERT_ID();

        IF MOD(i, 2) = 0 THEN
            INSERT INTO order_items (order_id, product_id, warehouse_id, quantity, unit_price, discount_rate)
            VALUES (
                current_order_id,
                second_product_id,
                1 + MOD(i * 5, 8),
                1 + MOD(i * 5, 18),
                ROUND((SELECT list_price FROM products WHERE product_id = second_product_id) * (0.90 + MOD(i, 7) / 100), 2),
                ROUND(MOD(i, 5) / 100, 4)
            );
        END IF;

        IF MOD(i, 5) = 0 THEN
            INSERT INTO order_items (order_id, product_id, warehouse_id, quantity, unit_price, discount_rate)
            VALUES (
                current_order_id,
                third_product_id,
                1 + MOD(i * 7, 8),
                1 + MOD(i * 2, 12),
                ROUND((SELECT list_price FROM products WHERE product_id = third_product_id) * (0.86 + MOD(i, 11) / 100), 2),
                ROUND(MOD(i, 8) / 100, 4)
            );
        END IF;

        SELECT ROUND(SUM(quantity * unit_price * (1 - discount_rate)), 2)
          INTO current_order_total
          FROM order_items
         WHERE order_id = current_order_id;

        INSERT INTO payments (order_id, payment_method, payment_status, paid_amount, paid_at)
        VALUES (
            current_order_id,
            ELT(1 + MOD(i, 5), 'alipay', 'wechat_pay', 'credit_card', 'bank_transfer', 'corporate_credit'),
            CASE WHEN current_status = 'cancelled' THEN 'failed' WHEN current_status = 'refunded' THEN 'refunded' ELSE 'paid' END,
            CASE WHEN current_status = 'cancelled' THEN 0 ELSE current_order_total END,
            CASE WHEN current_status = 'cancelled' THEN NULL ELSE DATE_ADD(DATE_SUB(NOW(), INTERVAL MOD(i * 7, 720) DAY), INTERVAL MOD(i, 12) HOUR) END
        );

        IF current_status <> 'cancelled' THEN
            INSERT INTO shipments (order_id, warehouse_id, carrier, shipped_at, delivered_at, delivery_status, shipping_fee)
            VALUES (
                current_order_id,
                current_warehouse_id,
                ELT(1 + MOD(i, 4), 'SF Express', 'JD Logistics', 'ZTO Express', 'YTO Express'),
                DATE_ADD(DATE_SUB(NOW(), INTERVAL MOD(i * 7, 720) DAY), INTERVAL 1 DAY),
                DATE_ADD(DATE_SUB(NOW(), INTERVAL MOD(i * 7, 720) DAY), INTERVAL 3 + MOD(i, 5) DAY),
                CASE WHEN current_status = 'shipped' THEN 'in_transit' ELSE 'delivered' END,
                ROUND(8 + MOD(i, 18) * 1.5, 2)
            );
        END IF;

        IF MOD(i, 14) = 0 THEN
            INSERT INTO returns (order_item_id, return_date, reason, return_quantity, refund_amount, status)
            VALUES (
                first_order_item_id,
                DATE_SUB(CURDATE(), INTERVAL MOD(i * 3, 180) DAY),
                ELT(1 + MOD(i, 5), 'quality_issue', 'wrong_item', 'late_delivery', 'no_longer_needed', 'price_reason'),
                1,
                ROUND((SELECT unit_price FROM order_items WHERE order_item_id = first_order_item_id), 2),
                ELT(1 + MOD(i, 3), 'approved', 'processing', 'completed')
            );
        END IF;

        IF MOD(i, 3) = 0 AND current_status <> 'cancelled' THEN
            INSERT INTO product_reviews (order_item_id, product_id, customer_id, rating, review_date, sentiment)
            VALUES (
                first_order_item_id,
                first_product_id,
                current_customer_id,
                3 + MOD(i, 3),
                DATE_SUB(CURDATE(), INTERVAL MOD(i * 5, 360) DAY),
                ELT(1 + MOD(i, 3), 'positive', 'neutral', 'negative')
            );
        END IF;

        IF MOD(i, 20) = 0 THEN
            INSERT INTO support_tickets (customer_id, order_id, ticket_type, priority, status, created_at, resolved_at)
            VALUES (
                current_customer_id,
                current_order_id,
                ELT(1 + MOD(i, 5), 'delivery', 'refund', 'invoice', 'product_usage', 'account'),
                ELT(1 + MOD(i, 3), 'low', 'medium', 'high'),
                ELT(1 + MOD(i, 4), 'open', 'processing', 'resolved', 'closed'),
                DATE_SUB(NOW(), INTERVAL MOD(i * 4, 365) DAY),
                CASE WHEN MOD(i, 4) IN (2, 3) THEN DATE_SUB(NOW(), INTERVAL MOD(i * 4, 300) DAY) ELSE NULL END
            );
        END IF;

        SET i = i + 1;
    END WHILE;
END$$
DELIMITER ;

CALL seed_datawhisperer_demo();
DROP PROCEDURE seed_datawhisperer_demo;""",
    ]


def _case_specs() -> dict[str, dict[str, object]]:
    specs: dict[str, dict[str, object]] = {
        "region_order_count": {
            "difficulty": "simple",
            "requires_rag": False,
            "ablation_tags": ["baseline"],
            "tags": ["region", "orders", "bar"],
            "expected_sql_contains": [
                "r.region_name",
                "COUNT(DISTINCT o.order_id) AS order_count",
                "GROUP BY r.region_name",
            ],
            "expected_columns": ["region_name", "order_count"],
            "expected_chart_type": "bar",
            "questions": [
                "查询各地区订单数量",
                "各地区订单数量对比",
                "按地区统计订单数",
                "哪个地区订单量最高",
                "地区维度订单数量排行",
                "每个地区有多少订单",
                "查看地区订单分布",
                "region order count ranking",
                "查询订单数量按地区分布",
                "各地区订单数量柱状图",
                "地区订单表现看板",
                "统计区域订单规模",
            ],
        },
        "industry_customer_count": {
            "difficulty": "simple",
            "requires_rag": False,
            "ablation_tags": ["baseline"],
            "tags": ["industry", "customer", "bar"],
            "expected_sql_contains": [
                "c.industry",
                "COUNT(DISTINCT c.customer_id) AS customer_count",
                "GROUP BY c.industry",
            ],
            "expected_columns": ["industry", "customer_count"],
            "expected_chart_type": "bar",
            "questions": [
                "查询各行业客户数量",
                "按行业统计客户数",
                "行业维度客户数量排行",
                "每个行业有多少客户",
                "查看各行业客户数量分布",
                "industry customer count ranking",
                "客户行业分布统计",
                "查询行业客户 count",
                "各行业客户数量柱状图",
                "统计客户所在行业分布",
                "不同行业客户规模对比",
                "客户数量按行业汇总",
            ],
        },
        "monthly_sales_trend": {
            "difficulty": "medium",
            "requires_rag": True,
            "ablation_tags": ["rag_metric", "sql_of_thought"],
            "tags": ["sales", "trend", "line", "time_series"],
            "expected_sql_contains": [
                "DATE_FORMAT(o.order_date, '%Y-%m') AS month",
                "SUM(oi.quantity * oi.unit_price)",
                "GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')",
            ],
            "expected_columns": ["month", "sales_amount"],
            "expected_chart_type": "line",
            "questions": [
                "查询最近 6 个月每月销售额趋势",
                "最近6个月销售额走势",
                "近 6 个月 GMV 趋势",
                "查看最近六个月月度销售额",
                "最近 6 个月每月成交额变化",
                "过去6个月销售金额趋势图",
                "最近 6 个月销售额折线图",
                "按月份汇总最近6个月销售额",
                "查询近六个月 GMV 变化",
                "最近6个月销售额有没有增长",
                "月度销售趋势分析",
                "最近 6 个月成交额趋势看板",
            ],
        },
        "category_sales_share": {
            "difficulty": "medium",
            "requires_rag": True,
            "ablation_tags": ["rag_metric"],
            "tags": ["sales", "category", "pie", "share"],
            "expected_sql_contains": [
                "p.category",
                "SUM(oi.quantity * oi.unit_price)",
                "GROUP BY p.category",
            ],
            "expected_columns": ["category", "sales_amount"],
            "expected_chart_type": "pie",
            "questions": [
                "查询各商品品类销售额占比",
                "各品类销售额占比",
                "商品品类 GMV 占比",
                "查看各商品类别销售贡献占比",
                "按商品品类统计销售额占比",
                "各品类销售金额 share",
                "商品结构占比分析",
                "品类销售额贡献分析",
                "商品品类销售额饼图",
                "哪些商品品类贡献最高",
                "商品类别销售份额",
                "category sales share",
            ],
        },
        "region_avg_order_value": {
            "difficulty": "medium",
            "requires_rag": True,
            "ablation_tags": ["rag_metric", "sql_of_thought"],
            "tags": ["region", "aov", "bar"],
            "expected_sql_contains": [
                "r.region_name",
                "COUNT(DISTINCT o.order_id)",
                "avg_order_value",
            ],
            "expected_columns": ["region_name", "avg_order_value"],
            "expected_chart_type": "bar",
            "questions": [
                "哪个地区客单价最高",
                "各地区客单价对比",
                "按地区统计平均订单金额",
                "哪个区域的平均订单价值最高",
                "地区维度 AOV 排名",
                "查询区域客单价排行",
                "各地区平均客单价柱状图",
                "地区订单均价对比",
                "region average order value ranking",
                "客单价最高的地区是哪里",
                "地区客单价表现看板",
                "统计每个地区的 AOV",
            ],
        },
        "product_sales_decline": {
            "difficulty": "complex",
            "requires_rag": False,
            "ablation_tags": ["sql_of_thought", "sql_repair"],
            "tags": ["product", "decline", "bar", "period_compare"],
            "expected_sql_contains": ["previous_month", "last_month", "amount_change"],
            "expected_columns": [
                "product_name",
                "previous_amount",
                "last_amount",
                "amount_change",
            ],
            "expected_chart_type": "bar",
            "questions": [
                "找出销售额下滑最明显的商品",
                "哪些商品销售额下降最多",
                "查询销售额下滑最大的产品",
                "最近一个月销售额跌幅最大的商品",
                "商品销售下滑预警",
                "找出环比销售金额下降最明显的商品",
                "sales decline products ranking",
                "产品销售额下降榜单",
                "上月到本月销售额下降最大的商品",
                "哪些产品出现明显下滑",
                "商品销售额下滑分析",
                "找出销售额下降最严重的 SKU",
            ],
        },
        "east_top_growth": {
            "difficulty": "complex",
            "requires_rag": False,
            "ablation_tags": ["sql_of_thought", "sql_repair", "multi_agent"],
            "tags": ["east", "top", "growth", "bar"],
            "expected_sql_contains": ["current_q", "previous_q", "growth_rate_percent"],
            "expected_columns": [
                "product_name",
                "current_quantity",
                "previous_quantity",
                "growth_rate_percent",
            ],
            "expected_chart_type": "bar",
            "questions": [
                "查询华东地区销量前三的商品及其环比增长",
                "华东销量 top3 商品",
                "East China top 3 sales volume products",
                "查询华东地区销量前三商品",
                "华东销售量前三商品环比",
                "华东地区销量 top 商品及增长率",
                "查询 East China 销量前三商品及环比",
                "华东地区销量前三的产品",
                "华东地区 top3 产品销量变化",
                "华东热销商品前三名和增长率",
                "华东区域销量排名前三商品",
                "查询华东销量前三商品的环比表现",
            ],
        },
    }
    for spec in specs.values():
        spec["forbidden_sql_contains"] = ["INSERT", "UPDATE", "DELETE", "DROP"]
        spec["must_be_safe"] = True
    return specs


def _make_cases(layout: list[tuple[str, int]], prefix: str) -> list[dict[str, object]]:
    specs = _case_specs()
    stable_questions = _stable_question_overrides()
    suffixes = [
        "",
        "，用于经营看板",
        "，按结果从高到低展示",
        "，给业务负责人看",
        "，用于周会复盘",
        "，要求返回可画图的数据",
        "，帮我做一个快速分析",
        "，用于版本回归测试",
        "，用于复杂库 schema linking 验证",
        "，作为消融实验样本",
    ]
    cases: list[dict[str, object]] = []
    for key, count in layout:
        spec = specs[key]
        questions = stable_questions.get(key, spec["questions"]) if prefix == "stable" else spec["questions"]
        assert isinstance(questions, list)
        for index in range(count):
            cases.append(
                {
                    "id": f"{prefix}_{key}_{index + 1:03d}",
                    "question": str(questions[index % len(questions)])
                    + suffixes[(index // len(questions)) % len(suffixes)],
                    "difficulty": spec["difficulty"],
                    "requires_rag": spec["requires_rag"],
                    "ablation_tags": spec["ablation_tags"],
                    "tags": spec["tags"],
                    "expected_sql_contains": spec["expected_sql_contains"],
                    "forbidden_sql_contains": spec["forbidden_sql_contains"],
                    "expected_columns": spec["expected_columns"],
                    "expected_chart_type": spec["expected_chart_type"],
                    "must_be_safe": True,
                }
            )
    return cases


def _stable_question_overrides() -> dict[str, list[str]]:
    """??????????????????????"""

    return {
        "region_order_count": [
            "\u67e5\u8be2\u5404\u5730\u533a\u8ba2\u5355\u6570\u91cf",
            "\u5404\u5730\u533a\u8ba2\u5355\u6570\u91cf\u5bf9\u6bd4",
            "\u67e5\u8be2\u8ba2\u5355\u6570\u91cf\u6309\u5730\u533a\u5206\u5e03",
            "\u5404\u5730\u533a\u8ba2\u5355\u6570\u91cf\u67f1\u72b6\u56fe",
            "region order count ranking",
        ],
        "industry_customer_count": [
            "\u67e5\u8be2\u5404\u884c\u4e1a\u5ba2\u6237\u6570\u91cf",
            "\u6309\u884c\u4e1a\u7edf\u8ba1\u5ba2\u6237\u6570\u91cf",
            "\u6bcf\u4e2a\u884c\u4e1a\u6709\u591a\u5c11\u5ba2\u6237\u6570\u91cf",
            "\u5404\u884c\u4e1a\u5ba2\u6237\u6570\u91cf\u67f1\u72b6\u56fe",
            "industry customer count ranking",
        ],
        "monthly_sales_trend": [
            "\u67e5\u8be2\u6700\u8fd1 6 \u4e2a\u6708\u6bcf\u6708\u9500\u552e\u989d\u8d8b\u52bf",
            "\u6700\u8fd16\u4e2a\u6708\u9500\u552e\u989d\u8d70\u52bf",
            "\u8fd1 6 \u4e2a\u6708 GMV \u8d8b\u52bf",
            "\u6700\u8fd1 6 \u4e2a\u6708\u9500\u552e\u989d\u6298\u7ebf\u56fe",
            "\u6700\u8fd16\u4e2a\u6708\u9500\u552e\u989d\u6709\u6ca1\u6709\u589e\u957f",
        ],
        "category_sales_share": [
            "\u67e5\u8be2\u5404\u5546\u54c1\u54c1\u7c7b\u9500\u552e\u989d\u5360\u6bd4",
            "\u5404\u54c1\u7c7b\u9500\u552e\u989d\u5360\u6bd4",
            "\u5546\u54c1\u54c1\u7c7b GMV \u5360\u6bd4",
            "\u6309\u5546\u54c1\u54c1\u7c7b\u7edf\u8ba1\u9500\u552e\u989d\u5360\u6bd4",
            "category sales share",
        ],
        "region_avg_order_value": [
            "\u54ea\u4e2a\u5730\u533a\u5ba2\u5355\u4ef7\u6700\u9ad8",
            "\u5404\u5730\u533a\u5ba2\u5355\u4ef7\u5bf9\u6bd4",
            "\u5730\u533a\u7ef4\u5ea6 AOV \u6392\u540d",
            "\u67e5\u8be2\u533a\u57df\u5ba2\u5355\u4ef7\u6392\u884c",
            "region average order value ranking",
        ],
        "product_sales_decline": [
            "\u627e\u51fa\u9500\u552e\u989d\u4e0b\u6ed1\u6700\u660e\u663e\u7684\u5546\u54c1",
            "\u67e5\u8be2\u9500\u552e\u989d\u4e0b\u6ed1\u6700\u5927\u7684\u4ea7\u54c1",
            "\u5546\u54c1\u9500\u552e\u4e0b\u6ed1\u9884\u8b66",
            "sales decline products ranking",
            "\u5546\u54c1\u9500\u552e\u989d\u4e0b\u6ed1\u5206\u6790",
        ],
        "east_top_growth": [
            "\u67e5\u8be2\u534e\u4e1c\u5730\u533a\u9500\u91cf\u524d\u4e09\u7684\u5546\u54c1\u53ca\u5176\u73af\u6bd4\u589e\u957f",
            "\u534e\u4e1c\u9500\u91cf top3 \u5546\u54c1",
            "East China top 3 sales volume products",
            "\u67e5\u8be2\u534e\u4e1c\u5730\u533a\u9500\u91cf\u524d\u4e09\u5546\u54c1",
            "\u534e\u4e1c\u9500\u552e\u91cf\u524d\u4e09\u5546\u54c1\u73af\u6bd4",
        ],
    }


def _benchmark_doc() -> str:
    return """# V4 评测体系与大样本 Benchmark 设计

DataWhisperer 后续要证明的不只是“能生成 SQL”，而是：在不同 SQL 难度、不同业务知识依赖、不同 Agent 组合下，系统质量是否稳定提升。

## 1. 样例数据库规模

`scripts/mysql_sample.sql` 已从早期演示数据升级为更接近真实企业库的电商经营分析样例库。

核心规模：

- 6 个地区。
- 5 类客户分层。
- 500 个客户，覆盖零售、科技、食品、贸易、金融、制造、教育、医疗等行业。
- 16 个品类节点，包含父子品类关系。
- 8 个供应商。
- 8 个仓库。
- 30 个商品。
- 6 个销售渠道。
- 8 个营销活动。
- 6 类优惠券。
- 5000 笔订单。
- 8000 条以上订单明细。
- 3000 条以上库存快照。
- 支付、物流、退货、评价、客服工单等经营链路数据。

## 2. 表结构复杂度

当前样例库从 5 张表扩展为 18 张表：

| 模块 | 表 | 说明 |
| --- | --- | --- |
| 地区与客户 | regions、customer_segments、customers | 地区、客户行业、客户分层 |
| 商品中心 | categories、suppliers、products | 父子品类、供应商、商品主数据 |
| 履约库存 | warehouses、inventory_snapshots | 仓库与库存快照 |
| 营销渠道 | sales_channels、campaigns、coupons | 渠道、活动、优惠券 |
| 交易核心 | orders、order_items、payments、shipments | 订单、明细、支付、物流 |
| 售后体验 | returns、product_reviews、support_tickets | 退货、评价、客服工单 |

保留兼容字段：

- `products.category` 仍然保留，兼容现有 Text-to-SQL 和图表逻辑。
- `orders.region_id / customer_id / order_date / status` 仍然保留。
- `order_items.product_id / quantity / unit_price` 仍然保留。

因此旧问题仍能跑，新问题可以逐步扩展到：渠道 ROI、活动效果、供应商交付、库存周转、退货率、评价情绪、客服响应等更复杂场景。

## 3. 测试集分层

默认内置集：`evals/text_to_sql_cases.json`

- 60 条稳定回归用例。
- 用于每次开发后快速验证。
- 保证当前 fallback / prompt 链路能稳定通过。

产品级大评测集：`evals/text_to_sql_product_360_cases.jsonl`

- 360 条用例。
- 适合上传到“测试集管理”，再到“评测中心”运行。
- 用于版本发布前、CSDN 展示、面试讲解和后续消融实验。

难度分布：

| 难度 | 占比 | 典型能力 |
| --- | --- | --- |
| simple | 40% | 单表/简单 Join、分组统计、排序 |
| medium | 40% | 多表 Join、聚合、时间趋势、占比、客单价 |
| complex | 20% | CTE、环比、TopN、销售下滑、跨周期比较 |

## 4. 消融实验规划

| 实验版本 | RAG | SQL-of-Thought | SQL 修复 | 多 Agent | 目的 |
| --- | --- | --- | --- | --- | --- |
| Baseline | 否 | 否 | 否 | 否 | 看基础 Text-to-SQL 能力 |
| + RAG | 是 | 否 | 否 | 否 | 证明指标口径检索的收益 |
| + SQL-of-Thought | 是 | 是 | 否 | 是 | 证明查询规划和 schema linking 的收益 |
| + SQL Repair | 是 | 是 | 是 | 是 | 证明错误诊断和修复 Agent 的收益 |
| Full Agent | 是 | 是 | 是 | 是 | 当前完整链路效果 |

## 5. 下一步

- 前端评测中心展示 simple / medium / complex 准确率。
- 增加有 RAG / 无 RAG 的同集对比。
- 增加 SQL-of-Thought 与 SQLRepairAgent 的消融开关。
- 把评测结果落库，形成版本趋势和失败案例库。
- 在大样例库基础上继续扩展渠道、库存、售后、客服类复杂 SQL 测试集。
"""


if __name__ == "__main__":
    main()
