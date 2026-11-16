-- =====================================================================
-- 03_data_quality.sql  -  Data quality report: raw (staging) vs clean.
-- Each query returns: check_name | issue_count
-- =====================================================================

-- 1. Row counts: raw vs cleaned
SELECT 'customers' AS table_name, (SELECT COUNT(*) FROM staging.customers) AS raw_rows, (SELECT COUNT(*) FROM customers) AS clean_rows
UNION ALL SELECT 'orders',          (SELECT COUNT(*) FROM staging.orders),          (SELECT COUNT(*) FROM orders)
UNION ALL SELECT 'order_items',     (SELECT COUNT(*) FROM staging.order_items),     (SELECT COUNT(*) FROM order_items)
UNION ALL SELECT 'products',        (SELECT COUNT(*) FROM staging.products),        (SELECT COUNT(*) FROM products)
UNION ALL SELECT 'support_tickets', (SELECT COUNT(*) FROM staging.support_tickets), (SELECT COUNT(*) FROM support_tickets)
UNION ALL SELECT 'web_sessions',    (SELECT COUNT(*) FROM staging.web_sessions),    (SELECT COUNT(*) FROM web_sessions);

-- 2. Issues found in the raw data
SELECT 'duplicate customer rows (raw)' AS check_name,
       COUNT(*) - COUNT(DISTINCT customer_id) AS issue_count FROM staging.customers
UNION ALL
SELECT 'duplicate order rows (raw)', COUNT(*) - COUNT(DISTINCT order_id) FROM staging.orders
UNION ALL
SELECT 'emails with whitespace / uppercase (raw)',
       COUNT(*) FILTER (WHERE email <> LOWER(TRIM(email))) FROM staging.customers
UNION ALL
SELECT 'customers missing age',  COUNT(*) FILTER (WHERE age IS NULL)  FROM customers
UNION ALL
SELECT 'customers missing city', COUNT(*) FILTER (WHERE city IS NULL) FROM customers
UNION ALL
SELECT 'orders missing shipping_days', COUNT(*) FILTER (WHERE shipping_days IS NULL) FROM orders;

-- 3. Integrity checks on the clean tables (all should be 0)
SELECT 'orders without customer' AS check_name, COUNT(*) AS issue_count
FROM   orders o LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL
SELECT 'orders without items', COUNT(*)
FROM   orders o WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)
UNION ALL
SELECT 'items with unknown product', COUNT(*)
FROM   order_items i LEFT JOIN products p USING (product_id) WHERE p.product_id IS NULL
UNION ALL
SELECT 'orders before customer signup', COUNT(*)
FROM   orders o JOIN customers c USING (customer_id) WHERE o.order_date < c.signup_date
UNION ALL
SELECT 'orders outside data window', COUNT(*)
FROM   orders WHERE order_date NOT BETWEEN DATE '2024-01-01' AND DATE '2026-09-30'
UNION ALL
SELECT 'duplicate emails', COUNT(*) - COUNT(DISTINCT email) FROM customers;
