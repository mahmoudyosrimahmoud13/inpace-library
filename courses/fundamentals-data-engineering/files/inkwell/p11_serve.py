"""Project 11: serving data to the three kinds of users the chapter describes.

1. A METRICS LAYER: each business metric is defined ONCE (revenue, orders, average order value...), and any
   report asks for "metric by dimension". Two dashboards can no longer show two different revenues.
2. ANALYTICS: a one-file HTML dashboard for the owner (serve/dashboard.html), built only from the metrics layer.
3. MACHINE LEARNING: a feature table for a "will this customer buy again?" model (serve/customer_features.csv),
   with POINT-IN-TIME correctness: features use only data from before the cutoff day, the label only data after.
4. REVERSE ETL: a list of customers to win back, in the format the shop's email tool imports
   (serve/crm_winback.csv). Data goes back into an operational system, where people act on it.

Run:  python p11_serve.py
"""
import csv
import html

import duckdb

from common import SERVE, WAREHOUSE, log, need

# ---- 1. The metrics layer ---------------------------------------------------------------------------------
SALES = """fct_sales f JOIN dim_customer c USING (customer_key) JOIN dim_book b USING (book_key)
           JOIN dim_date d USING (date_key)"""
METRICS = {
    "revenue": {"sql": "round(sum(f.amount) FILTER (WHERE f.status <> 'cancelled'), 2)",
                "about": "Money from order lines, not counting cancelled orders."},
    "orders": {"sql": "count(DISTINCT f.order_id) FILTER (WHERE f.status <> 'cancelled')",
               "about": "Orders that weren't cancelled."},
    "avg_order_value": {"sql": "round(sum(f.amount) FILTER (WHERE f.status <> 'cancelled') / "
                               "nullif(count(DISTINCT f.order_id) FILTER (WHERE f.status <> 'cancelled'), 0), 2)",
                        "about": "Revenue divided by orders."},
    "buyers": {"sql": "count(DISTINCT c.customer_id) FILTER (WHERE f.status <> 'cancelled')",
               "about": "Different customers with at least one order that wasn't cancelled."},
}
DIMENSIONS = {"day": "d.date_key", "weekday": "d.weekday", "city": "c.city", "genre": "b.genre"}


def metric_query(metrics: list, by: str) -> str:
    cols = ", ".join(f"{METRICS[m]['sql']} AS {m}" for m in metrics)
    return f"SELECT {DIMENSIONS[by]} AS {by}, {cols} FROM {SALES} GROUP BY 1 ORDER BY 1"


def bars(rows: list, value_index: int, width: int = 420) -> str:
    """A small horizontal bar chart as inline SVG: no libraries, opens anywhere."""
    top = max((r[value_index] or 0) for r in rows) or 1
    out = [f'<svg width="{width + 160}" height="{len(rows) * 26}" role="img">']
    for i, r in enumerate(rows):
        w = (r[value_index] or 0) / top * width
        out.append(f'<text x="0" y="{i * 26 + 17}" font-size="13">{html.escape(str(r[0]))}</text>'
                   f'<rect x="100" y="{i * 26 + 4}" width="{w:.0f}" height="18" fill="#3b6ea8"/>'
                   f'<text x="{106 + w:.0f}" y="{i * 26 + 17}" font-size="12">{r[value_index]}</text>')
    return "".join(out) + "</svg>"


if __name__ == "__main__":
    need(WAREHOUSE, "p10_transform.py")
    SERVE.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE), read_only=True)

    # ---- 2. Analytics: the dashboard -----------------------------------------------------------------------
    by_day = con.execute(metric_query(["revenue", "orders", "avg_order_value", "buyers"], "day")).fetchall()
    by_genre = con.execute(metric_query(["revenue"], "genre")).fetchall()
    by_city = con.execute(metric_query(["revenue", "buyers"], "city")).fetchall()
    total = con.execute(f"SELECT {METRICS['revenue']['sql']}, {METRICS['orders']['sql']} FROM {SALES}").fetchone()
    table = "".join(f"<tr><td>{d}</td><td>{r}</td><td>{o}</td><td>{a}</td><td>{b}</td></tr>" for d, r, o, a, b in by_day)
    defs = "".join(f"<li><b>{m}</b>: {html.escape(v['about'])}</li>" for m, v in METRICS.items())
    page = f"""<!doctype html><meta charset="utf-8"><title>Inkwell Books: sales</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #ddd;padding:4px 10px;text-align:right}}</style>
<h1>Inkwell Books: sales</h1><p><b>{total[0]}</b> revenue from <b>{total[1]}</b> orders.</p>
<h2>Revenue by day</h2>{bars(by_day, 1)}
<h2>Revenue by genre</h2>{bars(by_genre, 1)}
<h2>Revenue by customer city (city at the time of the order)</h2>{bars(by_city, 1)}
<h2>Every day</h2><table><tr><th>day</th><th>revenue</th><th>orders</th><th>avg order</th><th>buyers</th></tr>{table}</table>
<h2>What the numbers mean</h2><ul>{defs}</ul>"""
    (SERVE / "dashboard.html").write_text(page, encoding="utf-8")

    # ---- 3. Machine learning: point-in-time features --------------------------------------------------------
    cutoff = con.execute("SELECT max(date_key) - 2 FROM fct_sales").fetchone()[0]   # keep 2 days to see the future
    feats = con.execute(f"""
        WITH past AS (SELECT c.customer_id, f.order_id, f.date_key, f.amount, b.genre
                      FROM {SALES} WHERE f.status <> 'cancelled' AND f.date_key < DATE '{cutoff}'),
             future AS (SELECT DISTINCT c.customer_id FROM {SALES}
                        WHERE f.status <> 'cancelled' AND f.date_key >= DATE '{cutoff}')
        SELECT p.customer_id,
               DATE '{cutoff}' - max(p.date_key) AS days_since_last_order,   -- recency
               count(DISTINCT p.order_id) AS orders_before,                     -- frequency
               round(sum(p.amount), 2) AS spent_before,                         -- monetary
               mode(p.genre) AS favourite_genre,
               (p.customer_id IN (SELECT customer_id FROM future)) AS label_bought_again
        FROM past p GROUP BY p.customer_id ORDER BY p.customer_id""").fetchall()
    with open(SERVE / "customer_features.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "days_since_last_order", "orders_before", "spent_before", "favourite_genre",
                    "label_bought_again"])
        w.writerows(feats)

    # ---- 4. Reverse ETL: back into the email tool ------------------------------------------------------------
    winback = con.execute(f"""
        SELECT now.email, split_part(now.name, ' ', 1) AS first_name, max(f.date_key) AS last_order,
               count(DISTINCT f.order_id) AS orders, mode(b.genre) AS suggest_genre
        FROM {SALES}
        JOIN dim_customer now ON now.customer_id = c.customer_id AND now.is_current   -- today's email address
        WHERE f.status <> 'cancelled' AND NOT now.is_deleted                          -- never email closed accounts
        GROUP BY 1, 2
        HAVING max(f.date_key) <= (SELECT max(date_key) - 3 FROM fct_sales)
        ORDER BY orders DESC""").fetchall()
    with open(SERVE / "crm_winback.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Email", "First Name", "Last Order", "Orders", "Suggested Genre"])  # the tool's own column names
        w.writerows(winback)

    log("p11", "served", dashboard_days=len(by_day), feature_rows=len(feats), winback=len(winback))
    print(f"Open {SERVE.name}/dashboard.html in your browser.")
    print(f"Features as of {cutoff}: {len(feats)} customers, {sum(1 for r in feats if r[-1])} bought again later.")
