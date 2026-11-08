"""Clean the DoorDash delivery data and build the tables the analysis runs on.

Input : data/raw/historical_data.csv  (Kaggle: dharun4772/doordash-eta-prediction; not committed)
        data/india_summary.json       batching delay, from src/prepare_india.py (run that first)
Output: data/doordash.db              SQLite: deliveries (one row per delivery) + the three tables below
        data/market_hour.csv          market x date x local hour: orders, late, delivery time, dashers
        data/market_hour_load.csv     the same, split by load-ratio bin (what the lever model uses)
        data/market_weekday_hour.csv  market x weekday x hour averages (heatmaps, scorecards)
        data/doordash_cleaning.json   every cleaning step and how many rows it removed

Run from the repository root: python src/prepare_doordash.py

Decisions (each is justified by a printout of this script):
- Delivery time = actual_delivery_time - created_at, in minutes. Kept between 5 and 180 minutes:
  under 5 is not physically a delivery, and 180 is above the 99.9th percentile (166 min).
- Timestamps are UTC. UTC-8 (US/Pacific winter time, no daylight saving in Jan-Feb) puts the
  peaks at 12:00 and 18:00 local; UTC-5 would put "lunch" at 15:00. The data card agrees.
- Late = delivered in more than 60 minutes: the "within the hour" promise, at the 80th percentile.
- busy_ratio = busy / on-shift dashers, capped at 1 (busy > on-shift in ~20% of rows: Kaggle added noise).
- load_ratio = outstanding orders / on-shift dashers: orders waiting per available dasher.
"""
import json
import sqlite3

import numpy as np
import pandas as pd

RAW = "data/raw/historical_data.csv"
UTC_OFFSET_HOURS = -8          # US/Pacific in winter
MIN_MINUTES, MAX_MINUTES = 5, 180
LATE_MINUTES = 60
LOAD_BIN_WIDTH, LOAD_CAP = 0.1, 2.5   # bins of 0.1; everything at or above 2.5 shares one top bin
FIRST_DAY, LAST_DAY = "2015-01-21", "2015-02-17"   # 28 full local days = 4 weeks


def batching_delay_pct():
    """Extra delivery time of a two-order trip, like-for-like, from the Indian data (run prepare_india.py first)."""
    return json.load(open("data/india_summary.json"))["batching_delay_pct"]


def load_raw():
    d = pd.read_csv(RAW, parse_dates=["created_at", "actual_delivery_time"])
    d["delivery_minutes"] = (d.actual_delivery_time - d.created_at).dt.total_seconds() / 60
    d["local_time"] = d.created_at + pd.Timedelta(hours=UTC_OFFSET_HOURS)
    return d


def clean(d):
    """Apply each filter in turn and record how many rows it removes."""
    counts = [("raw rows", len(d))]
    steps = [
        ("missing timestamps", d.actual_delivery_time.notna()),
        ("missing market_id", d.market_id.notna()),
        ("missing dasher / outstanding-order counts", d.total_onshift_dashers.notna()
         & d.total_busy_dashers.notna() & d.total_outstanding_orders.notna()),
        ("negative dasher or order counts (noise)", (d.total_onshift_dashers >= 0)
         & (d.total_busy_dashers >= 0) & (d.total_outstanding_orders >= 0)),
        ("zero dashers on shift (ratios undefined)", d.total_onshift_dashers > 0),
        (f"delivery time outside {MIN_MINUTES}-{MAX_MINUTES} min", d.delivery_minutes.between(MIN_MINUTES, MAX_MINUTES)),
        (f"outside {FIRST_DAY} to {LAST_DAY} local", d.local_time.dt.date.astype(str).between(FIRST_DAY, LAST_DAY)),
    ]
    keep = pd.Series(True, index=d.index)
    for label, ok in steps:
        removed = int((keep & ~ok.fillna(False)).sum())
        keep &= ok.fillna(False)
        counts.append((label, -removed))
    counts.append(("clean rows", int(keep.sum())))
    return d[keep].copy(), counts


