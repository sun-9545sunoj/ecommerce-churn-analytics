"""E-commerce Customer Churn Analytics - interactive dashboard.

Reads only the exported CSVs and the trained model, so it runs anywhere
(locally or on Streamlit Community Cloud) without a database.

Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
EXPORTS, MODELS, IMAGES = ROOT / "data" / "exports", ROOT / "models", ROOT / "images"

BLUE, ORANGE, MUTED = "#2a78d6", "#eb6834", "#8a8984"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
TIER_COLORS = {"High": "#d03b3b", "Medium": "#fab219", "Low": "#0ca30c"}
TIER_ORDER = ["High", "Medium", "Low"]

st.set_page_config(page_title="E-commerce Churn Analytics", page_icon="📊", layout="wide")


# ----------------------------------------------------------------------------- data
@st.cache_data
def load_data():
    d = {n: pd.read_csv(EXPORTS / f"{n}.csv") for n in
         ["monthly_kpis", "category_monthly", "cohort_retention", "customer_360", "state_summary", "model_features"]}
    d["monthly_kpis"]["month"] = pd.to_datetime(d["monthly_kpis"]["month"])
    d["category_monthly"]["month"] = pd.to_datetime(d["category_monthly"]["month"])
    d["cohort_retention"]["cohort_month"] = pd.to_datetime(d["cohort_retention"]["cohort_month"])
    d["importance"] = pd.read_csv(MODELS / "feature_importance.csv")
    d["metrics"] = json.loads((MODELS / "metrics.json").read_text())
    return d


@st.cache_resource
def load_model():
    return joblib.load(MODELS / "churn_model.pkl")


def inr(v: float) -> str:
    if abs(v) >= 1e7:
        return f"₹{v / 1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"₹{v / 1e5:,.1f} L"
    return f"₹{v:,.0f}"


def style(fig, height=380):
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10, r=10, t=40, b=10),
                      font=dict(size=13), hoverlabel=dict(bgcolor="white"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


d = load_data()
bundle = load_model()
model, NUM, CAT = bundle["model"], bundle["numeric"], bundle["categorical"]
m = d["metrics"]
kpi, c360 = d["monthly_kpis"], d["customer_360"]

# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### 📊 E-commerce Churn Analytics")
    st.caption("End-to-end portfolio project: Python · PostgreSQL · SQL · scikit-learn / XGBoost · Tableau · Streamlit")
    st.markdown(
        "- Synthetic data for an Indian online retailer, **Jan 2024 – Sep 2026**\n"
        f"- Model trained at snapshot **{m['snapshot_date']}**, customers scored as of **{m['scoring_date']}**\n"
        "- Churn = no order in the next **90 days**"
    )
    st.markdown("[GitHub repository](https://github.com/sun-9545sunoj/ecommerce-churn-analytics)")

st.title("E-commerce Customer Churn Analytics")
st.caption("Which customers are likely to stop buying in the next 90 days, why, and how much revenue is at risk?")

# ----------------------------------------------------------------------------- KPI row
last12 = kpi[kpi["month"] > kpi["month"].max() - pd.DateOffset(months=12)]
prev12 = kpi[(kpi["month"] <= kpi["month"].max() - pd.DateOffset(months=12)) &
             (kpi["month"] > kpi["month"].max() - pd.DateOffset(months=24))]
rev_growth = last12["revenue"].sum() / prev12["revenue"].sum() - 1
high = c360[c360["risk_tier"] == "High"]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Revenue (last 12 mo)", inr(last12["revenue"].sum()), f"{rev_growth:+.0%} YoY")
k2.metric("Orders (last 12 mo)", f"{last12['orders'].sum():,}")
k3.metric("Avg order value", inr(last12["revenue"].sum() / last12["delivered_orders"].sum()))
k4.metric("Active customers", f"{len(c360):,}", help="Ordered at least once in the last 365 days")
k5.metric("Revenue at risk", inr(c360["revenue_at_risk"].sum()), f"{len(high):,} high-risk customers",
          delta_color="off")

tab_over, tab_ret, tab_risk, tab_pred, tab_model = st.tabs(
    ["📈 Overview", "🔁 Retention & Segments", "⚠️ Churn Risk", "🧪 What-if Predictor", "🤖 Model"])

# ----------------------------------------------------------------------------- overview
with tab_over:
    fig = go.Figure()
    fig.add_scatter(x=kpi["month"], y=kpi["revenue"], name="Monthly revenue", mode="lines+markers",
                    line=dict(color=BLUE, width=2), marker=dict(size=6),
                    hovertemplate="%{x|%b %Y}<br>Revenue ₹%{y:,.0f}<extra></extra>")
    fig.add_scatter(x=kpi["month"], y=kpi["revenue_3m_avg"], name="3-month average",
                    line=dict(color=ORANGE, width=2, dash="dash"),
                    hovertemplate="%{x|%b %Y}<br>3-mo avg ₹%{y:,.0f}<extra></extra>")
    fig.update_layout(title="Monthly net revenue", hovermode="x unified", yaxis_tickprefix="₹")
    st.plotly_chart(style(fig), width="stretch")

    c1, c2 = st.columns(2)
    cat = (d["category_monthly"].groupby("category")[["revenue", "margin"]].sum()
           .assign(margin_pct=lambda x: x["margin"] / x["revenue"]).sort_values("revenue"))
    fig = px.bar(cat, x="revenue", y=cat.index, orientation="h", title="Revenue by category",
                 custom_data=["margin_pct"], color_discrete_sequence=[BLUE])
    fig.update_traces(hovertemplate="%{y}<br>₹%{x:,.0f}<br>Margin %{customdata[0]:.0%}<extra></extra>")
    fig.update_layout(yaxis_title=None, xaxis_title=None, xaxis_tickprefix="₹")
    c1.plotly_chart(style(fig), width="stretch")

    st_sum = d["state_summary"].sort_values("avg_shipping_days")
    fig = px.bar(st_sum, x="avg_shipping_days", y="state", orientation="h",
                 title="Average delivery days by state", color="avg_churn_probability",
                 color_continuous_scale=SEQ, labels={"avg_churn_probability": "Avg churn<br>probability"},
                 custom_data=["late_rate", "avg_churn_probability"])
    fig.update_traces(hovertemplate="%{y}<br>%{x:.1f} days<br>Late %{customdata[0]:.0%}"
                                    "<br>Avg churn prob %{customdata[1]:.0%}<extra></extra>")
    fig.update_layout(yaxis_title=None, xaxis_title="days")
    c2.plotly_chart(style(fig), width="stretch")

# ----------------------------------------------------------------------------- retention
with tab_ret:
    coh = d["cohort_retention"]
    coh = coh[(coh["months_since_signup"].between(0, 12)) & (coh["cohort_month"] <= "2025-09-01")]
    pv = coh.pivot(index="cohort_month", columns="months_since_signup", values="retention_pct")
    fig = px.imshow(pv.to_numpy(), x=[f"M{c}" for c in pv.columns], y=[f"{i:%b %Y}" for i in pv.index],
                    color_continuous_scale=SEQ, aspect="auto", text_auto=".0f",
                    labels=dict(x="Months since signup", y="Signup cohort", color="Retention %"))
    fig.update_layout(title="Cohort retention (% of cohort ordering N months after signup)")
    st.plotly_chart(style(fig, 620), width="stretch")

    order = ["Champions", "Loyal", "New / Promising", "Needs Attention", "At Risk", "Hibernating", "Lost"]
    seg = (c360.groupby("rfm_segment").agg(customers=("customer_id", "count"),
                                            avg_churn=("churn_probability", "mean"),
                                            revenue_at_risk=("revenue_at_risk", "sum"))
           .reindex([o for o in order if o in c360["rfm_segment"].unique()]))
    c1, c2 = st.columns(2)
    fig = px.bar(seg, x=seg.index, y="customers", title="Customers by RFM segment",
                 color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title=None)
    c1.plotly_chart(style(fig), width="stretch")
    fig = px.bar(seg, x=seg.index, y="avg_churn", title="Average churn probability by RFM segment",
                 color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title=None, yaxis_tickformat=".0%")
    c2.plotly_chart(style(fig), width="stretch")

# ----------------------------------------------------------------------------- churn risk
with tab_risk:
    f1, f2, f3 = st.columns(3)
    tiers = f1.multiselect("Risk tier", TIER_ORDER, default=["High", "Medium"])
    states = f2.multiselect("State", sorted(c360["state"].unique()))
    channels = f3.multiselect("Acquisition channel", sorted(c360["acquisition_channel"].unique()))
    view = c360[c360["risk_tier"].isin(tiers or TIER_ORDER)]
    if states:
        view = view[view["state"].isin(states)]
    if channels:
        view = view[view["acquisition_channel"].isin(channels)]

    a, b, c = st.columns(3)
    a.metric("Customers in view", f"{len(view):,}")
    b.metric("Revenue at risk", inr(view["revenue_at_risk"].sum()))
    c.metric("Avg churn probability", f"{view['churn_probability'].mean():.0%}" if len(view) else "–")

    c1, c2 = st.columns(2)
    tier = c360.groupby("risk_tier").agg(customers=("customer_id", "count"),
                                          revenue_at_risk=("revenue_at_risk", "sum")).reindex(TIER_ORDER)
    fig = px.bar(tier, x=tier.index, y="revenue_at_risk", color=tier.index, text="customers",
                 color_discrete_map=TIER_COLORS, title="Revenue at risk by tier (label = customers)")
    fig.update_traces(texttemplate="%{text:,} customers", textposition="outside",
                      hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>")
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_tickprefix="₹")
    c1.plotly_chart(style(fig), width="stretch")

    drv = view["top_driver"].value_counts().head(8).sort_values()
    fig = px.bar(x=drv.values, y=drv.index, orientation="h", title="Top churn driver (customers in view)",
                 color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title="customers", yaxis_title=None)
    c2.plotly_chart(style(fig), width="stretch")

    cols = ["customer_id", "full_name", "city", "state", "acquisition_channel", "rfm_segment",
            "churn_probability", "risk_tier", "top_driver", "recency_days", "monetary_365d", "revenue_at_risk"]
    st.markdown("**Customers to target with a retention campaign** (sorted by churn probability)")
    st.dataframe(view[cols], width="stretch", hide_index=True, height=360,
                 column_config={"churn_probability": st.column_config.ProgressColumn(
                     "Churn probability", format="%.2f", min_value=0, max_value=1),
                     "monetary_365d": st.column_config.NumberColumn("Spend 12 mo (₹)", format="%.0f"),
                     "revenue_at_risk": st.column_config.NumberColumn("Revenue at risk (₹)", format="%.0f")})
    st.download_button("Download target list (CSV)", view[cols].to_csv(index=False),
                       "churn_target_list.csv", "text/csv")

# ----------------------------------------------------------------------------- what-if
with tab_pred:
    feats = d["model_features"]
    st.markdown("Pick a customer, then change their experience to see how the churn probability responds.")
    default = int(c360.iloc[0]["customer_id"])
    ids = feats["customer_id"].tolist()
    cid = st.selectbox("Customer ID", ids, index=ids.index(default) if default in ids else 0)
    row = feats.loc[feats["customer_id"] == cid].iloc[[0]].copy()
    base_p = float(model.predict_proba(row[NUM + CAT])[:, 1][0])

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f"**{row['acquisition_channel'].iat[0]}** customer from **{row['state'].iat[0]}**, "
                    f"{int(row['tenure_days'].iat[0])} days tenure, favourite category "
                    f"**{row['favourite_category'].iat[0]}**")
        new = row.copy()
        new["avg_shipping_days"] = st.slider("Average delivery days", 1.0, 15.0,
                                             float(np.nan_to_num(row["avg_shipping_days"].iat[0], nan=4.0)), 0.5)
        new["late_delivery_rate"] = st.slider("Late-delivery rate", 0.0, 1.0, float(row["late_delivery_rate"].iat[0] or 0), 0.05)
        sat = row["avg_satisfaction"].iat[0]
        new["avg_satisfaction"] = st.slider("Support satisfaction (1–5)", 1.0, 5.0,
                                            4.5 if pd.isna(sat) else float(sat), 0.1)
        new["orders_last_90d"] = st.slider("Orders in last 90 days", 0, 20, int(row["orders_last_90d"].iat[0]))
        new["order_trend"] = new["orders_last_90d"] - new["orders_prev_90d"]
        new["sessions_last_90d"] = st.slider("Web sessions in last 90 days", 0, 80, int(row["sessions_last_90d"].iat[0]))
        new["session_trend"] = new["sessions_last_90d"] - new["sessions_prev_90d"]
        new["recency_days"] = st.slider("Days since last order", 0, 365, int(row["recency_days"].iat[0]))
    new_p = float(model.predict_proba(new[NUM + CAT])[:, 1][0])
    with c2:
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta", value=new_p * 100, number=dict(suffix="%"),
            delta=dict(reference=base_p * 100, increasing=dict(color="#d03b3b"), decreasing=dict(color="#0ca30c"),
                       valueformat=".1f"),
            gauge=dict(axis=dict(range=[0, 100]), bar=dict(color=BLUE),
                       steps=[dict(range=[0, 30], color="#e7f6e7"), dict(range=[30, 60], color="#fdf1d6"),
                              dict(range=[60, 100], color="#f8dede")]),
            title=dict(text="Churn probability (next 90 days)")))
        st.plotly_chart(style(fig, 330), width="stretch")
        tier = "High" if new_p >= 0.6 else "Medium" if new_p >= 0.3 else "Low"
        st.markdown(f"Risk tier: **{tier}** · original prediction **{base_p:.0%}**")

# ----------------------------------------------------------------------------- model
with tab_model:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Model", m["best_model"])
    c2.metric("ROC-AUC (test)", f"{m['test_roc_auc']:.3f}")
    c3.metric("PR-AUC (test)", f"{m['test_pr_auc']:.3f}", f"baseline {m['churn_rate']:.2f}", delta_color="off")
    c4.metric("Top-decile lift", f"{m['top_decile_lift']:.1f}×")
    st.markdown("**Model comparison** (5-fold cross-validation on the training set)")
    st.dataframe(pd.DataFrame(m["model_comparison"]), width="stretch", hide_index=True)

    imp = d["importance"].head(12).sort_values("mean_abs_shap")
    fig = px.bar(imp, x="mean_abs_shap", y="feature_label", orientation="h",
                 title="Global feature importance (mean |SHAP|)", color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title="mean |SHAP value|", yaxis_title=None)
    c1, c2 = st.columns(2)
    c1.plotly_chart(style(fig, 440), width="stretch")
    if (IMAGES / "model_performance.png").exists():
        c2.image(str(IMAGES / "model_performance.png"))
        c2.image(str(IMAGES / "confusion_matrix.png"), width=360)
