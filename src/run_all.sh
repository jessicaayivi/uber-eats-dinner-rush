#!/usr/bin/env bash
# Rebuilds everything from the raw Meituan files: cleaning, SQL, lever model, simulator, and the sync check.
# Run from the repository root:  bash src/run_all.sh      (needs: pip install -r requirements.txt)
set -euo pipefail
PY="${PYTHON:-python}"

[ -f data/raw/meituan/all_waybill_info_meituan_0322.csv ] || bash src/download_data.sh
"$PY" src/prepare_meituan.py                              # clean orders, root causes, aggregated tables, data/meituan.db
"$PY" src/run_sql.py sql/analysis.sql data/meituan.db     # sql/analysis.sql -> data/results/*.csv
"$PY" src/sizing.py                                       # load curves, levers, sensitivity -> data/sizing.json
"$PY" src/build_simulator.py                              # simulator/index.html
"$PY" src/check_simulator.py                              # simulator defaults must reproduce sizing.py
