-- depends_on: stg_orders, stg_order_lines, dim_customer
-- Grain: one row per order line. The customer version is the one valid when the order was placed.
SELECT o.order_id, l.book_id AS book_key, c.customer_key, CAST(o.created_at AS DATE) AS date_key,
       o.status, l.qty, l.unit_price, l.qty * l.unit_price AS amount
FROM stg_orders o
JOIN stg_order_lines l USING (order_id)
LEFT JOIN dim_customer c ON c.customer_id = o.customer_id
     AND o.created_at >= c.valid_from AND o.created_at < c.valid_to
