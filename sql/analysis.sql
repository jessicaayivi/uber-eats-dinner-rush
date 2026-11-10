-- Dinner Rush on real data: Meituan food-delivery orders, 23 business districts, Mon 17 - Mon 24 Oct 2022 (8 days)
-- Source: github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge (CC BY-NC 4.0), cleaned by src/prepare_meituan.py
-- Tables (data/meituan.db): orders (one row per delivered order), merchants, slots_by_date (district x date x half-hour),
--                           dispatch_snapshots (24 lunch-peak dispatch moments)
-- Late = delivered after the time promised to the customer. Weekly figures = 8-day totals x 7/8.
-- Stages: dispatch (created -> first offered to a courier), accept (offered -> accepted, incl. refusals),
--         pickup (accepted -> picked up at the restaurant), last mile (picked up -> delivered).
--
-- A note on how I read these queries: is_late, redispatched and slow_merchant are 0/1 flags, so AVG() of a flag
-- is simply the share of orders where it is true (AVG(is_late) = the late rate). I use that trick a lot below.

-- Q1. District scorecard
-- name: q1_district
-- One row per district with the numbers an ops manager would check first, worst districts on top.
SELECT da_id                                   AS district,
       COUNT(*) * 7 / 8                        AS orders_per_week,         -- 8 days of data scaled to a 7-day week
       ROUND(100.0 * AVG(is_late), 1)          AS late_pct,                -- is_late is 1 or 0, so AVG = share of late orders
       ROUND(100.0 * AVG(late_min > 5), 1)     AS late_over_5min_pct,      -- (late_min > 5) is also 1 or 0
       ROUND(AVG(promise_min), 1)              AS avg_promise_min,
       ROUND(AVG(total_min), 1)                AS avg_delivery_min,
       ROUND(100.0 * AVG(redispatched), 1)     AS redispatched_pct,        -- refused by a courier at least once
       ROUND(AVG(wave_orders), 2)              AS avg_run_size_per_order   -- orders the courier carried in the same run
FROM orders
GROUP BY da_id
ORDER BY late_pct DESC;

-- Q2. When it breaks: hour of day, weekdays vs weekend
-- name: q2_hour
-- I split weekdays and weekends because Friday-Sunday dinners usually behave differently.
-- My 8 days (Mon 17 - Mon 24 Oct) contain 6 weekdays and 2 weekend days, so I divide by 6 and by 2
-- to get orders for one typical day of each kind.
SELECT hour,
       CAST(SUM(1 - is_weekend) / 6.0 AS INT)                      AS orders_per_weekday,
       CAST(SUM(is_weekend) / 2.0 AS INT)                          AS orders_per_weekend_day,
       ROUND(100.0 * AVG(CASE WHEN is_weekend = 0 THEN is_late END), 1) AS weekday_late_pct,  -- CASE gives NULL on weekends,
       ROUND(100.0 * AVG(CASE WHEN is_weekend = 1 THEN is_late END), 1) AS weekend_late_pct,  -- and AVG ignores NULLs
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
-- The hard part happens before this query, in src/prepare_meituan.py: for every late order I compare each stage
-- (dispatch, accept, pickup, last mile) with the median of ON-TIME orders in the same district and hour, and
-- for the two travel stages also at a similar distance. The stage that ran longest over normal becomes
-- root_cause. Here I just count late orders per cause and check when they happen.
SELECT root_cause,
       COUNT(*)                                                             AS late_orders,
       ROUND(100.0 * COUNT(*) / (SELECT SUM(is_late) FROM orders), 1)       AS share_of_late_pct,  -- out of ALL late orders
       ROUND(AVG(late_min), 1)                                              AS avg_minutes_late,
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 10 AND 12 THEN 1.0 ELSE 0 END), 1) AS share_at_lunch_pct,   -- 10:00-12:59
       ROUND(100.0 * AVG(CASE WHEN hour BETWEEN 16 AND 19 THEN 1.0 ELSE 0 END), 1) AS share_at_dinner_pct   -- 16:00-19:59
FROM orders
WHERE is_late = 1
GROUP BY root_cause
ORDER BY late_orders DESC;

-- Q4. Where the extra minutes go: average stage times, late versus on-time orders
-- name: q4_stages
-- A simple side-by-side: if late orders spend much longer in one stage, that stage is where the time is lost.
-- I also show distance and run size, to check the gap isn't only because late orders travel further.
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
-- Question: are late orders spread everywhere, or packed into a few bad moments?
-- Step 1: rank every district-half-hour from the most late orders to the fewest (1 = the worst).
-- Step 2: for each cut-off (the worst 5%, 10% and 20% of half-hours), add up the late orders and all the orders
--         inside it, and divide by the totals. If 10% of half-hours hold 60% of late orders, they are concentrated.
--         I show the share of all orders too, to check it isn't only because those half-hours are busier.
WITH ranked AS (
  SELECT late, orders,
         ROW_NUMBER() OVER (ORDER BY late DESC) AS rnk,            -- 1 = the half-hour with the most late orders
         COUNT(*)     OVER ()                   AS n_half_hours    -- how many half-hours in total
  FROM slots_by_date
),
cutoffs(worst_pct) AS (VALUES (5), (10), (20))
SELECT c.worst_pct,
       ROUND(100.0 * SUM(CASE WHEN r.rnk <= r.n_half_hours * c.worst_pct / 100 THEN r.late END)   / SUM(r.late), 1)   AS pct_of_late,
       ROUND(100.0 * SUM(CASE WHEN r.rnk <= r.n_half_hours * c.worst_pct / 100 THEN r.orders END) / SUM(r.orders), 1) AS pct_of_orders
