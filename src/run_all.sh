#!/usr/bin/env bash
# Rebuilds everything: the Meituan case (cleaning, SQL, lever model, simulator) and the Brussels optimiser, with both sync checks.
# Run from the repository root:  bash src/run_all.sh      (needs: pip install -r requirements.txt)
set -euo pipefail
PY="${PYTHON:-python}"

[ -f data/raw/meituan/all_waybill_info_meituan_0322.csv ] || bash src/download_data.sh
"$PY" src/prepare_meituan.py                              # clean orders, root causes, aggregated tables, data/meituan.db
"$PY" src/run_sql.py sql/analysis.sql data/meituan.db     # sql/analysis.sql -> data/results/*.csv
"$PY" src/sizing.py                                       # load curves, levers, sensitivity -> data/sizing.json
"$PY" src/build_simulator.py                              # simulator/index.html
"$PY" src/check_simulator.py                              # simulator defaults must reproduce sizing.py

# Brussels courier-positioning optimiser (uses data/slots.csv from the steps above)
[ -f data/raw/brussels/osm_food_places.json ] || "$PY" src/optimiser/download.py
"$PY" src/optimiser/calibrate.py                          # response curve, minutes per order, staffing, demand shape
"$PY" src/optimiser/grid.py                               # Brussels H3 hexagons and 25 zones
"$PY" src/optimiser/demand.py                             # simulated orders, real rain hours
"$PY" src/optimiser/optimise.py                           # optimiser, PuLP cross-check, sensitivity
"$PY" src/optimiser/build_page.py                         # optimiser/index.html
"$PY" src/optimiser/check_page.py                         # the map's JS optimiser must reproduce optimise.py
