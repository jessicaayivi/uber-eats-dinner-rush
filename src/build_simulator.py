"""Builds simulator/index.html: injects the hourly marketplace data into simulator/template.html.
Run from the repository root: python src/build_simulator.py"""
import json
import pandas as pd

CITIES = {"Brussels": 0, "Antwerp": 1, "Ghent": 2, "Liege": 3}
DAYS = {d: i for i, d in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}

d = pd.read_csv("data/marketplace_hourly.csv")
rows = [[CITIES[r.city], DAYS[r.dow], int(r.hour), int(r.is_rain), int(r.orders_requested),
         int(r.couriers_online), int(r.orders_unfulfilled), int(r.orders_late)] for r in d.itertuples()]
html = open("simulator/template.html", encoding="utf-8").read()
html = html.replace("__DATA__", json.dumps(rows, separators=(",", ":")))
open("simulator/index.html", "w", encoding="utf-8").write(html)
print(f"simulator/index.html written ({len(rows)} city-hours)")
