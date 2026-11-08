"""Every input of the Brussels optimiser, with where it comes from.

  "data"       measured from real data in this repository (the script is named)
  "assumption" my judgement; optimise.py tests each one at 70% and 130% (+/-30%)

Only the order stream is simulated. Geography, residents, restaurants, weather and the behaviour of
deliveries under pressure are real. Nothing here is Uber data.
"""

ASSUMPTIONS = {
    # --- Real data ---
    "minutes_with_courier": dict(value=25.09, source="data", note="Minutes an order spends with a courier, accept to delivery (calibrate.py, Meituan)"),
    "curve_a":              dict(value=0.10554, source="data", note="Late rate at load 1 (calibrate.py, Meituan)"),
    "curve_b":              dict(value=0.06518, source="data", note="Extra late rate per unit of ln(load): +4.5 points per doubling (calibrate.py, Meituan)"),
    "curve_floor":          dict(value=0.10744, source="data", note="Lowest late rate observed at low load (calibrate.py, Meituan)"),
    "rain_threshold_mm":    dict(value=0.2, source="data", note="An hour counts as rainy from 0.2 mm (Open-Meteo, Brussels, Sep-Oct 2026)"),
    # --- Assumptions (sensitivity-tested) ---
    "weekly_orders":        dict(value=30000, source="assumption", note="Orders a week on one platform in the Brussels-Capital Region"),
    "pickup_weight_food":   dict(value=0.7, source="assumption", note="Pickup share of a zone = 70% its share of food places + 30% its share of residents"),
    "rain_uplift":          dict(value=0.15, source="assumption", note="Extra orders in a rainy hour (couriers do not increase)"),
    "compliance":           dict(value=0.6, source="assumption", note="Share of recommended moves that couriers actually follow (positioning is a nudge)"),
    "staffing_scale":       dict(value=1.0, source="assumption", note="Couriers online relative to Meituan's staffing by hour (load 1.1-2.5)"),
}
MIN_COURIERS_PER_ZONE = 1
HOURS = list(range(10, 23))          # service hours 10:00-22:59 (the demand shape has almost no orders at 23:00)


def value(name):
    return ASSUMPTIONS[name]["value"]


def defaults():
    return {k: v["value"] for k, v in ASSUMPTIONS.items()}


def sensitivity_names():
    return [k for k, v in ASSUMPTIONS.items() if v["source"] == "assumption"] + ["curve_b", "minutes_with_courier"]
