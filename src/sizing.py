"""Size the levers that cut late deliveries, on the real Meituan data, and compare with a blanket peak bonus.

How the model works, in plain words:
- Every late order is late by a known number of minutes (rounded up). It becomes on time if the levers
  save at least that many minutes on its journey.
- Each lever saves minutes on one stage, measured from the data (prepare_meituan.py):
    1. Merchant fixes   (account management): part of the pickup overrun at the slowest 10% of merchants.
    2. Refusal fixes    (dispatch/product):   part of the delay caused by couriers refusing the order.
    3. Stacking cap     (dispatch policy):    at-risk orders that would be the 3rd+ in a run go to another
                                              courier; saves the measured extra last-mile time of a bigger run.
    4. Targeted quests  (courier incentives): extra couriers where load is highest; the dispatch wait and
                                              last mile drop along the curves measured against load.
- Compared with: a blanket bonus for every busy courier at the lunch and dinner peaks.

Inputs : data/slots.csv, data/late_buckets.csv (prepare_meituan.py), src/assumptions.py
Output : data/sizing.json (printed too), data/results/sensitivity.csv
Run from the repository root: python src/sizing.py
"""
import json

import numpy as np
import pandas as pd

from assumptions import ASSUMPTIONS, defaults, sensitivity_names

PEAK_HALFHOURS = set(range(22, 26)) | set(range(34, 40))      # 11:00-13:00 and 17:00-20:00
LOAD_BINS = np.round(np.arange(0.5, 4.01, 0.25), 2)           # curve points; loads outside are flat


# ---------- data ----------
def load_tables():
    s = pd.read_csv("data/slots.csv")
    s["key"] = np.arange(len(s))
    s["busy_couriers"] = s.courier_min / s.days / 30                       # average couriers on a run in the half-hour
    s["load"] = np.where(s.courier_min > 0, s.order_min / s.courier_min.where(s.courier_min > 0, 1), np.nan)
    s["peak"] = s.halfhour.isin(PEAK_HALFHOURS)
    b = pd.read_csv("data/late_buckets.csv").merge(s[["da_id", "dow", "halfhour", "key", "days"]],
                                                    on=["da_id", "dow", "halfhour"])
    b["per_week"] = b.orders / b.days
    return s, b


