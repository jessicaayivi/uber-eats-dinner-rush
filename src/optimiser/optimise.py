"""Run the Brussels courier-positioning optimiser.

For each hour: the same number of couriers, three ways of placing them, and the expected late orders.
  Drift (today):  couriers end each trip where customers live, so they sit in proportion to residents.
  Restaurants:    spread in proportion to food places (a simple static rule).
  Optimised:      greedy marginal allocation (model.py), checked against an integer program (PuLP / CBC).
Couriers only follow a share of the nudges (compliance), so the realised result sits between drift and optimised.

Outputs: data/optimiser/results.json, data/optimiser/sensitivity.csv, data/optimiser/hourly_scenarios.csv
Run from the repository root: python src/optimiser/optimise.py
"""
import json
import os

import pandas as pd
import pulp

from assumptions import ASSUMPTIONS, HOURS, MIN_COURIERS_PER_ZONE as MIN, defaults, sensitivity_names
from demand import calibration, city_orders, couriers_online, rain_hours, shape_table, simulate, zone_shares
from model import couriers_saved, greedy, late, moves, proportional, total_late

OUT = "data/optimiser/"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HEADLINE = (4, 19)        # Friday 19:00


def scenario(p, shares, shape, calib, dow, hour, rain=False):
    orders = list(city_orders(shape, dow, hour, p, rain) * shares.pickup_share.values)
    total = couriers_online(shape, calib, dow, hour, p)
    drift = proportional(list(shares.residents), total, MIN)
    food = proportional(list(shares.food_places), total, MIN)
    best, path = greedy(orders, total, p, MIN)
    realised = [d + p["compliance"] * (b - d) for d, b in zip(drift, best)]
    late_drift, late_best = total_late(orders, drift, p), total_late(orders, best, p)
    return dict(dow=dow, hour=hour, rain=rain, orders=sum(orders), couriers=total,
                late_drift=late_drift, late_food=total_late(orders, food, p), late_optimised=late_best,
                late_realised=total_late(orders, realised, p),
                moved=sum(max(0, b - d) for d, b in zip(drift, best)),
                couriers_saved=couriers_saved(path, late_drift, total),
                allocation=dict(drift=drift, food=food, optimised=best), zone_orders=orders,
                moves=moves(drift, best, list(shares.zone)))


def four_weeks(p, shares, shape, calib):
    """Plan on expected demand (rain known from the forecast), score on simulated orders.
    The 4 weeks are re-simulated for each parameter set (same seed), so every assumption flows through."""
    sim = simulate(p, shares, shape, rain_hours(p))
    totals = dict(orders=0, late_drift=0.0, late_optimised=0.0, late_realised=0.0)
    for (date, dow, hour, rain), g in sim.groupby(["date", "dow", "hour", "rain"], sort=False):
        expected, actual = list(g.expected_orders.values), list(g.orders.values)
        total = couriers_online(shape, calib, dow, hour, p)
        drift = proportional(list(shares.residents), total, MIN)
        best, _ = greedy(expected, total, p, MIN)
        realised = [d + p["compliance"] * (b - d) for d, b in zip(drift, best)]
        totals["orders"] += sum(actual)
        totals["late_drift"] += total_late(actual, drift, p)
        totals["late_optimised"] += total_late(actual, best, p)
        totals["late_realised"] += total_late(actual, realised, p)
    weeks = 4
    return {k: round(v / weeks, 1) for k, v in totals.items()}


def cbc_solver():
    """PuLP's bundled CBC; on Windows-on-ARM (no native build) use the bundled x64 build, which runs emulated."""
    solver = pulp.PULP_CBC_CMD(msg=False)
    if solver.available():
        return solver
    x64 = os.path.join(os.path.dirname(pulp.__file__), "solverdir", "cbc", "win", "64", "cbc.exe")
    return pulp.COIN_CMD(path=x64, msg=False)


def check_with_pulp(sc, p):
    """Integer program: minimise sum of zone late orders, each a piecewise-linear convex function of its
    couriers (exact at whole numbers), subject to the same courier total and minimum."""
    orders, total = sc["zone_orders"], sc["couriers"]
    prob = pulp.LpProblem("positioning", pulp.LpMinimize)
    n = [pulp.LpVariable(f"n{i}", lowBound=MIN, upBound=total, cat="Integer") for i in range(len(orders))]
    t = [pulp.LpVariable(f"t{i}") for i in range(len(orders))]
    prob += pulp.lpSum(t)
    prob += pulp.lpSum(n) == total
    for i, o in enumerate(orders):
        for k in range(MIN, total):
            f0, f1 = late(o, k, p), late(o, k + 1, p)
            prob += t[i] >= f0 + (f1 - f0) * (n[i] - k)
    prob.solve(cbc_solver())
    return round(pulp.value(prob.objective), 4), [int(round(v.value())) for v in n]


