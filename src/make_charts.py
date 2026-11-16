"""Render the static charts used in the README and report (images/*.png).

Run:  python -m src.make_charts
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve
from sqlalchemy import text

from src.config import DATA_EXPORTS, IMAGES_DIR, MODELS_DIR, SNAPSHOT_DATE, get_engine

# ---- palette (validated reference palette, light mode) ----------------------
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
BLUE, BLUE_DARK, ORANGE = "#2a78d6", "#184f95", "#eb6834"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#d03b3b"}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 10.5, "text.color": INK,
    "axes.labelcolor": INK_2, "axes.edgecolor": GRID, "axes.titleweight": "bold", "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK_2, "ytick.color": INK_2, "xtick.major.size": 0, "ytick.major.size": 0,
    "legend.frameon": False, "lines.linewidth": 2,
})
INR_LAKH = mtick.FuncFormatter(lambda v, _: f"₹{v / 1e5:,.0f}L")


def inr(v: float) -> str:
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.1f} L"


def save(fig, name: str, subtitle: str | None = None):
    if subtitle:
        fig.text(0.012, 0.005, subtitle, color=MUTED, fontsize=8.5, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03 if subtitle else 0, 1, 1))
    fig.savefig(IMAGES_DIR / f"{name}.png", dpi=160)
    plt.close(fig)
    print(f"  images/{name}.png")


def hbar(ax, labels, values, fmt, color=BLUE):
    y = np.arange(len(labels))
    ax.barh(y, values, color=color, height=0.62)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    vmax = max(values)
    for yi, v in zip(y, values):
        ax.text(v + vmax * 0.012, yi, fmt(v), va="center", color=INK_2, fontsize=9.5)
    ax.set_xlim(0, vmax * 1.15)


# -----------------------------------------------------------------------------
def monthly_revenue(kpi: pd.DataFrame):
    m =pd.to_datetime(kpi["month"])
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.plot(m, kpi["revenue"], color=BLUE, marker="o", markersize=4, label="Monthly revenue")
    ax.plot(m, kpi["revenue_3m_avg"], color=ORANGE, linestyle="--", label="3-month moving average")
    ax.yaxis.set_major_formatter(INR_LAKH)
    ax.set_ylim(0, kpi["revenue"].max() * 1.15)
    ax.set_title("Monthly net revenue grew steadily, with festive-season (Oct–Nov) peaks")
    peak = kpi.loc[kpi["revenue"].idxmax()]
    ax.annotate(f"Peak {pd.to_datetime(peak['month']):%b %Y}\n{inr(peak['revenue'])}",
                (pd.to_datetime(peak["month"]), peak["revenue"]), xytext=(-90, 4), textcoords="offset points",
                color=INK_2, fontsize=9, arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.legend(loc="upper left")
    save(fig, "monthly_revenue", "Delivered orders only, net of discounts. ₹1 L = ₹100,000.")


def category_revenue(cat: pd.DataFrame):
    g = cat.groupby("category")[["revenue", "margin"]].sum().sort_values("revenue", ascending=False)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    margin_pct = dict(zip(g["revenue"], g["margin"] / g["revenue"]))
    hbar(ax, g.index, g["revenue"].to_numpy(), lambda v: f"{inr(v)}  ({margin_pct[v]:.0%} margin)")
    ax.set_xlim(0, g["revenue"].max() * 1.35)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"₹{v / 1e7:,.0f} Cr"))
    share = g["revenue"].iloc[0] / g["revenue"].sum()
    ax.set_title(f"{g.index[0]} generates {share:.0%} of net revenue; margins are similar across categories")
    save(fig, "category_revenue", "Net revenue from delivered + returned lines, Jan 2024 – Sep 2026.")


def cohort_heatmap(coh: pd.DataFrame):
    coh = coh.assign(cohort_month=pd.to_datetime(coh["cohort_month"]))
    coh = coh[(coh["months_since_signup"].between(0, 12)) & (coh["cohort_month"] <= "2025-09-01")]
    pv = coh.pivot(index="cohort_month", columns="months_since_signup", values="retention_pct")
    pv = pv.loc[pv.index.month.isin([1, 4, 7, 10])]          # quarterly cohorts keep it readable
    fig, ax = plt.subplots(figsize=(11, 4.4))
    cmap = LinearSegmentedColormap.from_list("blues", SEQ)
    im = ax.imshow(pv.to_numpy(), cmap=cmap, aspect="auto", vmin=0, vmax=max(60, np.nanmax(pv.to_numpy())))
    ax.set_xticks(range(pv.shape[1]), [f"M{c}" for c in pv.columns])
    ax.set_yticks(range(pv.shape[0]), [f"{d:%b %Y}" for d in pv.index])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(pv.shape[0]):
        for j in range(pv.shape[1]):
            v = pv.iat[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8.5,
                        color="white" if v > 35 else INK)
    ax.set_xlabel("Months since signup")
    ax.set_title("Cohort retention: share of each signup cohort that ordered N months later")
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, format=mtick.PercentFormatter(decimals=0))
    cb.outline.set_visible(False)
    save(fig, "cohort_retention", "Quarterly signup cohorts shown. M0 = signup month.")


def rfm_segments(c360: pd.DataFrame):
    order = ["Champions", "Loyal", "New / Promising", "Needs Attention", "At Risk", "Hibernating", "Lost"]
    g = c360.groupby("rfm_segment").agg(customers=("customer_id", "count"), at_risk=("revenue_at_risk", "sum"))
    g = g.reindex([o for o in order if o in g.index])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    hbar(ax, g.index, g["customers"].to_numpy(), lambda v: f"{v:,.0f}")
    ax.set_title("RFM segments of the active customer base")
    ax.set_xlabel("Customers")
    save(fig, "rfm_segments", "Recency / Frequency / Monetary quintiles (NTILE) as of 30 Sep 2026.")


def churn_drivers(feat: pd.DataFrame):
    f = feat.copy()
    f["churned"] = f["churned"].astype(int)
    f["delivery"] = pd.cut(f["avg_shipping_days"], [0, 3, 5, 7, 99], labels=["≤3 days", "3–5", "5–7", ">7 days"])
    f["support"] = np.select([f["avg_satisfaction"].isna(), f["avg_satisfaction"] < 2.5, f["avg_satisfaction"] < 3.5],
                             ["No tickets", "Unhappy", "Neutral"], "Happy")
    f["trend"] = np.select([(f["orders_last_90d"] == 0) & (f["orders_prev_90d"] == 0),
                            f["order_trend"] < 0, f["order_trend"] == 0],
                           ["Dormant (0 orders)", "Declining", "Stable"], "Growing")
    panels = [
        ("acquisition_channel", "By acquisition channel", None),
        ("delivery", "By average delivery time", ["≤3 days", "3–5", "5–7", ">7 days"]),
        ("support", "By support satisfaction", ["No tickets", "Happy", "Neutral", "Unhappy"]),
        ("trend", "By order trend (last 90d vs prior 90d)", ["Growing", "Stable", "Declining", "Dormant (0 orders)"]),
    ]
    base = f["churned"].mean()
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, (col, title, order) in zip(axes.flat, panels):
        g = f.groupby(col, observed=True)["churned"].mean()
        g = g.reindex(order) if order else g.sort_values(ascending=False)
        hbar(ax, g.index, g.to_numpy(), lambda v: f"{v:.0%}")
        ax.axvline(base, color=MUTED, linestyle=":", linewidth=1.2)
        ax.text(base, len(g) - 0.5, f" overall {base:.0%}", color=MUTED, fontsize=8.5, va="bottom")
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
        ax.set_title(title, fontsize=11.5)
    fig.suptitle("90-day churn rate: slow delivery, bad support and fading engagement predict churn",
                 x=0.012, ha="left", fontweight="bold", fontsize=13.5)
    save(fig, "churn_drivers", f"Active customers at snapshot {SNAPSHOT_DATE:%d %b %Y}; churn = no order in the next 90 days.")


def model_curves(test: pd.DataFrame, metrics: dict):
    y, p = test["y_true"], test["churn_probability"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6))
    fpr, tpr, _ = roc_curve(y, p)
    a1.plot(fpr, tpr, color=BLUE)
    a1.plot([0, 1], [0, 1], color=MUTED, linestyle=":", linewidth=1.2)
    a1.text(0.55, 0.12, f"ROC-AUC = {roc_auc_score(y, p):.3f}", color=INK, fontsize=11, fontweight="bold")
    a1.text(0.62, 0.55, "random", color=MUTED, fontsize=9, rotation=36)
    a1.set(xlabel="False positive rate", ylabel="True positive rate", xlim=(0, 1), ylim=(0, 1.02))
    a1.set_title("ROC curve", fontsize=12)
    prec, rec, _ = precision_recall_curve(y, p)
    a2.plot(rec, prec, color=BLUE)
    a2.axhline(y.mean(), color=MUTED, linestyle=":", linewidth=1.2)
    a2.text(0.02, y.mean() + 0.02, f"baseline {y.mean():.0%}", color=MUTED, fontsize=9)
    a2.text(0.05, 0.12, f"PR-AUC = {average_precision_score(y, p):.3f}", color=INK, fontsize=11, fontweight="bold")
    a2.set(xlabel="Recall", ylabel="Precision", xlim=(0, 1), ylim=(0, 1.02))
    a2.set_title("Precision–recall curve", fontsize=12)
    fig.suptitle(f"{metrics['best_model']} on the held-out test set ({len(y):,} customers)",
                 x=0.012, ha="left", fontweight="bold", fontsize=13)
    save(fig, "model_performance")


def confusion(metrics: dict):
    cm = metrics["confusion_matrix"]
    mat = np.array([[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]])
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    cmap = LinearSegmentedColormap.from_list("blues", SEQ[:5])
    ax.imshow(mat, cmap=cmap)
    labels = [["True negative", "False positive"], ["False negative", "True positive"]]
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{mat[i, j]:,}\n{labels[i][j]}", ha="center", va="center", fontsize=10,
                    color="white" if mat[i, j] > mat.max() * 0.6 else INK)
    ax.set_xticks([0, 1], ["Stays", "Churns"])
    ax.set_yticks([0, 1], ["Stayed", "Churned"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"Confusion matrix (threshold {metrics['threshold']:.2f})", fontsize=12)
    save(fig, "confusion_matrix")


def feature_importance(imp: pd.DataFrame, metrics: dict):
    top = imp.head(12)
    unit = "log-odds" if metrics["best_model"] in ("XGBoost", "Logistic Regression") else "probability"
    fig, ax = plt.subplots(figsize=(9, 5))
    hbar(ax, top["feature_label"], top["mean_abs_shap"].to_numpy(), lambda v: f"{v:.3f}")
    ax.set_xlabel(f"Mean |SHAP value| (average impact on churn {unit})")
    ax.set_title("What drives the churn prediction? (top 12 features)")
    save(fig, "feature_importance")


def risk_tiers(c360: pd.DataFrame):
    order = ["High", "Medium", "Low"]
    g = c360.groupby("risk_tier").agg(customers=("customer_id", "count"),
                                      revenue_at_risk=("revenue_at_risk", "sum")).reindex(order)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, col, fmt, title in [(a1, "customers", lambda v: f"{v:,.0f}", "Customers by churn-risk tier"),
                                (a2, "revenue_at_risk", inr, "Expected revenue at risk")]:
        y = np.arange(len(order))
        ax.barh(y, g[col], color=[STATUS[t] for t in order], height=0.6)
        ax.set_yticks(y, [f"{t} risk" for t in order])
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
        ax.spines["left"].set_visible(False)
        vmax = g[col].max()
        for yi, v in zip(y, g[col]):
            ax.text(v + vmax * 0.015, yi, fmt(v), va="center", color=INK_2)
        ax.set_xlim(0, vmax * 1.25)
        ax.set_title(title, fontsize=12)
    a2.xaxis.set_major_formatter(INR_LAKH)
    save(fig, "risk_tiers", "High ≥ 60% churn probability, Medium 30–60%, Low < 30%. "
                            "Revenue at risk = probability × trailing-12-month spend.")


def main():
    kpi = pd.read_csv(DATA_EXPORTS / "monthly_kpis.csv")
    cat = pd.read_csv(DATA_EXPORTS / "category_monthly.csv")
    coh = pd.read_csv(DATA_EXPORTS / "cohort_retention.csv")
    c360 = pd.read_csv(DATA_EXPORTS / "customer_360.csv")
    metrics = json.loads((MODELS_DIR / "metrics.json").read_text())
    test = pd.read_csv(MODELS_DIR / "test_predictions.csv")
    imp = pd.read_csv(MODELS_DIR / "feature_importance.csv")
    with get_engine().begin() as c:
        c.execute(text("UPDATE feature_params SET snap = :s"), {"s": SNAPSHOT_DATE})
        feat = pd.read_sql("SELECT * FROM customer_features", c)

    monthly_revenue(kpi)
    category_revenue(cat)
    cohort_heatmap(coh)
    rfm_segments(c360)
    churn_drivers(feat)
    model_curves(test, metrics)
    confusion(metrics)
    feature_importance(imp, metrics)
    risk_tiers(c360)


if __name__ == "__main__":
    main()
