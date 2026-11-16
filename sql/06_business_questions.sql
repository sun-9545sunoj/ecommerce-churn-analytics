-- =====================================================================
-- 06_business_questions.sql  -  Ad-hoc analysis answering business questions
-- Run:  psql -d ecommerce -f sql/06_business_questions.sql
-- =====================================================================

-- Q1. Headline KPIs for the whole period
SELECT COUNT(DISTINCT customer_id)                                   AS customers,
       COUNT(*)                                                      AS orders,
       ROUND(SUM(order_value) FILTER (WHERE status = 'Delivered'))   AS net_revenue_inr,
       ROUND(AVG(order_value) FILTER (WHERE status = 'Delivered'))   AS avg_order_value,
       ROUND(100.0 * SUM(order_margin) FILTER (WHERE status = 'Delivered')
                   / SUM(order_value)  FILTER (WHERE status = 'Delivered'), 1) AS gross_margin_pct,
       ROUND(100.0 * AVG((status = 'Returned')::INT), 1)             AS return_rate_pct
FROM   v_orders;

-- Q2. Year-over-year revenue growth by quarter
WITH q AS (
    SELECT DATE_TRUNC('quarter', order_date)::DATE AS quarter,
           SUM(order_value) FILTER (WHERE status = 'Delivered') AS revenue
    FROM   v_orders GROUP BY 1
)
SELECT quarter,
       ROUND(revenue)                                                         AS revenue,
       ROUND(LAG(revenue, 4) OVER (ORDER BY quarter))                         AS revenue_last_year,
       ROUND(100.0 * (revenue / LAG(revenue, 4) OVER (ORDER BY quarter) - 1), 1) AS yoy_growth_pct
FROM   q ORDER BY quarter;

-- Q3. Category profitability and ranking
SELECT category,
       ROUND(SUM(net_revenue) FILTER (WHERE status = 'Delivered'))     AS revenue,
       ROUND(100.0 * SUM(net_revenue - cogs) FILTER (WHERE status = 'Delivered')
                   / SUM(net_revenue)        FILTER (WHERE status = 'Delivered'), 1) AS margin_pct,
       ROUND(100.0 * AVG((status = 'Returned')::INT), 1)               AS return_rate_pct,
       RANK() OVER (ORDER BY SUM(net_revenue) FILTER (WHERE status = 'Delivered') DESC) AS revenue_rank,
       ROUND(100.0 * SUM(net_revenue) FILTER (WHERE status = 'Delivered')
                   / SUM(SUM(net_revenue) FILTER (WHERE status = 'Delivered')) OVER (), 1) AS revenue_share_pct
FROM   v_order_lines
WHERE  status IN ('Delivered', 'Returned')
GROUP  BY category
ORDER  BY revenue DESC;

-- Q4. Top 3 products in each category (window function + filter)
SELECT *
FROM (
    SELECT l.category, p.product_name,
           ROUND(SUM(l.net_revenue)) AS revenue,
           DENSE_RANK() OVER (PARTITION BY l.category ORDER BY SUM(l.net_revenue) DESC) AS rnk
    FROM   v_order_lines l JOIN products p USING (product_id)
    WHERE  l.status = 'Delivered'
    GROUP  BY l.category, p.product_name
) t
WHERE  rnk <= 3
ORDER  BY category, rnk;

-- Q5. Acquisition channel quality: value per customer and 90-day churn
SELECT f.acquisition_channel,
       COUNT(*)                                          AS active_customers,
       ROUND(AVG(f.monetary_365d))                       AS avg_revenue_365d,
       ROUND(100.0 * AVG(f.churned::INT), 1)             AS churn_rate_pct
FROM   customer_features f
GROUP  BY f.acquisition_channel
ORDER  BY churn_rate_pct DESC;

-- Q6. Does delivery speed drive churn?
SELECT CASE WHEN avg_shipping_days <= 3 THEN '1. <= 3 days'
            WHEN avg_shipping_days <= 5 THEN '2. 3-5 days'
            WHEN avg_shipping_days <= 7 THEN '3. 5-7 days'
            ELSE                             '4. > 7 days' END   AS delivery_speed,
       COUNT(*)                                                  AS customers,
       ROUND(100.0 * AVG(churned::INT), 1)                       AS churn_rate_pct
FROM   customer_features
WHERE  avg_shipping_days IS NOT NULL
GROUP  BY 1 ORDER BY 1;

-- Q7. Support experience vs churn
SELECT CASE WHEN avg_satisfaction IS NULL THEN '0. No tickets'
            WHEN avg_satisfaction < 2.5   THEN '1. Unhappy (<2.5)'
            WHEN avg_satisfaction < 3.5   THEN '2. Neutral (2.5-3.5)'
            ELSE                               '3. Happy (>=3.5)' END AS support_experience,
       COUNT(*)                                                     AS customers,
       ROUND(100.0 * AVG(churned::INT), 1)                          AS churn_rate_pct
FROM   customer_features
GROUP  BY 1 ORDER BY 1;

-- Q8. Slowest-delivery states and their late-delivery rate
SELECT c.state,
       ROUND(AVG(o.shipping_days), 2)                       AS avg_shipping_days,
       ROUND(100.0 * AVG((o.shipping_days > 7)::INT), 1)    AS late_pct,
       COUNT(*)                                             AS orders
FROM   orders o JOIN customers c USING (customer_id)
GROUP  BY c.state
ORDER  BY avg_shipping_days DESC
LIMIT  5;

-- Q9. Revenue concentration: share of revenue from top 20% customers (Pareto)
WITH cust AS (
    SELECT customer_id, SUM(order_value) AS revenue,
           NTILE(5) OVER (ORDER BY SUM(order_value) DESC) AS quintile
    FROM   v_orders WHERE status = 'Delivered'
    GROUP  BY customer_id
)
SELECT quintile,
       COUNT(*)                                                   AS customers,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS revenue_share_pct
FROM   cust GROUP BY quintile ORDER BY quintile;

-- Q10. Repeat purchase: days between consecutive orders (LAG)
WITH gaps AS (
    SELECT customer_id,
           order_date - LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date) AS gap_days
    FROM   orders WHERE status <> 'Cancelled'
)
SELECT ROUND(AVG(gap_days), 1)                                     AS avg_days_between_orders,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap_days)       AS median_days_between_orders
FROM   gaps WHERE gap_days IS NOT NULL;
