"""Guided call flow for new-loan enquiries: the part that makes Ria behave like a proper finance calling agent.

A small language model is good at wording but unreliable at bookkeeping (it forgets what it was told, skips tools, invents digits).
So the bookkeeping is done here, in code, every turn:

  1. Pull the caller's exact values out of what they said (name, loan type, amount, job, income, city, existing loans,
     mobile number, consent, callback time). Numbers are parsed by code, never guessed by the model.
  2. If the caller asked something (interest, documents, how long ...), answer it with the approved reply from the reply bank.
  3. Ask the NEXT missing question, one at a time, acknowledging what was just captured.

Anything that is not a new-loan enquiry (existing customer, complaint, collections, odd requests) returns None, and brain.py
uses the full assistant (language model + CRM tools) for that turn. Switch the flow off with FLOW=0.

Test without voice:  python flow.py
"""
import random
import re

import db
import forms
import replybank
import voice

SLOTS = ["full_name", "loan_type", "loan_amount", "employment", "monthly_income", "city", "existing_loans", "phone", "consent", "callback_time"]

QUESTIONS = {
    "full_name": ["कृपया अपना पूरा नाम बताइए।"],
    "loan_type": ["आपको किस तरह का लोन चाहिए, पर्सनल, पेडे या सैलरी लोन?", "आपको कौन सा लोन चाहिए, पर्सनल लोन, पेडे लोन या सैलरी लोन?"],
    "loan_amount": ["आपको कितने रुपये का लोन चाहिए?", "आपको लगभग कितनी रकम का लोन चाहिए?"],
    "employment": ["आप नौकरी करते हैं या अपना बिज़नेस है?", "आप सैलरी वाले हैं या अपना बिज़नेस करते हैं?"],
    "monthly_income": ["आपकी महीने की सैलरी या कमाई लगभग कितनी है?", "हर महीने आपकी इनकम लगभग कितनी होती है?"],
    "city": ["आप किस शहर में रहते हैं?", "आप कौन से शहर से बोल रहे हैं?"],
    "existing_loans": ["क्या आपका कोई और लोन अभी चल रहा है?", "क्या आपके नाम पर कोई और लोन या ईएमआई चल रही है?"],
    "phone": ["आपका मोबाइल नंबर बता दीजिए।", "अब आप अपना मोबाइल नंबर बोल दीजिए।"],
    "consent": ["क्या हमारी टीम आपको इस नंबर पर कॉल कर सकती है?", "क्या हमारी टीम आपको कॉल करके आगे की जानकारी दे सकती है?"],
    "callback_time": ["आपको किस दिन और किस टाइम पर कॉल करवा दूँ?", "कॉल के लिए कौन सा दिन और टाइम ठीक रहेगा?"],
}
ACKS = ["जी।", "ठीक है।", "जी, समझ गई।", "अच्छा।", "धन्यवाद जी।", "शुक्रिया जी।", "बहुत अच्छा, धन्यवाद।"]
END_NOW = r"call\s*(kaat|kat\b|cut|band|disconnect|end)|kaat\s*do|cut\s*(the\s*)?call|phone\s*rakh|\bbye\b|alvida|rakh(ta|ti)\s*hoo?n|hang\s*up|disconnect"
END_DONE = r"dhanyavaad|dhanyawad|dhanyabad|shukriya|thank\s*you|thanks|bas\s*itn|ho\s*gaya|nothing\s*else|aur\s*kuch\s*nahi|that'?s\s*all|koi\s*sawal\s*nahi"
# bank topics that belong to existing customers, complaints or collections: the full assistant handles them
LEGACY_IDS = {"status_check", "payment_how", "existing_loan", "closure_papers", "app_issue", "complaint", "harassment", "dispute_loan",
              "late_fee", "overdue_collections", "hardship", "abusive"}
SKIP_IDS = {"how_apply", "wrong_number", "new_job", "not_heard", "not_understood", "off_topic"}      # these misfire on plain answers

