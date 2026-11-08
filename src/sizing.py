"""Size the opportunity and compare a fixed weekend boost vs. a forecast-triggered boost.
Assumptions (stated in the deck): 2.1 deliveries per courier-hour; 85% target utilisation;
60% of the targeted extra courier-hours actually show up; boost = EUR 4 per online courier-hour,
paid to every courier online in boosted hours; platform net revenue = 20% of gross bookings;
basket EUR 27. Defect response curve = the one estimated from the 4 weeks of data."""
import numpy as np, pandas as pd, json
d = pd.read_csv("marketplace_hourly.csv")
CAP, TGT, SHOW, BOOST, TAKE, AOV, WEEKS = 2.1, .85, .6, 4.0, .20, 27.0, 4
def unf_rate(u): return np.minimum(.35, .015 + .55 * np.maximum(0, u - .85) ** 1.3)

d["util"] = d.orders_requested / (d.couriers_online * CAP)
d["gap"] = np.maximum(0, np.ceil(d.orders_requested / (CAP * TGT)) - d.couriers_online)
d["weekend_dinner"] = d.dow.isin(["Friday", "Saturday", "Sunday"]) & d.hour.between(17, 21)

def scenario(mask):
    x = d[mask].copy()
    x["add"] = SHOW * x.gap
    new_u = x.orders_requested / ((x.couriers_online + x["add"]) * CAP)
    recovered = (x.orders_unfulfilled - x.orders_requested * unf_rate(new_u)).clip(lower=0)
    cost = BOOST * (x.couriers_online + x["add"]).sum()
    rec = recovered.sum()
    return dict(boosted_hours_per_week=len(x) / WEEKS,
                recovered_orders_per_week=rec / WEEKS,
                boost_cost_per_week=cost / WEEKS,
                recovered_gb_per_week=rec * AOV / WEEKS,
                recovered_net_rev_per_week=rec * AOV * TAKE / WEEKS,
                cost_per_recovered_order=cost / rec,
                net_roi=(rec * AOV * TAKE - cost) / cost)

res = {
    "baseline": dict(lost_orders_per_week=d.orders_unfulfilled.sum() / WEEKS,
                     lost_gb_per_week=d.orders_unfulfilled.sum() * AOV / WEEKS,
                     lost_gb_per_year=d.orders_unfulfilled.sum() * AOV / WEEKS * 52,
                     orders_per_week=d.orders_requested.sum() / WEEKS,
                     unfulfilled_pct=100 * d.orders_unfulfilled.sum() / d.orders_requested.sum(),
                     total_gap_courier_hours_per_week=d.gap.sum() / WEEKS),
    "A_fixed_weekend_dinner": scenario(d.weekend_dinner),
    "B_forecast_triggered": scenario(d.gap > 0),
}
# share of stressed hours that a fixed weekend schedule misses
stressed = d[d.gap > 0]
res["stressed_hours_outside_weekend_dinner_pct"] = 100 * (~stressed.weekend_dinner).mean()
res["lost_in_stressed_outside_weekend_dinner_pct"] = 100 * stressed.loc[~stressed.weekend_dinner, "orders_unfulfilled"].sum() / d.orders_unfulfilled.sum()
print(json.dumps(res, indent=1, default=float))
json.dump(res, open("sizing.json", "w"), indent=1, default=float)

# ---- Recommended plan: rebalance first, then product levers, then targeted incentives ----
SHIFT, QUEST, QUEST_EUR, LEAK, BATCH_CAP, QUEST_TRIGGER = .25, .35, 5.0, .30, 2.3, 1.10
def unf_late(u):
    o = np.maximum(0, u - .85)
    return unf_rate(u), np.minimum(.6, .06 + .9 * o ** 1.1)
x = d[d.gap > 0].copy()
steps = {}
for name, shift, cap, quest in [("1_rebalance_shifts", SHIFT, CAP, 0),
                                ("2_plus_batching", SHIFT, BATCH_CAP, 0),
                                ("3_plus_targeted_quests", SHIFT, BATCH_CAP, QUEST)]:
    c12 = x.couriers_online + shift * x.gap
    # quests fire only where utilisation after steps 1-2 stays above the trigger
    fire = (x.orders_requested / (c12 * cap)) > QUEST_TRIGGER
    add = quest * x.gap * fire
    c = c12 + add
    u = x.orders_requested / (c * cap)
    ur, lr = unf_late(u)
    rec = (x.orders_unfulfilled - x.orders_requested * ur).clip(lower=0).sum()
    late_after = ((x.orders_requested * (1 - ur)) * lr).sum()
    cost = QUEST_EUR * (1 + LEAK) * add.sum()
    steps[name] = dict(recovered_orders_per_week=rec / WEEKS,
                       recovered_gb_per_week=rec * AOV / WEEKS,
                       recovered_gb_per_year=rec * AOV / WEEKS * 52,
                       recovered_net_rev_per_week=rec * AOV * TAKE / WEEKS,
                       incentive_cost_per_week=cost / WEEKS,
                       late_orders_before_per_week=x.orders_late.sum() / WEEKS,
                       late_orders_after_per_week=late_after / WEEKS)
res["plan"] = steps
# off-peak slack that can be moved: courier-hours above what 85% utilisation needs, in hours under 60% utilisation
slack = d[d.util < .6]
res["offpeak_slack_courier_hours_per_week"] = (slack.couriers_online - np.ceil(slack.orders_requested / (CAP * TGT))).clip(lower=0).sum() / WEEKS
res["shift_hours_needed_per_week"] = SHIFT * d.gap.sum() / WEEKS
res["new_unfulfilled_pct_after_plan"] = 100 * (d.orders_unfulfilled.sum() / WEEKS - steps["3_plus_targeted_quests"]["recovered_orders_per_week"]) / (d.orders_requested.sum() / WEEKS)
print(json.dumps({k: res[k] for k in ["plan", "offpeak_slack_courier_hours_per_week", "shift_hours_needed_per_week", "new_unfulfilled_pct_after_plan"]}, indent=1, default=float))
json.dump(res, open("sizing.json", "w"), indent=1, default=float)
