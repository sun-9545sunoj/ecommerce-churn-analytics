# Tableau Public dashboard: build guide

Step-by-step instructions to build the three-page **E-commerce Churn Analytics** dashboard in
[Tableau Public](https://public.tableau.com/app/discover) (free; runs on macOS and Windows) from the CSV extracts in
`data/exports/`.

> Regenerate the extracts at any time with `make export`.

---

## 1. Connect the data

1. Open Tableau Public, then **Connect → To a File → Text file**, and pick `data/exports/fact_order_lines.csv`.
2. Add the other files with **Add** (next to *Connections*). Drag each one onto the canvas as its own
   **relationship** (logical layer, not a join):

| Table | Grain | Relate to `fact_order_lines` on |
|---|---|---|
| `fact_order_lines.csv` | one row per order line | (base table) |
| `customer_360.csv` | one row per active customer | `customer_id` = `customer_id` |
| `monthly_kpis.csv` | one row per month | standalone (no relationship needed) |
| `cohort_retention.csv` | cohort × months since signup | standalone |
| `state_summary.csv` | one row per state | `state` = `state` |

3. Check the data types: `order_date`, `signup_date`, `month` and `cohort_month` should be **Date**. Set `state` to
   **Geographic Role → State/Province** (country: India).

## 2. Calculated fields

Create these from **Analysis → Create Calculated Field**:

```text
Net Revenue (Delivered)   = SUM(IF [status] = "Delivered" THEN [net_revenue] END)
Orders                    = COUNTD([order_id])
AOV                       = [Net Revenue (Delivered)] / COUNTD(IF [status] = "Delivered" THEN [order_id] END)
Gross Margin %            = SUM(IF [status] = "Delivered" THEN [margin] END) / [Net Revenue (Delivered)]
Return Rate               = COUNTD(IF [status] = "Returned" THEN [order_id] END) / [Orders]
Late Delivery %           = AVG(IIF([is_late], 1, 0))
Revenue at Risk           = SUM([revenue_at_risk])
High-Risk Customers       = COUNTD(IF [risk_tier] = "High" THEN [customer_id] END)
Avg Churn Probability     = AVG([churn_probability])
Risk Tier Order           = CASE [risk_tier] WHEN "High" THEN 1 WHEN "Medium" THEN 2 ELSE 3 END
Retention Label           = STR(ROUND([retention_pct], 0)) + "%"
```

**Colour conventions** (keep them consistent across sheets):

| Use | Colour |
|---|---|
| Single-measure bars and lines | `#2a78d6` (blue) |
| Secondary line (e.g. 3-month average) | `#eb6834` (orange) |
| Heatmaps | sequential blue, light `#cde2fb` → dark `#0d366b` |
| Risk tiers | High `#d03b3b`, Medium `#fab219`, Low `#0ca30c`. Always show the tier name too, never colour alone. |

## 3. Sheets

| # | Sheet | Build |
|---|---|---|
| 1 | **KPI cards** | Five text sheets: `Net Revenue (Delivered)`, `Orders`, `AOV`, `COUNTD(customer_360.customer_id)`, `Revenue at Risk`. Large font, a small grey caption under each. |
| 2 | **Revenue trend** | `monthly_kpis`: Columns `MONTH(month)` (continuous), Rows `revenue` + `revenue_3m_avg` as a dual-*line* on a **shared** axis (synchronise the axis; don't use two scales). |
| 3 | **Category mix** | Horizontal bar: Rows `category`, Columns `Net Revenue (Delivered)`, sorted descending, `Gross Margin %` in the label. |
| 4 | **State map** | Filled map: `state` on Detail, colour = `Late Delivery %` (sequential), tooltip with revenue and average churn probability. |
| 5 | **Cohort heatmap** | `cohort_retention`: Rows `cohort_month` (Month/Year, discrete), Columns `months_since_signup` (discrete, filter 0–12), Square mark, Colour `retention_pct`, Label `Retention Label`. |
| 6 | **RFM segments** | `customer_360`: Treemap, `rfm_segment` on Label, size `COUNTD(customer_id)`, colour `Avg Churn Probability`. |
| 7 | **Risk tiers** | Bar: Columns `risk_tier` (sorted by `Risk Tier Order`), Rows `Revenue at Risk`, colour `risk_tier` with the palette above, label = customers. |
| 8 | **Top churn drivers** | Bar: Rows `top_driver`, Columns `COUNTD(customer_id)`, top 8 by count. |
| 9 | **At-risk customer list** | Text table: `customer_id`, `full_name`, `city`, `acquisition_channel`, `rfm_segment`, `churn_probability`, `top_driver`, `revenue_at_risk`. Sort by probability descending; filter `risk_tier` = High. |

## 4. Dashboards (1366 × 900, Automatic for phone)

1. **Executive Overview**: KPI cards (top row) → Revenue trend (full width) → Category mix | State map.
   Filters: `order_date` (range), `category`, `acquisition_channel`, applied to all sheets that use this data source.
2. **Customers & Retention**: Cohort heatmap (top) → RFM treemap | Repeat-purchase metrics.
3. **Churn Risk**: Risk tiers | Top churn drivers → At-risk customer list. Use **filter actions**: clicking a tier or a
   driver filters the customer list. Filters: `state`, `acquisition_channel`, `risk_tier`.

Add a title bar to each dashboard (*E-commerce Churn Analytics | page name*) and a footer:
*Synthetic data · Model: Random Forest, ROC-AUC 0.86 · Scored 30 Sep 2026*.

## 5. Publish

1. **File → Save to Tableau Public As…**, then name it `E-commerce Churn Analytics`.
2. On your Tableau Public profile, open the workbook and set **Show Sheets as Tabs**.
3. Copy the share link into `README.md` (*Live demo* section) and save screenshots of each dashboard into
   `tableau/screenshots/` as `overview.png`, `retention.png` and `churn_risk.png`.
