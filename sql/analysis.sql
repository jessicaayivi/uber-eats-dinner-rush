-- Dinner Rush on real data: Meituan food-delivery orders, 23 business districts, Mon 17 - Mon 24 Oct 2022 (8 days)
-- Source: github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge (CC BY-NC 4.0), cleaned by src/prepare_meituan.py
-- Tables (data/meituan.db): orders (one row per delivered order), merchants, slots_by_date (district x date x half-hour),
--                           dispatch_snapshots (24 lunch-peak dispatch moments)
-- Late = delivered after the time promised to the customer. Weekly figures = 8-day totals x 7/8.
-- Stages: dispatch (created -> first offered to a courier), accept (offered -> accepted, incl. refusals),
--         pickup (accepted -> picked up at the restaurant), last mile (picked up -> delivered).

-- Q1. District scorecard
-- name: q1_district
WITH ranked AS (
  SELECT da_id, total_min,
         ROW_NUMBER() OVER (PARTITION BY da_id ORDER BY total_min) AS rn,
         COUNT(*)     OVER (PARTITION BY da_id)                    AS n
  FROM orders
), p90 AS (
  SELECT da_id, MIN(CASE WHEN rn >= 0.9 * n THEN total_min END) AS p90_minutes FROM ranked GROUP BY da_id
)
SELECT o.da_id                                          AS district,
       CAST(COUNT(*) * 7 / 8 AS INT)                    AS orders_per_week,
       ROUND(100.0 * AVG(o.is_late), 1)                 AS late_pct,
       ROUND(100.0 * AVG(o.late_min > 5), 1)            AS late_over_5min_pct,
       ROUND(AVG(o.promise_min), 1)                     AS avg_promise_min,
       ROUND(AVG(o.total_min), 1)                       AS avg_delivery_min,
       ROUND(p.p90_minutes, 1)                          AS p90_delivery_min,
       ROUND(100.0 * AVG(o.redispatched), 1)            AS redispatched_pct,
       ROUND(AVG(o.wave_orders), 2)                     AS avg_run_size_per_order
FROM orders o JOIN p90 p USING (da_id)
GROUP BY o.da_id
ORDER BY late_pct DESC;

-- Q2. When it breaks: hour of day, weekdays vs weekend
-- name: q2_hour
SELECT hour,
       CAST(SUM(1 - is_weekend) / 6.0 AS INT)                      AS orders_per_weekday,
       CAST(SUM(is_weekend) / 2.0 AS INT)                          AS orders_per_weekend_day,
       ROUND(100.0 * AVG(CASE WHEN is_weekend = 0 THEN is_late END), 1) AS weekday_late_pct,
       ROUND(100.0 * AVG(CASE WHEN is_weekend = 1 THEN is_late END), 1) AS weekend_late_pct,
       ROUND(AVG(promise_min), 1)                                  AS avg_promise_min,
       ROUND(AVG(t_dispatch), 1)                                   AS avg_dispatch_wait_min,
       ROUND(AVG(wave_orders), 2)                                  AS avg_run_size_per_order
FROM orders
WHERE hour BETWEEN 9 AND 23
GROUP BY hour
ORDER BY hour;

-- Q3. Root cause of each late order: the stage with the largest overrun versus on-time orders
--     in the same district and hour (and distance band for the two travel stages)
-- name: q3_root_cause
SELECT root_cause,
       COUNT(*)                                                             AS late_orders,
       ROUND(100.0 * COUNT(*) / (SELECT SUM(is_late) FROM orders), 1)       AS share_of_late_pct,
       ROUND(AVG(late_min), 1)                                              AS avg_minutes_late,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 10 AND 12 THEN 1.0 ELSE 0 END), 1) AS share_at_lunch_pct,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 16 AND 19 THEN 1.0 ELSE 0 END), 1) AS share_at_dinner_pct
FROM orders
WHERE is_late = 1
GROUP BY root_cause
ORDER BY late_orders DESC;

-- Q4. Where the extra minutes go: average stage times, late versus on-time orders
-- name: q4_stages
SELECT CASE is_late WHEN 1 THEN 'late' ELSE 'on time' END AS orders,
       COUNT(*)                          AS n,
       ROUND(AVG(t_dispatch), 1)         AS dispatch_min,
       ROUND(AVG(t_accept), 1)           AS accept_min,
       ROUND(AVG(t_pickup), 1)           AS pickup_min,
       ROUND(AVG(t_lastmile), 1)         AS lastmile_min,
       ROUND(AVG(promise_min), 1)        AS promise_min,
       ROUND(AVG(customer_m)) AS restaurant_to_customer_m,
       ROUND(AVG(wave_orders), 2)        AS avg_run_size_per_order
FROM orders
GROUP BY is_late;

-- Q5. Concentration: share of late orders in the worst district-half-hours (by date)
-- name: q5_concentration
WITH s AS (
  SELECT late, orders,
         ROW_NUMBER() OVER (ORDER BY late DESC)                          AS rnk,
         COUNT(*)     OVER ()                                            AS n,
         SUM(late)    OVER (ORDER BY late DESC ROWS UNBOUNDED PRECEDING) AS cum_late,
         SUM(orders)  OVER (ORDER BY late DESC ROWS UNBOUNDED PRECEDING) AS cum_orders,
         SUM(late)    OVER ()                                            AS total_late,
         SUM(orders)  OVER ()                                            AS total_orders
  FROM slots_by_date
)
SELECT 'district-half-hours' AS unit, ROUND(100.0 * rnk / n) AS worst_pct,
       ROUND(100.0 * cum_late / total_late, 1) AS pct_of_late, ROUND(100.0 * cum_orders / total_orders, 1) AS pct_of_orders
