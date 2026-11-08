"""Synthetic Uber Eats-style Belgian marketplace data (illustrative only).
4 weeks, 4 cities, hourly 10:00-23:00. Writes marketplace.db (SQLite) + CSV."""
import numpy as np, pandas as pd, sqlite3

rng = np.random.default_rng(42)
cities = {  # dinner-peak base demand (orders/hour), courier pool scale
    "Brussels": dict(base=520, supply=1.00),
    "Antwerp":  dict(base=330, supply=0.97),
    "Ghent":    dict(base=210, supply=0.93),
    "Liege":    dict(base=140, supply=0.86),
}
hours = range(10, 24)
# demand shape by hour (share of dinner peak)
shape = {10:.10,11:.25,12:.62,13:.55,14:.25,15:.15,16:.15,17:.35,18:.80,19:1.0,20:.92,21:.60,22:.35,23:.18}
# courier supply shape: shifts lag the dinner ramp, drop off early
sshape = {10:.15,11:.30,12:.62,13:.58,14:.30,15:.20,16:.20,17:.38,18:.68,19:.82,20:.82,21:.62,22:.40,23:.22}
dow_demand = {0:.85,1:.82,2:.88,3:.95,4:1.18,5:1.25,6:1.22}   # Mon..Sun
dow_supply = {0:.95,1:.95,2:.97,3:1.00,4:1.02,5:.98,6:1.05}   # weekends barely move
days = pd.date_range("2026-09-07", periods=28, freq="D")
rain_days = set(rng.choice(28, size=8, replace=False))
CAP = 2.1      # deliveries a courier can do per online hour
AOV = 27.0     # average basket, EUR

rows = []
for city, p in cities.items():
    for d_i, day in enumerate(days):
        dow, rain = day.dayofweek, d_i in rain_days
        for h in hours:
            demand = p["base"] * shape[h] * dow_demand[dow] * (1.22 if rain and h >= 17 else 1.0)
            demand = rng.poisson(demand * rng.normal(1, .05))
            supply_need = p["base"] * sshape[h] / CAP * 1.42
            couriers = supply_need * p["supply"] * dow_supply[dow] * (0.88 if rain else 1.0) * rng.normal(1, .04)
            couriers = max(1, int(round(couriers)))
            util = demand / (couriers * CAP)
            # ETA and defects rise non-linearly once utilisation passes ~85%
            over = max(0, util - 0.85)
            eta = 27 + 4 * util + 55 * over**1.4 + rng.normal(0, 1.2)
            unfulfilled_rate = min(.35, .015 + .55 * over**1.3)
            late_rate = min(.6, .06 + .9 * over**1.1)
            unfulfilled = rng.binomial(demand, unfulfilled_rate)
            completed = demand - unfulfilled
            late = rng.binomial(completed, late_rate)
            rows.append(dict(city=city, date=day.date().isoformat(), dow=day.day_name(),
                             hour=h, is_rain=int(rain), orders_requested=demand,
                             orders_completed=completed, orders_unfulfilled=unfulfilled,
                             orders_late=late, couriers_online=couriers,
                             avg_eta_min=round(eta, 1), avg_basket_eur=AOV))
df = pd.DataFrame(rows)
df.to_csv("marketplace_hourly.csv", index=False)
con = sqlite3.connect("marketplace.db"); df.to_sql("marketplace_hourly", con, if_exists="replace", index=False); con.close()
print(df.shape, df.orders_requested.sum(), df.orders_unfulfilled.sum())
