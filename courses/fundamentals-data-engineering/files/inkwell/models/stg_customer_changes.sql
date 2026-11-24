-- Staging: every insert and update of a customer, from change data capture, with proper types.
SELECT change_id, op, CAST(changed_at AS TIMESTAMP) AS changed_at, CAST(customer_id AS BIGINT) AS customer_id,
       name, email, city, CAST(created_at AS TIMESTAMP) AS created_at, CAST(deleted_at AS TIMESTAMP) AS deleted_at
FROM {raw:customer_changes}
