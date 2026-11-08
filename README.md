# Winning the Dinner Rush: a delivery-marketplace case on real data

**Jessica Ayivi** · Strategy & Operations · [jessicaayivi1@gmail.com](mailto:jessicaayivi1@gmail.com)

When does courier supply fall behind demand in a food-delivery marketplace, what does it cost, and which levers fix it profitably? I analysed **176,448 real DoorDash deliveries** to answer that, and this is how I would apply the method at Uber Eats Belgium.

- 🎛️ **Interactive simulator:** [jessicaayivi.github.io/uber-eats-dinner-rush](https://jessicaayivi.github.io/uber-eats-dinner-rush/)
- 🧮 **Analysis:** SQL in [`sql/analysis.sql`](sql/analysis.sql), lever model in [`src/sizing.py`](src/sizing.py), every assumption in [`src/assumptions.py`](src/assumptions.py)
- 📊 **Deck:** [Winning the Dinner Rush](https://claude.ai/artifact/CSPXkXz3a7duPuGExZo2zm) (being updated to the real-data version)

> **About the data.** The deliveries are real but public and old: a Kaggle release of DoorDash orders from six anonymised US markets, 21 Jan – 17 Feb 2015, with noise added by the publisher. A second public dataset (Indian cities, 2022) supplies the weather and batching effects. **None of this is Uber data or Belgian data.** Money is in US dollars. The only Uber figure used is public: Delivery revenue ÷ gross bookings ≈ 19% (Q3 2026).

## Key findings

| | |
|---|---|
| **Service degrades past a measurable threshold** | Late deliveries (over 60 minutes) sit at ~8% while there are fewer than 0.8 outstanding orders per on-shift dasher. The curve bends at **1.2**: below it, each extra 0.1 of load adds 0.8 points of lateness; above it, 4.6 points. At 2.0+ more than half of deliveries are late. Driving distance stays flat across load levels, so this is a supply effect, not longer trips. |
| **Weekend dinners break** | Fri–Sun 17:00–21:00 is 26% of orders but **45% of late deliveries** (33% late vs 12–18% elsewhere). Worst hours: Sunday 18:00 (46% late) and Friday 19:00 (43%). |
| **Stress is routine, not a rare spike** | Half of all orders are placed in market-hours above the 1.2 knee; those hours hold 71% of late deliveries. The worst 10% of market-hours hold 58% of late orders (and 33% of orders). |
| **There is little idle capacity to move** | Quiet hours (load under 0.8) hold ~400 idle dasher-hours a week against a ~2,800-hour gap in stressed hours: **15%**, and only 3–8% in the three largest markets. |
| **Dashers are less productive than assumed** | ~1.5 deliveries per dasher-hour (Little's law on the data), not the 2.1 the simulated version assumed. |
| **Restaurants are a second bottleneck** | Orders sent to restaurants through the slower channel (7.4 vs 4.2 min to place) are late 6 points more often than their load explains; Japanese (+7 pts) and pizza (+4 pts) run late, Mexican and sandwich run early. |
| **Bad weather and batching (Indian data)** | Like-for-like, storms add 17% to delivery time, fog 28%, traffic jams 41%. A second order in the same trip adds only **11%**; three or more add 47–60%. |
| **The obvious fix doesn't pay** | A blanket $4/hour bonus for every dasher on weekend dinners costs **~$40 per late delivery avoided**. |

## Recommendation

1. **Rebalance shifts** from quiet hours into forecast stress hours. Free, but small: ~160 fewer late deliveries a week.
2. **Batch pairs, never more**, in stressed hours: ~280 fewer late deliveries a week at no cost, with a hard cap of two orders per trip.
3. **Targeted quests** above a load of 1.5: ~440 fewer late deliveries a week for ~$2,600, i.e. **~$6 per late delivery avoided, a seventh of the blanket bonus**.

**Impact:** late deliveries 19.5% → 17.5%, ~890 fewer a week (−10%), late deliveries in stressed hours −15%.

**The honest caveat:** quests only pay if a late delivery costs more than ~$6 of future net revenue (about 1.2 lost orders at a $27 basket and 19% take). With my default assumption of half a lost order ($2.57), steps 1–2 earn ~+$1,150 a week, and adding quests turns the plan slightly negative (−$360 a week). So: **roll out steps 1–2, run quests only inside the test, and never pay a blanket bonus.**

**How to prove it:** a switchback test (market × 2-hour blocks, randomised daily, 4 weeks), because dashers serve both arms of a user-level A/B test. The first thing to measure is the retention cost of a late delivery, because it decides whether quests pay. Guardrails: dasher earnings per hour, dasher churn, cancellations, food quality on paired orders.

## What changed from the simulated version

The first version of this case ran on invented data ([`archive/`](archive/)). Real data changed the story:

| | Simulated version | Real data |
|---|---|---|
| Pain metric | Unfulfilled orders, 5.1% | Late deliveries (>60 min), 19.5%. The data only contains delivered orders. |
| Breaking point | Assumed: 85% utilisation | Measured: knee at 1.2 outstanding orders per dasher, gradual then steep |
| Worst 10% of hours | 64% of lost orders | 58% of late orders |
| Deliveries per courier-hour | 2.1 (assumed) | ~1.5 (measured) |
| Free rebalancing | 25% of the gap, assumed | Idle slack covers 15% of the gap |
| Plan impact | 5.1% → 2.2% unfulfilled (−57%) | 19.5% → 17.5% late (−10%) |
| Blanket boost | ~€35 per saved order | ~$40 per late delivery avoided |
| Targeted quests | ~€660/week, roughly break-even | ~$2,600/week, pay only if a late delivery is worth > ~$6 |
| Rain | Demand +7%, couriers −14% (invented) | Not in the DoorDash data. Indian data: storms +17% delivery time; supply effect unmeasured |

The direction of the recommendation survived (targeted beats blanket, free levers first); the size of the prize is much smaller and the case for paid incentives is weaker.

## Data sources

| Dataset | What it gives | Licence on Kaggle | In this repo |
|---|---|---|---|
| [DoorDash ETA Prediction](https://www.kaggle.com/datasets/dharun4772/doordash-eta-prediction) (dharun4772) | 197,428 deliveries, 6 US markets, Jan–Feb 2015, with dashers on shift, busy dashers and outstanding orders at order time | MIT, but the data card describes it as a DoorDash subset with added noise | Raw file **not committed**; aggregated tables only |
| [Food Delivery Dataset](https://www.kaggle.com/datasets/gauravmalik26/food-delivery-dataset) (gauravmalik26) | 45,593 deliveries in Indian cities, 2022: weather, traffic, festivals, multiple deliveries | "Other", terms not stated | Raw file **not committed**; effect table only |

`bash src/download_data.sh` fetches both (public datasets download without a Kaggle token).

Caveats: the dasher and order counts are local (within 10 miles of the store), so dashers per market-hour are estimated with Little's law (orders × hours per delivery ÷ load ratio). The Indian weather categories are almost exactly equal in size, which suggests that dataset is partly synthetic; treat it as directional.

## Data cleaning (DoorDash)

| Step | Rows |
|---|---|
| Raw | 197,428 |
| Missing timestamps | −7 |
| Missing market | −987 |
| Missing dasher / outstanding-order counts | −16,194 |
| Negative counts (noise) | −81 |
| Zero dashers on shift | −3,595 |
| Delivery time outside 5–180 min (180 > the 99.9th percentile) | −116 |
| **Clean** | **176,448** |

Timestamps are UTC; **UTC−8** (US/Pacific winter time) puts the peaks at 12:00 and 18:00, where UTC−5 would put lunch at 15:00. Late = over 60 minutes: the "within the hour" promise, at the 80th percentile (p90 = 70 min). Busy dashers exceed on-shift dashers in 23% of rows (publisher noise), so the busy ratio is capped at 1. Full log: [`data/doordash_cleaning.json`](data/doordash_cleaning.json).

## Assumptions

Everything the model uses that is not measured in this run, in one place: [`src/assumptions.py`](src/assumptions.py).

| Input | Value | Source |
|---|---|---|
| Late threshold | 60 min | Data: 80th percentile, "within the hour" |
| Stress threshold | load 1.2 | Data: fitted knee of the response curve |
| Quiet threshold | load 0.8 | Data: late rate still at its floor |
| Basket | $27.02 | Data: average subtotal |
| Batching delay | +11.1% | Data (Indian): second order in the trip, like-for-like |
| Net revenue per order | 19% of bookings | Public: Uber Q3 2026, Delivery revenue $5.5B ÷ gross bookings $28.5B |
| Idle time movable by rebalancing | 50% | Assumption |
| Orders that can be paired | 20% | Assumption |
| Courier time saved per paired order | 30% | Assumption (Indian trip times imply up to 44%) |
| Gap filled by quests | 35% | Assumption |
| Quest trigger | load 1.5 | Assumption |
| Quest pay | $5 per extra hour | Assumption |
| Quest leakage | 30% | Assumption |
| Blanket bonus | $4 per online hour, Fri–Sun 17:00–21:00 | Assumption |
| Gap filled by blanket bonus | 60% | Assumption |
| Future orders lost per late delivery | 0.5 | Assumption |

## Sensitivity

Each assumption at 50% and 150% of its default, everything else unchanged ([`data/results/sensitivity.csv`](data/results/sensitivity.csv)). Default: 17.5% late after the plan, −$361/week, $5.98 of quest spend per late delivery avoided.

| Assumption (default) | At 50%: late after · net/week · quest $/late | At 150%: late after · net/week · quest $/late | Targeted still beats blanket? |
|---|---|---|---|
| Idle time moved by rebalancing (0.5) | 17.6% · −$647 · $5.97 | 17.4% · −$158 · $5.97 | Yes |
| Orders paired (0.2) | 17.7% · −$972 · $5.89 | 17.4% · +$320 · $5.96 | Yes |
| Courier time saved per paired order (0.3) | 18.2% · −$1,538 · $5.84 | 16.9% · +$852 · $6.03 | Yes |
| Gap filled by quests (0.35) | 18.0% · +$436 · $5.54 | 17.1% · −$1,270 · $6.59 | Yes |
| Quest trigger (load 1.5) | 16.5% · −$2,938 · $7.27 | 18.5% · +$1,143 · $3.18 | Yes |
| Quest pay per hour ($5) | 17.5% · +$957 · $2.99 | 17.5% · −$1,678 · $8.97 | Yes |
| Quest leakage (0.3) | 17.5% · −$57 · $5.29 | 17.5% · −$665 · $6.67 | Yes |
| Blanket bonus per hour ($4) | unchanged; blanket costs $19.85 per late avoided | unchanged; $59.56 | Yes |
| Gap filled by blanket bonus (0.6) | unchanged; blanket costs $66.78 per late avoided | unchanged; $32.08 | Yes |
| Future orders lost per late delivery (0.5) | 17.5% · −$1,498 · $5.98 | 17.5% · +$777 · $5.98 | Yes |

**What holds:** targeted quests beat a blanket bonus in all 20 cases (at worst ~$9 vs at best ~$20 per late delivery avoided). **What doesn't:** whether the plan makes money depends on the value of a late delivery, the batching gain and the quest price; that is why the test, not this model, should decide on quests.

## Repository

```
src/download_data.sh          fetches both Kaggle datasets into data/raw/ (not committed)
src/prepare_india.py          weather, traffic, festival and batching effects (Indian data)
src/prepare_doordash.py       cleans the deliveries, builds market-hour tables and data/doordash.db
sql/analysis.sql              6 questions: scorecard, when it breaks, response curve, concentration, gap vs slack, merchant check
src/run_sql.py                runs every query, saves data/results/<query>.csv
src/assumptions.py            every non-measured input, with its source
src/sizing.py                 response curve, levers, blanket comparison, sensitivity -> data/sizing.json
src/build_simulator.py        injects the data and curve into simulator/template.html
src/check_simulator.py        runs the simulator's JS model and checks it reproduces sizing.py
src/run_all.sh                the whole pipeline
simulator/index.html          built simulator, published by .github/workflows/pages.yml
archive/                      the first, simulated version (not used)
```

## Reproduce

```bash
pip install -r requirements.txt
bash src/run_all.sh
```

## Limitations

Old (2015), US, noisy and sampled data; dasher counts are local snapshots, not market supply; the response curve is observational (busy hours may differ in other ways, which is why dinner sits a few points above lunch at the same load); there are no cancellations or unfulfilled orders; the value of a late delivery is an assumption. Each of these is something I would check first on Uber's own data.
