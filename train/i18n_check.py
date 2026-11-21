"""Every sentence Ria can say must exist in English, Gujarati and Marwari (or be a template), the numbers and the helpline digits must be kept, and
the script must be right (English: Latin only; Gujarati: Gujarati script; Marwari: Devanagari).   python train/i18n_check.py"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import flow, i18n

SPLIT = re.compile(r"(?<=[।?!])\s+")
sents = []
for x in flow.static_sentences():
    sents += [p.strip() for p in SPLIT.split(x) if p.strip()]
bank = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "reply_bank.json"), encoding="utf-8"))["entries"]
for e in bank:
    sents += [p.strip() for p in SPLIT.split(e["reply"].strip()) if p.strip()]
sents = list(dict.fromkeys(sents))
DEV, GU, LAT = re.compile(r"[ऀ-ॿ]"), re.compile(r"[઀-૿]"), re.compile(r"[A-Za-z]")
bad = 0
for lg in ("en", "gu", "mwr"):
    miss, wrong = [], []
    for s in sents:
        t = i18n.sentence(s, lg, "Rahul")
        if t == s and DEV.search(s) and s not in i18n.table(lg):
            miss.append(s)
            continue
        if lg == "en" and DEV.search(t):
            wrong.append((s, t, "Devanagari left in English"))
        if lg == "gu" and DEV.search(t):
            wrong.append((s, t, "Devanagari left in Gujarati"))
        if lg == "mwr" and (GU.search(t) or len(LAT.findall(t)) > 6):
            wrong.append((s, t, "wrong script in Marwari"))
        for n in re.findall(r"\d+", s):
            if n not in t and n not in ("300", "900", "650"):                       # these are written out in words in the translations
                wrong.append((s, t, f"number {n} lost"))
        if "टोल-फ्री" in s and "एक आठ शून्य शून्य" in s:
            need = {"en": "one eight zero zero", "gu": "એક આઠ શૂન્ય શૂન્ય", "mwr": "एक आठ शून्य शून्य"}[lg]
            if need not in t:
                wrong.append((s, t, "helpline digits lost"))
    print(f"{lg}: {len(sents) - len(miss)}/{len(sents)} sentences translated, {len(wrong)} problems")
    for s in miss[:6]:
        print("   MISSING:", s[:80])
    for s, t, why in wrong[:6]:
        print("   PROBLEM:", why, "|", t[:90])
    bad += len(wrong) + len(miss)                                           # a new answer without a translation fails this check, so it gets translated
sys.exit(1 if bad else 0)
