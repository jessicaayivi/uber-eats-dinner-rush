# Where should Brussels couriers wait?

**Jessica Ayivi** · Strategy & Operations · [jessicaayivi1@gmail.com](mailto:jessicaayivi1@gmail.com)

A small case study I built to prepare for a Marketplace Strategy & Operations role in Brussels. It asks one question at the heart of the role: **with the same couriers, where should they wait so fewer orders arrive late?**

- 🗺️ **Try the map:** [jessicaayivi.github.io/uber-eats-dinner-rush](https://jessicaayivi.github.io/uber-eats-dinner-rush/)
- 📄 **All the details** (every number, assumption and test): [docs/DETAILS.md](docs/DETAILS.md)

> Uber's data isn't public, and nothing here is Uber data. The evidence comes from a real public dataset from another delivery company (Meituan), and the Brussels map uses real public data about the city with simulated orders. Everything that is a guess is labelled as one.

![Friday 19:00: couriers today vs repositioned](docs/brussels_friday_19h_optimised.png)

## The story in three steps

1. **Diagnose, on real data.** Why are food deliveries late? I analysed 538,689 real orders, each with the time the customer was promised.
2. **Act, in Brussels.** A map that shows where couriers are short or spare at each hour, and where to move them.
3. **Test it.** How I would prove it works before rolling it out.

## 1. What the real data shows

From 538,689 Meituan food-delivery orders (one Chinese city, 23 districts, 17–24 October 2022):

- **1 order in 7** arrives after the time the customer was promised.
- **2 in 3 late orders** miss it by 5 minutes or less, so small improvements matter.
- **Why orders are late** (the step that ran longest over normal):

  | Cause | Share of late orders |
  |---|---|
  | The last part of the trip | 55% |
  | Waiting at the restaurant | 34% |
  | Waiting for a courier | 7% |
  | A courier refused the order | 3% |

- **Uneven workloads:** at lunch rush, 30% of couriers carry nothing while others carry 3 or more orders.

The SQL behind these findings is in [`sql/analysis.sql`](sql/analysis.sql), with comments explaining each question.

## 2. What the Brussels map suggests (a model, not a measurement)

- **Real inputs:** where people live (Statbel), where restaurants are (OpenStreetMap), when it rained (Open-Meteo), and how lateness grows when couriers are busy (the Meituan data).
- **Simulated:** the orders themselves, from an assumed 30,000 orders a week.
- **Key assumption:** couriers wait where their last delivery ended (where customers live), while pickups are mostly in the centre, which has 29% of Brussels' restaurants but 5% of its residents.
- **Result, in my model:** at Friday 19:00, moving 43 of 163 couriers gives about **10% fewer late orders** with the same couriers. A simple rule, spreading couriers like the restaurants, gets almost the same result.

## 3. How I would test it

- **Measure first:** where available couriers really wait, compared with where pickups happen, hour by hour.
- **Start with free fixes:** help the slowest restaurants (with account managers) and reduce courier refusals.
- **Then test repositioning** with a randomised switchback test: switch it on and off by city and 2-hour block, while watching courier earnings, cancellations and food quality.

## What is real and what is assumed

| Real (public data) | Assumed (and stress-tested) |
|---|---|
| Brussels residents, restaurants, rain | 30,000 orders a week |
| 538,689 real orders and why they were late | 70% of orders start near restaurants, 30% near homes |
| How lateness grows when couriers are busy | +15% orders when it rains |
| How long an order keeps a courier busy (25 min) | 60% of couriers follow a nudge |

The limits I would check first: the real data comes from China, not Belgium; zones are treated as separate; couriers don't move instantly.

## How the repository is organised

| Folder or file | What it contains |
|---|---|
| [`sql/analysis.sql`](sql/analysis.sql) | The 10 questions asked to the real data, with comments |
| [`src/prepare_meituan.py`](src/prepare_meituan.py) | Cleans the real orders and finds why each late order was late |
| [`src/optimiser/`](src/optimiser/) | Builds the Brussels map: download the data, learn the rules, build the grid, simulate orders, place couriers |
| [`optimiser/index.html`](optimiser/index.html) | The map web page |
| [`data/`](data/) | Small summary tables. Raw data is never published |
| [`docs/DETAILS.md`](docs/DETAILS.md) | Every number, assumption, sensitivity test and limitation |
| `src/sizing.py`, `simulator/` | My first lever model on the real data (euros, five fixes), kept for reference, not published |
| [`archive/`](archive/) | Earlier versions of the case |

**Rebuild everything** (the raw data downloads automatically):

```bash
pip install -r requirements.txt
bash src/run_all.sh
```

## Sources and credits

Statbel (CC BY 4.0) · Map data © OpenStreetMap contributors (ODbL) · Weather data by Open-Meteo.com (CC BY 4.0) · Meituan INFORMS TSL Research Challenge data (CC BY-NC 4.0): *this research was supported by data provided by Meituan.* · DoorDash ETA dataset on Kaggle (weekly demand shape).

Independent analysis by Jessica Ayivi; not affiliated with Uber, Meituan or DoorDash. I designed the analysis and the decisions, and used an AI coding assistant to write and check the code.
