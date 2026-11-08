"""Simulate Brussels orders: real geography, residents, restaurants and weather; simulated order stream.

Expected orders in zone z at weekday d, hour h
    = weekly_orders x demand_shape(d, h) x pickup_share(z) x (1 + rain_uplift if that hour was rainy)
  pickup_share(z) = 70% the zone's share of food places + 30% its share of residents (assumption)
  demand_shape    = DoorDash weekday x hour profile (calibrate.py)
Couriers online at hour h = city orders (dry) x minutes_with_courier / 60 / Meituan staffing load at hour h.
Rain hours: real Open-Meteo hourly precipitation in Brussels (>= 0.2 mm).

Outputs: data/optimiser/zone_shares.csv, data/optimiser/rain_hours.csv,
         data/optimiser/simulated_orders.csv (4 weeks, 7 Sep - 4 Oct 2026, Poisson draws, seed 42)
Run from the repository root: python src/optimiser/demand.py
"""
import json

import numpy as np
import pandas as pd

from assumptions import HOURS, defaults

OUT = "data/optimiser/"
FIRST_DAY, DAYS_SIMULATED = "2026-09-07", 28
SEED = 42


def calibration():
    return json.load(open(OUT + "calibration.json"))


def zone_shares(p):
    z = pd.read_csv(OUT + "zones.csv")
    z["food_share"] = z.food_places / z.food_places.sum()
    z["resident_share"] = z.residents / z.residents.sum()
    z["pickup_share"] = p["pickup_weight_food"] * z.food_share + (1 - p["pickup_weight_food"]) * z.resident_share
    return z


def shape_table(calib):
    s = pd.DataFrame(calib["demand_shape"], columns=["dow", "hour", "share"])
    s[["dow", "hour"]] = s[["dow", "hour"]].astype(int)
    return s.set_index(["dow", "hour"]).share


def city_orders(shape, dow, hour, p, rain=False):
    return p["weekly_orders"] * shape.get((dow, hour), 0.0) * (1 + p["rain_uplift"] * rain)


def couriers_online(shape, calib, dow, hour, p):
    """Couriers staffed for a dry hour, at Meituan's load for that hour of day."""
    load = calib["staffing_load_by_hour"][str(hour)]
    return max(int(round(p["staffing_scale"] * city_orders(shape, dow, hour, p) * p["minutes_with_courier"] / 60 / load)), 1)


def rain_hours(p):
    w = json.load(open("data/raw/brussels/weather_brussels_2026_09_10.json"))["hourly"]
    r = pd.DataFrame(w)
    r["time"] = pd.to_datetime(r.time)
    r["rain"] = (r.precipitation >= p["rain_threshold_mm"]).astype(int)
    return r[["time", "precipitation", "rain"]]


def simulate(p, shares, shape, rain):
    rng = np.random.default_rng(SEED)
    rain = rain.set_index("time").rain
    rows = []
    for day in pd.date_range(FIRST_DAY, periods=DAYS_SIMULATED, freq="D"):
        for h in HOURS:
            wet = int(rain.get(day + pd.Timedelta(hours=h), 0))
            expected = city_orders(shape, day.dayofweek, h, p, wet) * shares.pickup_share.values
            for zone, lam, n in zip(shares.zone, expected, rng.poisson(expected)):
                rows.append((day.date().isoformat(), day.dayofweek, h, wet, zone, round(lam, 3), int(n)))
    return pd.DataFrame(rows, columns=["date", "dow", "hour", "rain", "zone", "expected_orders", "orders"])


def main():
    p, calib = defaults(), calibration()
    shares, shape = zone_shares(p), shape_table(calib)
    rain = rain_hours(p)
    sim = simulate(p, shares, shape, rain)
    shares.round(5).to_csv(OUT + "zone_shares.csv", index=False)
    rain.to_csv(OUT + "rain_hours.csv", index=False)
    sim.to_csv(OUT + "simulated_orders.csv", index=False)
    in_window = rain[(rain.time >= FIRST_DAY) & (rain.time < pd.Timestamp(FIRST_DAY) + pd.Timedelta(days=DAYS_SIMULATED))
                     & rain.time.dt.hour.isin(HOURS)]
    print(f"simulated {sim.orders.sum():,} orders over {DAYS_SIMULATED} days ({sim.orders.sum() / 4:,.0f} a week); "
          f"{int(in_window.rain.sum())} of {len(in_window)} service hours were rainy")
    print(shares[["zone", "food_share", "resident_share", "pickup_share"]].sort_values("pickup_share", ascending=False).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
