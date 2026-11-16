# Key Insights & Recommendations

*Data: synthetic Indian online retailer, Jan 2024 – Sep 2026 · 10,000 customers · 74,060 orders.
Churn = no order within 90 days of the snapshot.*

## Business health

| KPI | Value |
|---|---|
| Net revenue (delivered, all time) | ₹27.1 Cr |
| Revenue, last 12 months | ₹16.8 Cr (**+94% YoY**) |
| Average order value | ₹4,153 |
| Gross margin | 26.9% |
| Return rate | 8.8% |
| Active customers (ordered in last 365 days) | 7,346 |

## Findings

1. **Revenue is concentrated.** The top 20% of customers generate **70%** of revenue, and Electronics alone is
   **63%** of net revenue. Losing a small number of high-value customers hurts disproportionately.
2. **Retention decays steadily after the first month.** On average **44%** of a signup cohort orders again in
   month 1, falling steadily (about 1.5 points per month) to **27%** by month 12.
3. **Delivery delays drive churn.** Customers averaging **more than 7 days** per delivery churn at **58%**,
   against 41–45% for faster deliveries. Assam, Bihar and Odisha have **36–61%** late deliveries and the highest
   predicted churn (55–58%).
4. **Bad support experiences are costly.** Customers whose tickets average below 2.5/5 satisfaction churn at
   **54%**, against **39%** for happy customers.
5. **Acquisition channel predicts loyalty.** Referral customers churn at **35%** and spend the most
   (₹26k/yr). Social Media customers churn at **52%** and Affiliate customers at **49%**.
6. **Engagement is the earliest warning sign.** Web sessions in the last 90 days, days since last order and the
   recent order trend are the model's strongest predictors. Customers with no orders in the last 180 days churn at
   **87%**, and those whose ordering is growing churn at only **26%**.
7. **₹5.5 Cr of trailing-year revenue is at risk.** 2,252 customers are *High* risk (average probability 85%) and
   account for **44%** of the expected revenue at risk.

## Recommendations

| # | Action | Target | Expected impact |
|---|---|---|---|
| 1 | **Win-back campaign** for High-risk customers with above-median spend (personalised offer on their favourite category) | ~1,100 customers | Protects the largest share of the ₹2.4 Cr at risk in the High tier |
| 2 | **Fix last-mile delivery** in Assam, Bihar and Odisha (regional 3PL partner or a local fulfilment hub) | 3 states | Late deliveries are the most actionable churn driver |
| 3 | **Support recovery playbook**: auto-escalate unresolved *Late Delivery* tickets and follow up after any rating of 2 or below | Customers with low ratings | Moves customers from the 54% churn group towards 39% |
| 4 | **Shift acquisition spend** from Social Media and Affiliate towards Referral (refer-a-friend credits) | Marketing budget | Referral customers churn 17 points less and spend ~24% more per year than Social Media customers |
| 5 | **Engagement triggers**: when a customer's web sessions or orders drop quarter-on-quarter, send a re-engagement journey (email, push, app) | Medium-risk tier | Acts before customers reach the high-risk tier |
| 6 | **Monthly scoring**: rerun the pipeline monthly and feed the at-risk list to CRM; A/B test campaigns against a hold-out group to measure real uplift | Ongoing | Turns the model into a measurable retention programme |
