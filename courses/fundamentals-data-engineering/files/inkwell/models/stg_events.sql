-- Staging: one row per event (duplicates removed), with a flag for events that arrived late.
SELECT event_id, event_type, customer_id, event_time, order_id,
       CAST(event_time AS DATE) < CAST(replace(replace(_source_file, 'events-', ''), '.jsonl', '') AS DATE) AS arrived_late
FROM {raw:events}
QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY _ingested_at) = 1
