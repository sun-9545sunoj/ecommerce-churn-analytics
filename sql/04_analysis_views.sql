-- =====================================================================
-- 04_analysis_views.sql  -  Reusable analytical views (feed Tableau + app)
-- =====================================================================

-- ---------------------------------------------------------------------
-- Monthly KPIs with MoM growth, running total and 3-month moving average
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_monthly_kpis;
CREATE VIEW v_monthly_kpis AS
WITH m AS (
    SELECT DATE_TRUNC('month', order_date)::DATE               AS month,
           COUNT(*)                                           AS orders,
           COUNT(*) FILTER (WHERE status = 'Delivered')       AS delivered_orders,
           COUNT(DISTINCT customer_id)                        AS active_customers,
           SUM(order_value)  FILTER (WHERE status = 'Delivered') AS revenue,
           SUM(order_margin) FILTER (WHERE status = 'Delivered') AS gross_margin,
           AVG((status = 'Returned')::INT)                    AS return_rate,
           AVG(shipping_days)                                 AS avg_shipping_days
    FROM   v_orders
    GROUP  BY 1
),
new_c AS (
    SELECT DATE_TRUNC('month', signup_date)::DATE AS month, COUNT(*) AS new_customers
    FROM   customers GROUP BY 1
)
SELECT m.month,
       m.orders,
       m.delivered_orders,
       m.active_customers,
       COALESCE(n.new_customers, 0)                                         AS new_customers,
       ROUND(m.revenue, 2)                                                  AS revenue,
       ROUND(m.gross_margin, 2)                                             AS gross_margin,
       ROUND(m.revenue / NULLIF(m.delivered_orders, 0), 2)                  AS avg_order_value,
       ROUND(100.0 * (m.revenue - LAG(m.revenue) OVER w) / LAG(m.revenue) OVER w, 2) AS revenue_mom_pct,
       ROUND(SUM(m.revenue) OVER (ORDER BY m.month), 2)                     AS cumulative_revenue,
       ROUND(AVG(m.revenue) OVER (ORDER BY m.month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS revenue_3m_avg,
       ROUND(m.return_rate, 4)                                              AS return_rate,
       ROUND(m.avg_shipping_days, 2)                                        AS avg_shipping_days
FROM   m
LEFT   JOIN new_c n USING (month)
WINDOW w AS (ORDER BY m.month);

-- ---------------------------------------------------------------------
-- Cohort retention: % of each signup cohort ordering N months later
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_cohort_retention;
CREATE VIEW v_cohort_retention AS
WITH cohort AS (
    SELECT customer_id, DATE_TRUNC('month', signup_date)::DATE AS cohort_month
    FROM   customers
),
activity AS (
    SELECT DISTINCT o.customer_id, DATE_TRUNC('month', o.order_date)::DATE AS order_month
    FROM   orders o WHERE o.status <> 'Cancelled'
),
joined AS (
    SELECT c.cohort_month,
           (EXTRACT(YEAR FROM AGE(a.order_month, c.cohort_month)) * 12
            + EXTRACT(MONTH FROM AGE(a.order_month, c.cohort_month)))::INT AS months_since_signup,
           a.customer_id
    FROM   cohort c JOIN activity a USING (customer_id)
),
sizes AS (SELECT cohort_month, COUNT(*) AS cohort_size FROM cohort GROUP BY 1)
SELECT j.cohort_month,
       s.cohort_size,
       j.months_since_signup,
       COUNT(DISTINCT j.customer_id)                                         AS active_customers,
       ROUND(100.0 * COUNT(DISTINCT j.customer_id) / s.cohort_size, 2)       AS retention_pct
FROM   joined j JOIN sizes s USING (cohort_month)
GROUP  BY j.cohort_month, s.cohort_size, j.months_since_signup;

-- ---------------------------------------------------------------------
-- RFM segmentation as of the latest data date (NTILE quintiles)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_rfm_segments;
CREATE VIEW v_rfm_segments AS
WITH base AS (
    SELECT customer_id,
           (SELECT MAX(order_date) FROM orders) - MAX(order_date)  AS recency_days,
           COUNT(*)                                                AS frequency,
           SUM(order_value)                                        AS monetary
    FROM   v_orders
    WHERE  status = 'Delivered'
    GROUP  BY customer_id
),
scored AS (
    SELECT b.*,
           NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,   -- recent = 5
           NTILE(5) OVER (ORDER BY frequency)         AS f_score,
           NTILE(5) OVER (ORDER BY monetary)          AS m_score
    FROM   base b
)
SELECT customer_id, recency_days, frequency, ROUND(monetary, 2) AS monetary,
       r_score, f_score, m_score,
       CONCAT(r_score, f_score, m_score) AS rfm_code,
       CASE
           WHEN r_score >= 4 AND f_score >= 4                 THEN 'Champions'
           WHEN r_score >= 3 AND f_score >= 3                 THEN 'Loyal'
           WHEN r_score >= 4 AND f_score <= 2                 THEN 'New / Promising'
           WHEN r_score  = 3 AND f_score <= 2                 THEN 'Needs Attention'
           WHEN r_score <= 2 AND f_score >= 3                 THEN 'At Risk'
           WHEN r_score  = 2                                  THEN 'Hibernating'
           ELSE                                                    'Lost'
       END AS rfm_segment
FROM   scored;
