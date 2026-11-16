"""Train, evaluate and explain the churn model, then score the current customer base.

1. Pull training data from the `customer_features` view at the historical
   snapshot (2026-06-30) - the 90-day churn label is known.
2. Compare Logistic Regression, Random Forest and XGBoost with 5-fold CV.
3. Evaluate the best model on a held-out test set; explain it with SHAP.
4. Re-point the view to the latest date (2026-09-30), score every active
   customer and write `churn_predictions` back to Postgres.

Run:  python -m src.train_model
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text
from xgboost import XGBClassifier

from src.config import END_DATE, MODELS_DIR, RANDOM_SEED, SNAPSHOT_DATE, get_engine

NUMERIC = [
    "age", "tenure_days", "recency_days", "frequency_365d", "orders_last_90d", "orders_prev_90d",
    "order_trend", "monetary_365d", "avg_order_value", "lifetime_orders", "return_rate", "cancel_rate",
    "avg_shipping_days", "late_delivery_rate", "avg_discount_pct", "cod_share", "distinct_categories",
    "tickets_180d", "unresolved_tickets", "low_sat_tickets", "avg_satisfaction", "sessions_last_90d",
    "sessions_prev_90d", "session_trend", "avg_session_minutes",
]
CATEGORICAL = ["gender", "state", "acquisition_channel", "favourite_category"]
TARGET = "churned"

READABLE = {
    "recency_days": "Days since last order", "frequency_365d": "Orders in last year",
    "orders_last_90d": "Orders in last 90 days", "orders_prev_90d": "Orders in prior 90 days",
    "order_trend": "Order trend (90d vs prior)", "monetary_365d": "Spend in last year",
    "avg_order_value": "Average order value", "lifetime_orders": "Lifetime orders",
    "return_rate": "Return rate", "cancel_rate": "Cancellation rate",
    "avg_shipping_days": "Average delivery days", "late_delivery_rate": "Late-delivery rate",
    "avg_discount_pct": "Average discount", "cod_share": "Cash-on-delivery share",
    "distinct_categories": "Categories purchased", "tickets_180d": "Support tickets (180d)",
    "unresolved_tickets": "Unresolved tickets", "low_sat_tickets": "Low-satisfaction tickets",
    "avg_satisfaction": "Support satisfaction", "sessions_last_90d": "Web sessions (90d)",
    "sessions_prev_90d": "Web sessions (prior 90d)", "session_trend": "Web-session trend",
    "avg_session_minutes": "Session length", "tenure_days": "Customer tenure", "age": "Age",
}


def readable(feature: str) -> str:
    """Map a transformed column name (e.g. 'cat__acquisition_channel_Social Media') to plain English."""
    name = feature.split("__", 1)[-1]
    if name in READABLE:
        return READABLE[name]
    if name.startswith("missingindicator_"):
        return "No support tickets" if "satisfaction" in name else name
    for c in CATEGORICAL:
        if name.startswith(c + "_"):
            return f"{c.replace('_', ' ').title()}: {name[len(c) + 1:]}"
    return name


def load_features(engine, snap) -> pd.DataFrame:
    with engine.begin() as c:
        c.execute(text("UPDATE feature_params SET snap = :s"), {"s": snap})
        return pd.read_sql("SELECT * FROM customer_features", c)


def preprocessor(scale: bool) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median", add_indicator=True))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num_steps), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])


def candidate_models(pos_weight: float) -> dict[str, Pipeline]:
    return {
        "Logistic Regression": Pipeline([("prep", preprocessor(True)),
                                         ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))]),
        "Random Forest": Pipeline([("prep", preprocessor(False)),
                                   ("clf", RandomForestClassifier(n_estimators=400, min_samples_leaf=5,
                                                                  class_weight="balanced", n_jobs=-1,
                                                                  random_state=RANDOM_SEED))]),
        "XGBoost": Pipeline([("prep", preprocessor(False)),
                             ("clf", XGBClassifier(n_estimators=400, max_depth=4, learning_rate=0.04,
                                                   subsample=0.85, colsample_bytree=0.8, min_child_weight=3,
                                                   scale_pos_weight=pos_weight, eval_metric="logloss",
                                                   random_state=RANDOM_SEED, n_jobs=-1))]),
    }


def best_f1_threshold(y, proba) -> float:
    grid = np.linspace(0.1, 0.9, 81)
    return float(grid[np.argmax([f1_score(y, proba >= t) for t in grid])])


def shap_values(model: Pipeline, X: pd.DataFrame):
    prep, clf = model.named_steps["prep"], model.named_steps["clf"]
    Xt = pd.DataFrame(prep.transform(X), columns=prep.get_feature_names_out(), index=X.index)
    if isinstance(clf, LogisticRegression):
        explainer = shap.LinearExplainer(clf, Xt)
        sv = explainer.shap_values(Xt)
    else:
        explainer = shap.TreeExplainer(clf)
        sv = explainer.shap_values(Xt)
        if isinstance(sv, list):          # older RF API: one array per class
            sv = sv[1]
        elif sv.ndim == 3:
            sv = sv[:, :, 1]
    return Xt, np.asarray(sv)


def main() -> None:
    engine = get_engine()

    # ---------------- training data (historical snapshot) -----------------
    df = load_features(engine, SNAPSHOT_DATE)
    X, y = df[NUMERIC + CATEGORICAL], df[TARGET].astype(int)
    print(f"Training population: {len(df):,} customers | churn rate {y.mean():.1%}")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=RANDOM_SEED)
    cv = StratifiedKFold(5, shuffle=True, random_state=RANDOM_SEED)
    models = candidate_models(pos_weight=(1 - y_tr.mean()) / y_tr.mean())

    results = []
    for name, pipe in models.items():
        cv_auc = cross_val_score(pipe, X_tr, y_tr, cv=cv, scoring="roc_auc", n_jobs=-1)
        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        results.append({"model": name, "cv_roc_auc": cv_auc.mean(), "cv_roc_auc_std": cv_auc.std(),
                        "test_roc_auc": roc_auc_score(y_te, p), "test_pr_auc": average_precision_score(y_te, p)})
        print(f"  {name:<20} CV AUC {cv_auc.mean():.3f} ± {cv_auc.std():.3f} | test AUC {results[-1]['test_roc_auc']:.3f}")

    comparison = pd.DataFrame(results).sort_values("cv_roc_auc", ascending=False)
    best_name = comparison.iloc[0]["model"]
    best = models[best_name]
    print(f"Best model: {best_name}")

    # threshold chosen on out-of-fold training predictions (not the test set)
    oof = cross_val_predict(best, X_tr, y_tr, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
    threshold = best_f1_threshold(y_tr, oof)
    best.fit(X_tr, y_tr)
    p_te = best.predict_proba(X_te)[:, 1]
    yhat = (p_te >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_te, yhat).ravel()

    # top-decile lift: how much better than random is targeting the riskiest 10%?
    top = np.argsort(-p_te)[: max(1, len(p_te) // 10)]
    lift = y_te.iloc[top].mean() / y_te.mean()

    metrics = {
        "best_model": best_name,
        "snapshot_date": str(SNAPSHOT_DATE),
        "scoring_date": str(END_DATE),
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "churn_rate": float(y.mean()),
        "threshold": threshold,
        "test_roc_auc": float(roc_auc_score(y_te, p_te)),
        "test_pr_auc": float(average_precision_score(y_te, p_te)),
        "precision": float(precision_score(y_te, yhat)), "recall": float(recall_score(y_te, yhat)),
        "f1": float(f1_score(y_te, yhat)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "top_decile_lift": float(lift),
        "model_comparison": comparison.round(4).to_dict(orient="records"),
    }
    print(json.dumps({k: v for k, v in metrics.items() if k != "model_comparison"}, indent=2))

    # ---------------- explainability ---------------------------------------
    Xt_te, sv_te = shap_values(best, X_te)
    importance = (pd.DataFrame({"feature": Xt_te.columns, "mean_abs_shap": np.abs(sv_te).mean(0)})
                  .assign(feature_label=lambda d: d["feature"].map(readable))
                  .sort_values("mean_abs_shap", ascending=False))

    # ---------------- final model on all labelled data ----------------------
    best.fit(X, y)
    joblib.dump({"model": best, "numeric": NUMERIC, "categorical": CATEGORICAL,
                 "threshold": threshold, "metrics": metrics}, MODELS_DIR / "churn_model.pkl", compress=3)
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    importance.to_csv(MODELS_DIR / "feature_importance.csv", index=False)
    pd.DataFrame({"y_true": y_te.to_numpy(), "churn_probability": p_te}).to_csv(
        MODELS_DIR / "test_predictions.csv", index=False)
    # SHAP sample for the summary (beeswarm) chart
    joblib.dump({"shap_values": sv_te, "X": Xt_te, "labels": [readable(c) for c in Xt_te.columns]},
                MODELS_DIR / "shap_sample.pkl")

    # ---------------- score the current customer base ----------------------
    cur = load_features(engine, END_DATE)
    proba = best.predict_proba(cur[NUMERIC + CATEGORICAL])[:, 1]
    _, sv_cur = shap_values(best, cur[NUMERIC + CATEGORICAL])
    feat_names = best.named_steps["prep"].get_feature_names_out()
    top_driver = [readable(feat_names[i]) for i in sv_cur.argmax(axis=1)]

    preds = pd.DataFrame({
        "customer_id": cur["customer_id"],
        "snapshot_date": END_DATE,
        "churn_probability": proba.round(4),
        "risk_tier": pd.cut(proba, [-0.01, 0.30, 0.60, 1.01], labels=["Low", "Medium", "High"]).astype(str),
        "top_driver": top_driver,
        # actual_churned stays NULL: the future is unknown at scoring time
    })
    with engine.begin() as c:
        c.execute(text("TRUNCATE churn_predictions"))
        c.execute(text("UPDATE feature_params SET snap = :s"), {"s": SNAPSHOT_DATE})
    preds.to_sql("churn_predictions", engine, if_exists="append", index=False)

    at_risk_rev = float((proba * cur["monetary_365d"].astype(float)).sum())
    print(f"\nScored {len(preds):,} active customers as of {END_DATE}")
    print(preds["risk_tier"].value_counts().to_string())
    print(f"Expected revenue at risk (next 90d churners' trailing-year spend): ₹{at_risk_rev:,.0f}")


if __name__ == "__main__":
    main()
