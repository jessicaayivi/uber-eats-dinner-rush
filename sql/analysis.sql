-- Dinner Rush on real data: DoorDash deliveries, 6 US markets, 21 Jan - 17 Feb 2015 (4 weeks, local time UTC-8)
-- Source: Kaggle dharun4772/doordash-eta-prediction, cleaned by src/prepare_doordash.py into data/doordash.db
-- Tables: deliveries (one row per delivery), market_hour (market x date x hour)
-- Definitions: late = delivered in more than 60 minutes.
--              load_ratio = outstanding orders / on-shift dashers at order time.
--              Stressed: load_ratio > 1.2 (where the response curve bends, Q3 / src/sizing.py).
--              Quiet:    load_ratio < 0.8 (late rate still at its ~8% floor).

-- Q1. Market scorecard
-- name: q1_market
WITH ranked AS (
  SELECT market_id, delivery_minutes,
         ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY delivery_minutes) AS rn,
         COUNT(*)     OVER (PARTITION BY market_id)                           AS n
  FROM deliveries
), pct AS (
  SELECT market_id,
         MIN(CASE WHEN rn >= 0.5 * n THEN delivery_minutes END) AS median_minutes,
         MIN(CASE WHEN rn >= 0.9 * n THEN delivery_minutes END) AS p90_minutes
  FROM ranked
  GROUP BY market_id
)
SELECT d.market_id,
       COUNT(*) / 4                          AS orders_per_week,
       ROUND(p.median_minutes, 1)            AS median_minutes,
       ROUND(p.p90_minutes, 1)               AS p90_minutes,
       ROUND(100.0 * AVG(d.is_late), 1)      AS late_pct,
       ROUND(AVG(d.busy_ratio), 2)           AS avg_busy_ratio,
       ROUND(AVG(d.load_ratio), 2)           AS avg_load_ratio,
       ROUND(AVG(d.basket_usd), 2)           AS avg_basket_usd
FROM deliveries d
JOIN pct p USING (market_id)
GROUP BY d.market_id
ORDER BY orders_per_week DESC;

-- Q2. When it breaks: weekend x daypart
-- name: q2_daypart
WITH tagged AS (
  SELECT *,
         CASE WHEN dow IN ('Friday', 'Saturday', 'Sunday') THEN 'Fri-Sun' ELSE 'Mon-Thu' END AS week_part,
         CASE WHEN hour BETWEEN 11 AND 13 THEN 'Lunch 11-14'
              WHEN hour BETWEEN 17 AND 20 THEN 'Dinner 17-21'
              ELSE 'Other' END AS daypart
  FROM deliveries
)
SELECT week_part, daypart,
       COUNT(*) / 4                                                       AS orders_per_week,
       ROUND(AVG(delivery_minutes), 1)                                    AS avg_minutes,
       ROUND(100.0 * AVG(is_late), 1)                                     AS late_pct,
       ROUND(AVG(load_ratio), 2)                                          AS avg_load_ratio,
       ROUND(100.0 * SUM(is_late) / (SELECT SUM(is_late) FROM deliveries), 1) AS share_of_all_late_pct
FROM tagged
GROUP BY week_part, daypart
ORDER BY share_of_all_late_pct DESC;

-- Q2b. The ten worst weekday-hours (all markets)
-- name: q2b_worst_hours
SELECT dow, hour,
       COUNT(*) / 4                       AS orders_per_week,
       ROUND(100.0 * AVG(is_late), 1)     AS late_pct,
       ROUND(AVG(load_ratio), 2)          AS avg_load_ratio
FROM deliveries
GROUP BY dow, hour
HAVING COUNT(*) >= 400
ORDER BY late_pct DESC
LIMIT 10;

-- Q3. The response curve: how delivery time and lateness react to marketplace load
--     Driving time is shown as a control: if it were rising too, the curve would just be "longer trips".
-- name: q3_response_curve
WITH b AS (
  SELECT *, MIN(CAST(load_bin * 5 + 1e-9 AS INT) / 5.0, 2.4) AS load_bucket
  FROM deliveries
)
SELECT load_bucket                                                    AS load_from,
       COUNT(*)                                                       AS orders,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM deliveries), 1) AS share_of_orders_pct,
       ROUND(AVG(delivery_minutes), 1)                                AS avg_minutes,
       ROUND(100.0 * AVG(is_late), 1)                                 AS late_pct,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 17 AND 20 THEN is_late END), 1) AS dinner_late_pct,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 11 AND 13 THEN is_late END), 1) AS lunch_late_pct,
       ROUND(AVG(drive_min), 1)                                       AS avg_drive_minutes
FROM b
GROUP BY load_bucket
ORDER BY load_bucket;

-- Q4. Concentration: what share of late orders sits in the worst market-hours?
-- name: q4_concentration
WITH ranked AS (
  SELECT late, orders,
         ROW_NUMBER() OVER (ORDER BY late DESC)                       AS rnk,
         COUNT(*)     OVER ()                                         AS n_hours,
         SUM(late)    OVER (ORDER BY late DESC ROWS UNBOUNDED PRECEDING) AS cum_late,
         SUM(orders)  OVER (ORDER BY late DESC ROWS UNBOUNDED PRECEDING) AS cum_orders,
         SUM(late)    OVER ()                                         AS total_late,
         SUM(orders)  OVER ()                                         AS total_orders
  FROM market_hour
)
SELECT ROUND(100.0 * rnk / n_hours)               AS pct_of_market_hours,
       ROUND(100.0 * cum_late / total_late, 1)     AS pct_of_late_orders,
       ROUND(100.0 * cum_orders / total_orders, 1) AS pct_of_all_orders
