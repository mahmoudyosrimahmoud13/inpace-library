"""Naive Bayes, written with nothing but Bayes' theorem and counting (Bishop, sections 2.1 and 2.3).

p(spam | message) = p(message | spam) p(spam) / p(message)

'Naive' assumption: given the class, each word is drawn independently, so
log p(message | class) = sum over words of  count(word) * log p(word | class).
"""
import torch


class NaiveBayes:
    def __init__(self, alpha=1.0):
        self.alpha = alpha            # pseudo-count added to every word (alpha = 0 is plain maximum likelihood)

    def fit(self, X, t):
        """X: (messages, words) word counts. t: 0 = ham, 1 = spam."""
        self.log_prior = torch.log(torch.stack([(t == c).float().mean() for c in (0, 1)]))
        word_counts = torch.stack([X[t == c].sum(0) for c in (0, 1)]) + self.alpha        # (2, words)
        self.log_word = torch.log(word_counts / word_counts.sum(1, keepdim=True))          # log p(word | class)
        return self

    def log_joint(self, X):
        """log p(message, class) for both classes: shape (messages, 2)."""
        return X @ self.log_word.T + self.log_prior

    def prob_spam(self, X):
        """Bayes' theorem: normalize the joint over the two classes (done safely in log space)."""
        return torch.softmax(self.log_joint(X), dim=1)[:, 1]
