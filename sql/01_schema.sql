-- =====================================================================
-- 01_schema.sql  -  E-commerce star-ish schema (PostgreSQL)
-- Raw CSVs land in the "staging" schema as-is; cleaned data lives in
-- "public" with proper types, keys and indexes.
-- =====================================================================

DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA staging;

DROP TABLE IF EXISTS churn_predictions, web_sessions, support_tickets,
                     order_items, orders, products, customers CASCADE;

CREATE TABLE customers (
    customer_id          INTEGER PRIMARY KEY,
    full_name            TEXT        NOT NULL,
    email                TEXT        NOT NULL UNIQUE,
    gender               TEXT,
    age                  SMALLINT    CHECK (age BETWEEN 18 AND 100),
    city                 TEXT,
    state                TEXT        NOT NULL,
    signup_date          DATE        NOT NULL,
    acquisition_channel  TEXT        NOT NULL
);

CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,
    product_name  TEXT           NOT NULL,
    category      TEXT           NOT NULL,
    sub_category  TEXT           NOT NULL,
    unit_price    NUMERIC(10,2)  NOT NULL CHECK (unit_price > 0),
    unit_cost     NUMERIC(10,2)  NOT NULL CHECK (unit_cost > 0)
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER  NOT NULL REFERENCES customers(customer_id),
    order_date      DATE     NOT NULL,
    status          TEXT     NOT NULL CHECK (status IN ('Delivered','Returned','Cancelled')),
    payment_method  TEXT     NOT NULL,
    shipping_days   SMALLINT,
    discount_pct    SMALLINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    order_item_id  INTEGER PRIMARY KEY,
    order_id       INTEGER        NOT NULL REFERENCES orders(order_id),
    product_id     INTEGER        NOT NULL REFERENCES products(product_id),
    quantity       SMALLINT       NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(10,2)  NOT NULL
);

CREATE TABLE support_tickets (
    ticket_id           INTEGER PRIMARY KEY,
    customer_id         INTEGER   NOT NULL REFERENCES customers(customer_id),
    order_id            INTEGER   REFERENCES orders(order_id),
    created_at          TIMESTAMP NOT NULL,
    issue_type          TEXT      NOT NULL,
    resolved            BOOLEAN   NOT NULL,
    satisfaction_score  SMALLINT  CHECK (satisfaction_score BETWEEN 1 AND 5)
);

CREATE TABLE web_sessions (
    customer_id          INTEGER NOT NULL REFERENCES customers(customer_id),
    month                DATE    NOT NULL,
    sessions             INTEGER NOT NULL,
    avg_session_minutes  NUMERIC(5,1),
    PRIMARY KEY (customer_id, month)
);

CREATE TABLE churn_predictions (
    customer_id        INTEGER PRIMARY KEY REFERENCES customers(customer_id),
    snapshot_date      DATE          NOT NULL,
    churn_probability  NUMERIC(6,4)  NOT NULL,
    risk_tier          TEXT          NOT NULL,
    top_driver         TEXT,
    actual_churned     BOOLEAN
);

CREATE INDEX idx_orders_customer   ON orders (customer_id);
CREATE INDEX idx_orders_date       ON orders (order_date);
CREATE INDEX idx_items_order       ON order_items (order_id);
CREATE INDEX idx_items_product     ON order_items (product_id);
CREATE INDEX idx_tickets_customer  ON support_tickets (customer_id);

-- Net line revenue after order-level discount; used everywhere downstream.
CREATE OR REPLACE VIEW v_order_lines AS
SELECT  oi.order_item_id,
        o.order_id,
        o.customer_id,
        o.order_date,
        o.status,
        o.payment_method,
        o.shipping_days,
        o.discount_pct,
        p.product_id,
        p.category,
        p.sub_category,
        oi.quantity,
        ROUND(oi.quantity * oi.unit_price * (1 - o.discount_pct / 100.0), 2) AS net_revenue,
        ROUND(oi.quantity * p.unit_cost, 2)                                    AS cogs
FROM    order_items oi
JOIN    orders   o ON o.order_id   = oi.order_id
JOIN    products p ON p.product_id = oi.product_id;

-- Order-level revenue that counts only completed (delivered) orders.
CREATE OR REPLACE VIEW v_orders AS
SELECT  o.*,
        SUM(l.net_revenue)              AS order_value,
        SUM(l.net_revenue - l.cogs)     AS order_margin,
        SUM(l.quantity)                 AS units
FROM    orders o
JOIN    v_order_lines l USING (order_id)
GROUP BY o.order_id;
