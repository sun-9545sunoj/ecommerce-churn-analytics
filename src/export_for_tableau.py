"""Export Tableau-ready (and app-ready) CSV extracts from Postgres.

Tableau Public cannot connect to a database, so we publish flat extracts:
  fact_order_lines.csv   one row per order line, denormalised with customer + product attributes
  customer_360.csv       one row per active customer: features, RFM segment, churn score
  monthly_kpis.csv       monthly revenue / orders / AOV / growth
  cohort_retention.csv   signup cohort x months-since-signup retention
  category_monthly.csv   monthly revenue & margin by category (light file for the web app)
  state_summary.csv      revenue, delivery speed and churn risk by state

Run:  python -m src.export_for_tableau
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from src.config import DATA_EXPORTS, END_DATE, SNAPSHOT_DATE, get_engine

QUERIES = {
    "fact_order_lines": """
        SELECT l.order_item_id, l.order_id, l.order_date, l.status, l.payment_method,
               l.shipping_days, (l.shipping_days > 7) AS is_late, l.discount_pct,
               l.product_id, p.product_name, l.category, l.sub_category, l.quantity,
               l.net_revenue, l.cogs, l.net_revenue - l.cogs AS margin,
               c.customer_id, c.gender, c.city, c.state, c.acquisition_channel,
               CASE WHEN c.age < 25 THEN '18-24' WHEN c.age < 35 THEN '25-34'
                    WHEN c.age < 45 THEN '35-44' WHEN c.age < 55 THEN '45-54'
                    WHEN c.age IS NULL THEN 'Unknown' ELSE '55+' END AS age_band
        FROM   v_order_lines l
        JOIN   customers c USING (customer_id)
        JOIN   products  p USING (product_id)
        ORDER  BY l.order_date, l.order_item_id""",
    "customer_360": """
        SELECT f.customer_id, c.full_name, c.city, f.state, f.gender, f.age, f.acquisition_channel,
               c.signup_date, f.tenure_days, f.recency_days, f.frequency_365d, f.orders_last_90d,
               f.orders_prev_90d, f.order_trend, f.monetary_365d, f.avg_order_value,
               f.lifetime_orders, f.return_rate, f.avg_shipping_days, f.late_delivery_rate,
               f.tickets_180d, f.avg_satisfaction, f.sessions_last_90d, f.session_trend,
               f.favourite_category,
               r.rfm_segment, r.rfm_code,
               cp.churn_probability, cp.risk_tier, cp.top_driver,
               ROUND(cp.churn_probability * f.monetary_365d, 2) AS revenue_at_risk
        FROM   customer_features f
        JOIN   customers c USING (customer_id)
        LEFT   JOIN v_rfm_segments r USING (customer_id)
        JOIN   churn_predictions cp USING (customer_id)
        ORDER  BY cp.churn_probability DESC""",
    # full model inputs for the web app's what-if predictor (label is unknown at scoring time)
    "model_features": "SELECT f.* FROM customer_features f JOIN churn_predictions USING (customer_id) ORDER BY customer_id",
    "monthly_kpis": "SELECT * FROM v_monthly_kpis ORDER BY month",
    "cohort_retention": "SELECT * FROM v_cohort_retention ORDER BY cohort_month, months_since_signup",
    "category_monthly": """
        SELECT DATE_TRUNC('month', order_date)::DATE AS month, category,
               COUNT(DISTINCT order_id)                AS orders,
               ROUND(SUM(net_revenue), 2)              AS revenue,
               ROUND(SUM(net_revenue - cogs), 2)       AS margin,
               ROUND(AVG((status = 'Returned')::INT), 4) AS return_rate
        FROM   v_order_lines WHERE status = 'Delivered' OR status = 'Returned'
        GROUP  BY 1, 2 ORDER BY 1, 2""",
    "state_summary": """
        WITH o AS (
            SELECT c.state, SUM(v.order_value) FILTER (WHERE v.status = 'Delivered') AS revenue,
                   COUNT(*) AS orders, AVG(v.shipping_days) AS avg_shipping_days,
                   AVG((v.shipping_days > 7)::INT) AS late_rate
            FROM   v_orders v JOIN customers c USING (customer_id) GROUP BY c.state
        ), r AS (
            SELECT f.state, COUNT(*) AS active_customers, AVG(cp.churn_probability) AS avg_churn_probability,
                   SUM(cp.churn_probability * f.monetary_365d) AS revenue_at_risk
            FROM   customer_features f JOIN churn_predictions cp USING (customer_id) GROUP BY f.state
        )
        SELECT o.state, ROUND(o.revenue, 2) AS revenue, o.orders, ROUND(o.avg_shipping_days, 2) AS avg_shipping_days,
               ROUND(o.late_rate, 4) AS late_rate, r.active_customers,
               ROUND(r.avg_churn_probability, 4) AS avg_churn_probability, ROUND(r.revenue_at_risk, 2) AS revenue_at_risk
        FROM   o JOIN r USING (state) ORDER BY revenue DESC""",
}


def main() -> None:
    engine = get_engine()
    with engine.begin() as c:
        # customer_360 / state_summary describe "today", i.e. the scoring date
        c.execute(text("UPDATE feature_params SET snap = :s"), {"s": END_DATE})
        try:
            for name, sql in QUERIES.items():
                df = pd.read_sql(text(sql), c)
                path = DATA_EXPORTS / f"{name}.csv"
                df.to_csv(path, index=False)
                print(f"  {name:<18} {len(df):>8,} rows  {path.stat().st_size / 1e6:6.1f} MB")
        finally:
            c.execute(text("UPDATE feature_params SET snap = :s"), {"s": SNAPSHOT_DATE})


if __name__ == "__main__":
    main()
