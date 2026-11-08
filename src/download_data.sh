#!/usr/bin/env bash
# Downloads the two public Kaggle datasets this case uses into data/raw/.
# Raw files are NOT committed (redistribution terms are unclear); only aggregated tables are.
#
# Public Kaggle datasets download without an API token through the endpoint below.
# (Equivalent with the Kaggle CLI: kaggle datasets download -d <dataset> --unzip)
# Run from the repository root:  bash src/download_data.sh
set -euo pipefail
mkdir -p data/raw
cd data/raw

download() {  # $1 = owner/dataset on Kaggle
  local zip
  zip="$(basename "$1").zip"
  curl -fsSL -o "$zip" "https://www.kaggle.com/api/v1/datasets/download/$1"
  unzip -oq "$zip" && rm "$zip"
  echo "downloaded $1"
}

# 1. DoorDash ETA prediction: ~197k deliveries, early 2015, US markets (MIT on Kaggle). Main file: historical_data.csv
download dharun4772/doordash-eta-prediction

# 2. Food Delivery Dataset: ~45k deliveries in Indian cities, with weather, traffic, festivals,
#    multiple deliveries (licence "Other", terms not stated). Main file: train.csv
download gauravmalik26/food-delivery-dataset

ls -la
