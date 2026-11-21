"""Compare a no-context baseline with the HMM on 1,451 test sentences, then use the forward algorithm."""
from collections import Counter, defaultdict
from data import load
from hmm import HMMTagger

train, test = load("train"), load("test")
seen = Counter(w for words, _ in train for w in words)

# Baseline: each word gets the tag it had most often in training (unknown words: the most common tag, NN)
by_word = defaultdict(Counter)
for words, tags in train:
    for w, t in zip(words, tags):
        by_word[w][t] += 1
baseline = lambda words: [by_word[w].most_common(1)[0][0] if w in by_word else "NN" for w in words]

hmm = HMMTagger().fit(train)
results = {"most frequent tag": baseline, "HMM + Viterbi": hmm.viterbi}
for name, tagger in results.items():
    right = right_unk = n = n_unk = 0
    for words, tags in test:
        for w, guess, truth in zip(words, tagger(words), tags):
            n += 1; right += guess == truth
            if w not in seen:
                n_unk += 1; right_unk += guess == truth
    print(f"{name:18s} accuracy {right / n:.3f}   on words never seen in training ({n_unk / n:.1%} of words): {right_unk / n_unk:.3f}")

# Context resolves ambiguity: 'can' and 'back' have several possible tags
for sentence in ["I can open the can .", "They will back the plan to go back home ."]:
    words = sentence.split()
    print("\n" + " ".join(f"{w}/{t}" for w, t in zip(words, hmm.viterbi(words))))

# The forward algorithm: how probable is a sentence under the model? A scrambled one should be far less likely.
s = "The company said its profit rose sharply in the third quarter ."
scrambled = "quarter the rose The profit its company sharply said third in ."
print(f"\nlog p(sentence)  = {hmm.log_prob(s.split()):.1f}")
print(f"log p(scrambled) = {hmm.log_prob(scrambled.split()):.1f}")
