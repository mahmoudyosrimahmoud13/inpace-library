-- Fails on any status the business didn't define.
SELECT DISTINCT status FROM stg_orders WHERE status NOT IN ('placed', 'shipped', 'delivered', 'cancelled')
