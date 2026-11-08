#!/usr/bin/env bash
# Downloads the Meituan food-delivery dataset into data/raw/meituan/.
# Source: https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge
# Licence: CC BY-NC 4.0, and redistribution to third parties is not allowed, so the raw files are
# NEVER committed to this repository; only aggregated tables are.
# Required acknowledgement: "This research was supported by data provided by Meituan."
# Run from the repository root:  bash src/download_data.sh
set -euo pipefail
mkdir -p data/raw/meituan
cd data/raw/meituan
BASE=https://raw.githubusercontent.com/meituan/Meituan-INFORMS-TSL-Research-Challenge/main

curl -fsSL -o all_waybill_info_meituan_0322.csv.zip "$BASE/all_waybill_info_meituan_0322.csv.zip"   # orders (39 MB zipped)
unzip -oq all_waybill_info_meituan_0322.csv.zip -x "__MACOSX/*" && rm all_waybill_info_meituan_0322.csv.zip
for f in courier_wave_info_meituan.csv dispatch_rider_meituan.csv dispatch_waybill_meituan.csv License.txt; do
  curl -fsSL -o "$f" "$BASE/$f"
done
ls -la
