"""Project 9: data modeling. The same business question on three models of the same data.

Question: "Revenue by customer city and book genre."

1. NORMALIZED (3NF), the shape the shop's app uses: orders, order_lines, customers, books. Each fact once.
2. STAR SCHEMA (Kimball): one fact table (a row per order line) and dimensions (customer, book, date).
   The customer dimension is a TYPE 2 slowly changing dimension: when a customer moves city we add a new row
   with valid_from / valid_to, so a sale stays with the city the customer lived in WHEN they bought.
3. ONE BIG TABLE (wide, denormalized): everything joined once, easy to query, heavy to change.

The model is built in a scratch database, p09.duckdb. Project 10 turns it into a proper, tested pipeline.

Run:  python p09_model.py
"""
import duckdb

from common import DATA, LAKE, need

RAW = LAKE / "raw"


def raw(table: str) -> str:
    return f"read_parquet('{(RAW / table).as_posix()}/*/*.parquet', union_by_name = true)"


if __name__ == "__main__":
    need(RAW / "orders", "p07_ingest.py")
    con = duckdb.connect(str(DATA / "p09.duckdb"))

    # --- 1. Normalized: rebuild the source tables (latest version of each row) ---------------------------
    con.execute(f"""CREATE OR REPLACE TABLE orders AS
        SELECT * EXCLUDE (rn) FROM (SELECT *, row_number() OVER (PARTITION BY order_id ORDER BY updated_at DESC) rn
                                    FROM {raw('orders')}) WHERE rn = 1""")
    con.execute(f"CREATE OR REPLACE TABLE order_lines AS SELECT DISTINCT order_id, book_id, qty, unit_price FROM {raw('order_lines')}")
    con.execute(f"""CREATE OR REPLACE TABLE books AS SELECT book_id, title, author, genre, price FROM {raw('books')}
                    QUALIFY row_number() OVER (PARTITION BY book_id ORDER BY _batch_id DESC) = 1""")
    con.execute(f"""CREATE OR REPLACE TABLE customers AS
        SELECT customer_id, name, email, city, created_at, deleted_at FROM {raw('customer_changes')}
        QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY change_id DESC) = 1""")
    q_norm = """SELECT c.city, b.genre, round(sum(l.qty * l.unit_price), 2) AS revenue
                FROM orders o JOIN customers c USING (customer_id) JOIN order_lines l USING (order_id)
                JOIN books b USING (book_id) WHERE o.status <> 'cancelled' GROUP BY 1, 2"""

    # --- 2. Star schema ---------------------------------------------------------------------------------
    con.execute(f"""CREATE OR REPLACE TABLE dim_customer AS
        SELECT row_number() OVER (ORDER BY customer_id, change_id) AS customer_key,   -- surrogate key
               customer_id, name, city,
               CAST(changed_at AS TIMESTAMP) AS valid_from,
               coalesce(lead(CAST(changed_at AS TIMESTAMP)) OVER (PARTITION BY customer_id ORDER BY change_id),
                        TIMESTAMP '9999-12-31') AS valid_to,
               lead(change_id) OVER (PARTITION BY customer_id ORDER BY change_id) IS NULL AS is_current
        FROM {raw('customer_changes')}""")
    con.execute("CREATE OR REPLACE TABLE dim_book AS SELECT book_id AS book_key, title, author, genre FROM books")
    con.execute("""CREATE OR REPLACE TABLE dim_date AS
        SELECT CAST(d AS DATE) AS date_key, year(d) AS year, month(d) AS month, dayname(d) AS weekday,
               dayofweek(d) IN (0, 6) AS is_weekend
        FROM range(DATE '2026-01-01', DATE '2027-01-01', INTERVAL 1 DAY) t(d)""")
    con.execute("""CREATE OR REPLACE TABLE fact_sales AS
        SELECT o.order_id, l.book_id AS book_key, dc.customer_key, CAST(o.created_at AS DATE) AS date_key,
               l.qty, l.unit_price, l.qty * l.unit_price AS amount, o.status
        FROM orders o JOIN order_lines l USING (order_id)
        JOIN dim_customer dc ON dc.customer_id = o.customer_id
             AND CAST(o.created_at AS TIMESTAMP) >= dc.valid_from AND CAST(o.created_at AS TIMESTAMP) < dc.valid_to""")
    q_star = """SELECT c.city, b.genre, round(sum(f.amount), 2) AS revenue
                FROM fact_sales f JOIN dim_customer c USING (customer_key) JOIN dim_book b USING (book_key)
                WHERE f.status <> 'cancelled' GROUP BY 1, 2"""

    # --- 3. One big table ---------------------------------------------------------------------------------
    con.execute("""CREATE OR REPLACE TABLE obt_sales AS
        SELECT f.*, c.customer_id, c.name AS customer_name, c.city, b.title, b.author, b.genre, d.weekday, d.is_weekend
        FROM fact_sales f JOIN dim_customer c USING (customer_key) JOIN dim_book b USING (book_key)
        JOIN dim_date d USING (date_key)""")
    q_obt = "SELECT city, genre, round(sum(amount), 2) AS revenue FROM obt_sales WHERE status <> 'cancelled' GROUP BY 1, 2"

    totals = {name: con.execute(f"SELECT round(sum(revenue), 2) FROM ({q})").fetchone()[0]
              for name, q in [("normalized", q_norm), ("star", q_star), ("one big table", q_obt)]}
    print("Total revenue, three models:", totals, "-> the same, as it should be")

    # Where the models disagree: the city. Normalized uses the city the customer has TODAY.
    diff = con.execute(f"""
        SELECT n.city, n.genre, n.revenue AS by_city_today, coalesce(s.revenue, 0) AS by_city_when_bought
        FROM ({q_norm}) n LEFT JOIN ({q_star}) s USING (city, genre)
        WHERE n.revenue <> coalesce(s.revenue, 0) ORDER BY abs(n.revenue - coalesce(s.revenue, 0)) DESC LIMIT 5""").fetchall()
    print("\nRevenue by city and genre, where 'city today' and 'city when they bought' disagree:")
    for city, genre, now, then in diff:
        print(f"  {city:11} {genre:10} today: {now:8.2f}   when bought: {then:8.2f}")

    moved = con.execute(f"""SELECT customer_id, list(city || CASE WHEN deleted_at IS NOT NULL THEN ' (closed)' ELSE '' END
                                                  ORDER BY change_id)
                            FROM {raw('customer_changes')} GROUP BY 1 HAVING count(DISTINCT city) > 1
                            ORDER BY customer_id LIMIT 3""").fetchall()
    print("\nType 2 history for customers who moved:")
    for cid, cities in moved:
        print(f"  customer {cid}: " + " -> ".join(cities))
    for t in ("fact_sales", "dim_customer", "dim_book", "dim_date", "obt_sales"):
        print(f"  {t:13} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:6} rows")
