"""Clean the Meituan food-delivery data and build the tables the analysis runs on.

Input : data/raw/meituan/*.csv  (github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge; CC BY-NC 4.0,
        redistribution not allowed, so raw files are never committed)
Output: data/meituan.db            SQLite, local only: orders (one row per delivered order), merchants, slots, dispatch snapshots
        data/slots.csv             district x weekday x half-hour: orders, late, stage times, courier load (aggregated)
        data/late_buckets.csv      late orders counted by how late they were and how much each lever could save (aggregated)
        data/meituan_cleaning.json every cleaning step and how many orders it removed

Run from the repository root: python src/prepare_meituan.py

What one order looks like: created -> sent to dispatch -> offered to a courier (refusals create a new waybill)
-> accepted ("grab") -> picked up at the restaurant ("fetch") -> delivered ("arrive").
Late = delivered after the time the platform promised the customer (estimate_arrived_time): the real SLA.
Timestamps are Unix seconds; the data is from China, so local time = UTC+8 (peaks land at 11:00 and 17:00-18:00).

Root cause of a late order: each stage is compared with the median for ON-TIME orders in the same district and
hour (and, for the two travel stages, the same distance band). The stage with the largest overrun is the cause.
"""
import json
import sqlite3

import numpy as np
import pandas as pd

RAW = "data/raw/meituan/"
TZ_SECONDS = 8 * 3600
SLOT_SECONDS = 1800
MAX_MINUTES = 180
SLOW_MERCHANT_SHARE = 0.10      # the slowest 10% of merchants (by pickup overrun) are the account-management target
MIN_MERCHANT_ORDERS = 50
STACK_CAP = 2                   # like-for-like, a 3rd order in a run adds ~5 more late points than a 2nd (sql Q6)
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STAGES = ["dispatch", "accept", "pickup", "lastmile"]


def minutes(a, b):
    return (a - b) / 60


def distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres. Coordinates are degrees x 1e6, shifted (distances are preserved)."""
    lat1, lng1, lat2, lng2 = (np.radians(x / 1e6) for x in (lat1, lng1, lat2, lng2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(h))


def load_orders():
    """One row per delivered order: its final (accepted) waybill plus first dispatch time and refusal count."""
    w = pd.read_csv(RAW + "all_waybill_info_meituan_0322.csv", index_col=0)
    per_order = w.groupby("order_id").agg(first_dispatch=("dispatch_time", "min"), waybills=("waybill_id", "size"))
    raw_orders = len(per_order)
    o = w[w.is_courier_grabbed == 1].join(per_order, on="order_id")
    return o, raw_orders, len(w)


def clean(o, raw_orders):
    steps = [("orders in the data", raw_orders), ("never accepted by a courier", -(raw_orders - len(o)))]
    o["total_min"] = minutes(o.arrive_time, o.platform_order_time)
    in_order = ((o.platform_order_time <= o.order_push_time) & (o.order_push_time <= o.first_dispatch)
                & (o.first_dispatch <= o.grab_time) & (o.grab_time <= o.fetch_time) & (o.fetch_time <= o.arrive_time))
    filters = [
        ("not delivered (no arrival time)", o.arrive_time > 0),
        ("pre-booked orders (different promise logic)", o.is_prebook == 0),
        ("no meal-preparation estimate", o.estimate_meal_prepare_time > 0),
        ("timestamps out of order", in_order),
        (f"delivery time over {MAX_MINUTES} min", o.total_min <= MAX_MINUTES),
    ]
    keep = pd.Series(True, index=o.index)
    for label, ok in filters:
        steps.append((label, -int((keep & ~ok).sum())))
        keep &= ok
    steps.append(("clean orders", int(keep.sum())))
    return o[keep].copy(), steps


def add_features(o):
    local = pd.to_datetime(o.platform_order_time + TZ_SECONDS, unit="s")
    day = pd.to_datetime(o.dt.astype(str), format="%Y%m%d")      # the dataset's own business date
    o["date"] = day.dt.date.astype(str)
    o["dow"] = day.dt.day_name()
    o["hour"] = local.dt.hour
    o["halfhour"] = local.dt.hour * 2 + local.dt.minute // 30          # 0..47
    o["promise_min"] = minutes(o.estimate_arrived_time, o.platform_order_time)
    o["late_min"] = minutes(o.arrive_time, o.estimate_arrived_time)
    o["is_late"] = (o.late_min > 0).astype(int)
    o["redispatched"] = (o.waybills > 1).astype(int)
    o["t_dispatch"] = minutes(o.first_dispatch, o.platform_order_time)   # waiting to be offered to a courier
    o["t_accept"] = minutes(o.grab_time, o.first_dispatch)               # includes refusals and re-dispatch
    o["t_pickup"] = minutes(o.fetch_time, o.grab_time)                   # travel to the restaurant + waiting for food
    o["t_lastmile"] = minutes(o.arrive_time, o.fetch_time)               # restaurant to door, incl. other drops
    o["food_ready_wait"] = minutes(o.fetch_time, o.estimate_meal_prepare_time)
    o["store_m"] = distance_m(o.grab_lat, o.grab_lng, o.sender_lat, o.sender_lng)
    o["customer_m"] = distance_m(o.sender_lat, o.sender_lng, o.recipient_lat, o.recipient_lng)
    bands = [-1, 300, 700, 1200, 2000, np.inf]
    o["store_band"] = pd.cut(o.store_m, bands, labels=False)
    o["customer_band"] = pd.cut(o.customer_m, bands, labels=False)
    return o


def add_wave_size(o):
    """How many orders the courier carried in the run (wave) that included this order."""
    v = pd.read_csv(RAW + "courier_wave_info_meituan.csv")
    v["order_id"] = v.order_ids.str.strip("[]").str.split(",")
    v["wave_orders"] = v.order_id.str.len()
    v = v.explode("order_id")
    v["order_id"] = v.order_id.astype(int)
    sizes = v.drop_duplicates("order_id").set_index("order_id").wave_orders
    o["wave_orders"] = o.order_id.map(sizes).fillna(1).astype(int)
    # orders beyond the cap in each run, spread over the run's orders (sums to max(0, n - cap) per run)
    o["over_cap_share"] = np.maximum(0, o.wave_orders - STACK_CAP) / o.wave_orders
    return o, v


def add_root_causes(o):
    """Overrun of each stage versus on-time orders in the same district and hour (and distance band)."""
    on_time = o[o.is_late == 0]
    keys = {"dispatch": ["da_id", "hour"], "accept": ["da_id", "hour"],
            "pickup": ["da_id", "hour", "store_band"], "lastmile": ["da_id", "hour", "customer_band"]}
    for stage, k in keys.items():
        expected = on_time.groupby(k)[f"t_{stage}"].median().rename(f"exp_{stage}")
        o = o.join(expected, on=k)
        o[f"exp_{stage}"] = o[f"exp_{stage}"].fillna(on_time[f"t_{stage}"].median())
        o[f"over_{stage}"] = (o[f"t_{stage}"] - o[f"exp_{stage}"]).clip(lower=0)
    over = o[[f"over_{s}" for s in STAGES]]
    o["root_cause"] = np.where(over.max(axis=1) > 0, over.idxmax(axis=1).str.replace("over_", ""), "promise too tight")
    o.loc[o.is_late == 0, "root_cause"] = None
    return o


def merchants(o):
    m = o.groupby("poi_id").agg(orders=("is_late", "size"), late=("is_late", "sum"),
                                avg_pickup_overrun=("over_pickup", "mean"), avg_food_ready_wait=("food_ready_wait", "mean"))
    eligible = m[m.orders >= MIN_MERCHANT_ORDERS]
    cutoff = eligible.avg_pickup_overrun.quantile(1 - SLOW_MERCHANT_SHARE)
    m["slow_merchant"] = ((m.orders >= MIN_MERCHANT_ORDERS) & (m.avg_pickup_overrun >= cutoff)).astype(int)
    return m.reset_index(), float(cutoff)


def busy_minutes(df, start, end):
    """Split each [start, end] interval over half-hour slots; returns district, date-slot, minutes."""
    s, e = df[start].values + TZ_SECONDS, df[end].values + TZ_SECONDS
    a, b = s // SLOT_SECONDS, e // SLOT_SECONDS
    idx = np.repeat(np.arange(len(df)), (b - a + 1).astype(int))
    k = np.concatenate([np.arange(x, y + 1) for x, y in zip(a, b)])
    mins = (np.minimum(e[idx], (k + 1) * SLOT_SECONDS) - np.maximum(s[idx], k * SLOT_SECONDS)) / 60
    return pd.DataFrame({"da_id": df.da_id.values[idx], "abs_slot": k, "minutes": mins})


def slots(o, waves):
    """District x weekday x half-hour. Load = orders being carried / couriers on a run (Little's law)."""
    o["abs_slot"] = (o.platform_order_time + TZ_SECONDS) // SLOT_SECONDS
    carried = busy_minutes(o, "grab_time", "arrive_time").groupby(["da_id", "abs_slot"]).minutes.sum().rename("order_min")
    home = o.groupby(["dt", "courier_id"]).da_id.agg(lambda s: s.mode().iat[0]).rename("da_id").reset_index()
    runs = waves.drop_duplicates(["dt", "courier_id", "wave_id"])[["dt", "courier_id", "wave_start_time", "wave_end_time"]].merge(home, on=["dt", "courier_id"])
    busy = busy_minutes(runs, "wave_start_time", "wave_end_time").groupby(["da_id", "abs_slot"]).minutes.sum().rename("courier_min")
    per_date = (o.groupby(["da_id", "abs_slot", "date", "dow", "halfhour"])
                 .agg(orders=("is_late", "size"), late=("is_late", "sum"), redispatched=("redispatched", "sum"),
                      sum_promise=("promise_min", "sum"), sum_total=("total_min", "sum"), sum_dispatch=("t_dispatch", "sum"),
                      sum_lastmile=("t_lastmile", "sum"), over_cap_orders=("over_cap_share", "sum"))
                 .reset_index().join(carried, on=["da_id", "abs_slot"]).join(busy, on=["da_id", "abs_slot"]).fillna(0))
    g = per_date.groupby(["da_id", "dow", "halfhour"])
    out = g[["orders", "late", "redispatched", "sum_promise", "sum_total", "sum_dispatch", "sum_lastmile",
             "over_cap_orders", "order_min", "courier_min"]].sum()
    out["days"] = g.date.nunique()
    out["load"] = out.order_min / out.courier_min.replace(0, np.nan)
    out = out.reset_index()
    out["dow_idx"] = out.dow.map(DAYS.index)
    return out.round(3), per_date


def add_stack_cost(o):
    """Measured last-mile cost of a run bigger than the cap: average last mile for this run size minus the
    average for runs of exactly STACK_CAP orders, in the same district and hour (sizes above 6 pooled)."""
    size = np.minimum(o.wave_orders, 6)
    cell = o.assign(size=size).groupby(["da_id", "hour", "size"]).t_lastmile.agg(["mean", "size"])
    at_cap = cell.xs(STACK_CAP, level="size")
    at_cap = at_cap[at_cap["size"] >= 20]["mean"].rename("lastmile_at_cap")
    own = cell["mean"].rename("lastmile_own_size")
    o = o.assign(size=size).join(own, on=["da_id", "hour", "size"]).join(at_cap, on=["da_id", "hour"])
    o["stack_cost_min"] = np.where(o.wave_orders > STACK_CAP, (o.lastmile_own_size - o.lastmile_at_cap).clip(lower=0), 0)
    o["stack_cost_min"] = o.stack_cost_min.fillna(0)
    return o.drop(columns=["size", "lastmile_own_size", "lastmile_at_cap"])


def late_buckets(o):
    """Late orders by whole minutes late (rounded up) and minutes each free lever could save (rounded down)."""
    late = o[o.is_late == 1]
    b = pd.DataFrame({"da_id": late.da_id, "dow": late.dow, "halfhour": late.halfhour,
                      "late_min": np.minimum(np.ceil(late.late_min), 61).astype(int),
                      "merchant_save": np.minimum(np.floor(late.over_pickup * late.slow_merchant), 60).astype(int),
                      "refusal_save": np.minimum(np.floor(late.over_accept * late.redispatched), 60).astype(int),
                      "stack_save": np.minimum(np.floor(late.stack_cost_min), 60).astype(int)})
    return b.groupby(list(b.columns)).size().rename("orders").reset_index()


def dispatch_snapshots():
    rider = pd.read_csv(RAW + "dispatch_rider_meituan.csv", index_col=0)
    waiting = pd.read_csv(RAW + "dispatch_waybill_meituan.csv", index_col=0)
    rider["on_hand"] = rider.courier_waybills.str.strip("[]").str.split(",").map(lambda x: len([i for i in x if i.strip()]))
    snap = rider.groupby(["dt", "dispatch_time"]).agg(candidates=("courier_id", "nunique"),
                                                      idle=("on_hand", lambda s: int((s == 0).sum())),
                                                      avg_on_hand=("on_hand", "mean"))
    snap["orders_waiting"] = waiting.groupby(["dt", "dispatch_time"]).order_id.nunique()
    snap = snap.reset_index()
    snap["local_time"] = pd.to_datetime(snap.dispatch_time + TZ_SECONDS, unit="s").dt.strftime("%a %H:%M")
    return snap


def main():
    o, raw_orders, raw_waybills = load_orders()
    o, steps = clean(o, raw_orders)
    o = add_features(o)
    o, waves = add_wave_size(o)
    o = add_root_causes(o)
    o = add_stack_cost(o)
    m, cutoff = merchants(o)
    o = o.merge(m[["poi_id", "slow_merchant"]], on="poi_id")
    s, per_date = slots(o, waves)
    b = late_buckets(o)

    cols = ["order_id", "date", "dow", "hour", "halfhour", "da_id", "poi_id", "courier_id", "is_weekend",
            "promise_min", "total_min", "late_min", "is_late", "waybills", "redispatched", "wave_orders",
            "over_cap_share", "stack_cost_min", "t_dispatch", "t_accept", "t_pickup", "t_lastmile", "food_ready_wait", "store_m", "customer_m",
            "over_dispatch", "over_accept", "over_pickup", "over_lastmile", "root_cause", "slow_merchant"]
    con = sqlite3.connect("data/meituan.db")
    for name, table in [("orders", o[cols].round(3)), ("merchants", m), ("slots", s),
                        ("slots_by_date", per_date), ("dispatch_snapshots", dispatch_snapshots())]:
        table.to_sql(name, con, if_exists="replace", index=False)
    con.close()
    s.to_csv("data/slots.csv", index=False)
    b.to_csv("data/late_buckets.csv", index=False)

    report = {"cleaning_steps": steps, "raw_waybills": raw_waybills, "utc_offset_hours": 8,
              "dates": [o.date.min(), o.date.max()], "days": int(o.date.nunique()),
              "districts": int(o.da_id.nunique()), "merchants": int(o.poi_id.nunique()), "couriers": int(o.courier_id.nunique()),
              "late_pct": round(100 * o.is_late.mean(), 2), "late_over_5min_pct": round(100 * (o.late_min > 5).mean(), 2),
              "median_promise_min": round(o.promise_min.median(), 1), "median_total_min": round(o.total_min.median(), 1),
              "redispatched_pct": round(100 * o.redispatched.mean(), 2),
              "slow_merchant_cutoff_overrun_min": round(cutoff, 2), "slow_merchants": int(m.slow_merchant.sum())}
    json.dump(report, open("data/meituan_cleaning.json", "w"), indent=1, default=str)
    for label, n in steps:
        print(f"{label:<45}{n:>10,}")
    print(json.dumps({k: v for k, v in report.items() if k != "cleaning_steps"}, indent=1, default=str))
    print(f"slots: {len(s)} rows, late buckets: {len(b)} rows")


if __name__ == "__main__":
    main()
