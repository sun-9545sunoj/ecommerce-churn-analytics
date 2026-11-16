-- =====================================================================
-- 02_transform.sql  -  Clean staging data and load the typed tables.
-- staging.* tables are created by src/load_to_postgres.py (raw CSV copy).
-- =====================================================================

-- Customers: remove exact duplicate rows, normalise emails,
-- keep one row per customer_id.
INSERT INTO customers
SELECT DISTINCT ON (customer_id)
       customer_id::INT,
       TRIM(full_name),
       LOWER(TRIM(email)),
       gender,
       NULLIF(age, '')::NUMERIC::SMALLINT,
       NULLIF(TRIM(city), ''),
       state,
       signup_date::DATE,
       acquisition_channel
FROM   staging.customers
ORDER  BY customer_id;

INSERT INTO products
SELECT product_id::INT, product_name, category, sub_category,
       unit_price::NUMERIC, unit_cost::NUMERIC
FROM   staging.products;

-- Orders: drop duplicate order rows.
INSERT INTO orders
SELECT DISTINCT ON (order_id)
       order_id::INT, customer_id::INT, order_date::DATE, status,
       payment_method, NULLIF(shipping_days, '')::NUMERIC::SMALLINT, discount_pct::SMALLINT
FROM   staging.orders
ORDER  BY order_id;

INSERT INTO order_items
SELECT order_item_id::INT, order_id::INT, product_id::INT, quantity::SMALLINT, unit_price::NUMERIC
FROM   staging.order_items;

INSERT INTO support_tickets
SELECT ticket_id::INT, customer_id::INT, order_id::INT, created_at::TIMESTAMP,
       issue_type, resolved::BOOLEAN, satisfaction_score::SMALLINT
FROM   staging.support_tickets;

INSERT INTO web_sessions
SELECT customer_id::INT, month::DATE, sessions::INT, avg_session_minutes::NUMERIC
FROM   staging.web_sessions;

ANALYZE;
