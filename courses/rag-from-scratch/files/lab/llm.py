"""Talk to a local model through Ollama (free, runs on your computer): https://ollama.com
Install it, run `ollama pull qwen2.5:1.5b`, and leave it running. Set OLLAMA_MODEL to use another model."""
import json
import os
import urllib.request

URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")


def chat(messages, max_tokens=300):
    """Send a list of {"role", "content"} messages; get the model's reply and how many tokens went in and out."""
    body = json.dumps({"model": MODEL, "messages": messages, "stream": False,
                       "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(URL + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    return out["message"]["content"].strip(), out.get("prompt_eval_count", 0), out.get("eval_count", 0)


def available():
    try:
        urllib.request.urlopen(URL + "/api/tags", timeout=3)
        return True
    except OSError:
        return False