FROM ranked r CROSS JOIN cutoffs c   -- every half-hour is checked once against each cut-off
GROUP BY c.worst_pct
ORDER BY c.worst_pct;

-- Q6. Batching: late rate by orders in the courier's run, raw and like-for-like
--     (like-for-like compares with single-order runs in the same district and hour)
-- name: q6_batching
-- The raw late rate by run size is misleading: big runs mostly happen at busy hours in busy districts,
-- which are late anyway. So I compare like for like:
--   1. "cell" = late rate and last-mile time for each district x hour x run size (runs of 6+ grouped as 6);
--   2. "base" = the same for single-order runs, my reference, kept only where I have at least 20 orders;
--   3. for each run size I take the gap to that reference in the SAME district and hour, then average the gaps,
--      weighted by number of orders. The answer: how much later orders get just because the run is bigger.
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
FROM cell c JOIN base b USING (da_id, hour)   -- inner join: a district-hour without a reliable reference is left out
GROUP BY c.run_size
ORDER BY c.run_size;

-- Q7. Merchants: are slow restaurants a separate bottleneck?
--     Slow = top 10% of merchants (50+ orders) by average pickup overrun.
-- name: q7_merchants
-- "Pickup overrun" = how much longer the courier took to collect the food than on-time orders in the same
-- district, hour and distance. I flagged the worst 10% of restaurants (with enough orders to judge them fairly)
-- in prepare_meituan.py. If their share of late orders is bigger than their share of orders, they are a
-- bottleneck of their own, which account managers can work on.
SELECT CASE slow_merchant WHEN 1 THEN 'slowest 10%' ELSE 'other merchants' END AS merchants,
       COUNT(DISTINCT poi_id)                                   AS merchant_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM orders), 1) AS share_of_orders_pct,
       ROUND(100.0 * SUM(is_late) / (SELECT SUM(is_late) FROM orders), 1) AS share_of_late_pct,
       ROUND(100.0 * AVG(is_late), 1)                           AS late_pct,
       ROUND(AVG(t_pickup), 1)                                  AS avg_pickup_min,
       ROUND(AVG(over_pickup), 1)                               AS avg_pickup_overrun_min,
       ROUND(AVG(food_ready_wait), 1)                           AS picked_up_vs_food_ready_min  -- pickup time minus the restaurant's own ready estimate
FROM orders
GROUP BY slow_merchant;

-- Q8. Courier refusals: what does a re-dispatch cost?
-- name: q8_refusals
-- In this data, a refused order gets a new waybill, so "redispatched" = a courier said no at least once.
-- I compare those orders with the ones accepted first time, and check whether refusals cluster at peak hours.
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
-- "Load" is how many orders each busy courier is carrying at the same time, on average. I get it by dividing
-- the minutes orders spent with couriers by the minutes couriers spent on a run, in each district-half-hour
-- (Little's law: work in progress = time spent / time available).
--   1. "s" computes the load and drops tiny half-hours (under 30 courier-minutes or 10 orders), which are too noisy;
--   2. "b" puts each half-hour into a load band, plus a band number so the bands sort in the right order
--      (sorting the text labels would put "4+" in the wrong place);
--   3. then I compare late rate, dispatch wait, last mile and promised time across bands.
-- This shows a link between load and lateness, not proof that one causes the other: that needs a test.
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
       ROUND(100.0 * SUM(late) / SUM(orders), 1)         AS late_pct,          -- weighted by orders, not a plain average of half-hours
       ROUND(SUM(sum_dispatch) / SUM(orders), 1)         AS dispatch_wait_min,
       ROUND(SUM(sum_lastmile) / SUM(orders), 1)         AS lastmile_min,
       ROUND(SUM(sum_promise) / SUM(orders), 1)          AS promise_min
FROM b
GROUP BY load_band, band_order
ORDER BY band_order;

-- Q10. Idle couriers at the lunch peak (24 dispatch snapshots, 11:25-11:30 every day)
-- name: q10_idle_at_peak
-- The data includes 24 "photos" of the dispatch system at lunch peak: every courier who could take an order,
-- and how many orders each was already carrying. "idle" = candidates carrying nothing at that moment.
-- If many couriers are idle while orders wait, the problem is matching and position, not only headcount.
SELECT ROUND(AVG(candidates))                         AS candidate_couriers,
       ROUND(AVG(idle))                               AS idle_couriers,
       ROUND(100.0 * SUM(idle) / SUM(candidates), 1)  AS idle_pct,
       ROUND(AVG(orders_waiting))                     AS orders_waiting,
       ROUND(AVG(avg_on_hand), 2)                     AS orders_on_hand_per_candidate
FROM dispatch_snapshots;
