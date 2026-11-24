# Pedal & Co. support desk

The running project of the inPace course "LangChain and LangGraph: build agents with v1": a support desk for a
small bike shop, built one day at a time.

| File | Day | What it adds |
|---|---|---|
| `shop.py` | | The shop's orders and stock (SQLite) and its policies. Run it once: `python shop.py` |
| `p1_tools.py` | 1 | Tools: `get_order`, `check_stock`, and which one the model asks for |
| `p2_agent.py` | 2 | `create_agent`, and a structured `Ticket` your code can file |
| `p3_middleware.py` | 3 | A `refund` tool behind human approval, email redaction, a model call limit |
| `p4_memory_rag.py` | 4 | Memory per conversation, and `search_policies` |
| `p5_graph.py`, `tests/` | 5 | A LangGraph workflow that can't skip lookups, tests without a model, an evaluation |

```bash
pip install -U langchain langgraph langchain-ollama pytest
ollama pull qwen3            # or any model with tool calling
python shop.py
python p1_tools.py
```

Choose the model with `PEDAL_MODEL`, for example `PEDAL_MODEL=ollama:qwen2.5:1.5b` or `PEDAL_MODEL=openai:gpt-4.1-mini`.
