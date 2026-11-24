# TinyGPT: a language model from scratch

The running project of the inPace course "LLMs: how they work and how to use them". A small GPT trained on Tiny
Shakespeare (public domain, from Andrej Karpathy's char-rnn), one piece a day.

| File | Day | What it adds |
|---|---|---|
| `p1_tokenizer.py` | 1 | A BPE tokenizer trained on the text, saved as `tokenizer.json` |
| `gpt.py`, `p2_model.py` | 2 | The transformer, and checks before training |
| `p3_train.py` | 3 | Pretraining (10 to 20 minutes on a CPU), saved as `tinygpt.pt` |
| `p4_generate.py` | 4 | Temperature, top-k, top-p, and a KV cache |
| `p5_evaluate.py` | 5 | Perplexity against baselines, format and copy checks |

```bash
pip install torch
python p1_tokenizer.py
```
