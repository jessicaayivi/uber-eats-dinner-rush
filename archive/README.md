# Archive: earlier versions of this case

- **`generate.py`, `marketplace_hourly.csv`**: the first version, a **simulated** marketplace (4 Belgian cities, invented orders). Its response curve, thresholds and productivity were assumptions.
- **`doordash_version/`**: the second version, on a Kaggle release of DoorDash deliveries (2015) plus an Indian food-delivery dataset. Replaced because the DoorDash data has no promised delivery time. See its README.

The case now runs on Meituan's real food-delivery orders (see the main README). Nothing in the current pipeline reads these files.
