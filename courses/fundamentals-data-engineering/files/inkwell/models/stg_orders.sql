-- Staging: one row per order, its LATEST version. Ingestion kept every version it saw (project 7).
SELECT order_id, customer_id, status,
       CAST(created_at AS TIMESTAMP) AS created_at, CAST(updated_at AS TIMESTAMP) AS updated_at
FROM {raw:orders}
QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY updated_at DESC) = 1
