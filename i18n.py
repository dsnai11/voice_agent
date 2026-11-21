"""Ria's replies in the caller's language.

Every reply Ria writes is Hindi. localize() turns it into English / Gujarati / Marwari one sentence at a time:
  1. i18n/<lang>.json   Hindi sentence -> sentence in that language (checked by people, see train/i18n_check.py)
  2. templates          names, amounts, phone numbers, times, today's date
  3. nothing found      the Hindi sentence is kept (callers of all three languages follow simple Hindi) and noted in calls/untranslated.jsonl
Marwari is written in Devanagari (Rajasthani village forms: म्हारो, कांई, चाइजे, कितरो, सा ...), Gujarati in Gujarati script, English in Roman letters.
"""
import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
_TABLES = {}
_MISSING_LOG = os.path.join(HERE, "calls", "untranslated.jsonl")
SPLIT = re.compile(r"(?<=[।?!])\s+")


def table(lang: str) -> dict:
    if lang not in _TABLES:
        path = os.path.join(HERE, "i18n", f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _TABLES[lang] = json.load(f)
        except (OSError, ValueError):
            _TABLES[lang] = {}
    return _TABLES[lang]


def reload():
    _TABLES.clear()


# ---------------------------------------------------------------- templates
TIME_WORDS = {
    "en": {"आधे घंटे बाद": "in half an hour", "एक घंटे बाद": "in an hour", "दो घंटे बाद": "in two hours", "अभी": "right now", "आज": "today", "कल": "tomorrow", "परसों": "the day after tomorrow",
           "सुबह": "in the morning", "दोपहर": "in the afternoon", "शाम": "in the evening", "रात": "at night", "बजे": "o'clock"},
    "gu": {"आधे घंटे बाद": "અડધા કલાક પછી", "एक घंटे बाद": "એક કલાક પછી", "दो घंटे बाद": "બે કલાક પછી", "अभी": "હમણાં", "आज": "આજે", "कल": "કાલે", "परसों": "પરમ દિવસે",
           "सुबह": "સવારે", "दोपहर": "બપોરે", "शाम": "સાંજે", "रात": "રાત્રે", "बजे": "વાગ્યે"},
    "mwr": {"आधे घंटे बाद": "आधा घंटा पछै", "एक घंटे बाद": "एक घंटा पछै", "दो घंटे बाद": "दो घंटा पछै", "अभी": "अबार", "आज": "आज", "कल": "काल", "परसों": "परसूं",
            "सुबह": "सवेरे", "दोपहर": "दोपहर में", "शाम": "सांझ", "रात": "रात", "बजे": "बजे"},
}
MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
          "gu": ["જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન", "જુલાઈ", "ઑગસ્ટ", "સપ્ટેમ્બર", "ઑક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"],
          "mwr": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]}
DAYS = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "gu": ["સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર", "રવિવાર"],
        "mwr": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "इतवार"]}
HI_NUM = {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12}


def _when(phrase: str, lang: str) -> str:
    t = TIME_WORDS[lang]
    out = []
    rest = phrase
    for k in ("आधे घंटे बाद", "एक घंटे बाद", "दो घंटे बाद"):
        if k in rest:
            out.append(t[k])
            rest = rest.replace(k, " ")
    words = rest.split()
    i = 0
    clock = None
    while i < len(words):
        w = words[i]
        if i + 1 < len(words) and words[i + 1] == "बजे":
            n = words[i]
            clock = n if n.isdigit() else str(HI_NUM.get(n, n))
            i += 2
            continue
        if w in t:
            out.append(t[w])
        i += 1
    if clock:
        out.append(f"at {clock} o'clock" if lang == "en" else f"{clock} {t['बजे']}")
    if lang == "en":
        out.sort(key=lambda x: 0 if x in ("today", "tomorrow", "the day after tomorrow", "right now") else 1)
        return " ".join(out)
    return " ".join(out)


