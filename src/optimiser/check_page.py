"""Check that the map's JavaScript optimiser gives exactly the same result as optimise.py on three scenarios.

Runs the model section of optimiser/index.html (between "MODEL START" and "MODEL END") in a JavaScript
engine and compares allocations, late orders, moves and couriers saved. Exits with an error on any difference.
Needs: pip install mini-racer.  Run from the repository root: python src/optimiser/check_page.py
"""
import json
import re
import sys

from py_mini_racer import MiniRacer

sys.path.insert(0, "src/optimiser")
from assumptions import defaults  # noqa: E402
from demand import calibration, shape_table, zone_shares  # noqa: E402
from optimise import scenario  # noqa: E402

SCENARIOS = [(4, 19, False), (5, 12, True), (1, 15, False)]
NUMBERS = ["orders", "couriers", "late_drift", "late_food", "late_optimised", "late_realised", "moved", "couriers_saved"]


def js_results():
    html = open("optimiser/index.html", encoding="utf-8").read()
    data = re.search(r"const DATA = (.*?);\n", html).group(1)
    model = re.search(r"// MODEL START[^\n]*\n(.*)// MODEL END", html, re.S).group(1)
    ctx = MiniRacer()
    ctx.eval(f"const DATA = {data};\n{model}")
    calls = ",".join(f"scenario(DATA, DATA.defaults, {d}, {h}, {str(r).lower()})" for d, h, r in SCENARIOS)
    return json.loads(ctx.eval(f"JSON.stringify([{calls}])"))


def main():
    p, calib = defaults(), calibration()
    shares, shape = zone_shares(p), shape_table(calib)
    failures = 0
    for (dow, hour, rain), js in zip(SCENARIOS, js_results()):
        py = scenario(p, shares, shape, calib, dow, hour, rain)
        label = f"day {dow} {hour}:00{' rain' if rain else ''}"
        for key in NUMBERS:
            ok = abs(py[key] - js[key]) < 1e-6
            failures += not ok
            print(f"{'OK ' if ok else 'BAD'} {label:<16} {key:<16} python {py[key]:>12.4f}   page {js[key]:>12.4f}")
        same_alloc = all(py["allocation"][k] == js["allocation"][k] for k in ("drift", "food", "optimised"))
        same_moves = [list(m) for m in py["moves"]] == js["moves"]
        failures += (not same_alloc) + (not same_moves)
        print(f"{'OK ' if same_alloc else 'BAD'} {label:<16} allocations identical")
        print(f"{'OK ' if same_moves else 'BAD'} {label:<16} moves identical ({len(js['moves'])} moves)")
    if failures:
        sys.exit(f"{failures} difference(s) between the map and optimise.py")
    print("The map's optimiser reproduces optimise.py.")


if __name__ == "__main__":
    main()
