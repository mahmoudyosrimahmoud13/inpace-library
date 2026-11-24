-- depends_on: stg_customer_changes
-- A type 2 slowly changing dimension: one row per version of a customer, valid from..to.
SELECT row_number() OVER (ORDER BY customer_id, change_id) AS customer_key,
       customer_id, name, email, city,
       changed_at AS valid_from,
       coalesce(lead(changed_at) OVER w, TIMESTAMP '9999-12-31') AS valid_to,
       lead(change_id) OVER w IS NULL AS is_current,
       deleted_at IS NOT NULL AS is_deleted
FROM stg_customer_changes
WINDOW w AS (PARTITION BY customer_id ORDER BY change_id)