NUM = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "cheh": 6, "chhe": 6, "saat": 7,
       "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10, "dus": 10, "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
       "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20, "pachees": 25, "pachchis": 25, "tees": 30, "chalis": 40,
       "paintalis": 45, "pachas": 50, "pachaas": 50, "saath": 60, "sattar": 70, "pachhattar": 75, "assi": 80, "nabbe": 90,
       "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20,
       "thirty": 30, "forty": 40, "fifty": 50, "dedh": 1.5, "dhai": 2.5, "adhai": 2.5, "sava": 1.25, "aadha": 0.5, "half": 0.5}
MULT = {"sau": 100, "hundred": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "thousand": 1000, "k": 1000, "lakh": 100000, "laakh": 100000,
        "lac": 100000, "lacs": 100000, "lakhs": 100000, "laakhon": 100000, "crore": 10_000_000, "karod": 10_000_000, "cr": 10_000_000}
YES = {"haan", "han", "ha", "haa", "ji", "yes", "yeah", "yep", "theek", "thik", "sahi", "bilkul", "correct", "right", "ok", "okay", "zaroor", "kijiye", "karo", "kar"}
NO = {"nahi", "nahin", "nhi", "nai", "no", "mat", "na", "galat", "wrong", "incorrect", "nope"}
STOP = {"mera", "meraa", "naam", "name", "nam", "is", "hai", "hain", "main", "mai", "my", "the", "ji", "sir", "madam", "full", "i", "am", "hu", "hoon", "hun",
        "bol", "raha", "rahi", "rha", "rhi", "se", "ka", "ki", "toh", "to", "haan", "han", "ha", "yes", "sorry", "bhai", "aur", "and", "please", "plz", "mujhe", "hello", "namaste"}
LOAN_WORDS = [("payday", r"pay\s*-?\s*day|pe\s*day|पेडे|पे डे|\bp\.?\s?d\.?\s+loan|paid\s+loan|\bpedey?\b|\bpayd\b"), ("salary", r"salary\s+(?:loan|advance)|advance\s+salary|सैलरी\s+लोन"),
              ("personal", r"personal|पर्सनल"), ("home", r"home\s+loan|\bghar\b|property|makaan|मकान|होम"), ("business", r"business\s+loan|\bvyapar|vyapaar|\bdhandh|बिज़नेस\s+लोन"),
              ("vehicle", r"vehicle|\bcar\b|\bbike\b|gaadi|gadi|auto loan"), ("gold", r"\bgold\b|\bsona\b|सोना|गोल्ड")]
SALARIED = r"salar|naukri|nokri|\bjob\b|employee|private|sarkari|government|company|नौकरी|सैलरी"
SELF = r"business|dukaan|dukan|shop|self\s*-?\s*employ|vyapar|vyapaar|dhandha|dhanda|apna\s+kaam|freelanc|दुकान|बिज़नेस|व्यापार"


def _words(text: str) -> list:
    return re.findall(r"[a-z]+|\d+(?:\.\d+)?", text.lower())


def digits_from_speech(text: str) -> str:
    """Every digit in what was said: '9', 'nau', 'shoony', and 'double 9' (= 99) / 'triple 0' (= 000)."""
    def rep(m):
        n = 2 if m.group(1).lower() in ("double", "dabal", "dubal") else 3
        return (" " + m.group(2) + " ") * n

    t = re.sub(r"\b(double|dabal|dubal|triple|treble)\s+(\w+)", rep, text, flags=re.I)
    return re.sub(r"\D", "", db.spoken_digits(t))


def parse_amount(text: str):
    """'paanch laakh' / '5 lakh' / '2.5 lakh' / '50 hazaar' / '500000' -> rupees (int), or None if no amount is present.
    A small number with no lakh / hazaar / crore after it ("ek taarikh") is not part of an amount."""
    if re.search(r"\d{9,}", text.replace(",", "").replace(" ", "")):          # a phone number, not an amount
        return None
    words = _words(text.replace(",", ""))
    total, cur, found = 0.0, None, False
    for w in words:
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            cur = float(w)
            if cur >= 1000:                                   # plain digits such as 500000
                total, cur, found = total + cur, None, True
        elif w in NUM:
            cur = NUM[w] if (cur is None or w in ("dedh", "dhai", "adhai", "sava")) else cur + NUM[w]
        elif w in MULT and (cur is not None or w in ("lakh", "laakh", "lac", "hazaar", "crore", "karod")):
            total, cur, found = total + (1 if cur is None else cur) * MULT[w], None, True
        else:
            cur = None if w not in NUM and w not in MULT else cur
    return int(total) if found and total >= 1000 else None


