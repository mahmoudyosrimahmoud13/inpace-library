-- Referential integrity: every sale points to a book we know.
SELECT f.* FROM fct_sales f LEFT JOIN dim_book b USING (book_key) WHERE b.book_key IS NULL
