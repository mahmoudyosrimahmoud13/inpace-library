"""Project 1: give the model the shop's tools, and see which ones it asks for."""
import json
import sqlite3

from langchain.chat_models import init_chat_model
from langchain.tools import tool

from shop import MODEL, connect


@tool
def get_order(order_id: str) -> str:
    """Look up one order by its id (like A1002): the product, its status, and when it was placed and delivered."""
    with connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT o.*, p.name AS product, p.price FROM orders o JOIN products p ON p.sku = o.sku "
                         "WHERE o.id = ?", (order_id.strip().upper(),)).fetchone()
    if not row:
        return f"No order {order_id}. Order ids look like A1001."
    r = dict(row)
    return json.dumps({k: r[k] for k in ("id", "product", "price", "status", "placed", "delivered")})


@tool
def check_stock(product: str) -> str:
    """How many of a product are in stock and its price. `product` can be part of the name, like "helmet"."""
    with connect() as db:
        rows = db.execute("SELECT name, price, stock FROM products WHERE lower(name) LIKE ? OR lower(sku) LIKE ?",
                          (f"%{product.lower()}%", f"%{product.lower()}%")).fetchall()
    if not rows:
        return f"We don't sell anything called {product!r}."
    return json.dumps([{"name": n, "price": p, "in_stock": s} for n, p, s in rows])


TOOLS = [get_order, check_stock]

if __name__ == "__main__":
    model = init_chat_model(MODEL, temperature=0)
    print(f"Model: {MODEL}\n")
    print("1. The tools, as the model sees them:")
    for t in TOOLS:
        print(f"   {t.name}{list(t.args)}: {t.description[:70]}...")

    with_tools = model.bind_tools(TOOLS)
    print("\n2. Which tool does the model ask for?")
    for q in ["Where is my order A1002?", "Do you have helmets in stock?",
              "What are your opening hours?"]:
        msg = with_tools.invoke([("system", "You help customers of Pedal & Co., a bike shop."), ("human", q)])
        asked = [f"{c['name']}({c['args']})" for c in msg.tool_calls] or ["no tool"]
        print(f"   {q!r} -> {', '.join(asked)}")
        for c in msg.tool_calls:                         # the model only asks; your code runs the tool
            result = {t.name: t for t in TOOLS}[c["name"]].invoke(c["args"])
            print(f"      ran it: {result}")
