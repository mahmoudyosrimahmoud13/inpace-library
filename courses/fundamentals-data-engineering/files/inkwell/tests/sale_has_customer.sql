-- Fails if a sale found no customer version (the order is older than the customer: a source or join bug).
SELECT * FROM fct_sales WHERE customer_key IS NULL
