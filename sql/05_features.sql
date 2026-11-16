-- =====================================================================
-- 05_features.sql  -  One row per customer, as of the snapshot date.
--
-- Population : customers with >= 1 non-cancelled order in the 365 days
--              up to the snapshot (the "active base").
-- Features   : computed ONLY from data on/before the snapshot (no leakage).
-- Label      : churned = no order in the 90 days after the snapshot
--              (only meaningful when the snapshot is >= 90 days in the past).
-- =====================================================================

-- The snapshot date lives in a one-row parameter table so the same view
-- serves training (historical snapshot, label known) and scoring (today).
CREATE TABLE IF NOT EXISTS feature_params (snap DATE NOT NULL, churn_window INT NOT NULL DEFAULT 90);
TRUNCATE feature_params;
INSERT INTO feature_params VALUES (DATE '2026-06-30', 90);

DROP VIEW IF EXISTS customer_features;
CREATE VIEW customer_features AS
WITH params AS (
    SELECT snap, churn_window FROM feature_params LIMIT 1
),
hist AS (                               -- order history up to snapshot
    SELECT o.*
    FROM   v_orders o, params p
    WHERE  o.order_date <= p.snap
),
order_feats AS (
    SELECT h.customer_id,
           p.snap - MAX(h.order_date) FILTER (WHERE h.status <> 'Cancelled')                 AS recency_days,
           COUNT(*) FILTER (WHERE h.status <> 'Cancelled' AND h.order_date > p.snap - 365)    AS frequency_365d,
           COUNT(*) FILTER (WHERE h.status <> 'Cancelled' AND h.order_date > p.snap - 90)     AS orders_last_90d,
           COUNT(*) FILTER (WHERE h.status <> 'Cancelled' AND h.order_date >  p.snap - 180
                                                          AND h.order_date <= p.snap - 90)    AS orders_prev_90d,
           COALESCE(SUM(h.order_value) FILTER (WHERE h.status = 'Delivered'
                                                 AND h.order_date > p.snap - 365), 0)         AS monetary_365d,
           AVG(h.order_value) FILTER (WHERE h.status = 'Delivered')                           AS avg_order_value,
           COUNT(*) FILTER (WHERE h.status <> 'Cancelled')                                    AS lifetime_orders,
           AVG((h.status = 'Returned')::INT) FILTER (WHERE h.status <> 'Cancelled')           AS return_rate,
           AVG((h.status = 'Cancelled')::INT)                                                 AS cancel_rate,
           AVG(h.shipping_days) FILTER (WHERE h.order_date > p.snap - 365)                    AS avg_shipping_days,
           AVG((h.shipping_days > 7)::INT) FILTER (WHERE h.order_date > p.snap - 365)         AS late_delivery_rate,
           AVG(h.discount_pct)                                                                AS avg_discount_pct,
           AVG((h.payment_method = 'Cash on Delivery')::INT)                                  AS cod_share
    FROM   hist h, params p
    GROUP  BY h.customer_id, p.snap
),
fav_cat AS (                            -- most purchased category by revenue
    SELECT DISTINCT ON (l.customer_id)
           l.customer_id, l.category AS favourite_category
    FROM   v_order_lines l, params p
    WHERE  l.order_date <= p.snap AND l.status <> 'Cancelled'
    GROUP  BY l.customer_id, l.category
    ORDER  BY l.customer_id, SUM(l.net_revenue) DESC
),
cat_breadth AS (
    SELECT l.customer_id, COUNT(DISTINCT l.category) AS distinct_categories
    FROM   v_order_lines l, params p
    WHERE  l.order_date <= p.snap
    GROUP  BY l.customer_id
),
ticket_feats AS (
    SELECT t.customer_id,
           COUNT(*) FILTER (WHERE t.created_at::DATE > p.snap - 180)          AS tickets_180d,
           COUNT(*) FILTER (WHERE NOT t.resolved)                            AS unresolved_tickets,
           AVG(t.satisfaction_score)                                         AS avg_satisfaction,
           COUNT(*) FILTER (WHERE t.satisfaction_score <= 2)                 AS low_sat_tickets
    FROM   support_tickets t, params p
    WHERE  t.created_at::DATE <= p.snap
    GROUP  BY t.customer_id
),
session_feats AS (
    SELECT s.customer_id,
           SUM(s.sessions) FILTER (WHERE s.month >  p.snap - 90)                         AS sessions_last_90d,
           SUM(s.sessions) FILTER (WHERE s.month <= p.snap - 90 AND s.month > p.snap - 180) AS sessions_prev_90d,
           AVG(s.avg_session_minutes) FILTER (WHERE s.month > p.snap - 90)               AS avg_session_minutes
    FROM   web_sessions s, params p
    WHERE  s.month <= p.snap
    GROUP  BY s.customer_id
),
label AS (
    SELECT c.customer_id,
           NOT EXISTS (SELECT 1 FROM orders o
                       WHERE o.customer_id = c.customer_id
                         AND o.order_date >  p.snap
                         AND o.order_date <= p.snap + p.churn_window) AS churned
    FROM   customers c, params p
)
SELECT c.customer_id,
       c.gender,
       c.age,
       c.state,
       c.acquisition_channel,
       p.snap - c.signup_date                                       AS tenure_days,
       f.recency_days,
       f.frequency_365d,
       f.orders_last_90d,
       f.orders_prev_90d,
       f.orders_last_90d - f.orders_prev_90d                        AS order_trend,
       ROUND(f.monetary_365d, 2)                                    AS monetary_365d,
       ROUND(COALESCE(f.avg_order_value, 0), 2)                     AS avg_order_value,
       f.lifetime_orders,
       ROUND(COALESCE(f.return_rate, 0), 4)                         AS return_rate,
       ROUND(f.cancel_rate, 4)                                      AS cancel_rate,
       ROUND(f.avg_shipping_days, 2)                                AS avg_shipping_days,
       ROUND(f.late_delivery_rate, 4)                               AS late_delivery_rate,
       ROUND(f.avg_discount_pct, 2)                                 AS avg_discount_pct,
       ROUND(f.cod_share, 4)                                        AS cod_share,
       fc.favourite_category,
       COALESCE(cb.distinct_categories, 0)                          AS distinct_categories,
       COALESCE(t.tickets_180d, 0)                                  AS tickets_180d,
       COALESCE(t.unresolved_tickets, 0)                            AS unresolved_tickets,
       COALESCE(t.low_sat_tickets, 0)                               AS low_sat_tickets,
       ROUND(t.avg_satisfaction, 2)                                 AS avg_satisfaction,   -- NULL = never raised a ticket
       COALESCE(s.sessions_last_90d, 0)                             AS sessions_last_90d,
       COALESCE(s.sessions_prev_90d, 0)                             AS sessions_prev_90d,
       COALESCE(s.sessions_last_90d, 0) - COALESCE(s.sessions_prev_90d, 0) AS session_trend,
       ROUND(COALESCE(s.avg_session_minutes, 0), 2)                 AS avg_session_minutes,
       lb.churned
FROM   customers c
CROSS  JOIN params p
JOIN   order_feats   f  ON f.customer_id  = c.customer_id
LEFT   JOIN fav_cat  fc ON fc.customer_id = c.customer_id
LEFT   JOIN cat_breadth cb ON cb.customer_id = c.customer_id
LEFT   JOIN ticket_feats t ON t.customer_id = c.customer_id
LEFT   JOIN session_feats s ON s.customer_id = c.customer_id
JOIN   label lb ON lb.customer_id = c.customer_id
WHERE  c.signup_date <= p.snap
  AND  f.frequency_365d >= 1;
