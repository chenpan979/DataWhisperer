CREATE DATABASE IF NOT EXISTS datawhisperer_demo
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE datawhisperer_demo;

DROP TABLE IF EXISTS support_tickets;
DROP TABLE IF EXISTS product_reviews;
DROP TABLE IF EXISTS returns;
DROP TABLE IF EXISTS shipments;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS inventory_snapshots;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS campaigns;
DROP TABLE IF EXISTS sales_channels;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS warehouses;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS customer_segments;
DROP TABLE IF EXISTS regions;

CREATE TABLE regions (
    region_id INT PRIMARY KEY AUTO_INCREMENT,
    region_name VARCHAR(64) NOT NULL UNIQUE,
    region_tier VARCHAR(32) NOT NULL,
    manager_name VARCHAR(64) NOT NULL
);
CREATE TABLE customer_segments (
    segment_id INT PRIMARY KEY AUTO_INCREMENT,
    segment_name VARCHAR(64) NOT NULL UNIQUE,
    min_lifetime_value DECIMAL(12, 2) NOT NULL,
    description VARCHAR(255) NOT NULL
);
CREATE TABLE customers (
    customer_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_name VARCHAR(128) NOT NULL,
    industry VARCHAR(64) NOT NULL,
    region_id INT NOT NULL,
    segment_id INT NOT NULL,
    created_at DATE NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id),
    FOREIGN KEY (segment_id) REFERENCES customer_segments(segment_id)
);
CREATE TABLE categories (
    category_id INT PRIMARY KEY AUTO_INCREMENT,
    parent_category_id INT NULL,
    category_name VARCHAR(64) NOT NULL UNIQUE,
    category_level INT NOT NULL,
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);
CREATE TABLE suppliers (
    supplier_id INT PRIMARY KEY AUTO_INCREMENT,
    supplier_name VARCHAR(128) NOT NULL,
    region_id INT NOT NULL,
    rating DECIMAL(3, 2) NOT NULL,
    lead_time_days INT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);
CREATE TABLE warehouses (
    warehouse_id INT PRIMARY KEY AUTO_INCREMENT,
    warehouse_name VARCHAR(128) NOT NULL,
    region_id INT NOT NULL,
    capacity INT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);
