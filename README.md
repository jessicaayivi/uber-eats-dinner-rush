# Winning the Dinner Rush: an Uber Eats Belgium marketplace case

**Jessica Ayivi** · Strategy & Operations · [jessicaayivi1@gmail.com](mailto:jessicaayivi1@gmail.com)

An independent business case on one question: when does courier supply fall behind demand in a Belgian food-delivery marketplace, what does it cost, and which levers fix it profitably?

- 📊 **Deck:** [Winning the Dinner Rush](https://claude.ai/artifact/CSPXkXz3a7duPuGExZo2zm) (14 slides)
- 🎛️ **Interactive simulator:** [try it here](https://jessicaayivi.github.io/uber-eats-dinner-rush/) (GitHub Pages, built from [`simulator/index.html`](simulator/index.html))
- 🧮 **Analysis:** SQL in [`sql/analysis.sql`](sql/analysis.sql), impact model in [`src/sizing.py`](src/sizing.py)

> **About the data.** Uber does not publish city-level operating data, so this case runs on a **simulated** marketplace (4 cities × 4 weeks × 14 hours a day = 1,568 city-hours, ~223k orders). The economics are anchored on Uber’s public Q3 2026 results: Delivery revenue ÷ gross bookings ≈ 19%. Figures are illustrative; the method is built to be rerun on real data.

## Key findings

| | |
|---|---|
| **Where it breaks** | Weekend and rainy dinners hold 78% of lost orders. Courier utilisation runs at 97–143% there, against under 85% in healthy hours. |
| **How concentrated** | The worst 10% of city-hours hold 64% of lost orders. |
| **Rain** | Dinner demand +7%, couriers online −14%, unfulfilled rate 5.1% → 12.1%. |
| **Smaller cities are fragile** | Liège has a quarter of Brussels’ volume but half its lost bookings. |
| **The obvious fix doesn’t pay** | A blanket €4/hour weekend boost costs ~€35 per saved order, while an order earns ~€5. |

## Recommendation

1. **Rebalance shifts** into forecast stress hours, using idle off-peak courier time. Cost ≈ €0. +826 orders/week.
2. **Stretch capacity** with batching and a tighter radius when utilisation passes 85%. +682 orders/week.
3. **Pay only where it pays:** quests on incremental hours, triggered above 110% utilisation. ~€660/week, roughly break-even. +114 orders/week.

**Impact:** unfulfilled orders 5.1% → 2.2%, ~1,600 orders saved a week, ~€2.3M gross bookings a year, late orders in stressed hours down by about half.

**How to prove it:** a switchback test (city × 2-hour blocks, randomised daily, 4 weeks), because couriers serve both arms of a user-level A/B test. Guardrails: courier earnings per hour, courier churn, cancellations, food quality on batched orders.

## Repository

```
data/marketplace_hourly.csv   simulated hourly marketplace table
sql/analysis.sql              5 queries: scorecard, daypart × rain, loss concentration (window functions), courier gap, rain uplift
src/generate.py               builds the simulated marketplace (seeded, reproducible)
src/run_sql.py                runs every query in analysis.sql against SQLite
src/sizing.py                 lever scenarios and impact sizing
src/build_simulator.py        injects the data into the simulator template
simulator/template.html       simulator source (HTML, CSS, JS model)
simulator/index.html          built simulator, one self-contained page
.github/workflows/pages.yml   publishes the simulator with GitHub Pages
```

## Reproduce

```bash
pip install -r requirements.txt
cd data
python ../src/generate.py                              # rebuilds marketplace_hourly.csv and marketplace.db
python ../src/run_sql.py ../sql/analysis.sql marketplace.db
python ../src/sizing.py                                # prints the scenarios, writes sizing.json
cd ..
python src/build_simulator.py                          # rebuilds simulator/index.html
```

## Assumptions

- A courier completes 2.1 deliveries per online hour; healthy utilisation is at most 85%.
- Above 85%, unfulfilled and late rates rise along the response curve in `src/sizing.py`.
- €27 average basket; net revenue 20% of bookings (Uber Q3 2026 Delivery actual: ~19%).
- Blanket boost: €4 per online courier-hour, paid to everyone; 60% of the targeted gap shows up.
- Quests: €5 per extra hour, plus 30% paid to couriers who would have come anyway.
- Batching: 2.1 → 2.3 deliveries per hour in stressed hours.

## What I would check first on real data

Whether couriers move for nudges or only for pay; the true batching gain and its effect on ETA and food quality; the retention cost of a failed order; whether merchant prep time is a hidden bottleneck; and whether Liège has a pool-size or a zone-design problem.
