"""Project 2: an agent that runs the tools itself, and a ticket your code can use (structured output)."""
from typing import Literal

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from p1_tools import TOOLS
from shop import MODEL

SYSTEM = ("You are the support assistant of Pedal & Co., a bike shop. When the customer mentions an order id, call "
          "get_order first. When they ask about a product, call check_stock first. Never guess an order's status or a "
          "stock level. Answer in two or three friendly sentences.")


class Ticket(BaseModel):
    """A support ticket the shop's system can file automatically."""
    order_id: str | None = Field(description="The order id if the customer gave one, like A1002")
    category: Literal["order status", "stock", "return or refund", "repair", "other"]
    urgency: Literal["low", "normal", "high"] = Field(description="high if the customer is upset or can't ride")
    summary: str = Field(description="One sentence for the shop staff")


def show(result):
    for m in result["messages"][1:]:
        if m.type == "ai" and m.tool_calls:
            print("   agent asks:", ", ".join(f"{c['name']}({c['args']})" for c in m.tool_calls))
        elif m.type == "tool":
            print(f"   tool says: {m.content[:90]}")
        elif m.type == "ai":
            print(f"   agent: {m.content}")


if __name__ == "__main__":
    agent = create_agent(MODEL, tools=TOOLS, system_prompt=SYSTEM)
    print(f"Model: {MODEL}\n")
    for q in ["Hi, where is my order A1003? I ordered it days ago.",
              "Is the city bike in stock, and how much is it?"]:
        print(f"Customer: {q}")
        show(agent.invoke({"messages": [("human", q)]}))
        print()

    filer = create_agent(MODEL, tools=TOOLS, system_prompt=SYSTEM + " Then file a ticket.", response_format=Ticket)
    q = "My helmet from order A1002 still hasn't arrived and I need it for a race on Saturday!"
    print(f"Customer: {q}")
    out = filer.invoke({"messages": [("human", q)]})
    t = out.get("structured_response")
    print(f"   ticket from response_format: {t!r}")
    if t is None:
        # Small models sometimes answer in words instead of calling the Ticket tool at the end. A second, focused
        # call that does nothing but fill in the ticket is more reliable.
        transcript = "\n".join(f"{m.type}: {m.content}" for m in out["messages"] if m.content)
        extractor = init_chat_model(MODEL, temperature=0).with_structured_output(Ticket)
        t = extractor.invoke([("system", "Fill in a support ticket for this conversation."), ("human", transcript)])
        print(f"   ticket from a separate extraction call: {t!r}")
    print(f"   your code can route it: {'to a person now' if t.urgency == 'high' else 'to the normal queue'}")