CREATE TABLE products (
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
);
CREATE TABLE sales_channels (
    channel_id INT PRIMARY KEY AUTO_INCREMENT,
    channel_name VARCHAR(64) NOT NULL UNIQUE,
    channel_type VARCHAR(32) NOT NULL,
    commission_rate DECIMAL(5, 4) NOT NULL
);
CREATE TABLE campaigns (
    campaign_id INT PRIMARY KEY AUTO_INCREMENT,
    campaign_name VARCHAR(128) NOT NULL,
    channel_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    budget DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (channel_id) REFERENCES sales_channels(channel_id)
);
CREATE TABLE coupons (
    coupon_id INT PRIMARY KEY AUTO_INCREMENT,
    coupon_code VARCHAR(64) NOT NULL UNIQUE,
    discount_type VARCHAR(32) NOT NULL,
    discount_value DECIMAL(12, 2) NOT NULL,
    min_order_amount DECIMAL(12, 2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);
CREATE TABLE orders (
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
);
CREATE TABLE order_items (
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
);
CREATE TABLE inventory_snapshots (
    snapshot_id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    snapshot_date DATE NOT NULL,
    stock_quantity INT NOT NULL,
    reserved_quantity INT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
);
CREATE TABLE payments (
    payment_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL UNIQUE,
    payment_method VARCHAR(32) NOT NULL,
    payment_status VARCHAR(32) NOT NULL,
    paid_amount DECIMAL(12, 2) NOT NULL,
    paid_at DATETIME NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
CREATE TABLE shipments (
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
);
CREATE TABLE returns (
    return_id INT PRIMARY KEY AUTO_INCREMENT,
    order_item_id INT NOT NULL,
    return_date DATE NOT NULL,
    reason VARCHAR(128) NOT NULL,
    return_quantity INT NOT NULL,
    refund_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)
);
CREATE TABLE product_reviews (
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
);
CREATE TABLE support_tickets (
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
);

CREATE INDEX idx_customers_region ON customers(region_id);
CREATE INDEX idx_customers_segment ON customers(segment_id);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_supplier ON products(supplier_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_region ON orders(region_id);
CREATE INDEX idx_orders_channel ON orders(channel_id);
CREATE INDEX idx_orders_campaign ON orders(campaign_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_order_items_warehouse ON order_items(warehouse_id);
CREATE INDEX idx_inventory_product_warehouse ON inventory_snapshots(product_id, warehouse_id);
CREATE INDEX idx_returns_order_item ON returns(order_item_id);
CREATE INDEX idx_reviews_product ON product_reviews(product_id);
CREATE INDEX idx_tickets_customer ON support_tickets(customer_id);

INSERT INTO regions (region_name, region_tier, manager_name) VALUES
('East China', 'tier_1', 'Lin Chen'),
('North China', 'tier_1', 'Wei Zhang'),
('South China', 'tier_1', 'Yun Li'),
('West China', 'tier_2', 'Qiang Zhou'),
('Central China', 'tier_2', 'Min Zhao'),
('Northeast China', 'tier_3', 'Han Wu');
INSERT INTO customer_segments (segment_name, min_lifetime_value, description) VALUES
('New', 0.00, 'Newly acquired customers'),
('Growth', 10000.00, 'Customers with growing order value'),
('Loyal', 50000.00, 'Repeat customers with stable demand'),
('VIP', 150000.00, 'High value customers'),
('At Risk', 20000.00, 'Customers with recent activity decline');
INSERT INTO categories (parent_category_id, category_name, category_level) VALUES
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
(7, 'Kids Furniture', 2);
INSERT INTO suppliers (supplier_name, region_id, rating, lead_time_days) VALUES
('Orion Supply', 1, 4.80, 5),
('Harbor Electronics', 1, 4.65, 7),
('North Star Manufacturing', 2, 4.52, 9),
('South Home Factory', 3, 4.40, 8),
('West Outdoor Group', 4, 4.35, 10),
('Central Office Works', 5, 4.58, 6),
('Northeast Beauty Lab', 6, 4.20, 12),
('Aurora Kids Co', 3, 4.46, 11);
INSERT INTO warehouses (warehouse_name, region_id, capacity) VALUES
('Shanghai Main Warehouse', 1, 120000),
('Beijing North Warehouse', 2, 90000),
('Guangzhou South Warehouse', 3, 100000),
('Chengdu West Warehouse', 4, 70000),
('Wuhan Central Warehouse', 5, 85000),
('Shenyang Northeast Warehouse', 6, 65000),
('Hangzhou Fast Fulfillment', 1, 75000),
('Shenzhen Cross-border Warehouse', 3, 60000);
INSERT INTO sales_channels (channel_name, channel_type, commission_rate) VALUES
('Official Store', 'owned', 0.0000),
('Tmall Flagship', 'marketplace', 0.0450),
('JD Flagship', 'marketplace', 0.0400),
('Douyin Shop', 'content', 0.0550),
('WeChat Mini Program', 'private_domain', 0.0150),
('Offline Key Account', 'offline', 0.0200);
INSERT INTO campaigns (campaign_name, channel_id, start_date, end_date, budget) VALUES
('618 Mega Sale', 2, DATE_SUB(CURDATE(), INTERVAL 40 DAY), DATE_SUB(CURDATE(), INTERVAL 15 DAY), 300000.00),
('Back To School', 3, DATE_SUB(CURDATE(), INTERVAL 120 DAY), DATE_SUB(CURDATE(), INTERVAL 80 DAY), 180000.00),
('Winter Home Upgrade', 1, DATE_SUB(CURDATE(), INTERVAL 220 DAY), DATE_SUB(CURDATE(), INTERVAL 180 DAY), 160000.00),
('Private Domain Member Day', 5, DATE_SUB(CURDATE(), INTERVAL 70 DAY), DATE_SUB(CURDATE(), INTERVAL 65 DAY), 80000.00),
('Outdoor Spring Trip', 4, DATE_SUB(CURDATE(), INTERVAL 150 DAY), DATE_SUB(CURDATE(), INTERVAL 110 DAY), 120000.00),
('Office Refresh', 6, DATE_SUB(CURDATE(), INTERVAL 260 DAY), DATE_SUB(CURDATE(), INTERVAL 230 DAY), 90000.00),
('Beauty New Arrival', 4, DATE_SUB(CURDATE(), INTERVAL 95 DAY), DATE_SUB(CURDATE(), INTERVAL 50 DAY), 110000.00),
('VIP Appreciation', 5, DATE_SUB(CURDATE(), INTERVAL 25 DAY), DATE_ADD(CURDATE(), INTERVAL 5 DAY), 70000.00);
INSERT INTO coupons (coupon_code, discount_type, discount_value, min_order_amount, start_date, end_date) VALUES
('NEW50', 'amount', 50.00, 299.00, DATE_SUB(CURDATE(), INTERVAL 365 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY)),
('VIP200', 'amount', 200.00, 2999.00, DATE_SUB(CURDATE(), INTERVAL 365 DAY), DATE_ADD(CURDATE(), INTERVAL 120 DAY)),
('HOME8', 'percent', 0.08, 999.00, DATE_SUB(CURDATE(), INTERVAL 240 DAY), DATE_ADD(CURDATE(), INTERVAL 60 DAY)),
('OFFICE100', 'amount', 100.00, 1299.00, DATE_SUB(CURDATE(), INTERVAL 240 DAY), DATE_ADD(CURDATE(), INTERVAL 60 DAY)),
('SPORTS30', 'amount', 30.00, 199.00, DATE_SUB(CURDATE(), INTERVAL 180 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY)),
('BEAUTY20', 'amount', 20.00, 159.00, DATE_SUB(CURDATE(), INTERVAL 180 DAY), DATE_ADD(CURDATE(), INTERVAL 90 DAY));
INSERT INTO products (product_name, category, category_id, supplier_id, list_price, cost_price, launch_date, status) VALUES
('Aurora Laptop', 'Electronics', 8, 1, 6999.00, 5100.00, DATE_SUB(CURDATE(), INTERVAL 420 DAY), 'active'),
('Breeze Phone', 'Electronics', 9, 2, 3999.00, 2780.00, DATE_SUB(CURDATE(), INTERVAL 411 DAY), 'active'),
('Cipher Tablet', 'Electronics', 9, 2, 2999.00, 2100.00, DATE_SUB(CURDATE(), INTERVAL 402 DAY), 'active'),
('Dynamo Monitor', 'Electronics', 8, 3, 1599.00, 980.00, DATE_SUB(CURDATE(), INTERVAL 393 DAY), 'active'),
('Echo Earbuds', 'Electronics', 9, 2, 699.00, 390.00, DATE_SUB(CURDATE(), INTERVAL 384 DAY), 'active'),
('Nova Smart Watch', 'Electronics', 9, 2, 1299.00, 760.00, DATE_SUB(CURDATE(), INTERVAL 375 DAY), 'active'),
('Comet Coffee Maker', 'Home Appliance', 10, 4, 899.00, 520.00, DATE_SUB(CURDATE(), INTERVAL 366 DAY), 'active'),
('Dawn Air Purifier', 'Home Appliance', 11, 4, 1299.00, 810.00, DATE_SUB(CURDATE(), INTERVAL 357 DAY), 'active'),
('Ember Oven', 'Home Appliance', 10, 4, 2399.00, 1510.00, DATE_SUB(CURDATE(), INTERVAL 348 DAY), 'active'),
('Frost Mini Fridge', 'Home Appliance', 10, 4, 1899.00, 1210.00, DATE_SUB(CURDATE(), INTERVAL 339 DAY), 'active'),
('Halo Vacuum', 'Home Appliance', 11, 4, 1699.00, 1030.00, DATE_SUB(CURDATE(), INTERVAL 330 DAY), 'active'),
('Iris Humidifier', 'Home Appliance', 11, 4, 499.00, 260.00, DATE_SUB(CURDATE(), INTERVAL 321 DAY), 'active'),
('Echo Office Chair', 'Office', 12, 6, 599.00, 310.00, DATE_SUB(CURDATE(), INTERVAL 312 DAY), 'active'),
('Flux Standing Desk', 'Office', 12, 6, 1899.00, 1180.00, DATE_SUB(CURDATE(), INTERVAL 303 DAY), 'active'),
('Graph Notebook Pack', 'Office', 3, 6, 99.00, 38.00, DATE_SUB(CURDATE(), INTERVAL 294 DAY), 'active'),
('Helix Desk Lamp', 'Office', 3, 6, 269.00, 128.00, DATE_SUB(CURDATE(), INTERVAL 285 DAY), 'active'),
('Ink Printer', 'Office', 3, 6, 1199.00, 760.00, DATE_SUB(CURDATE(), INTERVAL 276 DAY), 'active'),
('Jade Storage Cabinet', 'Office', 12, 6, 799.00, 450.00, DATE_SUB(CURDATE(), INTERVAL 267 DAY), 'active'),
('Kite Running Shoes', 'Sports', 13, 5, 499.00, 230.00, DATE_SUB(CURDATE(), INTERVAL 258 DAY), 'active'),
('Lumen Yoga Mat', 'Sports', 13, 5, 159.00, 65.00, DATE_SUB(CURDATE(), INTERVAL 249 DAY), 'active'),
('Motion Bike Helmet', 'Sports', 13, 5, 329.00, 150.00, DATE_SUB(CURDATE(), INTERVAL 240 DAY), 'active'),
('Pulse Dumbbell Set', 'Sports', 13, 5, 459.00, 220.00, DATE_SUB(CURDATE(), INTERVAL 231 DAY), 'active'),
('Quartz Camping Tent', 'Outdoor', 14, 5, 899.00, 490.00, DATE_SUB(CURDATE(), INTERVAL 222 DAY), 'active'),
('River Backpack', 'Outdoor', 14, 5, 399.00, 180.00, DATE_SUB(CURDATE(), INTERVAL 213 DAY), 'active'),
('Solar Hiking Jacket', 'Outdoor', 14, 5, 699.00, 350.00, DATE_SUB(CURDATE(), INTERVAL 204 DAY), 'active'),
('Terra Travel Bottle', 'Outdoor', 14, 5, 129.00, 52.00, DATE_SUB(CURDATE(), INTERVAL 195 DAY), 'active'),
('Umber Skin Care Set', 'Beauty', 15, 7, 299.00, 128.00, DATE_SUB(CURDATE(), INTERVAL 186 DAY), 'active'),
('Velvet Hair Dryer', 'Beauty', 15, 7, 399.00, 205.00, DATE_SUB(CURDATE(), INTERVAL 177 DAY), 'active'),
('Willow Baby Stroller', 'Mother Baby', 16, 8, 1499.00, 870.00, DATE_SUB(CURDATE(), INTERVAL 168 DAY), 'active'),
('Zen Kids Desk', 'Mother Baby', 16, 8, 899.00, 510.00, DATE_SUB(CURDATE(), INTERVAL 159 DAY), 'active');

DROP PROCEDURE IF EXISTS seed_datawhisperer_demo;
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
DROP PROCEDURE seed_datawhisperer_demo;