def yes_no(text: str):
    w = set(_words(text))
    if w & NO:
        return "no"
    if w & YES:
        return "yes"
    return None


def parse_name(text: str, strict: bool):
    t = text.lower().strip()
    m = (re.search(r"(?:mera|meraa|my)\s+(?:full\s+)?(?:naam|nam|name)\s+(?:is\s+|hai\s+)?([a-z .]{2,40}?)(?:\s+(?:hai|hain|hu|hoon|hun|aur|and|bol|se|ka|ki|ko|mujhe|me|mein|ye|yeh)\b|[,.!?]|$)", t)
         or re.search(r"(?:i am|i'm|main|mai)\s+([a-z .]{2,30}?)\s+(?:bol|hoon|hu|hun|here|speaking)", t)
         or re.search(r"(?:naam|name)\s+([a-z .]{2,30})", t))
    cand = m.group(1) if m else (t if strict and len(t.split()) <= 5 else "")
    end = {"hai", "hain", "hu", "hoon", "hun", "aur", "and", "mujhe", "loan", "chahiye", "chahie", "kya", "kaise", "kitna", "ka", "ki", "ko", "se", "mein", "me",
           "ye", "yeh", "bol", "salary", "personal", "payday", "business", "job"}
    toks = []
    for w in re.findall(r"[a-z]+", cand):                         # the name ends at the first filler word after it ("priya hai aur mujhe ...")
        if w in end and toks:
            break
        if w not in STOP and len(w) > 1:
            toks.append(w)
    return " ".join(toks[:4]).title() if toks else None


def parse_city(text: str):
    low = text.lower()
    import difflib

    for c in forms.CITIES:
        if re.search(r"\b" + re.escape(c.lower()) + r"\b", low):
            return c
    words = re.findall(r"[a-z]{4,}", low)
    for w in words:
        hit = difflib.get_close_matches(w.title(), forms.CITIES, n=1, cutoff=0.82)
        if hit:
            return hit[0]
    return None


_C = {"b": "ब", "c": "क", "d": "द", "f": "फ", "g": "ग", "h": "ह", "j": "ज", "k": "क", "l": "ल", "m": "म", "n": "न", "p": "प", "q": "क", "r": "र",
      "s": "स", "t": "त", "v": "व", "w": "व", "x": "क्स", "y": "य", "z": "ज़"}
_C2 = {"sh": "श", "ch": "च", "kh": "ख", "gh": "घ", "th": "थ", "dh": "ध", "bh": "भ", "ph": "फ", "jh": "झ"}
_V = {"aa": "ा", "ai": "ै", "au": "ौ", "ee": "ी", "oo": "ू", "a": "", "i": "ि", "u": "ु", "e": "े", "o": "ो"}
_VI = {"aa": "आ", "ai": "ऐ", "au": "औ", "ee": "ई", "oo": "ऊ", "a": "अ", "i": "इ", "u": "उ", "e": "ए", "o": "ओ"}


_KNOWN = {"verma": "वर्मा", "singh": "सिंह", "kumar": "कुमार", "patel": "पटेल", "yadav": "यादव", "sharma": "शर्मा", "gupta": "गुप्ता", "khan": "खान",
          "rahul": "राहुल", "priya": "प्रिया", "amit": "अमित", "ajay": "अजय", "vijay": "विजय", "sanjay": "संजय", "ramesh": "रमेश", "suresh": "सुरेश",
          "mahesh": "महेश", "rakesh": "राकेश", "mukesh": "मुकेश", "deepak": "दीपक", "anil": "अनिल", "sunil": "सुनील", "rajesh": "राजेश", "manoj": "मनोज",
          "pooja": "पूजा", "neha": "नेहा", "sunita": "सुनीता", "anita": "अनीता", "kavita": "कविता", "sita": "सीता", "ravi": "रवि", "rohan": "रोहन",
          "rohit": "रोहित", "mohit": "मोहित", "ankit": "अंकित", "gaurav": "गौरव", "saurabh": "सौरभ", "mishra": "मिश्रा", "joshi": "जोशी", "jain": "जैन",
          "agarwal": "अग्रवाल", "meena": "मीना", "chauhan": "चौहान", "rathore": "राठौड़", "shekhawat": "शेखावत", "mehta": "मेहता", "shah": "शाह",
          "reddy": "रेड्डी", "nair": "नायर", "iyer": "अय्यर", "das": "दास", "ali": "अली", "ahmed": "अहमद", "mohammed": "मोहम्मद", "arjun": "अर्जुन",
          "pankaj": "पंकज", "nitin": "नितिन", "vikas": "विकास", "vikram": "विक्रम", "kiran": "किरण", "ritu": "ऋतु", "anjali": "अंजलि", "ritesh": "रितेश"}