def _templates(s: str, lang: str, name: str):
    """Sentences that carry a name, an amount, a number or a time."""
    m = re.fullmatch(r"धन्यवाद (.+) जी।", s)
    if m:
        return {"en": f"Thank you, {name or m.group(1)}.", "gu": f"આભાર {gu_script(m.group(1))} જી.", "mwr": f"धन्यवाद {m.group(1)} सा।"}[lang]
    m = re.fullmatch(r"जी, (\d+) रुपये, नोट कर लिया।", s)
    if m:
        n = m.group(1)
        return {"en": f"Noted, {n} rupees.", "gu": f"જી, {n} રૂપિયા, નોંધી લીધા.", "mwr": f"जी, {n} रुपया, नोट कर लिया।"}[lang]
    m = re.fullmatch(r"जी, (\d+) रुपये। क्या यह सही है\?", s)
    if m:
        n = m.group(1)
        return {"en": f"{n} rupees. Is that correct?", "gu": f"જી, {n} રૂપિયા. શું આ બરાબર છે?", "mwr": f"जी, {n} रुपया। कांई ओ सही है?"}[lang]
    m = re.fullmatch(r"आपका नंबर (\d+) है, क्या यह सही है\?", s)
    if m:
        n = m.group(1)
        return {"en": f"Your number is {n}. Is that correct?", "gu": f"તમારો નંબર {n} છે, શું આ બરાબર છે?", "mwr": f"आपरो नंबर {n} है, कांई ओ सही है?"}[lang]
    m = re.fullmatch(r"मैं दोबारा पढ़ती हूँ, आपका नंबर (\d+) है, क्या यह सही है\?", s)
    if m:
        n = m.group(1)
        return {"en": f"Let me read it again: your number is {n}. Is that correct?", "gu": f"હું ફરીથી વાંચું છું, તમારો નંબર {n} છે, શું આ બરાબર છે?",
                "mwr": f"म्हैं फेर पढ़ूं हूं, आपरो नंबर {n} है, कांई ओ सही है?"}[lang]
    m = re.fullmatch(r"अभी तक (\d+) अंक मिले हैं, बाकी के अंक भी बता दीजिए।", s)
    if m:
        n = m.group(1)
        return {"en": f"I have got {n} digits so far, please say the remaining digits too.", "gu": f"અત્યાર સુધી {n} અંક મળ્યા છે, બાકીના અંક પણ જણાવો.",
                "mwr": f"अबार तांई {n} अंक मिल्या है, बाकी रा अंक भी बताओ सा।"}[lang]
    m = re.fullmatch(r"ठीक है जी, टीम आपको (.+) कॉल करेगी।", s)
    if m:
        w = _when(m.group(1), lang)
        return {"en": f"Okay, our team will call you {w}.", "gu": f"ઠીક છે જી, ટીમ તમને {w} કૉલ કરશે.", "mwr": f"ठीक है सा, टीम आपनै {w} कॉल करसी।"}[lang]
    m = re.fullmatch(r"ठीक है (.+) जी, आपकी सारी जानकारी नोट हो गई है।", s)
    if m:
        return {"en": f"Alright {name or m.group(1)}, all your details are noted.", "gu": f"ઠીક છે {gu_script(m.group(1))} જી, તમારી બધી માહિતી નોંધાઈ ગઈ છે.",
                "mwr": f"ठीक है {m.group(1)} सा, आपरी सगळी जाणकारी नोट हो गई है।"}[lang]
    m = re.fullmatch(r"(.+) जी, (क्या हमारी टीम आपको इसी नंबर पर कॉल कर सकती है\?|हमारी टीम आपको कॉल करके आगे की जानकारी दे दे, चलेगा\?)", s)
    if m:
        rest = table(lang).get(m.group(2))
        if rest:
            return {"en": f"{name or m.group(1)}, {rest}", "gu": f"{gu_script(m.group(1))} જી, {rest}", "mwr": f"{m.group(1)} सा, {rest}"}[lang]
    m = re.fullmatch(r"जी, आज (.+) है।", s)
    if m:
        n = datetime.date.today()
        d = f"{DAYS[lang][n.weekday()]}, {n.day} {MONTHS[lang][n.month - 1]} {n.year}"
        return {"en": f"Today is {d}.", "gu": f"આજે {d} છે.", "mwr": f"आज {d} है।"}[lang]
    return None


def gu_script(text: str) -> str:
    """Devanagari -> Gujarati script (the two Unicode blocks have the same layout, 0x180 apart): used for names inside Gujarati sentences."""
    return "".join(chr(ord(c) + 0x180) if "ँ" <= c <= "ॣ" else c for c in text)


def _log_missing(s: str, lang: str):
    try:
        os.makedirs(os.path.dirname(_MISSING_LOG), exist_ok=True)
        with open(_MISSING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"lang": lang, "text": s}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def sentence(s: str, lang: str, name: str = "") -> str:
    key = s.strip()
    if not key or lang == "hi":
        return s
    tr = table(lang).get(key)
    if tr:
        return tr
    tpl = _templates(key, lang, name)
    if tpl:
        return tpl
    if re.search(r"[ऀ-ॿ]", key):
        _log_missing(key, lang)
    return s


def localize(text: str, lang: str, name: str = "") -> str:
    """The whole reply, sentence by sentence."""
    if not text or lang == "hi" or lang not in ("en", "gu", "mwr"):
        return text
    return " ".join(sentence(p, lang, name) for p in SPLIT.split(text.strip()) if p.strip())


def sentences_missing(lang: str, hindi_sentences) -> list:
    """Hindi sentences that have no translation yet (used by train/i18n_check.py)."""
    t = table(lang)
    return [s for s in hindi_sentences if s not in t and _templates(s, lang, "") is None]
