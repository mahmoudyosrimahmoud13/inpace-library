-- Staging: the newest snapshot of the books table.
SELECT book_id, title, author, genre, price FROM {raw:books}
QUALIFY row_number() OVER (PARTITION BY book_id ORDER BY _batch_id DESC) = 1