def devanagari_name(name: str) -> str:
    """'Gaurav Sharma' -> 'गौरव शर्मा' so the Hindi voice reads a name written in English letters correctly (approximate; for speech only)."""
    out = []
    for word in re.findall(r"[A-Za-z]+", name or ""):
        w, i, res, prev_cons = word.lower(), 0, "", False
        if w in _KNOWN:
            out.append(_KNOWN[w])
            continue
        while i < len(w):
            two = w[i:i + 2]
            if two in _C2 or w[i] in _C:
                if prev_cons:
                    res += "्"
                res += _C2.get(two) or _C[w[i]]
                i += 2 if two in _C2 else 1
                prev_cons = True
                continue
            v = two if two in _V else w[i]
            if v == "a" and i == len(w) - 1 and prev_cons and len(w) > 3:
                res += "ा"                                           # final 'a' of Sharma, Priya, Gupta ... is long
            elif prev_cons:
                res += _V.get(v, "")
            else:
                res += _VI.get(v, "")
            i += len(v)
            prev_cons = False
        out.append(res)
    return " ".join(out)


def speak_time(text: str) -> str:
    """A callback time said in Roman Hinglish, written in Devanagari so the voice can say it back ('aadhe ghante baad' -> 'आधे घंटे बाद')."""
    low = text.lower()
    words = set(re.findall(r"[a-z0-9]+", low))
    out = []
    if re.search(r"aadh[ie]\s*ghant|half\s*(an\s*)?hour|30\s*min", low):
        out.append("आधे घंटे बाद")
    elif re.search(r"\b(ek|1|one)\s*ghant|\bone\s*hour|\b1\s*hour", low):
        out.append("एक घंटे बाद")
    elif re.search(r"\b(do|2|two)\s*ghant|\btwo\s*hours?", low):
        out.append("दो घंटे बाद")
    for ws, hi in ((("abhi", "now"), "अभी"), (("aaj", "today"), "आज"), (("kal", "tomorrow"), "कल"), (("parso", "parson"), "परसों"),
                   (("subah", "morning", "savere"), "सुबह"), (("dopahar", "dophar", "afternoon"), "दोपहर"), (("shaam", "sham", "evening"), "शाम"),
                   (("raat", "night"), "रात")):
        if words & set(ws):
            out.append(hi)
    m = re.search(r"\b(\d{1,2}|ek|do|teen|char|chaar|paanch|panch|chhe|saat|aath|nau|das|gyarah|barah)\s*baje", low)
    if m:
        n = m.group(1)
        out.append(f"{n if n.isdigit() else NUM.get(n, '')} बजे")
    return " ".join(out)


