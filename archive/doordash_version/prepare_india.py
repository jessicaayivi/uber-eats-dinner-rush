"""Supporting analysis on a second market: weather, traffic, festivals and batching (India, 2022).

Input : data/raw/train.csv  (Kaggle: gauravmalik26/food-delivery-dataset; not committed)
Output: data/results/india_effects.csv   delivery-time effect of each condition, raw and like-for-like
        data/india_summary.json          the numbers sizing.py uses (batching delay)

Run from the repository root: python src/prepare_india.py

This is NOT Belgian or Uber data. It is used for two things the DoorDash data cannot show:
the effect of bad weather, and the delivery-time cost of carrying more than one order per trip.

"Like-for-like" effects compare orders within the same city type x traffic x weather x festival cell
(leaving out the factor being measured), then average the differences weighted by order count.
Caveat: the six weather categories are almost exactly the same size (~7,500 orders each), and there is
no "rain" category, which suggests the dataset is partly synthetic. Treat it as directional.
"""
import json
import os

import pandas as pd

RAW = "data/raw/train.csv"
CONTROLS = ["City", "Road_traffic_density", "Weatherconditions", "Festival"]


def load():
    d = pd.read_csv(RAW)
    for col in d.select_dtypes("object"):
        d[col] = d[col].str.strip()
    d["minutes"] = d["Time_taken(min)"].str.replace("(min)", "", regex=False).astype(float)
    d["Weatherconditions"] = d.Weatherconditions.str.replace("conditions ", "", regex=False)
    d = d.replace("NaN", pd.NA).dropna(subset=CONTROLS + ["multiple_deliveries"])
    d["multiple_deliveries"] = d.multiple_deliveries.astype(float).astype(int)
    return d


def effect(d, factor, baseline):
    """Raw and like-for-like difference in minutes of each level of `factor` versus `baseline`."""
    controls = [c for c in CONTROLS if c != factor]
    base_cells = d[d[factor] == baseline].groupby(controls).minutes.mean().rename("base")
    rows = []
    for level, grp in d.groupby(factor):
        if level == baseline:
            continue
        cells = grp.groupby(controls).minutes.agg(["mean", "size"]).join(base_cells, how="inner")
        adjusted = ((cells["mean"] - cells.base) * cells["size"]).sum() / cells["size"].sum()
        raw = grp.minutes.mean() - d.loc[d[factor] == baseline, "minutes"].mean()
        rows.append(dict(factor=factor, level=str(level), baseline=str(baseline), orders=len(grp),
                         avg_minutes=round(grp.minutes.mean(), 1), raw_diff_min=round(raw, 1),
                         like_for_like_diff_min=round(adjusted, 1),
                         like_for_like_diff_pct=round(100 * adjusted / d.loc[d[factor] == baseline, "minutes"].mean(), 1)))
    return rows


def main():
    d = load()
    rows = (effect(d, "Weatherconditions", "Sunny") + effect(d, "Road_traffic_density", "Low")
            + effect(d, "Festival", "No") + effect(d, "multiple_deliveries", 0))
    table = pd.DataFrame(rows)
    os.makedirs("data/results", exist_ok=True)
    table.to_csv("data/results/india_effects.csv", index=False)
    print(f"{len(d):,} deliveries, average {d.minutes.mean():.1f} min\n")
    print(table.to_string(index=False))

    single = d.loc[d.multiple_deliveries == 0, "minutes"].mean()
    second = table[(table.factor == "multiple_deliveries") & (table.level == "1")].iloc[0]
    summary = {
        "orders": len(d),
        "avg_minutes_single_order": round(single, 1),
        "batching_delay_min": float(second.like_for_like_diff_min),   # used by sizing.py
        "batching_delay_pct": float(second.like_for_like_diff_pct),
        "weather_category_sizes": d.Weatherconditions.value_counts().to_dict(),
    }
    json.dump(summary, open("data/india_summary.json", "w"), indent=1)
    print("\n", json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
