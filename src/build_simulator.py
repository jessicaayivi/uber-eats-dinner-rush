"""Build simulator/index.html: inject the aggregated Meituan tables and the measured load curves into simulator/template.html.

Only aggregated counts go into the page (district x weekday x half-hour), never order-level rows,
because the Meituan licence does not allow redistributing the dataset.
Uses the same tables as src/sizing.py (it imports them), so the page and the model cannot drift apart.
Run after sizing.py, from the repository root: python src/build_simulator.py
"""
import json

import numpy as np

from assumptions import defaults
from sizing import load_tables

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def page_data():
    s, b = load_tables()
    sizing = json.load(open("data/sizing.json"))
    curve = sizing["curve"]
    load = np.where(np.isnan(s.load), -1, s.load)
    return {
        "slots": [[int(r.da_id), DAYS.index(r.dow), int(r.halfhour), int(r.days), int(r.orders), int(r.late),
                   round(float(r.busy_couriers), 4), round(float(l), 4)] for r, l in zip(s.itertuples(), load)],
        "late": [[int(r.key), int(r.late_min), int(r.merchant_save), int(r.refusal_save), int(r.stack_save), int(r.orders)]
                 for r in b.itertuples()],
        "curve": {"x": curve["x"], "dispatch": curve["dispatch"], "lastmile": curve["lastmile"]},
        "stress": sizing["stress_load"],
        "defaults": defaults(),
        "districts": sorted(int(d) for d in s.da_id.unique()),
    }


def main():
    data = page_data()
    html = open("simulator/template.html", encoding="utf-8").read()
    html = html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open("simulator/index.html", "w", encoding="utf-8").write(html)
    print(f"simulator/index.html written ({len(data['slots'])} district-half-hours, {len(data['late'])} late-order cells, "
          f"{len(html) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