FROM ranked
WHERE rnk IN (CAST(n_hours * 0.05 AS INT), CAST(n_hours * 0.10 AS INT), CAST(n_hours * 0.20 AS INT));

-- Q5. Supply gap and slack, per market and week
--     The dasher counts in the data are local (within 10 miles of the store), so they cannot be summed
--     into market dasher-hours. Instead, by Little's law: orders in progress = orders x hours per delivery,
--     and dashers = orders in progress / load ratio. That puts dashers on the same scale as the orders.
--     Gap:   extra dasher-hours that would bring each stressed hour back to a load ratio of 1.2.
--     Slack: dasher-hours that quiet hours could give up while staying under 0.8 (no lateness cost).
-- name: q5_gap_slack
WITH mh AS (
  SELECT *, orders * avg_minutes / 60.0 / MAX(load_ratio, 0.3) AS dashers
  FROM market_hour
)
SELECT market_id,
       ROUND(SUM(dashers) / 4)                                                           AS dasher_hours_per_week,
       ROUND(SUM(orders) / SUM(dashers), 2)                                              AS deliveries_per_dasher_hour,
       SUM(CASE WHEN load_ratio > 1.2 THEN 1 ELSE 0 END) / 4                             AS stressed_hours_per_week,
       ROUND(100.0 * SUM(CASE WHEN load_ratio > 1.2 THEN late END) / SUM(late), 1)      AS pct_of_late_in_stressed_hours,
       ROUND(SUM(CASE WHEN load_ratio > 1.2 THEN dashers * (load_ratio / 1.2 - 1) END) / 4) AS gap_dasher_hours_per_week,
       SUM(CASE WHEN load_ratio < 0.8 THEN 1 ELSE 0 END) / 4                             AS quiet_hours_per_week,
       ROUND(SUM(CASE WHEN load_ratio < 0.8 THEN dashers * (1 - load_ratio / 0.8) END) / 4) AS slack_dasher_hours_per_week,
       ROUND(SUM(CASE WHEN load_ratio < 0.8 THEN dashers * (1 - load_ratio / 0.8) END)
           / SUM(CASE WHEN load_ratio > 1.2 THEN dashers * (load_ratio / 1.2 - 1) END), 2) AS slack_to_gap
FROM mh
GROUP BY market_id
ORDER BY market_id;

-- Q5b. The same, all markets together
-- name: q5b_gap_slack_total
WITH mh AS (
  SELECT *, orders * avg_minutes / 60.0 / MAX(load_ratio, 0.3) AS dashers
  FROM market_hour
)
SELECT ROUND(SUM(dashers) / 4)                                                           AS dasher_hours_per_week,
       ROUND(SUM(CASE WHEN load_ratio > 1.2 THEN dashers * (load_ratio / 1.2 - 1) END) / 4) AS gap_dasher_hours_per_week,
       ROUND(SUM(CASE WHEN load_ratio < 0.8 THEN dashers * (1 - load_ratio / 0.8) END) / 4) AS slack_dasher_hours_per_week,
       ROUND(100.0 * SUM(CASE WHEN load_ratio > 1.2 THEN late END) / SUM(late), 1)      AS pct_of_late_in_stressed_hours,
       ROUND(100.0 * SUM(CASE WHEN load_ratio > 1.2 THEN orders END) / SUM(orders), 1)  AS pct_of_orders_in_stressed_hours
FROM mh;

-- Q6a. Merchant check: does the order-placement time explain lateness once load is accounted for?
--      expected_late = late rate of deliveries at the same load (0.1 bins). Residual > 0: later than load explains.
-- name: q6a_order_placement
WITH curve AS (SELECT load_bin, AVG(is_late) AS curve_late FROM deliveries GROUP BY load_bin)
SELECT ROUND(d.order_place_min, 1)                          AS order_place_minutes,
       COUNT(*)                                             AS orders,
       ROUND(100.0 * AVG(d.is_late), 1)                     AS late_pct,
       ROUND(100.0 * AVG(c.curve_late), 1)                  AS expected_from_load_pct,
       ROUND(100.0 * (AVG(d.is_late) - AVG(c.curve_late)), 1) AS residual_pts,
       ROUND(AVG(d.load_ratio), 2)                          AS avg_load_ratio
FROM deliveries d JOIN curve c USING (load_bin)
GROUP BY ROUND(d.order_place_min, 1)
HAVING COUNT(*) >= 100
ORDER BY order_place_minutes;

-- Q6b. Merchant check by cuisine (12 largest categories)
-- name: q6b_category
WITH curve AS (SELECT load_bin, AVG(is_late) AS curve_late FROM deliveries GROUP BY load_bin)
SELECT d.store_primary_category                             AS category,
       COUNT(*)                                             AS orders,
       ROUND(100.0 * AVG(d.is_late), 1)                     AS late_pct,
       ROUND(100.0 * AVG(c.curve_late), 1)                  AS expected_from_load_pct,
       ROUND(100.0 * (AVG(d.is_late) - AVG(c.curve_late)), 1) AS residual_pts,
       ROUND(AVG(d.drive_min), 1)                           AS avg_drive_minutes
FROM deliveries d JOIN curve c USING (load_bin)
WHERE d.store_primary_category IS NOT NULL
GROUP BY d.store_primary_category
ORDER BY orders DESC
LIMIT 12;
