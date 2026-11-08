#!/usr/bin/env bash
# Rebuilds everything from the raw Kaggle files: cleaning, SQL, lever model, simulator, and the sync check.
# Run from the repository root:  bash src/run_all.sh      (needs: pip install -r requirements.txt)
set -euo pipefail
PY="${PYTHON:-python}"

[ -f data/raw/historical_data.csv ] && [ -f data/raw/train.csv ] || bash src/download_data.sh
"$PY" src/prepare_india.py          # weather + batching effects (needed by the next step)
"$PY" src/prepare_doordash.py       # clean deliveries, market-hour tables, data/doordash.db
"$PY" src/run_sql.py                # sql/analysis.sql -> data/results/*.csv
"$PY" src/sizing.py                 # response curve, levers, sensitivity -> data/sizing.json
"$PY" src/build_simulator.py        # simulator/index.html
"$PY" src/check_simulator.py        # simulator defaults must reproduce sizing.py