def static_sentences() -> list:
    """Every sentence the flow can say that does not depend on the caller (plus the common names and amounts), so the server can
    record them at start-up and play them instantly instead of waiting for the voice engine."""
    import json

    out = []
    for qs in QUESTIONS.values():
        out += qs
    out += ACKS
    out += ["धन्यवाद, नंबर कन्फ़र्म हो गया।", "ठीक है जी, कोई बात नहीं। कृपया अपना मोबाइल नंबर एक बार फिर, धीरे-धीरे बोलिए।",
            "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई।", "जी, लोन के बारे में मैं आपकी पूरी मदद करूँगी।",
            "कृपया नंबर दोबारा, धीरे-धीरे बोलिए।", "पूरा दस अंकों का नंबर चाहिए।",
            "ठीक है जी, मैंने नोट कर लिया, हमारी टीम आपको उसी समय कॉल करेगी।",
            "ठीक है जी, आपकी जानकारी नोट हो गई है और हमारी टीम जल्दी आपसे संपर्क करेगी।", "ठीक है जी, जितनी जानकारी मिली है वो मैंने नोट कर ली है।",
            "जी, मैं ठीक से समझ नहीं पाई। क्या आप अपनी बात एक बार फिर बता सकते हैं?",
            "जी, आप चाहें तो स्क्रीन पर फ़ॉर्म सबमिट कर दीजिए, हमारी टीम जल्दी आपसे संपर्क करेगी।",
            "यह नंबर सही नहीं लग रहा, मोबाइल नंबर छह, सात, आठ या नौ से शुरू होता है। कृपया नंबर दोबारा बोलिए।"]
    out += [f"अभी तक {n} अंक मिले हैं, बाकी के अंक भी बता दीजिए।" for n in range(1, 10)]
    try:
        with open(replybank.BANK_PATH, encoding="utf-8") as f:
            for e in json.load(f)["entries"]:
                out.append(e["reply"])
                out.append(_drop_trailing_questions(e["reply"]))
    except (OSError, ValueError, KeyError):
        pass
    for k in sorted(_KNOWN):
        out.append(f"धन्यवाद {_KNOWN[k]} जी।")
    for amt in (10000, 20000, 25000, 30000, 50000, 75000, 100000, 150000, 200000, 250000, 300000, 400000, 500000, 750000, 1000000):
        out.append(f"जी, {amt} रुपये, नोट कर लिया।")
    out.append("ठीक है।")
    seen, flat = set(), []
    for text in out:
        for s in voice.split_sentences(text):
            if s not in seen:
                seen.add(s)
                flat.append(s)
    return flat


def _drop_trailing_questions(text: str) -> str:
    """The flow asks its own next question, so an approved answer keeps its statements and loses a question at the end."""
    sents = voice.split_sentences(text)
    while len(sents) > 1 and sents[-1].rstrip().endswith("?"):
        sents.pop()
    return " ".join(sents)


