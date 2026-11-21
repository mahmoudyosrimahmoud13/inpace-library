"""Download Tiny Shakespeare (about 1.1 million characters) and split it into a training and a test part."""
from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
CACHE = Path("data/shakespeare.txt")


def load_text():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_bytes(urlopen(URL).read())
    return CACHE.read_text(encoding="utf-8")


def load_splits():
    text = load_text()
    cut = int(0.9 * len(text))
    return text[:cut], text[cut:]       # the last 10% of the plays is the test text


if __name__ == "__main__":
    train, test = load_splits()
    print(f"training text: {len(train):,} characters, test text: {len(test):,} characters")
    print(f"alphabet: {len(set(train))} different characters")
    print(repr(test[:80]))
