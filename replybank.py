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
MIN_HIT_IDF = 3.0        # the shared words must include one at least this informative (idf); "kya hai" alone is not a question about AI

_DEV = {}
for _chars, _lat in (("कख", "k"), ("गघ", "g"), ("चछ", "#"), ("जझ", "j"), ("टठ", "t"), ("डढ", "d"), ("ण", "n"), ("तथ", "t"),
                     ("दध", "d"), ("न", "n"), ("प", "p"), ("फ", "f"), ("बभ", "b"), ("म", "m"), ("य", "y"), ("र", "r"),
                     ("ल", "l"), ("व", "v"), ("शषस", "s"), ("ह", "h"), ("ंँ", "n"),
                     ("क़ख़", "k"), ("ग़", "g"), ("ज़", "j"), ("ड़ढ़", "r"), ("फ़", "f")):
    for _c in _chars:
        _DEV[_c] = _lat
_NUKTA_R = ("ड़", "ढ़")                                   # ड़ and ढ़ written as base letter + nukta sound like r
_NEGATIONS = {"nh", "nhi", "nhin", "mt", "n", "nt"}          # skeletons of nahi, nahin, mat, na, not: they flip a meaning, so they weigh more
_AI_WORDS = {"ai", "एआई", "एआइ", "आई"}                      # "AI" is all vowels, so its skeleton is empty and it used to vanish: "ai kya hai" became "kya hai" and matched everything
_FILLER_WORDS = "thik theek sir sahab saheb saahab madam hello hanji"       # only words whose skeleton is not shared with a real topic word (ji = mujhe, achha = chahiye)
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


# Different words that mean the same thing become one word before matching, for the stored examples and for the caller's sentence alike:
# "kagaz", "papers", "docs" are all "document"; "zamanat" is "guarantor"; "byaaj" is "interest"; "kist" is "emi" ...
_SYNONYMS = {
    "document": "document documents docs doc kagaz kagzat kagaj papers paper paperwork dastavez दस्तावेज़ दस्तावेज डॉक्यूमेंट कागज़ कागज",
    "interest": "interest byaaj byaj vyaj sood rate percent percentage ब्याज इंटरेस्ट रेट प्रतिशत",
    "emi": "emi kist kisht instalment installment किस्त ईएमआई",
    "guarantor": "guarantor gaurantor guarantee zamanat jamanat zamin jamin ज़मानत जमानत गारंटर",
    "fraud": "fraud fraudulent scam thagi dhokha dhoka nakli fake फ्रॉड ठगी धोखा नकली",
    "robot": "robot bot machine computer insaan human इंसान रोबोट मशीन",
    "message": "sms whatsapp message msg text email mail मैसेज",
    "quick": "jaldi turant urgent instant fast quick immediately tatkal तुरंत जल्दी",
    "approve": "pass approve approved sanction manjoor manzoor clear मंज़ूर मंजूर",
    "charge": "fee fees charge charges shulk kharcha katega katti कटेगा चार्ज फ़ीस फीस",
    "complaint": "complaint complain shikayat grievance शिकायत",
    "account": "account khata khaata khaate खाता अकाउंट",
    "safe": "safe surakshit secure bharosa trust भरोसा सुरक्षित",
    "pay": "bharni bharna bharu bharun pay payment jama deposit भरनी भरना",
    "registered": "registered registration licence license रजिस्टर्ड",
    "think": "soch sochna sochne think vichar",
    "close": "band close closure foreclose foreclosure khatam",
    "salary": "salary tankhwah tankhwa vetan सैलरी तनख्वाह वेतन",
}
_SYN = {w: canon for canon, words in _SYNONYMS.items() for w in words.split()}


_FILLER = {_skeleton(w) for w in _FILLER_WORDS.split()}                  # acknowledgements, forms of address and glue words: they never make a topic


def tokens(text: str) -> list:
    words = re.findall(r"[\wऀ-ॿ]+", text.lower())
    words = [_SYN.get(w, w) for w in words]
    out = ["NUM" if w.isdigit() else ("AIW" if w in _AI_WORDS else _skeleton(w)) for w in words]       # any number counts as one word
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
            hit = ct & ex
            hit = hit - _FILLER
            if not hit or max(self.idf.get(t, self.default_idf) for t in hit) < MIN_HIT_IDF:   # only "kya", "hai", "haan", "main" in common: not a real match
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


# ---- hybrid: when the word-matcher is unsure, the local model only PICKS a topic number from the approved list (it never writes an answer) ----
_cls_cache: dict = {}
_cls_schema = None
_cls_system = ""


def classify_llm(text: str, timeout: float = 8.0):
    """Entry the local model picks for this sentence, or None (NONE / model down / too slow). Offline: talks to the local Ollama only."""
    global _cls_schema, _cls_system, _bank
    if os.environ.get("CLASSIFIER", "1") != "1":
        return None
    if _bank is None:
        load()
    key = text.strip().lower()
    if key in _cls_cache:
        return _cls_cache[key]
    entries = {e["id"]: e for e, _ in _bank.rows}
    if _cls_schema is None:
        _cls_schema = {"type": "object", "properties": {"topic": {"type": "string", "enum": list(entries) + ["NONE"]}}, "required": ["topic"]}
        _cls_system = ("You route a customer's sentence from a loan phone call in India (Hinglish, Roman letters, often misspelled by a speech recogniser) to ONE topic of an approved-answer list. "
                       "Choose the topic whose answer best responds to what the customer said. If the sentence is only an answer to a form question (name, amount, city, yes/no, a time) "
                       "or matches no topic, answer NONE.\nTOPICS:\n" + "\n".join(f"{i}: {e.get('topic', i)[:70]} (e.g. \"{min(e['examples'], key=lambda x: abs(len(x) - 28))}\")" for i, e in entries.items()))
    try:
        import requests
        r = requests.post(os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat",
                          json={"model": os.environ.get("CLASSIFIER_MODEL", "qwen2.5:7b"), "stream": False, "format": _cls_schema, "keep_alive": "24h",
                                "options": {"temperature": 0, "num_predict": 20}, "messages": [{"role": "system", "content": _cls_system}, {"role": "user", "content": text}]},
                          timeout=timeout).json()
        import json as _j
        topic = _j.loads(r["message"]["content"])["topic"]
    except Exception:
        return None
    got = entries.get(topic)
    _cls_cache[key] = got
    return got


def match_hybrid(text: str, limit: int = MAX_REPLIES, sure: float = 0.8) -> list:
    """match(), but when the best word-match is below `sure` the local model gets a vote; its pick wins only when it is a real topic."""
    found = match(text, limit)
    if found and found[0]["score"] >= sure:
        return found
    if len(text.split()) < 3 and not found:                                  # "ji haan", "do lakh": an answer, not a question
        return found
    pick = classify_llm(text)
    if pick is None:
        return found
    if found and found[0]["id"] == pick["id"]:                               # both agree: now it is certain
        found[0]["score"] = max(found[0]["score"], 0.9)
        return found
    return [{"id": pick["id"], "score": 0.9, "chunk": text, "entry": pick}]
