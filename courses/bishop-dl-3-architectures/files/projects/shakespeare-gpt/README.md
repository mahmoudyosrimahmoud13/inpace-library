# A character-level GPT trained on Shakespeare

A small decoder-only transformer (4 layers, 4 heads, 826k parameters, written in PyTorch with masked self-attention)
trained to predict the next character of Shakespeare's plays, then used to generate new text at different temperatures.
Measured in bits per character on held-out text and compared with classic compressors.

## Results (held-out text: the last 10% of the plays)

| model | bits per character |
|---|---|
| unigram character frequencies (entropy) | 4.77 |
| gzip -9 | 3.19 |
| trigram model | 2.98 |
| bzip2 -9 | 2.64 |
| **this GPT, 1,500 steps on a laptop CPU** | **2.30** |

(Earlier rows from my [text-compressor](https://github.com/YOUR-USERNAME/text-compressor) project, same text and split.)

Sample, temperature 0.8, top-10:

```text
ROMEO:
Thou must what self I do thee hath a sword, then
Thou would for me in his death being some on
For that he lords appear.
```

## Run it

```bash
pip install -r requirements.txt
python train.py     # about 25 minutes on a laptop CPU, a couple of minutes on a GPU
python sample.py
```

## What I learned

- A GPT is a stack of masked self-attention blocks trained only to predict the next token.
- Cross-entropy in bits per character connects language models to compression: better prediction, shorter codes.
- Temperature trades safety for variety: low is repetitive, high is gibberish.

Based on chapter 12 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
