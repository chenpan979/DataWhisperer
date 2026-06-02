CREATE DATABASE IF NOT EXISTS datawhisperer_demo
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE datawhisperer_demo;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS regions;

CREATE TABLE regions (
    region_id INT PRIMARY KEY AUTO_INCREMENT,
    region_name VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE customers (
    customer_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_name VARCHAR(128) NOT NULL,
    industry VARCHAR(64) NOT NULL,
    region_id INT NOT NULL,
    created_at DATE NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE products (
    product_id INT PRIMARY KEY AUTO_INCREMENT,
    product_name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    list_price DECIMAL(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT NOT NULL,
    region_id INT NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

INSERT INTO regions (region_name) VALUES
('East China'), ('North China'), ('South China'), ('West China');

INSERT INTO customers (customer_name, industry, region_id, created_at) VALUES
('Aster Retail', 'Retail', 1, '2025-01-10'),
('Bright Mart', 'Retail', 1, '2025-02-14'),
('Cloud Nine Tech', 'Technology', 2, '2025-03-05'),
('Delta Foods', 'Food', 3, '2025-03-18'),
('Evergreen Trading', 'Trading', 4, '2025-04-01'),
('Future Home', 'Retail', 1, '2025-04-20');

INSERT INTO products (product_name, category, list_price) VALUES
('Aurora Laptop', 'Electronics', 6999.00),
('Breeze Phone', 'Electronics', 3999.00),
('Comet Coffee Maker', 'Home Appliance', 899.00),
('Dawn Air Purifier', 'Home Appliance', 1299.00),
('Echo Office Chair', 'Office', 599.00),
('Flux Standing Desk', 'Office', 1899.00);

INSERT INTO orders (customer_id, region_id, order_date, status) VALUES
(1, 1, DATE_SUB(CURDATE(), INTERVAL 170 DAY), 'paid'),
(2, 1, DATE_SUB(CURDATE(), INTERVAL 150 DAY), 'paid'),
(3, 2, DATE_SUB(CURDATE(), INTERVAL 130 DAY), 'paid'),
(4, 3, DATE_SUB(CURDATE(), INTERVAL 110 DAY), 'paid'),
(5, 4, DATE_SUB(CURDATE(), INTERVAL 95 DAY), 'paid'),
(1, 1, DATE_SUB(CURDATE(), INTERVAL 80 DAY), 'paid'),
(2, 1, DATE_SUB(CURDATE(), INTERVAL 65 DAY), 'paid'),
(6, 1, DATE_SUB(CURDATE(), INTERVAL 45 DAY), 'paid'),
(3, 2, DATE_SUB(CURDATE(), INTERVAL 35 DAY), 'paid'),
(4, 3, DATE_SUB(CURDATE(), INTERVAL 25 DAY), 'paid'),
(5, 4, DATE_SUB(CURDATE(), INTERVAL 15 DAY), 'paid'),
(6, 1, DATE_SUB(CURDATE(), INTERVAL 5 DAY), 'paid');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 8, 6799.00), (1, 5, 20, 559.00),
(2, 2, 15, 3899.00), (2, 3, 18, 849.00),
(3, 1, 6, 6899.00), (3, 6, 12, 1799.00),
(4, 4, 20, 1199.00), (4, 3, 16, 829.00),
(5, 6, 10, 1799.00), (5, 5, 30, 549.00),
(6, 1, 12, 6699.00), (6, 2, 20, 3799.00),
(7, 3, 35, 799.00), (7, 4, 25, 1199.00),
(8, 2, 28, 3699.00), (8, 1, 10, 6599.00),
(9, 6, 16, 1759.00), (9, 5, 24, 529.00),
(10, 4, 18, 1169.00), (10, 3, 22, 789.00),
(11, 5, 36, 519.00), (11, 6, 9, 1699.00),
(12, 2, 32, 3599.00), (12, 4, 30, 1149.00);
