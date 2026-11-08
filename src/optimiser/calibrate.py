"""Calibrate how deliveries behave under pressure, from real data already aggregated in this repository.

Inputs (committed aggregates, no raw data needed):
  data/slots.csv                                     Meituan, 23 districts x weekday x half-hour (real SLA data)
  archive/doordash_version/market_weekday_hour.csv   DoorDash, 6 US markets x weekday x hour (demand shape only)
Output: data/optimiser/calibration.json, data/optimiser/response_curve.csv

What is calibrated, in plain words:
- Load = orders being carried per courier at a moment. Little's law: load = orders per hour x hours each order
  spends with a courier / couriers. Measured on Meituan as order-minutes carried / courier-minutes on a run.
- Response curve: share of orders delivered after their promise, as a function of load. Fitted as
  late = a + b x ln(load): "each doubling of the load adds b x ln 2 points of lateness", floored at the lowest
  observed level. This matches the measured shape (steep, then flattening) and is convex in the number of
  couriers, which makes the greedy optimiser exactly optimal.
- Minutes an order spends with a courier, and staffing (load) by hour of day: from Meituan.
- Demand shape by weekday and hour: from DoorDash (a Western, dinner-peaked pattern, closer to Brussels than
  Meituan's 11:00 lunch rush). Only the shape is used, never the volume.
Run from the repository root: python src/optimiser/calibrate.py
"""
import json
import os

import numpy as np
import pandas as pd

OUT = "data/optimiser/"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BINS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]


def meituan_slots():
    s = pd.read_csv("data/slots.csv")
    s = s[(s.courier_min >= 30) & (s.orders >= 10)].copy()
    s["load"] = s.order_min / s.courier_min
    s["hour"] = s.halfhour // 2
    return s[s.load.between(BINS[0], BINS[-1])]


def fit_curve(s):
    """Weighted least squares of late rate on ln(load), on district-weekday-half-hour cells."""
    w, x, y = s.orders.values, np.log(s.load.values), (s.late / s.orders).values
    X = np.c_[np.ones_like(x), x] * np.sqrt(w)[:, None]
    (a, b), *_ = np.linalg.lstsq(X, y * np.sqrt(w), rcond=None)
    s = s.assign(band=pd.cut(s.load, BINS))
    t = s.groupby("band", observed=True).agg(orders=("orders", "sum"), late=("late", "sum"),
                                             load=("load", lambda v: np.average(v, weights=s.loc[v.index, "orders"])))
    t["observed_late"] = t.late / t.orders
    floor = float(t.observed_late.min())
    t["fitted_late"] = np.maximum(floor, a + b * np.log(t.load))
    t["band"] = t.index.astype(str)
    return float(a), float(b), floor, t.reset_index(drop=True)[["band", "load", "orders", "observed_late", "fitted_late"]]


def staffing_by_hour(s_all):
    """City-wide load by hour of day: how tightly the real network is staffed relative to its demand."""
    s = s_all.groupby(s_all.halfhour // 2)[["order_min", "courier_min", "orders"]].sum()
    s = s[s.orders >= 500]
    return (s.order_min / s.courier_min).round(3)


def demand_shape():
    d = pd.read_csv("archive/doordash_version/market_weekday_hour.csv")
    g = d.groupby(["dow", "hour"]).orders.sum().reset_index()
    g["share"] = g.orders / g.orders.sum()
    g["dow_idx"] = g.dow.map(DAYS.index)
    return g.sort_values(["dow_idx", "hour"])[["dow_idx", "hour", "share"]]


def main():
    os.makedirs(OUT, exist_ok=True)
    raw = pd.read_csv("data/slots.csv")
    s = meituan_slots()
    a, b, floor, table = fit_curve(s)
    table.round(4).to_csv(OUT + "response_curve.csv", index=False)
    minutes_with_courier = raw.order_min.sum() / raw.orders.sum()
    healthy = s[s.load < 1.5]
    calib = {
        "curve": {"a": round(a, 5), "b": round(b, 5), "floor": round(floor, 5),
                  "late_pts_per_doubling": round(100 * b * np.log(2), 2)},
        "minutes_with_courier_per_order": round(float(minutes_with_courier), 2),
        "orders_per_busy_courier_hour_healthy": round(float(healthy.orders.sum() / (healthy.courier_min.sum() / 60)), 2),
        "staffing_load_by_hour": {int(h): float(v) for h, v in staffing_by_hour(raw).items()},
        "demand_shape": demand_shape().round(6).values.tolist(),   # [weekday 0=Mon, hour, share of weekly orders]
        "sources": {"curve, minutes, staffing": "Meituan INFORMS TSL data (data/slots.csv)",
                    "demand shape": "DoorDash Kaggle data (archive/doordash_version/market_weekday_hour.csv)"},
    }
    json.dump(calib, open(OUT + "calibration.json", "w"), indent=1)
    print(table.round(3).to_string(index=False))
    print(json.dumps({k: v for k, v in calib.items() if k != "demand_shape"}, indent=1))


if __name__ == "__main__":
    main()
