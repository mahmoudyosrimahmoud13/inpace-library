"""Which words give spam away, and what does the filter think of a few new messages?"""
import sys
import torch
from data import load_splits, Vocabulary
from model import NaiveBayes

(train_x, train_t), _, _ = load_splits()
vocab = Vocabulary(train_x)
model = NaiveBayes(alpha=1.0).fit(vocab.counts(train_x), train_t)

# log p(word | spam) - log p(word | ham): how many times more likely the word is in spam (in log units)
ratio = model.log_word[1] - model.log_word[0]
print("most spam-like words:", ", ".join(vocab.words[i] for i in ratio.argsort(descending=True)[:12]))
print("most real-like words:", ", ".join(vocab.words[i] for i in ratio.argsort()[:12]))

messages = sys.argv[1:] or ["Are we still on for dinner tonight?",
                            "URGENT! You have won a 1 week FREE membership. Call now to claim your prize",
                            "Call me when you get this"]
print()
for text, p in zip(messages, model.prob_spam(vocab.counts(messages))):
    print(f"p(spam) = {p:.4f}  {text}")
