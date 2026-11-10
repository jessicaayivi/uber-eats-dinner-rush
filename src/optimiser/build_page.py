"""Build optimiser/index.html: inject zones, hexagon outlines, demand shape, staffing and defaults into
optimiser/template.html. Run after optimise.py, from the repository root: python src/optimiser/build_page.py
"""
import json

import h3
import pandas as pd

from assumptions import HOURS, MIN_COURIERS_PER_ZONE, defaults
from demand import FIRST_DAY, DAYS_SIMULATED, calibration, zone_shares

OUT = "data/optimiser/"


def page_data():
    p, calib = defaults(), calibration()
    z = zone_shares(p)
    index = {name: i for i, name in enumerate(z.zone)}
    hexes = pd.read_csv(OUT + "hexes.csv")
    rain = pd.read_csv(OUT + "rain_hours.csv", parse_dates=["time"])
    window = rain[(rain.time >= FIRST_DAY) & (rain.time < pd.Timestamp(FIRST_DAY) + pd.Timedelta(days=DAYS_SIMULATED))
                  & rain.time.dt.hour.isin(HOURS)]
    results = json.load(open(OUT + "results.json"))
    return {
        "zones": [dict(zone=r.zone, residents=float(r.residents), food_places=int(r.food_places),
                       pickup_share=float(r.pickup_share)) for r in z.itertuples()],
        "hexes": [dict(zone=index[r.zone], residents=round(float(r.residents)), food_places=int(r.food_places),
                       boundary=[[round(a, 5), round(b, 5)] for a, b in h3.cell_to_boundary(r.h3)]) for r in hexes.itertuples()],
        "shape": {f"{int(d)}-{int(h)}": s for d, h, s in calib["demand_shape"]},
        "staffing": {int(h): v for h, v in calib["staffing_load_by_hour"].items()},
        "defaults": p, "min": MIN_COURIERS_PER_ZONE,
        "rain": {"rainy": int(window.rain.sum()), "hours": len(window)},
        "rule_gap_pct": f"{results['headline']['friday_19_vs_restaurant_rule_pct']}%",
        "sens_range": "{}% and {}%".format(*results["sensitivity_reduction_range_pct"]),
    }


def main():
    data = page_data()
    html = open("optimiser/template.html", encoding="utf-8").read().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open("optimiser/index.html", "w", encoding="utf-8").write(html)
    print(f"optimiser/index.html written ({len(data['zones'])} zones, {len(data['hexes'])} hexagons, {len(html) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
