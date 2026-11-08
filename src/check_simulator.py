"""Check that the simulator, at its default settings, reproduces src/sizing.py.

Runs the model section of simulator/index.html (between "MODEL START" and "MODEL END") in a
JavaScript engine and compares it with data/sizing.json. Exits with an error if any number differs.
Needs: pip install mini-racer.  Run from the repository root: python src/check_simulator.py
"""
import json
import re
import sys

from py_mini_racer import MiniRacer

# metric -> allowed difference (sizing.json rounds counts and euros to whole numbers, rates to 0.01)
CHECKS = {
    "late_pct_before": 0.006, "late_pct_after": 0.006,
    "avoided_per_week_merchants": 1, "avoided_per_week_refusals": 1, "avoided_per_week_stacking": 1,
    "avoided_per_week_quests": 1, "avoided_per_week_total": 1,
    "rerouted_orders_per_week": 1, "reroute_spend_per_week_eur": 1, "reroute_cost_per_late_avoided_eur": 0.006,
    "quest_courier_hours_per_week": 1, "quest_spend_per_week_eur": 1, "quest_cost_per_late_avoided_eur": 0.006,
    "plan_spend_per_week_eur": 1, "plan_net_per_week_eur": 1, "free_levers_net_per_week_eur": 1,
    "blanket_avoided_per_week": 1, "blanket_spend_per_week_eur": 1, "blanket_cost_per_late_avoided_eur": 0.006,
    "blanket_net_per_week_eur": 1, "value_per_late_avoided_eur": 0.006,
}


def simulator_results():
    html = open("simulator/index.html", encoding="utf-8").read()
    data = re.search(r"const DATA = (.*?);\n", html).group(1)
    model = re.search(r"// MODEL START[^\n]*\n(.*)// MODEL END", html, re.S).group(1)
    ctx = MiniRacer()
    ctx.eval(f"const DATA = {data};\n{model}")
    return json.loads(ctx.eval("JSON.stringify((({cells, ...r}) => r)(plan(DATA, DATA.defaults, -1)))"))


def main():
    expected = json.load(open("data/sizing.json"))["plan"]
    actual = simulator_results()
    failures = 0
    for key, tolerance in CHECKS.items():
        ok = abs(actual[key] - expected[key]) <= tolerance
        failures += not ok
        print(f"{'OK ' if ok else 'BAD'} {key:<36} sizing.py {expected[key]:>12,.2f}   simulator {actual[key]:>12,.2f}")
    if failures:
        sys.exit(f"{failures} metric(s) differ between the simulator and sizing.py")
    print("Simulator defaults reproduce sizing.py.")


if __name__ == "__main__":
    main()
