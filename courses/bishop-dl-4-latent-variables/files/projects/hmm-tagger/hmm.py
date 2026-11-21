"""A hidden Markov model tagger (Bishop, section 11.3.1): hidden states = tags, observations = words.

p(words, tags) = p(tag_1) * prod_t p(tag_t | tag_t-1) * prod_t p(word_t | tag_t)
Everything is estimated by counting, then Viterbi finds the most probable tag sequence for a new sentence."""
import math
from collections import Counter, defaultdict
import torch


def shape(word):
    """A stand-in for words never seen in training: what they look like (suffix, capital, digits)."""
    if any(c.isdigit() for c in word):
        return "<num>"
    if word[0].isupper():
        return "<Cap>"
    for suffix in ("ing", "ed", "ly", "s", "tion", "able", "al", "ive", "est", "er"):
        if word.endswith(suffix):
            return "<-" + suffix + ">"
    return "<unk>"


class HMMTagger:
    def fit(self, sentences, rare=1):
        word_count = Counter(w for words, _ in sentences for w in words)
        self.known = {w for w, c in word_count.items() if c > rare}       # rare words teach the 'unknown' shapes
        self.tags = sorted({t for _, tags in sentences for t in tags})
        T = len(self.tags); ti = {t: i for i, t in enumerate(self.tags)}
        start, trans = torch.ones(T), torch.ones(T, T)                     # +1: nothing is impossible
        emit = defaultdict(lambda: torch.full((T,), 0.01))
        for words, tags in sentences:
            start[ti[tags[0]]] += 1
            for a, b in zip(tags, tags[1:]):
                trans[ti[a], ti[b]] += 1
            for w, t in zip(words, tags):
                emit[self.token(w)][ti[t]] += 1
        self.log_start = (start / start.sum()).log()
        self.log_trans = (trans / trans.sum(1, keepdim=True)).log()        # p(next tag | tag)
        tag_totals = sum(emit.values())
        self.log_emit = {w: (c / tag_totals).log() for w, c in emit.items()}  # p(word | tag)
        return self

    def token(self, w):
        return w if w in self.known else shape(w)

    def emissions(self, words):
        return torch.stack([self.log_emit.get(self.token(w), self.log_emit["<unk>"]) for w in words])

    def viterbi(self, words):
        """The most probable tag sequence: the Viterbi algorithm, dynamic programming over positions."""
        E = self.emissions(words)
        score = self.log_start + E[0]
        back = []
        for t in range(1, len(words)):
            total = score[:, None] + self.log_trans                         # (previous tag, next tag)
            score, best_prev = total.max(0)
            score = score + E[t]
            back.append(best_prev)
        path = [int(score.argmax())]
        for bp in reversed(back):
            path.append(int(bp[path[-1]]))
        return [self.tags[i] for i in reversed(path)]

    def log_prob(self, words):
        """log p(words), summing over ALL tag sequences: the forward algorithm (sum instead of max)."""
        E = self.emissions(words)
        alpha = self.log_start + E[0]
        for t in range(1, len(words)):
            alpha = torch.logsumexp(alpha[:, None] + self.log_trans, 0) + E[t]
        return torch.logsumexp(alpha, 0).item()
