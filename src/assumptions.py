"""Every number the lever model uses that is not computed from the data in this run.

Each entry says where it comes from:
  "data"       measured in this repository (the script is named), kept here so it is visible
  "public"     a published figure (source given)
  "assumption" my judgement; sizing.py tests each one at 50% and 150% of its value

Money is in US dollars because the delivery data is American (DoorDash, 2015).
"""

ASSUMPTIONS = {
    # --- Measured from the data ---
    "late_minutes":        dict(value=60, source="data", note="Late = over 60 min: the 'within the hour' promise, 80th percentile (prepare_doordash.py)"),
    "quiet_load":          dict(value=0.8, source="data", note="Below 0.8 outstanding orders per dasher the late rate sits at its ~8% floor (sql Q3)"),
    "basket_usd":          dict(value=27.02, source="data", note="Average order subtotal (prepare_doordash.py)"),
    "batch_delay_pct":     dict(value=11.1, source="data", note="A second order in the trip adds 11% delivery time, like-for-like (prepare_india.py, Indian data)"),
    # --- Public ---
    "take_rate":           dict(value=0.19, source="public", note="Uber Q3 2026: Delivery revenue $5.5B / gross bookings $28.5B"),
    # --- Assumptions (sensitivity-tested) ---
    "rebalance_share":     dict(value=0.50, source="assumption", note="Share of idle quiet-hour dasher time that can be moved into stressed hours by shift planning"),
    "batch_share":         dict(value=0.20, source="assumption", note="Share of orders in stressed hours that can be paired with another order"),
    "batch_courier_saving": dict(value=0.30, source="assumption", note="Courier time saved per paired order (Indian trip times imply up to 44%)"),
    "quest_share":         dict(value=0.35, source="assumption", note="Share of the original gap that targeted quests bring online"),
    "quest_trigger_load":  dict(value=1.5, source="assumption", note="Quests fire only where load after steps 1-2 is still above this"),
    "quest_pay_usd":       dict(value=5.0, source="assumption", note="Quest pay per extra dasher-hour"),
    "quest_leakage":       dict(value=0.30, source="assumption", note="Extra quest spend paid to dashers who would have worked anyway"),
    "blanket_bonus_usd":   dict(value=4.0, source="assumption", note="Blanket bonus per online dasher-hour, Fri-Sun 17:00-21:00"),
    "blanket_show_share":  dict(value=0.60, source="assumption", note="Share of the gap that the blanket bonus brings online"),
    "lost_orders_per_late": dict(value=0.5, source="assumption", note="Future orders lost per late delivery (retention effect)"),
}


def value(name):
    return ASSUMPTIONS[name]["value"]


def defaults():
    """All values as a plain dict (what the simulator starts from)."""
    return {name: a["value"] for name, a in ASSUMPTIONS.items()}


def sensitivity_names():
    return [name for name, a in ASSUMPTIONS.items() if a["source"] == "assumption"]
