"""Tests that need no model: the tools, the routing, and the graph's plumbing, with stand-ins for the model's
steps. Run them on every change:  pytest -q"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shop  # noqa: E402

shop.create()
from p1_tools import check_stock, get_order  # noqa: E402
from p4_memory_rag import search_policies  # noqa: E402
from p5_graph import build  # noqa: E402


def test_get_order_finds_and_refuses():
    assert json.loads(get_order.invoke({"order_id": " a1002 "}))["status"] == "shipped"
    assert "No order" in get_order.invoke({"order_id": "Z9"})


def test_check_stock_matches_part_of_a_name():
    assert json.loads(check_stock.invoke({"product": "helmet"}))[0]["in_stock"] == 12
    assert "don't sell" in check_stock.invoke({"product": "skateboard"})


def test_policy_search_puts_the_right_policy_first():
    assert search_policies.invoke({"question": "return a worn helmet"}).startswith("[returns]")
    assert search_policies.invoke({"question": "when is the workshop open"}).startswith("[repairs]")


def fake(category):
    return lambda state: {"category": category}


def echo(state):
    return {"answer": "FACTS:" + state["facts"]}


def test_returns_always_get_the_order_and_the_policy():
    out = build(fake("return or refund"), echo).invoke({"question": "Refund A1004 please"})
    assert '"id": "A1004"' in out["answer"] and "[returns]" in out["answer"]


def test_other_questions_go_to_a_person_without_the_model_writing():
    out = build(fake("other"), echo).invoke({"question": "Do you sponsor clubs?"})
    assert out["handoff"] and "member of our team" in out["answer"]
