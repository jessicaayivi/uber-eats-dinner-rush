"""Size the three levers on the real DoorDash data and compare them with a blanket peak bonus.

How the model works, in plain words:
1. The response curve: the share of late deliveries at each load ratio (outstanding orders per
   on-shift dasher), read straight from the data in 0.1 steps and forced to never decrease.
2. Every lever changes the number of dashers (or how much each one can carry) in a market-hour.
   That lowers the load each order faces, and the curve says how many late deliveries that removes.
3. Dashers per market-hour come from Little's law: orders x hours per delivery / load ratio.

Levers (applied in order, only to stressed market-hours, where load > the knee of the curve):
  1. Rebalance shifts: move idle dasher time out of quiet hours (load < 0.8) in the same market.
  2. Batching: pair a share of orders; each pair frees courier time but delivers 11% later.
  3. Targeted quests: paid extra hours, only where load after steps 1-2 is still above a trigger.
Compared with: a blanket bonus for every online dasher on Fri-Sun dinners.

Inputs : data/market_hour.csv, data/market_hour_load.csv (prepare_doordash.py), src/assumptions.py
Output : data/sizing.json (printed too), data/results/sensitivity.csv
Run from the repository root: python src/sizing.py
"""
import json

import numpy as np
import pandas as pd

from assumptions import ASSUMPTIONS, defaults, sensitivity_names

WEEKS = 4
MIN_LOAD_FOR_DASHERS = 0.3   # Little's law estimate is unstable at near-zero load (36 tiny market-hours)


# ---------- data ----------
def load_tables():
    mh = pd.read_csv("data/market_hour.csv")
    mh["dashers"] = mh.orders * mh.avg_minutes / 60 / np.maximum(mh.load_ratio, MIN_LOAD_FOR_DASHERS)
    mh["weekend_dinner"] = mh.dow.isin(["Friday", "Saturday", "Sunday"]) & mh.hour.between(17, 20)
    mh["mh"] = np.arange(len(mh))
    bins = pd.read_csv("data/market_hour_load.csv").merge(mh[["market_id", "date", "hour", "mh"]],
                                                         on=["market_id", "date", "hour"])
    return mh, bins


# ---------- response curve ----------
def monotone(rate, weight):
    """Weighted pool-adjacent-violators: the closest non-decreasing curve to the observed rates."""
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


def response_curve(bins):
    g = bins.groupby("load_bin")[["orders", "late", "late_if_batched"]].sum()
    return dict(x=(g.index.values + 0.05).round(2).tolist(),
                late=monotone(g.late / g.orders, g.orders).round(4).tolist(),
                late_batched=monotone(g.late_if_batched / g.orders, g.orders).round(4).tolist(),
                orders=g.orders.astype(int).tolist(),
                observed=(g.late / g.orders).round(4).tolist())


def knee(curve):
    """Load where the curve bends: best two-line fit (weighted), searched in 0.05 steps."""
    x, y, w = map(np.asarray, (curve["x"], curve["observed"], curve["orders"]))
    best = None
    for k in np.arange(0.6, 2.01, 0.05):
        X = np.c_[np.ones_like(x), x, np.maximum(0, x - k)] * np.sqrt(w)[:, None]
        coef, *_ = np.linalg.lstsq(X, y * np.sqrt(w), rcond=None)
        sse = (((X @ coef) - y * np.sqrt(w)) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, round(float(k), 2), coef)
    _, k, coef = best
    return dict(load=k, slope_below_per_0_1=round(coef[1] * 10, 3), slope_above_per_0_1=round((coef[1] + coef[2]) * 10, 3))


# ---------- the model ----------
def simulate(mh, bins, curve, p, stress_load):
    """Late deliveries avoided and incentive spend for parameter set p (see assumptions.py)."""
    c = lambda x: np.interp(x, curve["x"], curve["late"])
    cb = lambda x: np.interp(x, curve["x"], curve["late_batched"])
    D, load = mh.dashers.values, mh.load_ratio.values
    stressed = load > stress_load
    quiet = load < p["quiet_load"]
    gap = np.where(stressed, D * (load / stress_load - 1), 0)
    slack = np.where(quiet, D * (1 - load / p["quiet_load"]), 0)

    # Step 1: each market's movable slack is spread over its stressed hours in proportion to their gap
    m = mh.market_id.values
    add1, give = np.zeros(len(mh)), np.zeros(len(mh))
    for market in np.unique(m):
        sel = m == market
        need, pool = gap[sel].sum(), slack[sel].sum()
        used = min(p["rebalance_share"] * pool, need)
        if need > 0:
            add1[sel] = gap[sel] * used / need
        if pool > 0:
            give[sel] = slack[sel] * used / pool

    # Step 2: batching stretches each dasher in stressed hours
    stretch = np.where(stressed, 1 / (1 - p["batch_share"] * p["batch_courier_saving"]), 1)
    load12 = np.where(stressed, load * D / ((D + add1) * stretch), load)

    # Step 3: quests where load is still above the trigger
    add3 = np.where(stressed & (load12 > p["quest_trigger_load"]), p["quest_share"] * gap, 0)
    quest_cost = (add3 * p["quest_pay_usd"] * (1 + p["quest_leakage"])).sum()

    scale = np.where(stressed, D / ((D + add1 + add3) * stretch), D / np.maximum(D - give, 1e-9))
    b = bins.mh.values
    x, n = bins.load_bin.values + 0.05, bins.orders.values
    before = n * c(x)
    s_share = np.where(stressed[b], p["batch_share"], 0)
    after = n * ((1 - s_share) * c(x * scale[b]) + s_share * cb(x * scale[b]))

    # Blanket bonus on Fri-Sun dinners, for comparison
    wd = mh.weekend_dinner.values
    add_bl = np.where(wd, p["blanket_show_share"] * gap, 0)
    blanket_cost = (np.where(wd, D + add_bl, 0) * p["blanket_bonus_usd"]).sum()
    after_bl = n * c(x * (D / (D + add_bl))[b])

    # "Before" is the observed late count; the curve only says how much each lever changes it
    in_stress = stressed[b]
    observed, avoided = bins.late.values, before - after
    return dict(late_before=observed.sum(), late_after=observed.sum() - avoided.sum(), avoided=avoided.sum(),
                late_stressed_before=observed[in_stress].sum(),
                late_stressed_after=observed[in_stress].sum() - avoided[in_stress].sum(),
                quest_cost=quest_cost, quest_hours=add3.sum(), rebalanced_hours=add1.sum(),
                gap_hours=gap.sum(), slack_hours=slack.sum(),
                blanket_avoided=(before - after_bl).sum(), blanket_cost=blanket_cost)


