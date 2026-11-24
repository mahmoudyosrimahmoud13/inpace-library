# Ask Python: a RAG assistant built from scratch

The project for the inPace course "RAG: build a docs assistant from scratch". It answers questions about Python's
standard library from its own docstrings, with sources.

| File | What it is |
|---|---|
| `pydocs.json` | 1,517 standard library docstrings (Python 3.13, PSF License): the documents |
| `evalset.json` | 45 test questions, each with the document(s) that answer it |
| `common.py` | Loading, tokenizing, and the recall@k / MRR scorer |
| `llm.py` | A tiny client for a local model through Ollama |
| `p01_bm25.py` | Day 1: BM25 search from scratch |
| `p02_chunking.py` | Day 2: three ways to chunk, measured |
| `p03_embeddings.py` | Day 3: LSA from scratch, a trained embedding model, a vector index |
| `p04_hybrid.py` | Day 4: hybrid search with reciprocal rank fusion |
| `p05_answer.py` | Day 5: prompt, model, citations, refusals |
| `p06_evaluate.py` | Day 6: five checks on every answer, two prompts compared |
| `p07_production.py` | Day 7: incremental index, filters, injection scan, cache, HTTP API |

## Setup

```bash
pip install -r requirements.txt
```

From day 5, install Ollama (https://ollama.com), then run `ollama pull qwen2.5:1.5b`. Use another model with
`OLLAMA_MODEL=qwen2.5:7b python p05_answer.py`.

Run each project from this folder: `python p01_bm25.py`.
