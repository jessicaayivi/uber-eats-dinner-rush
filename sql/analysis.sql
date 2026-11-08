-- Uber Eats Belgium: peak supply gap analysis (synthetic data, 4 weeks, Sep-Oct 2026)
-- Table: marketplace_hourly(city, date, dow, hour, is_rain, orders_requested, orders_completed,
--        orders_unfulfilled, orders_late, couriers_online, avg_eta_min, avg_basket_eur)
-- Assumptions: 1 courier completes ~2.1 deliveries per online hour; healthy utilisation <= 85%.

-- Q1. City health scorecard
-- name: q1_city
SELECT city,
       SUM(orders_requested) / 4                                         AS orders_per_week,
       ROUND(100.0 * SUM(orders_unfulfilled) / SUM(orders_requested), 1) AS unfulfilled_pct,
       ROUND(100.0 * SUM(orders_late) / SUM(orders_completed), 1)        AS late_pct,
       ROUND(SUM(avg_eta_min * orders_completed) / SUM(orders_completed), 1) AS avg_eta_min,
       ROUND(SUM(orders_unfulfilled * avg_basket_eur) / 4)               AS lost_gross_bookings_per_week
FROM marketplace_hourly
GROUP BY city
ORDER BY orders_per_week DESC;

-- Q2. Where the network breaks: daypart x weekend x rain
-- name: q2_daypart
WITH tagged AS (
  SELECT *,
         CASE WHEN dow IN ('Friday','Saturday','Sunday') THEN 'Fri-Sun' ELSE 'Mon-Thu' END AS week_part,
         CASE WHEN hour BETWEEN 11 AND 13 THEN 'Lunch 11-14'
              WHEN hour BETWEEN 17 AND 21 THEN 'Dinner 17-22'
              ELSE 'Off-peak' END AS daypart
  FROM marketplace_hourly
)
SELECT week_part, daypart, is_rain,
       SUM(orders_requested)                                             AS orders,
       ROUND(1.0 * SUM(orders_requested) / (SUM(couriers_online) * 2.1), 2) AS utilisation,
       ROUND(100.0 * SUM(orders_unfulfilled) / SUM(orders_requested), 1) AS unfulfilled_pct,
       ROUND(100.0 * SUM(orders_late) / SUM(orders_completed), 1)        AS late_pct,
       SUM(orders_unfulfilled)                                           AS lost_orders
FROM tagged
GROUP BY week_part, daypart, is_rain
ORDER BY lost_orders DESC;

-- Q3. Concentration: what share of lost orders sits in the most stressed hours?
-- name: q3_concentration
WITH h AS (
  SELECT city, date, hour, orders_unfulfilled,
         1.0 * orders_requested / (couriers_online * 2.1) AS utilisation
  FROM marketplace_hourly
), ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (ORDER BY orders_unfulfilled DESC)                 AS rnk,
         COUNT(*)     OVER ()                                                 AS n_hours,
         SUM(orders_unfulfilled) OVER (ORDER BY orders_unfulfilled DESC
                                       ROWS UNBOUNDED PRECEDING)              AS cum_lost,
         SUM(orders_unfulfilled) OVER ()                                      AS total_lost
  FROM h
)
SELECT ROUND(100.0 * rnk / n_hours) AS pct_of_city_hours,
       ROUND(100.0 * cum_lost / total_lost, 1) AS pct_of_lost_orders
FROM ranked
WHERE rnk IN (CAST(n_hours * 0.05 AS INT), CAST(n_hours * 0.10 AS INT),
              CAST(n_hours * 0.15 AS INT), CAST(n_hours * 0.20 AS INT));

-- Q4. Courier-hour gap: extra couriers needed to bring stressed hours back to 85% utilisation
-- name: q4_gap
WITH need AS (
  SELECT city, dow, hour, is_rain, orders_requested, orders_unfulfilled, couriers_online,
         MAX(0, CAST(orders_requested / (2.1 * 0.85) + 0.999 AS INT) - couriers_online) AS courier_gap
  FROM marketplace_hourly
)
SELECT city,
       SUM(courier_gap) / 4                                                AS gap_courier_hours_per_week,
       SUM(CASE WHEN courier_gap > 0 THEN 1 ELSE 0 END) / 4                AS stressed_hours_per_week,
       ROUND(100.0 * SUM(CASE WHEN courier_gap > 0 THEN orders_unfulfilled END)
             / SUM(orders_unfulfilled), 1)                                 AS pct_lost_in_stressed_hours,
       SUM(CASE WHEN courier_gap > 0 THEN orders_unfulfilled ELSE 0 END) / 4 AS lost_orders_stressed_per_week
FROM need
GROUP BY city
ORDER BY gap_courier_hours_per_week DESC;

-- Q5. Rain uplift at dinner (forecastable trigger for incentives)
-- name: q5_rain
SELECT is_rain,
       ROUND(AVG(orders_requested), 1) AS avg_orders_per_city_hour,
       ROUND(AVG(couriers_online), 1)  AS avg_couriers_per_city_hour,
       ROUND(100.0 * SUM(orders_unfulfilled) / SUM(orders_requested), 1) AS unfulfilled_pct
FROM marketplace_hourly
WHERE hour BETWEEN 17 AND 21
GROUP BY is_rain;