def plan(mh, bins, curve, p, stress_load):
    """Run the plan step by step and turn it into weekly business numbers."""
    v = p["lost_orders_per_late"] * p["basket_usd"] * p["take_rate"]   # net revenue per late delivery
    s1 = simulate(mh, bins, curve, {**p, "batch_share": 0, "quest_share": 0}, stress_load)
    s2 = simulate(mh, bins, curve, {**p, "quest_share": 0}, stress_load)
    s3 = simulate(mh, bins, curve, p, stress_load)
    w = lambda x: x / WEEKS
    orders = bins.orders.sum()
    quest_avoided = s3["avoided"] - s2["avoided"]
    return {
        "value_per_late_avoided_usd": round(v, 2),
        "orders_per_week": round(w(orders)),
        "late_per_week_before": round(w(s3["late_before"])),
        "late_pct_before": round(100 * s3["late_before"] / orders, 1),
        "late_pct_after": round(100 * s3["late_after"] / orders, 1),
        "late_in_stressed_hours_per_week": [round(w(s3["late_stressed_before"])), round(w(s3["late_stressed_after"]))],
        "avoided_per_week_step1": round(w(s1["avoided"])),
        "avoided_per_week_step2": round(w(s2["avoided"] - s1["avoided"])),
        "avoided_per_week_step3": round(w(quest_avoided)),
        "avoided_per_week_total": round(w(s3["avoided"])),
        "gap_dasher_hours_per_week": round(w(s3["gap_hours"])),
        "slack_dasher_hours_per_week": round(w(s3["slack_hours"])),
        "rebalanced_dasher_hours_per_week": round(w(s3["rebalanced_hours"])),
        "quest_dasher_hours_per_week": round(w(s3["quest_hours"])),
        "quest_spend_per_week_usd": round(w(s3["quest_cost"])),
        "quest_cost_per_late_avoided_usd": round(s3["quest_cost"] / quest_avoided, 2) if quest_avoided > 0 else None,
        "plan_net_per_week_usd": round(w(s3["avoided"] * v - s3["quest_cost"])),
        "blanket_avoided_per_week": round(w(s3["blanket_avoided"])),
        "blanket_spend_per_week_usd": round(w(s3["blanket_cost"])),
        "blanket_cost_per_late_avoided_usd": round(s3["blanket_cost"] / s3["blanket_avoided"], 2),
        "blanket_net_per_week_usd": round(w(s3["blanket_avoided"] * v - s3["blanket_cost"])),
    }


def sensitivity(mh, bins, curve, stress_load):
    """Each assumption at 50% and 150%: does the recommendation still hold?"""
    rows = []
    for name in sensitivity_names():
        for factor in (0.5, 1.5):
            p = defaults()
            p[name] = p[name] * factor
            if name.endswith("share") or name == "batch_courier_saving":
                p[name] = min(p[name], 0.95)
            r = plan(mh, bins, curve, p, stress_load)
            quest = r["quest_cost_per_late_avoided_usd"]
            rows.append(dict(assumption=name, setting=f"{int(factor * 100)}%", value=round(p[name], 3),
                             late_pct_after=r["late_pct_after"], avoided_per_week=r["avoided_per_week_total"],
                             quest_spend_per_week=r["quest_spend_per_week_usd"], plan_net_per_week=r["plan_net_per_week_usd"],
                             quest_cost_per_late=quest, blanket_cost_per_late=r["blanket_cost_per_late_avoided_usd"],
                             targeted_beats_blanket=bool(quest is not None and quest < r["blanket_cost_per_late_avoided_usd"]
                                                         and r["plan_net_per_week_usd"] > r["blanket_net_per_week_usd"])))
    return pd.DataFrame(rows)


def main():
    mh, bins = load_tables()
    curve = response_curve(bins)
    k = knee(curve)
    stress = k["load"]
    result = {"knee": k, "stress_load": stress, "assumptions": ASSUMPTIONS, "curve": curve,
              "plan": plan(mh, bins, curve, defaults(), stress)}
    sens = sensitivity(mh, bins, curve, stress)
    sens.to_csv("data/results/sensitivity.csv", index=False)
    result["sensitivity_holds"] = f"{int(sens.targeted_beats_blanket.sum())} of {len(sens)}"
    json.dump(result, open("data/sizing.json", "w"), indent=1)
    print("Knee of the response curve:", json.dumps(k))
    print(json.dumps(result["plan"], indent=1))
    print("\nSensitivity (each assumption at 50% / 150%):")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
