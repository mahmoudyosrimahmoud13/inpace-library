-- depends_on: fct_sales, dim_date
-- What the owner looks at: one row per day. Cancelled orders don't count as sales.
SELECT d.date_key AS day, d.weekday,
       count(DISTINCT f.order_id) AS orders,
       coalesce(round(sum(f.amount), 2), 0) AS revenue,
       count(DISTINCT f.customer_key) AS customers,
       coalesce(round(sum(f.amount) / nullif(count(DISTINCT f.order_id), 0), 2), 0) AS avg_order_value
FROM dim_date d
LEFT JOIN fct_sales f ON f.date_key = d.date_key AND f.status <> 'cancelled'
GROUP BY 1, 2 ORDER BY 1
