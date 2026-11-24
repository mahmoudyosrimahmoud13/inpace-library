"""Project 3: middleware. A refund tool that waits for a person to approve it, customers' emails hidden before
anything reaches the model, and a limit on model calls so a confused agent can't loop forever."""
import json
import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, ModelCallLimitMiddleware, PIIMiddleware
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from p1_tools import TOOLS
from p2_agent import SYSTEM
from shop import MODEL, connect


@tool
def refund(order_id: str, amount: float, reason: str) -> str:
    """Refund money for an order. Only after checking the order and the returns policy."""
    with connect() as db:
        db.execute("INSERT INTO refunds (order_id, amount, reason) VALUES (?, ?, ?)", (order_id, amount, reason))
    return f"Refunded ${amount:.2f} for {order_id}."


def refunds():
    with connect() as db:
        return db.execute("SELECT order_id, amount, reason FROM refunds").fetchall()


def build():
    return create_agent(
        MODEL, tools=TOOLS + [refund], checkpointer=InMemorySaver(),
        system_prompt=SYSTEM + " If the customer asks for a refund for an order, look it up, then call refund.",
        middleware=[
            PIIMiddleware("email", strategy="redact", apply_to_input=True),       # emails never reach the model
            ModelCallLimitMiddleware(run_limit=6, exit_behavior="end"),          # at most 6 model calls per question
            HumanInTheLoopMiddleware(interrupt_on={"refund": True}),             # refunds wait for a person
        ])


if __name__ == "__main__":
    with connect() as db:
        db.execute("DELETE FROM refunds")
    agent = build()
    print(f"Model: {MODEL}\n")
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    q = "I'm ben.cole@example.com. Please refund my order A1004, the lights stopped working."
    print(f"Customer: {q}")
    out = agent.invoke({"messages": [("human", q)]}, cfg)
    print(f"   what the model saw: {out['messages'][0].content!r}")
    for m in out["messages"][1:]:
        if m.type == "ai" and m.tool_calls:
            print("   agent asks:", ", ".join(f"{c['name']}({c['args']})" for c in m.tool_calls))
        elif m.type == "tool":
            print(f"   tool says: {m.content[:90]}")
    pause = out.get("__interrupt__")
    if pause:
        req = pause[0].value["action_requests"][0]
        print(f"\n   PAUSED for approval: {req['name']}({json.dumps(req['args'])})")
        print(f"   refunds in the database so far: {refunds()}")
        print("   A person reads it: the lights were delivered on 4 September, more than 30 days ago. Rejected.")
        out = agent.invoke(Command(resume={"decisions": [
            {"type": "reject", "message": "Outside the 30-day return window. Offer a warranty repair instead."}]}), cfg)
        print(f"   agent: {out['messages'][-1].content}")
        print(f"   refunds in the database after: {refunds()}")
    else:
        print("   (the model didn't ask for a refund this time; run it again or try a bigger model)")