FROM s WHERE rnk IN (CAST(n * 0.05 AS INT), CAST(n * 0.10 AS INT), CAST(n * 0.20 AS INT));

-- Q6. Batching: late rate by orders in the courier's run, raw and like-for-like
--     (like-for-like compares with single-order runs in the same district and hour)
-- name: q6_batching
WITH cell AS (
  SELECT da_id, hour, MIN(wave_orders, 6) AS run_size, COUNT(*) AS n, AVG(is_late) AS late, AVG(t_lastmile) AS lastmile
  FROM orders GROUP BY da_id, hour, MIN(wave_orders, 6)
), base AS (
  SELECT da_id, hour, late AS late1, lastmile AS lastmile1 FROM cell WHERE run_size = 1 AND n >= 20
)
SELECT c.run_size                                           AS orders_in_run,
       SUM(c.n)                                             AS orders,
       ROUND(100.0 * SUM(c.n * c.late) / SUM(c.n), 1)       AS late_pct,
       ROUND(100.0 * SUM(c.n * (c.late - b.late1)) / SUM(c.n), 1) AS extra_late_pts_like_for_like,
       ROUND(SUM(c.n * c.lastmile) / SUM(c.n), 1)           AS lastmile_min,
       ROUND(SUM(c.n * (c.lastmile - b.lastmile1)) / SUM(c.n), 1) AS extra_lastmile_min_like_for_like
FROM cell c JOIN base b USING (da_id, hour)
GROUP BY c.run_size
ORDER BY c.run_size;

-- Q7. Merchants: are slow restaurants a separate bottleneck?
--     Slow = top 10% of merchants (50+ orders) by average pickup overrun.
-- name: q7_merchants
SELECT CASE slow_merchant WHEN 1 THEN 'slowest 10%' ELSE 'other merchants' END AS merchants,
       COUNT(DISTINCT poi_id)                                   AS merchant_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM orders), 1) AS share_of_orders_pct,
       ROUND(100.0 * SUM(is_late) / (SELECT SUM(is_late) FROM orders), 1) AS share_of_late_pct,
       ROUND(100.0 * AVG(is_late), 1)                           AS late_pct,
       ROUND(AVG(t_pickup), 1)                                  AS avg_pickup_min,
       ROUND(AVG(over_pickup), 1)                               AS avg_pickup_overrun_min,
       ROUND(AVG(food_ready_wait), 1)                           AS picked_up_vs_food_ready_min
FROM orders
GROUP BY slow_merchant;

-- Q8. Courier refusals: what does a re-dispatch cost?
-- name: q8_refusals
SELECT CASE redispatched WHEN 1 THEN 'refused at least once' ELSE 'accepted first time' END AS orders,
       COUNT(*)                                   AS n,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM orders), 1) AS share_pct,
       ROUND(100.0 * AVG(is_late), 1)             AS late_pct,
       ROUND(AVG(t_accept), 1)                    AS accept_min,
       ROUND(AVG(total_min), 1)                   AS delivery_min,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 10 AND 12 OR hour BETWEEN 16 AND 19 THEN 1.0 ELSE 0 END), 1) AS share_at_peaks_pct
FROM orders
GROUP BY redispatched;

-- Q9. Supply pressure: how lateness, dispatch wait and last mile respond to courier load
--     Load = orders being carried / couriers on a run, per district-half-hour (Little's law)
-- name: q9_load_response
WITH s AS (
  SELECT *, order_min / courier_min AS load FROM slots_by_date WHERE courier_min >= 30 AND orders >= 10
), b AS (
  SELECT *, CASE WHEN load < 1.25 THEN '< 1.25' WHEN load < 1.5 THEN '1.25-1.5' WHEN load < 2 THEN '1.5-2'
                 WHEN load < 2.5 THEN '2-2.5' WHEN load < 3 THEN '2.5-3' WHEN load < 4 THEN '3-4' ELSE '4+' END AS load_band,
            CASE WHEN load < 1.25 THEN 1 WHEN load < 1.5 THEN 2 WHEN load < 2 THEN 3
                 WHEN load < 2.5 THEN 4 WHEN load < 3 THEN 5 WHEN load < 4 THEN 6 ELSE 7 END AS band_order
  FROM s
)
SELECT load_band,
       COUNT(*)                                          AS half_hours,
       SUM(orders)                                       AS orders,
       ROUND(100.0 * SUM(late) / SUM(orders), 1)         AS late_pct,
       ROUND(SUM(sum_dispatch) / SUM(orders), 1)         AS dispatch_wait_min,
       ROUND(SUM(sum_lastmile) / SUM(orders), 1)         AS lastmile_min,
       ROUND(SUM(sum_promise) / SUM(orders), 1)          AS promise_min
FROM b
GROUP BY load_band, band_order
ORDER BY band_order;

-- Q10. Idle couriers at the lunch peak (24 dispatch snapshots, 11:25-11:30 every day)
-- name: q10_idle_at_peak
SELECT ROUND(AVG(candidates))                         AS candidate_couriers,
       ROUND(AVG(idle))                               AS idle_couriers,
       ROUND(100.0 * SUM(idle) / SUM(candidates), 1)  AS idle_pct,
       ROUND(AVG(orders_waiting))                     AS orders_waiting,
       ROUND(AVG(avg_on_hand), 2)                     AS orders_on_hand_per_candidate
FROM dispatch_snapshots;
