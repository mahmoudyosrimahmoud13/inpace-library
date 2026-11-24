-- depends_on: stg_orders
-- One row per day from the first order to the last: every day exists, even days with no sales.
SELECT CAST(d AS DATE) AS date_key, year(d) AS year, month(d) AS month, dayname(d) AS weekday,
       dayofweek(d) IN (0, 6) AS is_weekend
FROM range((SELECT CAST(min(created_at) AS DATE) FROM stg_orders),
           (SELECT CAST(max(created_at) AS DATE) FROM stg_orders) + 1, INTERVAL 1 DAY) t(d)
