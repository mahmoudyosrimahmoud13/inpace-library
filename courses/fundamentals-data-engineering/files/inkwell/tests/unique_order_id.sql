-- Fails if an order appears twice in staging.
SELECT order_id, count(*) FROM stg_orders GROUP BY 1 HAVING count(*) > 1