def headline_numbers(p, shares, shape, calib):
    dow, hour = HEADLINE
    dry, wet = scenario(p, shares, shape, calib, dow, hour), scenario(p, shares, shape, calib, dow, hour, rain=True)
    pct = lambda s, key: round(100 * (1 - s[key] / s["late_drift"]), 1)
    return dry, wet, {
        "friday_19_orders": round(dry["orders"]), "friday_19_couriers": dry["couriers"],
        "friday_19_late_drift": round(dry["late_drift"], 1), "friday_19_late_optimised": round(dry["late_optimised"], 1),
        "friday_19_improvement_pct": pct(dry, "late_optimised"), "friday_19_realised_pct": pct(dry, "late_realised"),
        "friday_19_vs_restaurant_rule_pct": round(100 * (1 - dry["late_optimised"] / dry["late_food"]), 1),
        "friday_19_couriers_moved": dry["moved"], "friday_19_couriers_saved": dry["couriers_saved"],
        "friday_19_rain_late_drift": round(wet["late_drift"], 1), "friday_19_rain_late_optimised": round(wet["late_optimised"], 1),
        "friday_19_rain_improvement_pct": pct(wet, "late_optimised"),
    }


def sensitivity(shares_fn, shape, calib):
    rows = []
    for name in sensitivity_names():
        for factor in (0.7, 1.3):
            p = defaults()
            p[name] = min(p[name] * factor, 1.0) if name in ("compliance", "pickup_weight_food") else p[name] * factor
            shares = shares_fn(p)
            _, _, h = headline_numbers(p, shares, shape, calib)
            w = four_weeks(p, shares, shape, calib)
            rows.append(dict(assumption=name, setting=f"{int(factor * 100)}%", value=round(p[name], 4),
                             week_late_drift=w["late_drift"], week_late_realised=w["late_realised"],
                             week_reduction_realised_pct=round(100 * (1 - w["late_realised"] / w["late_drift"]), 1),
                             week_reduction_full_pct=round(100 * (1 - w["late_optimised"] / w["late_drift"]), 1),
                             friday_19_improvement_pct=h["friday_19_improvement_pct"],
                             friday_19_couriers_saved=h["friday_19_couriers_saved"]))
    return pd.DataFrame(rows)


def main():
    p, calib = defaults(), calibration()
    shares, shape = zone_shares(p), shape_table(calib)
    dry, wet, head = headline_numbers(p, shares, shape, calib)

    checks = []
    for dow, hour, rain in [(4, 19, False), (5, 12, True), (1, 15, False)]:
        sc = scenario(p, shares, shape, calib, dow, hour, rain)
        obj, alloc = check_with_pulp(sc, p)
        checks.append(dict(scenario=f"{DAY_NAMES[dow]} {hour}:00{' rain' if rain else ''}", greedy_late=round(sc["late_optimised"], 4),
                           pulp_late=obj, same_objective=bool(abs(obj - sc["late_optimised"]) < 1e-3),
                           same_allocation=bool(alloc == sc["allocation"]["optimised"])))

    hourly = []
    for dow in range(7):
        for hour in HOURS:
            for rain in (False, True):
                s = scenario(p, shares, shape, calib, dow, hour, rain)
                hourly.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()
                               if k not in ("allocation", "zone_orders", "moves")})
    hourly = pd.DataFrame(hourly)
    hourly.to_csv(OUT + "hourly_scenarios.csv", index=False)

    weeks = four_weeks(p, shares, shape, calib)
    sens = sensitivity(zone_shares, shape, calib)
    sens.to_csv(OUT + "sensitivity.csv", index=False)

    zones = list(shares.zone)
    gap = {z: b - d for z, d, b in zip(zones, dry["allocation"]["drift"], dry["allocation"]["optimised"])}
    result = {
        "assumptions": ASSUMPTIONS, "headline": head, "four_weeks_per_week": weeks,
        "four_weeks_reduction_full_pct": round(100 * (1 - weeks["late_optimised"] / weeks["late_drift"]), 1),
        "four_weeks_reduction_realised_pct": round(100 * (1 - weeks["late_realised"] / weeks["late_drift"]), 1),
        "friday_19_moves": [dict(source=a, to=b, couriers=k) for a, b, k in dry["moves"]],
        "friday_19_most_under_served": sorted(gap.items(), key=lambda x: -x[1])[:3],
        "friday_19_most_over_served": sorted(gap.items(), key=lambda x: x[1])[:3],
        "busiest_zones": shares.sort_values("pickup_share", ascending=False).zone.head(3).tolist(),
        "pulp_checks": checks,
        "sensitivity_reduction_range_pct": [float(sens.week_reduction_realised_pct.min()), float(sens.week_reduction_realised_pct.max())],
    }
    json.dump(result, open(OUT + "results.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in result.items() if k != "assumptions"}, indent=1, default=str))
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
