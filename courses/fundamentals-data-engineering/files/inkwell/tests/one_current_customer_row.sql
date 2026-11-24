-- Fails if a customer has zero or several current rows in the type 2 dimension.
SELECT customer_id FROM dim_customer GROUP BY 1 HAVING sum(CAST(is_current AS INTEGER)) <> 1
