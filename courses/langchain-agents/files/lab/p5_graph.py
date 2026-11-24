"""Project 5: the support desk as a LangGraph workflow. Steps that must always happen (look up the order, read the
policy) are plain code; the model only classifies and writes. Then tests and a small evaluation."""
import re
import time
from typing import Literal, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from p1_tools import get_order
from p4_memory_rag import search_policies
from shop import MODEL

ORDER_ID = re.compile(r"\bA\d{4}\b", re.I)


class Route(BaseModel):
    category: Literal["order status", "return or refund", "policy question", "other"]


class Desk(TypedDict, total=False):
    question: str
    category: str
    facts: str
    answer: str
    handoff: bool


def classify(state: Desk) -> Desk:
    model = init_chat_model(MODEL, temperature=0).with_structured_output(Route)
    r = model.invoke([("system", "Classify the customer's message for a bike shop's support desk."),
                      ("human", state["question"])])
    return {"category": r.category}


def gather(state: Desk) -> Desk:
    """Plain code, not the model's choice: always look up the order and always read the matching policies."""
    facts = []
    m = ORDER_ID.search(state["question"])
    if m:
        facts.append("Order: " + get_order.invoke({"order_id": m.group(0)}))
    if state["category"] in ("return or refund", "policy question"):
        facts.append("Policies:\n" + search_policies.invoke({"question": state["question"]}))
    return {"facts": "\n".join(facts)}


def write(state: Desk) -> Desk:
    model = init_chat_model(MODEL, temperature=0)
    reply = model.invoke([("system", "You are Pedal & Co.'s support assistant. Answer in two or three sentences, "
                                     "using only these facts. Today is 2026-11-24.\n" + state["facts"]),
                          ("human", state["question"])])
    return {"answer": reply.content}


def handoff(state: Desk) -> Desk:
    return {"handoff": True, "answer": "Thanks! A member of our team will reply within one working day."}


def route(state: Desk) -> str:
    return "handoff" if state["category"] == "other" else "gather"


def build(classifier=classify, writer=write):
    g = StateGraph(Desk)
    g.add_node("classify", classifier)
    g.add_node("gather", gather)
    g.add_node("write", writer)
    g.add_node("handoff", handoff)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route, ["gather", "handoff"])
    g.add_edge("gather", "write")
    g.add_edge("write", END)
    g.add_edge("handoff", END)
    return g.compile()


if __name__ == "__main__":
    desk = build()
    print(f"Model: {MODEL}\n")
    edges = [f"{e.source} -> {e.target}" + (" (if)" if e.conditional else "") for e in desk.get_graph().edges]
    print("The graph:", "; ".join(edges))
    cases = [("Can I still return order A1001? I've ridden it twice.", "return or refund", ["14 days", "10%"]),
             ("Where is my order A1003?", "order status", ["waiting for stock"]),
             ("Can I return a helmet I wore once?", "policy question", ["can't be returned", "hygiene"]),
             ("Do you sponsor local cycling clubs?", "other", [])]
    passed = 0
    for q, want, must in cases:
        t = time.perf_counter()
        out = desk.invoke({"question": q})
        ok_route = out["category"] == want
        ok_fact = all(w.lower() in out.get("facts", "").lower() for w in must)
        passed += ok_route and ok_fact
        print(f"\nCustomer: {q}\n   route: {out['category']} ({'ok' if ok_route else 'expected ' + want})   "
              f"facts found: {'ok' if ok_fact else 'MISSING'}   {time.perf_counter() - t:.0f} s")
        print(f"   answer: {out['answer']}")
    print(f"\nEvaluation: {passed} of {len(cases)} questions routed right with the right facts in front of the model")
