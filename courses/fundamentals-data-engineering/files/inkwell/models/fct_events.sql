-- depends_on: stg_events
-- materialized: incremental, unique_key: event_id
-- Only events we haven't stored yet are added: re-running adds nothing.
SELECT event_id, event_type, customer_id, event_time, order_id, arrived_late FROM stg_events
