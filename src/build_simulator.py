"""Build simulator/index.html: inject the real market-hour data and the fitted curve into simulator/template.html.

Uses the same tables and response curve as src/sizing.py (it imports them), so the page and the
model cannot drift apart. Run after sizing.py, from the repository root: python src/build_simulator.py
"""
import json

from assumptions import defaults
from sizing import load_tables

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def page_data():
    mh, bins = load_tables()
    sizing = json.load(open("data/sizing.json"))
    curve = sizing["curve"]
    return {
        "mh": [[int(r.market_id), DAYS.index(r.dow), int(r.hour), int(r.orders), round(float(r.dashers), 4), float(r.load_ratio)]
               for r in mh.itertuples()],
        "bins": [[int(r.mh), int(round(r.load_bin * 10)), int(r.orders), int(r.late)] for r in bins.itertuples()],
        "curve": {"x": curve["x"], "late": curve["late"], "late_batched": curve["late_batched"]},
        "stress": sizing["stress_load"],
        "defaults": defaults(),
        "markets": [f"Market {m}" for m in sorted(mh.market_id.unique())],
    }


def main():
    data = page_data()
    html = open("simulator/template.html", encoding="utf-8").read()
    html = html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open("simulator/index.html", "w", encoding="utf-8").write(html)
    print(f"simulator/index.html written ({len(data['mh'])} market-hours, {len(data['bins'])} load cells)")


if __name__ == "__main__":
    main()
