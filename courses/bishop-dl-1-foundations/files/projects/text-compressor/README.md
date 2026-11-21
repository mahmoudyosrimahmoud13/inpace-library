# Shakespeare text compressor

Measures how much information one character of Shakespeare carries, with entropy, cross-entropy and KL divergence,
and builds a working Huffman compressor in Python and PyTorch. Compared with gzip and bzip2.

## Results (test text: the last 111,540 characters of the plays)

| method | bits per character |
|---|---|
| plain text file | 8.000 |
| uniform code over 65 characters | 6.022 |
| Huffman code (from training frequencies) | 4.868 |
| gzip -9 | 3.191 |
| bigram model, cross-entropy | 3.583 |
| bzip2 -9 | 2.635 |
| trigram model, cross-entropy | 2.980 |

The Huffman code sits just above the character entropy (4.774), as Shannon's theorem predicts. Real compressors win
because they use context: a model that knows the previous two characters needs only 2.98 bits per character.

## Run it

```bash
pip install -r requirements.txt
python entropy.py     # entropy, cross-entropy, KL, n-gram models
python huffman.py     # build the code, compress, decompress, compare with gzip and bzip2
```

## What I learned

- Entropy is a hard lower limit on the average code length for a given model of the data.
- Cross-entropy measures a model on new data; the gap to the data's own entropy is the KL divergence.
- Better predictions are better compression: the same idea scores today's language models (bits per character).

Based on chapter 2 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
