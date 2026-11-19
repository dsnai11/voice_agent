"""Matches what the caller said against knowledge/reply_bank.json and returns the best-suited approved replies.

Caller speech is cut into chunks (sentences, "aur"/"lekin" parts), each chunk is matched on its own, and the best
replies are handed to the LLM as guidance. Matching ignores spelling and script: Hindi (Devanagari) and Roman
Hinglish both reduce to the same consonant skeleton, so the bank only needs examples in Roman letters.
No model and no internet needed. To add or change a reply, edit the JSON file and restart the app.
"""
import json
import math
import os
import re
from collections import Counter

BANK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "reply_bank.json")
MIN_SCORE = 0.45         # below this a chunk is treated as "no approved reply fits"
MAX_REPLIES = 3

_DEV = {}
for _chars, _lat in (("कख", "k"), ("गघ", "g"), ("चछ", "#"), ("जझ", "j"), ("टठ", "t"), ("डढ", "d"), ("ण", "n"), ("तथ", "t"),
                     ("दध", "d"), ("न", "n"), ("प", "p"), ("फ", "f"), ("बभ", "b"), ("म", "m"), ("य", "y"), ("र", "r"),
                     ("ल", "l"), ("व", "v"), ("शषस", "s"), ("ह", "h"), ("ंँ", "n"),
                     ("क़ख़", "k"), ("ग़", "g"), ("ज़", "j"), ("ड़ढ़", "r"), ("फ़", "f")):
    for _c in _chars:
        _DEV[_c] = _lat
_NUKTA_R = ("ड़", "ढ़")                                   # ड़ and ढ़ written as base letter + nukta sound like r
_NEGATIONS = {"nh", "nhi", "nhin", "mt", "n", "nt"}          # skeletons of nahi, nahin, mat, na, not: they flip a meaning, so they weigh more
_SPLIT = re.compile(r"[?।!.;\n]+|,| (?:aur|lekin|par|magar|and|but|और|लेकिन|पर|मगर) ")


def _skeleton(word: str) -> str:
    word = word.lower().replace(_NUKTA_R[0], "r").replace(_NUKTA_R[1], "r").replace("़", "")
    w = "".join(_DEV.get(c, c) for c in word)
    w = (w.replace("sh", "s").replace("ch", "#").replace("kh", "k").replace("gh", "g").replace("th", "t")
           .replace("dh", "d").replace("bh", "b").replace("jh", "j").replace("ph", "f"))
    w = w.replace("c", "k").replace("#", "c").replace("w", "v").replace("z", "j").replace("q", "k").replace("x", "ks")
    w = re.sub(r"[^a-z]", "", re.sub(r"[aeiouy]", "", w))      # y is dropped too: क्यू and "kyu" differ in spelling only
    w = re.sub(r"[nm](?=[bpkgtdcj])", "", w)                   # नंबर and "number" both lose the nasal before a stop
    w = re.sub(r"(.)\1+", r"\1", w)
    return _ALIAS.get(w, w)


_ALIAS = {"mn": "m", "mnn": "m", "hn": "h", "hnn": "h", "nhn": "nh"}        # me / mein / mai, hai / hain


def tokens(text: str) -> list:
    words = re.findall(r"[\wऀ-ॿ]+", text.lower())
    out = ["NUM" if w.isdigit() else _skeleton(w) for w in words]       # any number counts as one word
    return [t for t in out if t]


def chunks(text: str) -> list:
    """Parts of one utterance, each ideally one question or statement."""
    parts = [p.strip() for p in _SPLIT.split(f" {text} ") if p and p.strip()]
    return [p for p in parts if len(tokens(p)) >= 2 or any(len(t) >= 3 for t in tokens(p))]


def _has_any(low: str, words) -> bool:
    """True if any of the words appears in the (lower-case) text as a whole word. Entries use this for 'require' and 'forbid'."""
    for w in words:
        w = w.lower()
        if w.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low):
                return True
        elif w in low:
            return True
    return False


