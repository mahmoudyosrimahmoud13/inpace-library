-- Staging: order lines never change, but a re-run batch could land them twice.
SELECT DISTINCT order_id, book_id, qty, unit_price FROM {raw:order_lines}
