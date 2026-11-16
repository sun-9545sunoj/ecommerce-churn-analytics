"""Generate a realistic synthetic e-commerce dataset (India-based online retailer).

Customers are simulated month by month. Each month an active customer places a
Poisson number of orders; every order has a delivery time, may be returned or
cancelled, and may trigger a support ticket. Bad experiences (late deliveries,
returns, unhappy tickets) accumulate in a decaying "frustration" score that
raises the monthly probability of becoming disengaged and, finally, churning.
That makes churn genuinely predictable from pre-snapshot behaviour, without
the model ever seeing the hidden simulation state.

A little "dirt" (duplicates, nulls, messy emails) is injected on purpose so the
data-quality step has something real to catch.

Run:  python -m src.generate_data
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from faker import Faker

from src.config import DATA_RAW, END_DATE, RANDOM_SEED, START_DATE

N_CUSTOMERS = 10_000
N_PRODUCTS = 500

rng = np.random.default_rng(RANDOM_SEED)
fake = Faker("en_IN")
Faker.seed(RANDOM_SEED)

START = pd.Timestamp(START_DATE)
END = pd.Timestamp(END_DATE)

# state: (cities, share of customers, mean delivery days)
STATES = {
    "Maharashtra": (["Mumbai", "Pune", "Nagpur"], 0.16, 3.0),
    "Karnataka": (["Bengaluru", "Mysuru"], 0.12, 3.0),
    "Delhi": (["New Delhi"], 0.11, 2.8),
    "Tamil Nadu": (["Chennai", "Coimbatore"], 0.09, 3.4),
    "Telangana": (["Hyderabad"], 0.08, 3.2),
    "Gujarat": (["Ahmedabad", "Surat"], 0.07, 3.8),
    "West Bengal": (["Kolkata"], 0.06, 4.5),
    "Uttar Pradesh": (["Lucknow", "Noida", "Kanpur"], 0.07, 4.8),
    "Kerala": (["Kochi", "Thiruvananthapuram"], 0.05, 4.6),
    "Rajasthan": (["Jaipur", "Udaipur"], 0.04, 5.0),
    "Punjab": (["Ludhiana", "Amritsar"], 0.03, 4.8),
    "Madhya Pradesh": (["Indore", "Bhopal"], 0.04, 5.2),
    "Bihar": (["Patna"], 0.03, 7.2),
    "Odisha": (["Bhubaneswar"], 0.025, 6.8),
    "Assam": (["Guwahati"], 0.025, 7.8),
}

# channel: (share, churn-hazard effect on logit scale)
CHANNELS = {
    "Organic": (0.30, 0.0),
    "Paid Search": (0.22, 0.15),
    "Social Media": (0.18, 0.55),
    "Email": (0.10, -0.20),
    "Referral": (0.12, -0.50),
    "Affiliate": (0.08, 0.30),
}

# category: (share of demand, price range in INR, sub-categories, base return rate multiplier)
CATEGORIES = {
    "Electronics": (0.16, (1500, 60000), ["Mobiles", "Headphones", "Laptops", "Smartwatches", "Accessories"], 1.0),
    "Fashion": (0.22, (299, 4500), ["Men's Clothing", "Women's Clothing", "Footwear", "Bags"], 1.8),
    "Home & Kitchen": (0.15, (250, 9000), ["Cookware", "Decor", "Appliances", "Storage"], 0.8),
    "Beauty": (0.12, (149, 2500), ["Skincare", "Haircare", "Makeup", "Fragrance"], 0.6),
    "Sports & Fitness": (0.08, (399, 12000), ["Gym Equipment", "Sportswear", "Outdoor"], 1.0),
    "Books": (0.08, (149, 1200), ["Fiction", "Non-Fiction", "Academic"], 0.3),
    "Grocery": (0.13, (49, 900), ["Staples", "Snacks", "Beverages"], 0.2),
    "Toys": (0.06, (199, 3500), ["Educational", "Action Figures", "Board Games"], 0.7),
}
BRANDS = ["Nova", "Zenith", "Aura", "Kraft", "Vista", "Orion", "Lumen", "Pulse", "Terra", "Swift",
          "Bloom", "Apex", "Hive", "Echo", "Prism"]
PAYMENT = (["UPI", "Credit Card", "Debit Card", "Cash on Delivery", "Net Banking"], [0.42, 0.20, 0.14, 0.19, 0.05])
DISCOUNTS = ([0, 5, 10, 15, 20, 30], [0.40, 0.15, 0.18, 0.12, 0.10, 0.05])
# festive season (Diwali / Big sale) lift
SEASONALITY = {1: 0.9, 2: 0.9, 3: 0.95, 4: 1.0, 5: 1.0, 6: 0.95, 7: 1.0, 8: 1.05, 9: 1.1, 10: 1.45, 11: 1.35, 12: 1.15}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def day_num(ts) -> np.ndarray:
    """Days since START (int)."""
    return np.asarray((pd.to_datetime(ts) - START) / pd.Timedelta(days=1)).astype(int)


def make_products() -> pd.DataFrame:
    rows = []
    cats = list(CATEGORIES)
    counts = rng.multinomial(N_PRODUCTS, [CATEGORIES[c][0] for c in cats])
    pid = 1
    for cat, n in zip(cats, counts):
        _, (lo, hi), subs, _ = CATEGORIES[cat]
        for _ in range(n):
            sub = rng.choice(subs)
            price = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
            price = round(price / 10) * 10 - 1 if price > 100 else round(price)
            rows.append({
                "product_id": pid,
                "product_name": f"{rng.choice(BRANDS)} {sub} {fake.bothify('??-###').upper()}",
                "category": cat,
                "sub_category": sub,
                "unit_price": price,
                "unit_cost": round(price * rng.uniform(0.55, 0.80), 2),
            })
            pid += 1
    return pd.DataFrame(rows)


def make_customers() -> pd.DataFrame:
    # signups grow over time (business is scaling): density proportional to t + 0.4
    span = (END - START).days
    u = rng.random(N_CUSTOMERS)
    t = (-0.4 + np.sqrt(0.16 + u * (1 + 0.8))) / 1.0  # inverse CDF of (t+0.4) on [0,1]
    signup = START + pd.to_timedelta(np.floor(t * span * 0.97), unit="D")

    states = list(STATES)
    st = rng.choice(states, N_CUSTOMERS, p=np.array([STATES[s][1] for s in states]) / sum(STATES[s][1] for s in states))
    city = [rng.choice(STATES[s][0]) for s in st]
    ch = list(CHANNELS)
    channel = rng.choice(ch, N_CUSTOMERS, p=[CHANNELS[c][0] for c in ch])
    gender = rng.choice(["Male", "Female", "Other"], N_CUSTOMERS, p=[0.52, 0.46, 0.02])
    age = np.clip(rng.normal(33, 10, N_CUSTOMERS), 18, 70).round().astype(int)

    names, emails = [], []
    for i in range(N_CUSTOMERS):
        first, last = fake.first_name(), fake.last_name()
        names.append(f"{first} {last}")
        emails.append(f"{first.lower()}.{last.lower()}{i}@{rng.choice(['gmail.com', 'yahoo.in', 'outlook.com', 'rediffmail.com'])}")

    return pd.DataFrame({
        "customer_id": np.arange(1, N_CUSTOMERS + 1),
        "full_name": names,
        "email": emails,
        "gender": gender,
        "age": age,
        "city": city,
        "state": st,
        "signup_date": signup.date,
        "acquisition_channel": channel,
    })


def simulate(customers: pd.DataFrame, products: pd.DataFrame):
    n = len(customers)
    signup_day = day_num(customers["signup_date"])
    state_ship = customers["state"].map({s: v[2] for s, v in STATES.items()}).to_numpy()
    ch_eff = customers["acquisition_channel"].map({c: v[1] for c, v in CHANNELS.items()}).to_numpy()

    # hidden per-customer traits
    rate = np.clip(np.exp(rng.normal(-0.55, 0.75, n)), 0.08, 4.0)          # orders / month
    ret_prop = rng.beta(2, 25, n)                                            # return propensity
    cats = list(CATEGORIES)
    fav_cat = rng.choice(cats, n, p=[CATEGORIES[c][0] for c in cats])

    churned = np.zeros(n, bool)
    at_risk = np.zeros(n, bool)
    frustration = np.zeros(n)

    orders, sessions = [], []
    month_starts = pd.date_range(START, END, freq="MS")
    for ms in month_starts:
        me = ms + pd.offsets.MonthEnd(0)
        d0, d1 = day_num(ms), day_num(me)
        signed = signup_day <= d1
        active = signed & ~churned
        idx = np.flatnonzero(active)

        # ---- orders --------------------------------------------------------
        lo = np.maximum(signup_day[idx], d0)
        frac = (d1 - lo + 1) / (d1 - d0 + 1)
        lam = rate[idx] * np.where(at_risk[idx], 0.30, 1.0) * SEASONALITY[ms.month] * frac
        k = rng.poisson(lam)
        cust = np.repeat(idx, k)
        m = len(cust)
        lo_c = np.maximum(signup_day[cust], d0)
        oday = lo_c + np.floor(rng.random(m) * (d1 - lo_c + 1)).astype(int)

        ship = np.maximum(1, np.round(rng.normal(state_ship[cust], 1.3, m)))
        delayed = rng.random(m) < 0.07
        ship = ship + delayed * rng.integers(4, 11, m)
        late = ship > 7

        cancelled = rng.random(m) < 0.03
        p_ret = np.clip(ret_prop[cust] * np.where(late, 1.8, 1.0) * 1.2, 0, 0.9)
        returned = (~cancelled) & (rng.random(m) < p_ret)
        status = np.where(cancelled, "Cancelled", np.where(returned, "Returned", "Delivered"))

        # ---- support tickets ----------------------------------------------
        p_tk = 0.03 + 0.30 * late + 0.45 * returned + 0.15 * cancelled
        has_tk = rng.random(m) < p_tk
        resolved = rng.random(m) < np.where(late, 0.65, 0.85)
        sat = np.clip(np.round(rng.normal(4.1, 0.8, m) - 1.4 * late - 0.6 * returned - 1.2 * (~resolved)), 1, 5)
        issue = np.where(late, "Late Delivery", np.where(returned, "Return / Refund",
                         np.where(cancelled, "Payment Issue",
                                  rng.choice(["Damaged Product", "Wrong Item", "Account Help", "Other"], m))))

        if m:
            orders.append(pd.DataFrame({
                "customer_id": cust + 1, "order_day": oday, "status": status,
                "shipping_days": ship.astype(int), "is_late": late,
                "payment_method": rng.choice(PAYMENT[0], m, p=PAYMENT[1]),
                "discount_pct": rng.choice(DISCOUNTS[0], m, p=DISCOUNTS[1]),
                "fav_cat": fav_cat[cust],
                "has_ticket": has_tk, "ticket_resolved": resolved, "satisfaction": sat.astype(int),
                "issue_type": issue,
            }))

        # ---- web sessions (monthly) ---------------------------------------
        sidx = np.flatnonzero(signed)
        s_lam = np.where(churned[sidx], 0.35,
                         (1.5 + 3.5 * np.minimum(rate[sidx], 3)) * np.where(at_risk[sidx], 0.45, 1.0))
        s_cnt = rng.poisson(s_lam)
        keep = s_cnt > 0
        sessions.append(pd.DataFrame({
            "customer_id": sidx[keep] + 1, "month": ms.date(), "sessions": s_cnt[keep],
            "avg_session_minutes": np.clip(rng.normal(np.where(at_risk[sidx][keep], 4.0, 6.5), 1.8), 0.5, None).round(1),
        }))

        # ---- update hidden state ------------------------------------------
        bad = late.astype(float) + returned + (has_tk & (sat <= 2)) * 1.5
        frustration = 0.55 * frustration + np.bincount(cust, weights=bad, minlength=n)

        tenure_m = (d1 - signup_day[idx]) / 30.4
        logit_risk = -3.4 + 0.65 * frustration[idx] + 0.6 * ch_eff[idx] - 0.25 * np.log(rate[idx])
        newly_risk = (~at_risk[idx]) & (rng.random(len(idx)) < sigmoid(logit_risk))
        recover = at_risk[idx] & (rng.random(len(idx)) < 0.08)
        at_risk[idx[newly_risk]] = True
        at_risk[idx[recover]] = False

        logit_churn = (-4.6 + ch_eff[idx] + 0.45 * frustration[idx] - 0.35 * np.log(rate[idx])
                       + 2.0 * at_risk[idx] + 0.5 * (tenure_m < 3))
        churned[idx[rng.random(len(idx)) < sigmoid(logit_churn)]] = True

    orders = pd.concat(orders, ignore_index=True).sort_values(["order_day", "customer_id"]).reset_index(drop=True)
    orders["order_id"] = np.arange(100001, 100001 + len(orders))
    orders["order_date"] = (START + pd.to_timedelta(orders["order_day"], unit="D")).dt.date
    sessions = pd.concat(sessions, ignore_index=True)
    return orders, sessions


def make_items(orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    n_items = np.clip(1 + rng.poisson(0.7, len(orders)), 1, 6)
    oid = np.repeat(orders["order_id"].to_numpy(), n_items)
    fav = np.repeat(orders["fav_cat"].to_numpy(), n_items)
    cats = list(CATEGORIES)
    rand_cat = rng.choice(cats, len(oid), p=[CATEGORIES[c][0] for c in cats])
    cat = np.where(rng.random(len(oid)) < 0.6, fav, rand_cat)

    pid = np.empty(len(oid), dtype=int)
    for c in cats:
        mask = cat == c
        pool = products.loc[products["category"] == c]
        # popularity: cheaper products sell more
        w = 1 / np.sqrt(pool["unit_price"].to_numpy())
        pid[mask] = rng.choice(pool["product_id"].to_numpy(), mask.sum(), p=w / w.sum())
    qty = 1 + rng.poisson(np.where(cat == "Grocery", 1.2, 0.15))
    price = products.set_index("product_id").loc[pid, "unit_price"].to_numpy()

    items = pd.DataFrame({"order_id": oid, "product_id": pid, "quantity": qty, "unit_price": price})
    items = items.groupby(["order_id", "product_id"], as_index=False).agg(quantity=("quantity", "sum"),
                                                                           unit_price=("unit_price", "first"))
    items.insert(0, "order_item_id", np.arange(1, len(items) + 1))
    return items


def make_tickets(orders: pd.DataFrame) -> pd.DataFrame:
    t = orders.loc[orders["has_ticket"]].copy()
    t["created_at"] = pd.to_datetime(t["order_date"]) + pd.to_timedelta(t["shipping_days"] + rng.integers(0, 4, len(t)), unit="D") \
        + pd.to_timedelta(rng.integers(8 * 60, 22 * 60, len(t)), unit="min")
    t = t.loc[t["created_at"] <= END + pd.Timedelta(days=1)]
    tickets = pd.DataFrame({
        "ticket_id": np.arange(1, len(t) + 1),
        "customer_id": t["customer_id"].to_numpy(),
        "order_id": t["order_id"].to_numpy(),
        "created_at": t["created_at"].to_numpy(),
        "issue_type": t["issue_type"].to_numpy(),
        "resolved": t["ticket_resolved"].to_numpy(),
        "satisfaction_score": t["satisfaction"].to_numpy(),
    })
    return tickets.sort_values("created_at").assign(ticket_id=lambda d: np.arange(1, len(d) + 1))


def add_dirt(customers: pd.DataFrame, orders: pd.DataFrame):
    """Inject realistic data-quality issues for the cleaning step to fix."""
    c = customers.copy()
    c.loc[c.sample(frac=0.012, random_state=1).index, "age"] = np.nan
    c.loc[c.sample(frac=0.006, random_state=2).index, "city"] = None
    messy = c.sample(frac=0.03, random_state=3).index
    c.loc[messy, "email"] = "  " + c.loc[messy, "email"].str.upper() + " "
    c = pd.concat([c, c.sample(60, random_state=4)], ignore_index=True)  # duplicate rows

    o = orders.copy()
    o["shipping_days"] = o["shipping_days"].astype("Int64")
    o.loc[o.sample(frac=0.003, random_state=5).index, "shipping_days"] = pd.NA
    o = pd.concat([o, o.sample(120, random_state=6)], ignore_index=True)
    return c, o


def main():
    products = make_products()
    customers = make_customers()
    orders, sessions = simulate(customers, products)
    items = make_items(orders, products)
    tickets = make_tickets(orders)
    customers_dirty, orders_dirty = add_dirt(customers, orders)

    order_cols = ["order_id", "customer_id", "order_date", "status", "payment_method", "shipping_days", "discount_pct"]
    out = {
        "customers": customers_dirty,
        "products": products,
        "orders": orders_dirty[order_cols],
        "order_items": items,
        "support_tickets": tickets,
        "web_sessions": sessions,
    }
    for name, df in out.items():
        df.to_csv(DATA_RAW / f"{name}.csv", index=False)
        print(f"{name:<16} {len(df):>9,} rows")


if __name__ == "__main__":
    main()