class _Bank:
    def __init__(self, path: str = BANK_PATH):
        with open(path, encoding="utf-8") as f:
            self.entries = json.load(f)["entries"]
        self.rows = [(e, set(tokens(x))) for e in self.entries for x in e["examples"]]
        df = Counter(t for _, s in self.rows for t in s)
        n = len(self.rows)
        self.idf = {t: (math.log((n + 1) / (c + 1)) + 1) * (2.5 if t in _NEGATIONS else 1) for t, c in df.items()}
        self.default_idf = math.log(n + 1) + 1

    def score(self, chunk_tokens: set, ex_tokens: set) -> float:
        if not chunk_tokens or not ex_tokens:
            return 0.0
        w = lambda t: self.idf.get(t, self.default_idf)
        hit = chunk_tokens & ex_tokens
        recall = sum(w(t) for t in hit) / sum(w(t) for t in ex_tokens)          # how much of the example the caller said
        precision = sum(w(t) for t in hit) / sum(w(t) for t in chunk_tokens)    # how much of what they said the example explains
        return recall * (0.6 + 0.4 * precision) * (0.85 + 0.05 * min(len(hit), 3))      # more shared words beat a lucky single one

    def best(self, text: str) -> tuple:
        """(entry, score) for the best example of one chunk, or (None, 0)."""
        ct = set(tokens(text))
        top, top_score = None, 0.0
        low = text.lower()
        for entry, ex in self.rows:
            if entry.get("require") and not _has_any(low, entry["require"]):      # "NACH kya hota hai" must not get the EMI answer
                continue
            if entry.get("require2") and not _has_any(low, entry["require2"]):      # a second word that must also be there ("mera" + "score")
                continue
            if entry.get("forbid") and _has_any(low, entry["forbid"]):
                continue
            s = self.score(ct, ex)
            if entry.get("require"):                                              # the question names the exact topic: prefer it over a generic entry
                s *= 1.2
            if s > top_score:
                top, top_score = entry, s
        return top, top_score


_bank = None


def load(path: str = BANK_PATH) -> _Bank:
    global _bank
    _bank = _Bank(path)
    return _bank


def match(text: str, limit: int = MAX_REPLIES) -> list:
    """Best-suited replies for what the caller said, in the order they said it: [{id, score, chunk, entry}]."""
    global _bank
    if _bank is None:
        try:
            load()
        except (OSError, ValueError, KeyError):
            return []
    found, seen = [], set()
    for chunk in chunks(text) or [text]:
        entry, score = _bank.best(chunk)
        if entry and score >= MIN_SCORE and entry["id"] not in seen:
            seen.add(entry["id"])
            found.append({"id": entry["id"], "score": round(score, 2), "chunk": chunk, "entry": entry})
    if not found:                                                              # the whole utterance may match even if no single chunk does
        entry, score = _bank.best(text)
        if entry and score >= MIN_SCORE:
            found.append({"id": entry["id"], "score": round(score, 2), "chunk": text, "entry": entry})
    return found[:limit]


def hint(text: str) -> str:
    """A note for the LLM with the approved replies for this utterance; empty if nothing fits."""
    found = match(text)
    if not found:
        return ""
    lines = ["(Approved reply guide for what the caller just said. Use the MEANING of the approved reply and say it fresh in natural Hinglish, "
             "in the order below, at most 3 short sentences in total. Follow the 'action' if there is one. Do not add facts that are not here. If an item clearly does not fit what the caller said, ignore it.)"]
    for i, m in enumerate(found, 1):
        e = m["entry"]
        lines.append(f"{i}. Caller said: \"{m['chunk']}\" -> topic: {e['topic']}\n   approved reply: {e['reply']}" + (f"\n   action: {e['note']}" if e.get("note") else ""))
    return "\n".join(lines)


if __name__ == "__main__":   # python replybank.py "your sentence"
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for m in match(" ".join(sys.argv[1:])):
        print(m["score"], m["id"], "<-", m["chunk"])
