# Part-of-speech tagger with a hidden Markov model

Tags every word of an English sentence with its part of speech (noun, verb, determiner, ...) using a hidden Markov model
trained by counting on 13,054 tagged news sentences, with the Viterbi algorithm for decoding and the forward algorithm
for sentence probabilities. Written with PyTorch tensors.

## Results (1,451 test sentences)

| tagger | accuracy | accuracy on words never seen in training (4.4%) |
|---|---|---|
| most frequent tag for each word | 0.912 | 0.160 |
| HMM + Viterbi, word-shape model for unknown words | **0.957** | **0.804** |

Forward algorithm: log p("The company said its profit rose sharply in the third quarter .") = -60.8; the same words
scrambled: -81.7, about e^21 (a billion) times less likely.

## Run it

```bash
pip install -r requirements.txt
python evaluate.py
```

## What I learned

- An HMM is a graphical model: a chain of hidden tags, each emitting one observed word.
- Dynamic programming makes it practical: Viterbi (max) and forward (sum) cost O(length x tags^2), not tags^length.
- Context fixes ambiguity ("I can open the can"), but one tag of memory is not enough for everything ("will back the plan").

Based on section 11.3 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
