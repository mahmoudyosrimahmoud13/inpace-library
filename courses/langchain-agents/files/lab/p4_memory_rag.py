"""Project 4: memory (a conversation that continues) and answers from the shop's policies (retrieval as a tool)."""
import re
import uuid

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from p1_tools import TOOLS
from p2_agent import SYSTEM
from shop import MODEL, POLICIES

WORDS = re.compile(r"[a-z]+")


@tool
def search_policies(question: str) -> str:
    """Search the shop's policies (returns, shipping, warranty, repairs, price match). Use it for any question about
    rules, times or prices of services, and quote what it returns."""
    q = set(WORDS.findall(question.lower())) - {"the", "a", "can", "i", "my", "do", "you", "is", "it", "to", "of"}
    scored = sorted(POLICIES.items(), key=lambda kv: -len(q & set(WORDS.findall(kv[1].lower()))))
    return "\n\n".join(f"[{name}] {text}" for name, text in scored[:2])


def build():
    return create_agent(MODEL, tools=TOOLS + [search_policies], checkpointer=InMemorySaver(),
                        system_prompt=SYSTEM + " For questions about rules (returns, shipping, warranty, repairs), "
                                               "call search_policies and answer only from what it returns.")


def ask(agent, cfg, q):
    out = agent.invoke({"messages": [("human", q)]}, cfg)
    new = out["messages"][len(out["messages"]) - 1 - next(i for i, m in enumerate(reversed(out["messages"])) if m.type == "human"):]
    for m in new[1:]:
        if m.type == "ai" and m.tool_calls:
            print("   agent asks:", ", ".join(f"{c['name']}({c['args']})" for c in m.tool_calls))
        elif m.type == "ai":
            print(f"   agent: {m.content}")
    return out


if __name__ == "__main__":
    agent = build()
    print(f"Model: {MODEL}\n")
    print(f"search_policies('can I return a helmet') ->\n   {search_policies.invoke({'question': 'can I return a helmet'})[:150]}...\n")
    mine = {"configurable": {"thread_id": str(uuid.uuid4())}}
    for q in ["Hi, my order is A1001. What did I buy?",
              "Can I still return it? I've ridden it twice.",
              "What was my order number again?"]:
        print(f"Customer: {q}")
        out = ask(agent, mine, q)
    print(f"\n   messages kept in this conversation: {len(out['messages'])}")
    other = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("A different customer (a new thread): What was my order number?")
    ask(agent, other, "What was my order number?")