class Flow:
    def __init__(self, call):
        self.call = call
        self.asked = "full_name"          # the slot the last question was about
        self.v = {}                       # captured values
        self.skipped = set()
        self.fails = {}
        self.phone_pending = None
        self.phone_buf = ""                # digits heard so far while the number is still being said
        self.done = False
        self.unclear_after_done = 0
        self.told = set()                 # approved answers already given in this call

    # -------------------------------------------------------------- saving
    def _save(self, core=None, details=None, **extra):
        args = dict(core or {})
        if details:
            args["details"] = [{"label": k, "value": str(val)} for k, val in details.items()]
        args.update(extra)
        res = self.call._run_tool("update_form", args)
        return res

    def _sync_reason(self):
        lt, amt = self.v.get("loan_type"), self.v.get("loan_amount")
        if not (lt or amt):
            return
        reason = "Wants " + (f"a {lt} loan" if lt else "a loan") + (f" of {amt} rupees" if amt else "")
        if self.v.get("city"):
            reason += f", in {self.v['city']}"
        self._save({"category": "new_loan_enquiry", "reason": reason})

    def _name(self):
        n = self.v.get("full_name") or self.call.form.get("full_name") or ""
        return devanagari_name(n.split()[0]) if n else ""

    # ----------------------------------------------------------- main entry
    def handle(self, text: str):
        """Reply text for this turn, or None if the full assistant should answer."""
        c = self.call
        if self.v.get("full_name") is None and c.form.get("full_name"):
            self.v["full_name"] = c.form["full_name"]
        text = (text or "").strip()
        low = text.lower()
        captured, ack = [], None

        # --- the caller wants to end the call: say one closing line; the server then plays the thank-you and the call ends
        if re.search(END_NOW, low) or (self.done and re.search(END_DONE, low)):
            c.finished = True
            if self.done:
                return "ठीक है जी, आपकी जानकारी नोट हो गई है और हमारी टीम जल्दी आपसे संपर्क करेगी।"
            return "ठीक है जी, जितनी जानकारी मिली है वो मैंने नोट कर ली है।"

        # --- phone read-back answer
        if self.asked == "phone_confirm" and self.phone_pending:
            yn = yes_no(text)
            if yn == "yes":
                self._save(confirmed=["phone"])
                self.v["phone"] = self.phone_pending
                self.phone_pending, self.asked = None, None
                ack = "धन्यवाद, नंबर कन्फ़र्म हो गया।"
            elif yn == "no":
                c.form.pop("phone", None)
                c.confirmed.discard("phone")
                self.phone_pending, self.asked = None, "phone"
                return "ठीक है जी, कोई बात नहीं। कृपया अपना मोबाइल नंबर एक बार फिर, धीरे-धीरे बोलिए।"
            # anything else: treat as a new utterance below, keep waiting for the confirmation
            elif not (set(_words(low)) & {"nau", "do", "teen", "char"} or re.search(r"\d{5,}", low)):
                pass

        # --- approved reply for a question or special request
        bank = [m for m in replybank.match(text) if m["score"] >= 0.6 and m["id"] not in SKIP_IDS]
        # "call me in half an hour" must never be mistaken for "do not call me": stopping needs an explicit refusal word
        strong = re.search(r"\b(mat|band|stop|dnd|do\s+not|don't|dont|not\s+interested|nahin\s+chahiye|nahi\s+chahiye|nhi\s+chahiye)\b", low)
        if self.asked in ("callback_time", "consent") and not re.search(r"\b(mat|stop|dnd|do\s+not|don't|dont|not\s+interested|band)\b", low):
            strong = None
        if not strong:
            bank = [m for m in bank if m["id"] not in ("stop_calling", "not_interested")]
        if self.asked in ("callback_time", "phone", "phone_confirm", "consent", "existing_loans") and not strong:
            bank = []                                                   # in these steps the caller's words are the answer, not a question
        ids = [m["id"] for m in bank]
        if "stop_calling" in ids or "not_interested" in ids:
            entry = next(m for m in bank if m["id"] in ("stop_calling", "not_interested"))["entry"]
            if entry["id"] == "stop_calling":
                self._save({"consent_to_contact": "no"})
                try:
                    c._run_tool("request_callback", {"note": "DO NOT CALL: caller asked to stop calling"})
                except Exception:
                    pass
            c.finished = True
            return entry["reply"]

        # --- extraction: only when the value is clearly present or the question asked for it
        asked = self.asked
        core, details = {}, {}
        # the name is asked for in the greeting: always try it until captured
        if "full_name" not in self.v:
            n = parse_name(text, strict=(asked == "full_name" and not bank))
            if n is None and re.search(r"[ऀ-ॿ]", text) and asked == "full_name":
                n = self._llm_name(text)
            if n:
                core["full_name"] = n
                captured.append("full_name")
        for lt, pat in LOAN_WORDS:
            if re.search(pat, low):
                if "loan_type" not in self.v or asked == "loan_type":
                    details["loan_type"] = lt
                    captured.append("loan_type")
                break
        income_re = r"salary|income|kamat|kamai|tankhw|mahin|monthly|महीने|सैलरी|कमाई"
        loan_re = r"loan|lakh|laakh|hazaar|rupe|rs\b|chahiye|chahie|paisa|paise|लोन"
        for clause in re.split(r"[.;!?]|\b(?:aur|and|but|lekin|par)\b", text):
            amt = parse_amount(clause)
            if not amt:
                continue
            plain = re.sub(r"salary\s+(?:loan|advance)|advance\s+salary|सैलरी\s+लोन", " ", clause.lower())     # "salary loan" is a product, not income
            if re.search(income_re, plain) or asked == "monthly_income":
                target = "monthly_income"
            elif asked == "loan_amount" or re.search(loan_re, plain):
                target = "loan_amount"
            else:
                continue
            if target not in self.v or asked == target:
                details[target] = amt
                captured.append(target)
        emp = None
        if asked == "employment" or re.search(SELF, low) and not re.search(r"business\s+loan", low) or re.search(r"naukri|nokri|\bjob\b", low):
            emp = "self-employed" if re.search(SELF, low) and not re.search(SALARIED.replace("company|", ""), low.replace("salary", "")) else ("salaried" if re.search(SALARIED, low) else None)
            if asked == "employment" and emp is None and re.search(SELF, low):
                emp = "self-employed"
        if emp and ("employment" not in self.v or asked == "employment"):
            details["employment_type"] = emp
            captured.append("employment")
        city = parse_city(text)
        if city and ("city" not in self.v or asked == "city"):
            details["city"] = city
            captured.append("city")
        elif asked == "city" and not city and 0 < len(re.findall(r"[a-z]+", low)) <= 2 and not bank:
            details["city"] = " ".join(re.findall(r"[a-z]+", low)).title()
            captured.append("city")
        if asked == "existing_loans":
            yn = yes_no(text)
            if yn:
                details["existing_loans"] = yn
                captured.append("existing_loans")
        digits = digits_from_speech(text)
        if asked == "phone_confirm" and len(digits) >= 10:
            self.phone_pending = digits[-10:]
            if forms.clean("phone", self.phone_pending)[0]:
                core["phone"] = self.phone_pending
                captured.append("phone")
        elif asked == "phone" or len(digits) >= 10:
            buf = (self.phone_buf if asked == "phone" else "") + digits
            if asked == "phone" and digits and re.search(r"\b(galat|wrong|dobara|again|restart|phir\s*se|naya|naye|shuru)\b", low):
                buf = digits                                              # the caller starts the number again
            if len(buf) >= 10:
                self.phone_buf = ""
                self.phone_pending = buf[-10:]
                if forms.clean("phone", self.phone_pending)[0]:
                    core["phone"] = self.phone_pending
                    captured.append("phone")
                else:
                    return "यह नंबर सही नहीं लग रहा, मोबाइल नंबर छह, सात, आठ या नौ से शुरू होता है। कृपया नंबर दोबारा बोलिए।"
            elif asked == "phone" and digits:
                self.phone_buf = buf                                      # keep what was said: the caller may be mid-number
                return f"अभी तक {len(buf)} अंक मिले हैं, बाकी के अंक भी बता दीजिए।"
        if asked == "consent":
            yn = yes_no(text)
            if yn:
                core["consent_to_contact"] = yn
                captured.append("consent")
        if asked == "callback_time" and text and not bank:
            core["preferred_callback_time"] = re.sub(r"\s+", " ", text)[:80]
            captured.append("callback_time")

        # --- apply what was captured
        if core or details:
            self._save(core, details)
            for k in captured:
                if k == "full_name":
                    self.v[k] = core["full_name"]
                elif k == "phone":
                    pass                          # confirmed after the read-back
                elif k == "consent":
                    self.v[k] = core["consent_to_contact"]
                elif k == "callback_time":
                    self.v[k] = core["preferred_callback_time"]
                elif k == "employment":
                    self.v[k] = details["employment_type"]
                else:
                    self.v[k] = details[k]
            self._sync_reason()

        # --- the legacy assistant answers existing-customer / complaint / collections topics
        if any(i in LEGACY_IDS for i in ids) and not captured:
            return None

        parts = []
        if "callback_time" in captured and not ack:
            when = speak_time(self.v.get("callback_time", ""))
            ack = f"ठीक है जी, टीम आपको {when} कॉल करेगी।" if when else "ठीक है जी, मैंने नोट कर लिया, टीम आपको उसी समय कॉल करेगी।"
        if ack:
            parts.append(ack)
        elif "full_name" in captured:
            parts.append(f"धन्यवाद {self._name()} जी।")
        elif "loan_amount" in captured:
            parts.append(f"जी, {self.v['loan_amount']} रुपये, नोट कर लिया।")
        elif captured:
            parts.append(random.choice(ACKS))
        elif asked in ("loan_type", "full_name") and re.search(r"loan|लोन|paisa|paise|rupe|udhaar|udhar", low) and not bank:
            parts.append("जी, लोन के बारे में मैं आपकी पूरी मदद करूँगी।")
            self.fails[asked] = -1                                  # not a failure: the caller just has not said which kind yet
        asked_question = False
        for m in bank[:2]:
            if m["id"] in LEGACY_IDS or m["id"] in self.told:            # an approved answer is given once per call: never repeat it
                continue
            self.told.add(m["id"])
            reply = m["entry"]["reply"]
            if self._next() is not None:
                reply = _drop_trailing_questions(reply)
            parts.append(reply)
            asked_question = asked_question or reply.rstrip().endswith("?")

        if c.more_coming:                                               # the caller is still speaking: brief acknowledgement only
            return " ".join(parts[:1]) or random.choice(ACKS)

        if "phone" in captured:                                         # read the number back before trusting it
            self.asked = "phone_confirm"
            parts.append(f"आपका नंबर {self.phone_pending} है, क्या यह सही है?")
            return " ".join(parts)
        if self.asked == "phone_confirm" and self.phone_pending:
            parts.append(f"मैं दोबारा पढ़ती हूँ, आपका नंबर {self.phone_pending} है, क्या यह सही है?")
            return " ".join(parts)

        if captured == ["callback_time"] or ("consent" in captured and self.v.get("consent") == "no"):
            if self.v.get("consent") == "yes" and self.v.get("callback_time"):
                try:
                    c._run_tool("request_callback", {"note": f"{self.call.form.get('full_name', '')}: {self.call.form.get('reason', '')}; call back: {self.v['callback_time']}"})
                except Exception:
                    pass

        nxt = self._next()
        if nxt is None:
            if not self.done:
                self.done = True
                parts.append(f"बहुत शुक्रिया {self._name()} जी, आपकी सारी डिटेल्स नोट हो गई हैं। कृपया स्क्रीन पर फ़ॉर्म देखकर सबमिट बटन दबा दीजिए। और कुछ पूछना हो तो बताइए।")
            elif not parts:                                              # everything is collected and the caller said something we cannot place
                self.unclear_after_done += 1
                if self.unclear_after_done == 1:
                    return "जी, मैं ठीक से समझ नहीं पाई। क्या आप अपनी बात एक बार फिर बता सकते हैं?"
                return "जी, आप चाहें तो स्क्रीन पर फ़ॉर्म सबमिट कर दीजिए, हमारी टीम जल्दी आपसे संपर्क करेगी।"
            self.asked = None
            return " ".join(parts)
        if asked_question and nxt == self.asked:
            return " ".join(parts)                                      # the approved answer already ends with a question
        self.fails[nxt] = self.fails.get(nxt, 0) + (1 if (nxt == self.asked and not captured) else 0)
        if self.fails.get(nxt, 0) >= 3:                                  # the caller keeps not answering this one: move on
            self.skipped.add(nxt)
            nxt = self._next()
            if nxt is None:
                return " ".join(parts) or random.choice(ACKS)
        self.asked = nxt
        question = random.choice(QUESTIONS[nxt])
        if nxt == self.asked and not captured and not bank and self.fails.get(nxt, 0) >= 1:
            parts.append("माफ़ कीजिए, मैं ठीक से समझ नहीं पाई।")
        if nxt == "consent":
            question = f"{self._name()} जी, " + question if self._name() else question
        parts.append(question)
        return " ".join(parts)

    def _next(self):
        for s in SLOTS:
            if s == "callback_time" and self.v.get("consent") != "yes":
                continue
            if s in self.v or s in self.skipped:
                continue
            if s == "phone" and self.call.form.get("phone") and "phone" in self.call.confirmed:
                continue
            if s == "monthly_income" and self.v.get("employment") is None and False:
                continue
            return s
        return None

    def _llm_name(self, text: str):
        """A name said in Devanagari must be written in English letters for the form."""
        try:
            import json

            import brain

            r = brain._llm.chat.completions.create(model=brain.LLM_MODEL, response_format={"type": "json_object"}, max_tokens=60, temperature=0,
                                                   messages=[{"role": "user", "content": 'The caller said (Hindi): "%s". Reply ONLY JSON {"name": "<their name written in English letters, or empty>"}.' % text}])
            name = json.loads(r.choices[0].message.content).get("name", "")
            return name.title() if re.fullmatch(r"[A-Za-z .]{2,40}", name or "") else None
        except Exception:
            return None


if __name__ == "__main__":      # typed test: python flow.py   (uses the real Call, needs LLM env only for non-flow turns)
    import sys

    import brain

    sys.stdout.reconfigure(encoding="utf-8")
    call = brain.Call("enquiry", on_form=lambda v, ch, f, k: print("   [form]", v))
    call.start_with("नमस्ते, मैं रिया हूँ। कृपया अपना पूरा नाम बताइए।")
    while True:
        print("Ria:", call.reply(input("You: ")))