def add_features(d):
    d["market_id"] = d.market_id.astype(int)
    d["date"] = d.local_time.dt.date.astype(str)
    d["dow"] = d.local_time.dt.day_name()
    d["hour"] = d.local_time.dt.hour
    d["busy_ratio"] = (d.total_busy_dashers / d.total_onshift_dashers).clip(upper=1)
    d["load_ratio"] = d.total_outstanding_orders / d.total_onshift_dashers
    d["load_bin"] = (np.minimum(d.load_ratio, LOAD_CAP) // LOAD_BIN_WIDTH * LOAD_BIN_WIDTH).round(1)
    d["is_late"] = (d.delivery_minutes > LATE_MINUTES).astype(int)
    # Would this order be late if it were batched with a second one? (delay measured in prepare_india.py)
    d["late_if_batched"] = (d.delivery_minutes * (1 + batching_delay_pct() / 100) > LATE_MINUTES).astype(int)
    d["basket_usd"] = d.subtotal / 100
    d["order_place_min"] = d.estimated_order_place_duration / 60
    d["drive_min"] = d.estimated_store_to_consumer_driving_duration / 60
    cols = ["market_id", "date", "dow", "hour", "store_id", "store_primary_category", "order_protocol",
            "basket_usd", "total_items", "total_onshift_dashers", "total_busy_dashers", "total_outstanding_orders",
            "busy_ratio", "load_ratio", "load_bin", "order_place_min", "drive_min", "delivery_minutes", "is_late", "late_if_batched"]
    return d[cols]


def market_hour(d):
    """One row per market x local date x hour. Dashers = average on-shift count seen by that hour's orders."""
    g = d.groupby(["market_id", "date", "dow", "hour"])
    return g.agg(orders=("is_late", "size"), late=("is_late", "sum"),
                 avg_minutes=("delivery_minutes", "mean"),
                 avg_onshift=("total_onshift_dashers", "mean"), avg_busy=("total_busy_dashers", "mean"),
                 avg_outstanding=("total_outstanding_orders", "mean"),
                 load_ratio=("load_ratio", "mean"), busy_ratio=("busy_ratio", "mean"),
                 basket_usd=("basket_usd", "mean")).round(3).reset_index()


def market_hour_load(d):
    g = d.groupby(["market_id", "date", "dow", "hour", "load_bin"])
    return g.agg(orders=("is_late", "size"), late=("is_late", "sum"),
                 late_if_batched=("late_if_batched", "sum"),
                 minutes_sum=("delivery_minutes", "sum")).round(1).reset_index()


def market_weekday_hour(mh):
    weeks = mh.groupby(["market_id", "dow", "hour"]).date.nunique()
    g = mh.groupby(["market_id", "dow", "hour"])
    out = g.agg(orders=("orders", "sum"), late=("late", "sum"), avg_onshift=("avg_onshift", "mean"),
                load_ratio=("load_ratio", "mean"), busy_ratio=("busy_ratio", "mean"))
    out["days_observed"] = weeks
    out["late_pct"] = 100 * out.late / out.orders
    return out.round(3).reset_index()


def main():
    raw = load_raw()
    d, counts = clean(raw)
    d = add_features(d)
    mh, mhl = market_hour(d), market_hour_load(d)
    mwh = market_weekday_hour(mh)

    con = sqlite3.connect("data/doordash.db")
    for name, table in [("deliveries", d), ("market_hour", mh), ("market_hour_load", mhl), ("market_weekday_hour", mwh)]:
        table.to_sql(name, con, if_exists="replace", index=False)
    con.close()
    mh.to_csv("data/market_hour.csv", index=False)
    mhl.to_csv("data/market_hour_load.csv", index=False)
    mwh.to_csv("data/market_weekday_hour.csv", index=False)

    hours = d.hour.value_counts(normalize=True).sort_index().mul(100).round(1)
    report = {
        "cleaning_steps": counts,
        "utc_offset_hours": UTC_OFFSET_HOURS,
        "local_order_share_by_hour_pct": hours.to_dict(),
        "delivery_minutes_percentiles": d.delivery_minutes.quantile([.5, .8, .9, .95, .99]).round(1).to_dict(),
        "late_threshold_minutes": LATE_MINUTES,
        "late_rate_pct": round(100 * d.is_late.mean(), 1),
        "avg_basket_usd": round(d.basket_usd.mean(), 2),
        "median_basket_usd": round(d.basket_usd.median(), 2),
        "busy_above_onshift_share_pct": round(100 * (d.total_busy_dashers > d.total_onshift_dashers).mean(), 1),
        "markets": int(d.market_id.nunique()), "market_hours": len(mh), "weeks": 4,
    }
    json.dump(report, open("data/doordash_cleaning.json", "w"), indent=1, default=str)
    for label, n in counts:
        print(f"{label:<45}{n:>10,}")
    print(json.dumps({k: v for k, v in report.items() if k != "cleaning_steps"}, indent=1, default=str))


if __name__ == "__main__":
    main()
