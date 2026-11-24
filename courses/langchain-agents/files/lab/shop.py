"""Pedal & Co., a small bike shop: its orders and stock (SQLite) and its policies (text). Every project uses this.
Run it once to create shop.db:  python shop.py"""
import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "shop.db"
MODEL = os.environ.get("PEDAL_MODEL", "ollama:qwen3")   # any "provider:model" that supports tool calling

PRODUCTS = [
    ("CITY-7", "City bike, 7 gears", 549.00, 4),
    ("GRAVEL-2", "Gravel bike, carbon fork", 1299.00, 0),
    ("HELMET-M", "Helmet, size M", 59.00, 12),
    ("LOCK-U", "U-lock with cable", 39.00, 25),
    ("LIGHTS", "Front and rear lights", 34.00, 3),
]
ORDERS = [  # id, customer, email, product, status, placed, delivered
    ("A1001", "Sara Ali", "sara.ali@example.com", "CITY-7", "delivered", "2026-11-02", "2026-11-06"),
    ("A1002", "Omar Hassan", "omar.h@example.com", "HELMET-M", "shipped", "2026-11-18", None),
    ("A1003", "Lina Park", "lina.park@example.com", "GRAVEL-2", "waiting for stock", "2026-11-20", None),
    ("A1004", "Ben Cole", "ben.cole@example.com", "LIGHTS", "delivered", "2026-09-01", "2026-09-04"),
]
POLICIES = {
    "returns": "Returns: unused items can be returned within 30 days of delivery for a full refund. Bikes that have "
               "been ridden can be returned within 14 days for a refund minus a 10% restocking fee. Helmets can't be "
               "returned once worn, for hygiene reasons.",
    "shipping": "Shipping: orders ship within 2 working days if the item is in stock. Delivery takes 3 to 5 working "
                "days. Bikes arrive 90% assembled; we include the tools to finish. Free shipping over $100.",
    "warranty": "Warranty: bike frames have a 5-year warranty against manufacturing defects; parts and accessories "
                "have 1 year. Wear and tear (tyres, brake pads, chains) isn't covered.",
    "repairs": "Repairs: our workshop is open Tuesday to Saturday, 9 am to 6 pm. A basic service costs $49 and takes "
               "one day. Book by phone or in the shop; no appointment needed for flat tyres.",
    "price-match": "Price match: if you find the same new item cheaper at a local shop within 14 days of buying it, "
                   "we refund the difference. Online marketplaces and second-hand items don't count.",
}


def connect():
    return sqlite3.connect(DB)


def create():
    DB.unlink(missing_ok=True)
    with connect() as db:
        db.execute("CREATE TABLE products (sku TEXT PRIMARY KEY, name TEXT, price REAL, stock INTEGER)")
        db.execute("CREATE TABLE orders (id TEXT PRIMARY KEY, customer TEXT, email TEXT, sku TEXT, status TEXT, "
                   "placed TEXT, delivered TEXT)")
        db.execute("CREATE TABLE refunds (order_id TEXT, amount REAL, reason TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP)")
        db.executemany("INSERT INTO products VALUES (?,?,?,?)", PRODUCTS)
        db.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", ORDERS)


if __name__ == "__main__":
    create()
    print(f"Created {DB.name}: {len(PRODUCTS)} products, {len(ORDERS)} orders, {len(POLICIES)} policies")
