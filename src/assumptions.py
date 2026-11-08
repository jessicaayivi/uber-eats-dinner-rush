"""Every number the lever model uses that is not computed from the data in this run.

Each entry says where it comes from:
  "data"       measured in this repository (the script is named), kept here so it is visible
  "public"     a published figure (source given)
  "assumption" my judgement; sizing.py tests each one at 50% and 150% of its value

The Meituan data has no prices, fees or courier pay, so every euro figure is an assumption,
set to plausible Western-European levels and tested in the sensitivity table.
"""

ASSUMPTIONS = {
    # --- Measured from the data (prepare_meituan.py, sql/analysis.sql) ---
    "late_definition":       dict(value="arrive > promise", source="data", note="Late = delivered after the time the platform promised the customer"),
    "slow_merchant_share":   dict(value=0.10, source="data", note="Account-management target: the 10% of merchants (50+ orders) with the largest pickup overrun"),
    "stack_cap":             dict(value=2, source="data", note="Like-for-like, a 3rd order in a run adds ~5 late points over a 2nd (sql Q6)"),
    # --- Public ---
    "take_rate":             dict(value=0.19, source="public", note="Uber Q3 2026: Delivery revenue $5.5B / gross bookings $28.5B"),
    # --- Assumptions (sensitivity-tested) ---
    "merchant_fix_share":    dict(value=0.50, source="assumption", note="Share of the slowest merchants' pickup overrun removed by account management (prep-time fixes, earlier courier timing)"),
    "refusal_fix_share":     dict(value=0.30, source="assumption", note="Share of the delay from courier refusals removed by better matching / acceptance nudges"),
    "stack_reroute_share":   dict(value=0.50, source="assumption", note="Share of at-risk over-cap orders the dispatcher hands to another (idle) courier"),
    "stack_precision":       dict(value=0.25, source="assumption", note="Share of re-routed orders that would really have been late (the rest are re-routed unnecessarily)"),
    "reroute_cost_eur":      dict(value=2.5, source="assumption", note="Extra courier pay for a separate trip instead of a stacked drop"),
    "quest_share":           dict(value=0.35, source="assumption", note="Share of the courier gap that targeted quests bring online"),
    "quest_trigger_load":    dict(value=2.5, source="assumption", note="Quests fire only in district-half-hours whose load is above this"),
    "quest_pay_eur":         dict(value=5.0, source="assumption", note="Quest pay per extra courier-hour"),
    "quest_leakage":         dict(value=0.30, source="assumption", note="Extra quest spend paid to couriers who would have worked anyway"),
    "blanket_bonus_eur":     dict(value=4.0, source="assumption", note="Blanket bonus per busy courier-hour at lunch (11-13) and dinner (17-20) peaks"),
    "blanket_show_share":    dict(value=0.60, source="assumption", note="Share of the courier gap that the blanket bonus brings online"),
    "basket_eur":            dict(value=27.0, source="assumption", note="Average basket (the Meituan data has no prices)"),
    "lost_orders_per_late":  dict(value=0.5, source="assumption", note="Future orders lost per late delivery (retention effect)"),
}


def value(name):
    return ASSUMPTIONS[name]["value"]


def defaults():
    """All numeric values as a plain dict (what the simulator starts from)."""
    return {name: a["value"] for name, a in ASSUMPTIONS.items() if not isinstance(a["value"], str)}


def sensitivity_names():
    return [name for name, a in ASSUMPTIONS.items() if a["source"] == "assumption"]