# ---------- curves against load ----------
def monotone(rate, weight):
    """Weighted pool-adjacent-violators: the closest non-decreasing curve to the observed values."""
    blocks = [[r, w, 1] for r, w in zip(rate, weight)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            (r1, w1, n1), (r2, w2, n2) = blocks[i], blocks[i + 1]
            blocks[i:i + 2] = [[(r1 * w1 + r2 * w2) / (w1 + w2), w1 + w2, n1 + n2]]
            i = max(i - 1, 0)
        else:
            i += 1
    return np.concatenate([[r] * n for r, _, n in blocks])


def load_curves(s):
    """Order-weighted late rate, dispatch wait and last mile per load bin (0.25 wide), made non-decreasing."""
    x = s.dropna(subset=["load"])
    x = x[x.courier_min >= 30]
    idx = np.clip(np.floor((x.load - LOAD_BINS[0]) / 0.25 + 0.5).astype(int), 0, len(LOAD_BINS) - 1)
    g = x.assign(i=idx).groupby("i")[["orders", "late", "sum_dispatch", "sum_lastmile"]].sum().reindex(range(len(LOAD_BINS)))
    g = g.fillna(0)
    w = g.orders.clip(lower=1)
    return dict(x=LOAD_BINS.tolist(), orders=g.orders.astype(int).tolist(),
                late=(g.late / w).round(4).tolist(),
                dispatch=monotone((g.sum_dispatch / w).values, g.orders.values).round(3).tolist(),
                lastmile=monotone((g.sum_lastmile / w).values, g.orders.values).round(3).tolist())


def knee(curve):
    """Load where the late-rate curve bends: best two-line fit (weighted), searched in 0.05 steps."""
    x, y, w = map(np.asarray, (curve["x"], curve["late"], curve["orders"]))
    keep = w > 0
    x, y, w = x[keep], y[keep], w[keep]
    best = None
    for k in np.arange(1.0, 3.01, 0.05):
        X = np.c_[np.ones_like(x), x, np.maximum(0, x - k)] * np.sqrt(w)[:, None]
        coef, *_ = np.linalg.lstsq(X, y * np.sqrt(w), rcond=None)
        sse = ((X @ coef - y * np.sqrt(w)) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, round(float(k), 2), coef)
    _, k, coef = best
    return dict(load=k, late_pts_per_1_load_below=round(100 * coef[1], 2), late_pts_per_1_load_above=round(100 * (coef[1] + coef[2]), 2))


# ---------- the model ----------
def supply_saving(s, curve, stress, add):
    """Minutes of dispatch wait + last mile saved in each slot when `add` couriers join."""
    c = s.busy_couriers.values
    load = np.nan_to_num(s.load.values)
    new_load = np.where(add > 0, load * c / np.maximum(c + add, 1e-9), load)
    f = lambda y, l: np.interp(l, curve["x"], y)
    return (f(curve["dispatch"], load) - f(curve["dispatch"], new_load)) + (f(curve["lastmile"], load) - f(curve["lastmile"], new_load))


def courier_gap(s, stress):
    load = np.nan_to_num(s.load.values)
    return np.where(load > stress, s.busy_couriers.values * (load / stress - 1), 0)


def simulate(s, b, curve, p, stress):
    """Late orders avoided per week, and weekly spend, for parameter set p."""
    gap = courier_gap(s, stress)
    load = np.nan_to_num(s.load.values)
    add_q = np.where(load > p["quest_trigger_load"], p["quest_share"] * gap, 0)
    save_q = supply_saving(s, curve, stress, add_q)[b.key.values]
    base = p["merchant_fix_share"] * b.merchant_save.values + p["refusal_fix_share"] * b.refusal_save.values + save_q
    need = b.late_min.values
    fixed_without = base >= need
    fixed_with = base + b.stack_save.values >= need
    share = np.where(b.stack_save.values > 0, p["stack_reroute_share"], 0)
    fixed = (1 - share) * fixed_without + share * fixed_with
    wk = b.per_week.values
    eligible_stack = (wk * (b.stack_save.values > 0)).sum()
    rerouted = p["stack_reroute_share"] * eligible_stack / p["stack_precision"]

    add_bl = np.where(s.peak.values, p["blanket_show_share"] * gap, 0)
    save_bl = supply_saving(s, curve, stress, add_bl)[b.key.values]
    bl_cost = (np.where(s.peak.values, s.busy_couriers.values + add_bl, 0) * 0.5 * p["blanket_bonus_eur"]).sum()
    return dict(avoided=(wk * fixed).sum(), quest_hours=(add_q * 0.5).sum(),
                quest_cost=(add_q * 0.5).sum() * p["quest_pay_eur"] * (1 + p["quest_leakage"]),
                rerouted=rerouted, reroute_cost=rerouted * p["reroute_cost_eur"],
                blanket_avoided=(wk * (save_bl >= need)).sum(), blanket_cost=bl_cost)


def plan(s, b, curve, p, stress):
    """Run the levers one after another and turn them into weekly business numbers."""
    off = dict(merchant_fix_share=0, refusal_fix_share=0, stack_reroute_share=0, quest_share=0)
    steps = [("merchant_fix_share",), ("merchant_fix_share", "refusal_fix_share"),
             ("merchant_fix_share", "refusal_fix_share", "stack_reroute_share"),
             ("merchant_fix_share", "refusal_fix_share", "stack_reroute_share", "quest_share")]
    runs = [simulate(s, b, curve, {**p, **{k: v for k, v in off.items() if k not in on}}, stress) for on in steps]
    r = runs[-1]
    v = p["lost_orders_per_late"] * p["basket_eur"] * p["take_rate"]
    orders = (s.orders / s.days).sum()
    late = (s.late / s.days).sum()
    avoided = [x["avoided"] for x in runs]
    quest_avoided = avoided[3] - avoided[2]
    stack_avoided = avoided[2] - avoided[1]
    spend = r["quest_cost"] + r["reroute_cost"]
    return {
        "value_per_late_avoided_eur": round(v, 2),
        "orders_per_week": round(orders),
        "late_per_week_before": round(late),
        "late_pct_before": round(100 * late / orders, 2),
        "late_pct_after": round(100 * (late - avoided[3]) / orders, 2),
        "avoided_per_week_merchants": round(avoided[0]),
        "avoided_per_week_refusals": round(avoided[1] - avoided[0]),
        "avoided_per_week_stacking": round(stack_avoided),
        "avoided_per_week_quests": round(quest_avoided),
        "avoided_per_week_total": round(avoided[3]),
        "rerouted_orders_per_week": round(r["rerouted"]),
        "reroute_spend_per_week_eur": round(r["reroute_cost"]),
        "reroute_cost_per_late_avoided_eur": round(r["reroute_cost"] / stack_avoided, 2) if stack_avoided > 0 else None,
        "quest_courier_hours_per_week": round(r["quest_hours"]),
        "quest_spend_per_week_eur": round(r["quest_cost"]),
        "quest_cost_per_late_avoided_eur": round(r["quest_cost"] / quest_avoided, 2) if quest_avoided > 0 else None,
        "plan_spend_per_week_eur": round(spend),
        "plan_net_per_week_eur": round(avoided[3] * v - spend),
        "free_levers_net_per_week_eur": round(avoided[1] * v),
        "blanket_avoided_per_week": round(r["blanket_avoided"]),
        "blanket_spend_per_week_eur": round(r["blanket_cost"]),
        "blanket_cost_per_late_avoided_eur": round(r["blanket_cost"] / r["blanket_avoided"], 2) if r["blanket_avoided"] > 0 else None,
        "blanket_net_per_week_eur": round(r["blanket_avoided"] * v - r["blanket_cost"]),
    }


def sensitivity(s, b, curve, stress):
    """Each assumption at 50% and 150%: what happens to the plan and to the targeted-vs-blanket comparison?"""
    rows = []
    for name in sensitivity_names():
        for factor in (0.5, 1.5):
            p = defaults()
            p[name] = p[name] * factor
            if name.endswith("share") or name == "stack_precision":
                p[name] = min(p[name], 1.0)
            r = plan(s, b, curve, p, stress)
            q, bl = r["quest_cost_per_late_avoided_eur"], r["blanket_cost_per_late_avoided_eur"]
            rows.append(dict(assumption=name, setting=f"{int(factor * 100)}%", value=round(p[name], 3),
                             late_pct_after=r["late_pct_after"], avoided_per_week=r["avoided_per_week_total"],
                             spend_per_week=r["plan_spend_per_week_eur"], plan_net_per_week=r["plan_net_per_week_eur"],
                             reroute_cost_per_late=r["reroute_cost_per_late_avoided_eur"], quest_cost_per_late=q,
                             blanket_cost_per_late=bl,
                             targeted_beats_blanket=bool(q is not None and bl is not None and q < bl)))
    return pd.DataFrame(rows)


def main():
    s, b = load_tables()
    curve = load_curves(s)
    k = knee(curve)
    stress = k["load"]
    result = {"knee": k, "stress_load": stress, "assumptions": ASSUMPTIONS, "curve": curve,
              "plan": plan(s, b, curve, defaults(), stress)}
    sens = sensitivity(s, b, curve, stress)
    sens.to_csv("data/results/sensitivity.csv", index=False)
    result["sensitivity_targeted_beats_blanket"] = f"{int(sens.targeted_beats_blanket.sum())} of {len(sens)}"
    json.dump(result, open("data/sizing.json", "w"), indent=1)
    print("Knee of the late-rate curve:", json.dumps(k))
    print(json.dumps(result["plan"], indent=1))
    print("\nSensitivity (each assumption at 50% / 150%):")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
