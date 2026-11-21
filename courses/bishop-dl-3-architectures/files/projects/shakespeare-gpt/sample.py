"""Generate new 'Shakespeare' with the trained GPT, at different temperatures (section 12.3.2)."""
import torch
from model import GPT

saved = torch.load("gpt.pt")
chars = saved["chars"]
model = GPT(len(chars))
model.load_state_dict(saved["model"])
model.eval()
stoi = {c: i for i, c in enumerate(chars)}
prompt = "ROMEO:\n"

for temperature, top_k, n in [(0.8, 10, 400), (0.3, None, 150), (1.5, None, 150)]:
    g = torch.Generator().manual_seed(0)
    start = torch.tensor([[stoi[c] for c in prompt]])
    out = model.generate(start, n, temperature=temperature, top_k=top_k, generator=g)
    label = f"temperature {temperature}" + (f", top-{top_k}" if top_k else "")
    print(f"----- {label} -----")
    print("".join(chars[i] for i in out[0].tolist()))
    print()
