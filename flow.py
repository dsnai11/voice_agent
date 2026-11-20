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

FREE_RULES = ("तुम रिया हो, लक्ष्मी इंडिया फाइनेंस लिमिटेड की फ़ोन असिस्टेंट (महिला, एआई)। कॉलर ने अभी जो पूछा या कहा है उसका सीधा, सही और विनम्र जवाब दो।\n"
              "- हिंग्लिश में बोलो: आसान रोज़ की हिंदी देवनागरी में, लोन, ईएमआई, सैलरी, सिबिल जैसे अंग्रेज़ी शब्द भी देवनागरी में लिखो। अगर कॉलर पूरी अंग्रेज़ी में बोले तो अंग्रेज़ी में जवाब दो।\n"
              "- जवाब सिर्फ़ 1 से 2 छोटे वाक्यों का हो। कोई मार्कडाउन, लिस्ट या इमोजी नहीं। अपने लिए स्त्रीलिंग (करती हूँ, बताती हूँ) और कॉलर के लिए लिंग-निरपेक्ष शब्द, नाम के बाद 'जी'।\n"
              "- कंपनी, लोन के नियम, दस्तावेज़, चार्ज, सिबिल, ईएमआई वगैरह के बारे में सिर्फ़ नीचे लिखे तथ्यों और सामान्य, सरल समझाइश से जवाब दो। जो तथ्यों में नहीं है, उसके लिए साफ़ कहो कि टीम कन्फ़र्म करेगी। कोई नंबर, रेट, फ़ीस या तारीख़ अपनी तरफ़ से मत बनाओ।\n"
              "- लोन पास होने, रेट, लिमिट या समय का कोई वादा मत करो। ओटीपी, पिन, पासवर्ड कभी मत माँगो।\n"
              "- 'कैसे हो', 'धन्यवाद', 'कुछ और बात करनी है' जैसी बातों का छोटा, गर्मजोशी वाला जवाब दो और कहो कि वे बताएँ।\n"
              "- कॉलर से कोई नई जानकारी (नाम, नंबर, राशि) मत माँगो; वह फ़ॉर्म में अलग से पूछी जाती है।\n"
              "- अगर सवाल फ़ाइनेंस या बैंकिंग का है और जवाब नीचे के तथ्यों या सामान्य जानकारी में है, तो पूरा, साफ़ और सरल जवाब दो। अगर पक्का नहीं पता, तो ईमानदारी से कहो: इसके बारे में मुझे अभी पक्का नहीं पता, मैं इसे टीम से कन्फ़र्म करवा दूँगी। अंदाज़ा कभी मत लगाओ।\n"
              "- अगर सवाल फ़ाइनेंस या बैंकिंग से बिल्कुल अलग है (मौसम, क्रिकेट, राजनीति, धर्म, फ़िल्म), तो विनम्रता से कहो कि तुम सिर्फ़ लोन और फ़ाइनेंस में मदद कर सकती हो।\n")
COMPANY_INFO = ""
try:
    import os as _os
    with open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "knowledge", "company_info.txt"), encoding="utf-8") as _f:
        COMPANY_INFO = _f.read().strip()
except OSError:
    pass
GENERAL_FINANCE = ""
try:
    with open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "knowledge", "general_finance.txt"), encoding="utf-8") as _f:
        GENERAL_FINANCE = _f.read().strip()
except OSError:
    pass
OFF_LINE = "जी, मैं सिर्फ़ लक्ष्मी इंडिया फाइनेंस और लोन-बैंकिंग से जुड़ी बातें करती हूँ। इससे जुड़ा कोई काम हो तो बताइए, मैं ज़रूर मदद करूँगी। बाकी बातों के लिए आप हमारे कस्टमर हेल्पलाइन नंबर एक आठ शून्य शून्य, एक दो एक, सात सात चार सात पर बात कर सकते हैं।"
UNSURE = "इसके बारे में मुझे अभी पक्का नहीं पता, मैं इसे टीम से कन्फ़र्म करवा दूँगी।"

SLOTS = ["full_name", "loan_type", "loan_amount", "loan_purpose", "employment", "monthly_income", "work_tenure", "city", "existing_loans", "existing_emi", "phone", "consent", "callback_time"]

QUESTIONS = {
    "loan_purpose": ["ये लोन किस काम के लिए चाहिए?", "लोन किस ज़रूरत के लिए ले रहे हैं आप?"],
    "existing_emi": ["सब ईएमआई मिलाकर महीने की कितनी जाती है, लगभग?", "महीने में कुल कितनी ईएमआई भरते हैं आप, लगभग?"],
    "full_name": ["कृपया अपना पूरा नाम बताइए।"],
    "loan_type": ["अच्छा, कौन सा लोन चाहिए आपको, पर्सनल, पेडे या सैलरी?", "कौन सा लोन देख रहे हैं आप, पर्सनल, पेडे या सैलरी लोन?"],
    "loan_amount": ["कितनी रकम चाहिए आपको, लगभग?", "रकम कितनी चाहिए, लगभग कितने रुपये का लोन?"],
    "employment": ["आप जॉब करते हैं या अपना बिज़नेस है?", "आप सैलरी वाले हैं या अपना बिज़नेस करते हैं?"],
    "monthly_income": ["महीने की सैलरी या कमाई लगभग कितनी है?", "हर महीने की इनकम लगभग कितनी होती है?"],
    "city": ["आप किस शहर में रहते हैं?", "आप कौन से शहर से हैं?"],
    "existing_loans": ["कोई और लोन या ईएमआई अभी चल रही है क्या?", "अभी कोई और लोन चल रहा है आपका?"],
    "phone": ["आपका मोबाइल नंबर बता दीजिए।", "अब मोबाइल नंबर बोल दीजिए, धीरे-धीरे।"],
    "consent": ["क्या हमारी टीम आपको इसी नंबर पर कॉल कर सकती है?", "हमारी टीम आपको कॉल करके आगे की जानकारी दे दे, चलेगा?"],
    "callback_time": ["कब कॉल करवाऊँ, कौन सा दिन और टाइम ठीक रहेगा?", "किस दिन और किस टाइम पर कॉल करें?"],
}
INCOME_Q = {
    "salaried": ["महीने की सैलरी लगभग कितनी आ जाती है?", "आपकी महीने की सैलरी लगभग कितनी है?"],
    "self-employed": ["बिज़नेस से महीने की इनकम लगभग कितनी हो जाती है?", "बिज़नेस से महीने की कमाई लगभग कितनी हो जाती है?"],
    "pensioner": ["महीने की पेंशन लगभग कितनी आती है?"],
    "not-earning": ["आपके परिवार की महीने की कुल इनकम लगभग कितनी है?"],
}
TENURE_Q = {
    "salaried": ["अभी की कंपनी में कितने समय से हैं आप?", "इस कंपनी में कितने टाइम से काम कर रहे हैं?"],
    "self-employed": ["बिज़नेस कितने साल से चल रहा है आपका?"],
}
# answers that must change with the caller's work type (the general ones above assume a salaried person)
ALT_REPLIES = {
    ("documents", "self-employed"): "जी, अपना बिज़नेस करने वालों के लिए आमतौर पर आधार या पैन जैसा आईडी प्रूफ, एड्रेस प्रूफ, पिछले छह महीने का बैंक स्टेटमेंट, बिज़नेस का प्रूफ और आईटीआर जैसे इनकम के कागज़ लगते हैं। सही लिस्ट टीम कन्फ़र्म करेगी।",
    ("documents", "pensioner"): "जी, पेंशनर के लिए आमतौर पर आईडी प्रूफ, एड्रेस प्रूफ, पेंशन सर्टिफ़िकेट या पेंशन की पर्ची और बैंक स्टेटमेंट लगता है। सही लिस्ट टीम कन्फ़र्म करेगी।",
    ("documents", "not-earning"): "जी, आमतौर पर आईडी प्रूफ, एड्रेस प्रूफ, बैंक स्टेटमेंट और घर में कमाने वाले, यानी को-एप्लिकेंट, के इनकम के कागज़ लगते हैं। सही लिस्ट टीम कन्फ़र्म करेगी।",
    ("low_salary", "self-employed"): "जी, बिज़नेस करने वालों की इनकम उनके बैंक स्टेटमेंट और आईटीआर जैसे कागज़ों से देखी जाती है, और सही रकम टीम चेक करके बताएगी।",
    ("low_salary", "pensioner"): "जी, पेंशनर की इनकम पेंशन और बैंक स्टेटमेंट से देखी जाती है, और सही रकम टीम चेक करके बताएगी।",
    ("new_job", "self-employed"): "जी, बिज़नेस वालों के लिए आमतौर पर कम से कम दो साल का बिज़नेस देखा जाता है।",
}
EXAMPLES = {"work_tenure": "आप बस बोल दीजिए, जैसे दो साल या छह महीने।", "loan_purpose": "आप बस एक-दो शब्द में बता दीजिए, जैसे मेडिकल, शादी या घर की मरम्मत।", "existing_emi": "आप बस रकम बोल दीजिए, जैसे पाँच हज़ार।", "full_name": "जैसे, मेरा नाम अर्जुन शर्मा है।", "loan_type": "आप बस पर्सनल, पेडे या सैलरी बोल दीजिए।", "loan_amount": "आप बस रकम बोल दीजिए, जैसे पाँच लाख।",
            "employment": "आप बस नौकरी या बिज़नेस बोल दीजिए।", "monthly_income": "आप बस रकम बोल दीजिए, जैसे पचास हज़ार।", "city": "आप बस शहर का नाम बोल दीजिए, जैसे जयपुर।",
            "existing_loans": "आप बस हाँ या ना बोल दीजिए।", "phone": "आप दस अंकों का नंबर धीरे-धीरे बोल दीजिए।", "consent": "आप बस हाँ या ना बोल दीजिए।",
            "callback_time": "आप बस दिन और टाइम बोल दीजिए, जैसे कल शाम पाँच बजे।"}
ACKS = ["जी।", "ठीक है।", "अच्छा।", "जी, समझ गई।", "ओके जी।", "जी बिल्कुल।", "अच्छा जी।", "धन्यवाद जी।"]
END_NOW = r"call\s*(kaat|kat\b|cut|band|disconnect|end)|kaat\s*do|cut\s*(the\s*)?call|phone\s*rakh|\bbye\b|alvida|rakh(ta|ti)\s*hoo?n|hang\s*up|disconnect"
END_DONE = r"dhanyavaad|dhanyawad|dhanyabad|shukriya|thank\s*you|thanks|bas\s*itn|ho\s*gaya|nothing\s*else|aur\s*kuch\s*nahi|that'?s\s*all|koi\s*sawal\s*nahi"
# bank topics that belong to existing customers, complaints or collections: the full assistant handles them
LEGACY_IDS = {"status_check", "payment_how", "existing_loan", "closure_papers", "app_issue", "complaint", "harassment", "dispute_loan",
              "late_fee", "overdue_collections", "hardship", "abusive"}
SKIP_IDS = {"how_apply", "wrong_number", "new_job", "not_heard", "not_understood", "off_topic"}      # these misfire on plain answers

NUM = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "cheh": 6, "chhe": 6, "saat": 7,
       "sat": 7, "aath": 8, "ath": 8, "nau": 9, "tin": 3, "teenn": 3, "paach": 5, "chah": 6, "nou": 9, "baarah": 12, "ik": 1, "das": 10, "dus": 10, "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
       "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20, "pachees": 25, "pachchis": 25, "tees": 30, "chalis": 40,
       "paintalis": 45, "pachas": 50, "pachaas": 50, "saath": 60, "sattar": 70, "pachhattar": 75, "assi": 80, "nabbe": 90,
       "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20,
       "thirty": 30, "forty": 40, "fifty": 50, "dedh": 1.5, "dhai": 2.5, "adhai": 2.5, "sava": 1.25, "aadha": 0.5, "half": 0.5}
MULT = {"sau": 100, "hundred": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "thousand": 1000, "k": 1000, "lakh": 100000, "laakh": 100000,
        "lac": 100000, "lacs": 100000, "lakhs": 100000, "laakhon": 100000, "crore": 10_000_000, "karod": 10_000_000, "cr": 10_000_000}
YES = {"haan", "han", "ha", "haa", "hanji", "haanji", "haji", "ji", "yes", "yeah", "yep", "theek", "thik", "sahi", "bilkul", "correct", "right", "ok", "okay", "okey",
       "oke", "kk", "zaroor", "kijiye", "karo", "kar", "de", "dijiye", "chalega", "chalo", "chaliye", "accha", "achha", "acha", "sure", "done", "hmm", "hm", "aage",
       "continue", "proceed"}
ACK_WORDS = YES | {"hai", "to", "toh", "bhai", "abhi", "bas", "thanks", "thank", "you", "fine", "good", "great", "perfect", "nice", "badhiya", "mera", "meri",
                   "taraf", "se", "aap", "chalu", "karein", "karte", "hain", "chal", "ahead", "go", "next", "phir", "fir"}
NO = {"nahi", "nahin", "nhi", "nai", "no", "mat", "na", "galat", "wrong", "incorrect", "nope"}


def is_ack_only(text: str) -> bool:
    """A very short agreement such as 'ok', 'theek hai', 'chalo aage chalo' (it brings no new information)."""
    w = _words(text)
    return 0 < len(w) <= 5 and all(x in ACK_WORDS for x in w)


DOMAIN = {"loan", "lone", "emi", "interest", "byaaj", "byaj", "rate", "cibil", "civil", "score", "credit", "company", "fee", "fees", "charge", "charges", "document",
          "documents", "eligibility", "eligible", "salary", "bank", "payment", "apply", "approval", "approve", "process", "tenure", "paisa", "paise", "rupee", "rupe",
          "rupaye", "lakh", "laakh", "hazaar", "kist", "installment", "penalty", "foreclosure", "prepayment", "insurance", "kyc", "pan", "aadhaar", "aadhar", "branch",
          "office", "nbfc", "rbi", "limit", "amount", "disbursal", "processing", "payday", "overdraft", "guarantor", "collateral", "security", "safe", "trust", "fraud",
          "account", "savings", "current", "fd", "rd", "deposit", "upi", "neft", "rtgs", "imps", "atm", "card", "debit", "cheque", "check", "nach", "mandate", "bounce",
          "kist", "moratorium", "foreclose", "foreclosure", "closure", "apr", "kfs", "cooling", "ombudsman", "complaint", "grievance", "cibil", "bureau", "experian", "equifax",
          "insurance", "mutual", "sip", "tax", "gst", "itr", "pan", "aadhaar", "gold", "property", "mortgage", "vehicle", "business", "msme", "scam", "otp", "kyc", "paise",
          "interest", "sood", "byaj", "karz", "karza", "udhaar", "udhar", "paisa", "rupaya", "rupees", "bank", "banks", "lender", "borrower", "credit", "debt", "dicgc", "nbfcs"}
OFFTOPIC = {"mausam", "weather", "cricket", "match", "movie", "film", "gaana", "song", "khana", "restaurant", "news", "politics", "neta", "election", "modi", "bhagwan", "dharm", "god",
            "joke", "chutkula", "shayari", "biwi", "girlfriend", "boyfriend", "pyaar", "love", "football", "ipl", "weather", "barish", "rain", "hotel", "flight", "ticket"}


def offtopic_like(text: str) -> bool:
    """Clearly not about money: weather, cricket, politics, jokes ... (she politely says she only helps with loans and finance)."""
    w = set(_words(text))
    return bool(w & OFFTOPIC) and not (w & DOMAIN)


def domain_like(text: str) -> bool:
    """True when the caller is asking about loans, money or the company (the only things worth an AI-written answer)."""
    return bool(set(_words(text)) & DOMAIN)


def looks_like_question(text: str) -> bool:
    low = text.lower()
    return "?" in text or bool(re.search(r"\b(kya|kaise|kyun|kyu|kab|kitna|kitni|kitne|kaun|kahan|kaha|what|how|why|when|which|who|where|can|could|batao|bataiye|bataye|samjhao|samjhaiye|matlab|explain|details?|jankari|jaankari|baare|bare|baat|poochna|puchna|company|civil|cibil|score)\b", low))


STOP = {"mera", "meraa", "naam", "name", "nam", "is", "hai", "hain", "main", "mai", "my", "the", "ji", "sir", "madam", "full", "i", "am", "hu", "hoon", "hun",
        "bol", "raha", "rahi", "rha", "rhi", "se", "ka", "ki", "toh", "to", "haan", "han", "ha", "yes", "sorry", "bhai", "aur", "and", "please", "plz", "mujhe", "hello", "namaste"}
LOAN_WORDS = [("payday", r"pay\s*-?\s*day|pe\s*day|पेडे|पे डे|\bp\.?\s?d\.?\s+loan|paid\s+loan|\bpedey?\b|\bpayd\b"), ("salary", r"salary\s+(?:loan|advance)|advance\s+salary|सैलरी\s+लोन"),
              ("personal", r"personal|पर्सनल"), ("home", r"home\s+loan|\bghar\b|property|makaan|मकान|होम"), ("business", r"business\s+loan|\bvyapar|vyapaar|\bdhandh|बिज़नेस\s+लोन"),
              ("vehicle", r"vehicle|\bcar\b|\bbike\b|gaadi|gadi|auto loan"), ("gold", r"\bgold\b|\bsona\b|सोना|गोल्ड")]
SALARIED = r"salar|naukri|nokri|service|sarvice|employed|\bjob\b|employee|private|sarkari|government|company|नौकरी|सैलरी"
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


def parse_amount(text: str, minimum: int = 1000):
    """'paanch laakh' / '5 lakh' / '2.5 lakh' / '50 hazaar' / '500000' -> rupees (int), or None if no amount is present.
    A small number with no lakh / hazaar / crore after it ("ek taarikh") is not part of an amount."""
    if re.search(r"\d{9,}", text.replace(",", "").replace(" ", "")):          # a phone number, not an amount
        return None
    text = re.sub(r"one and a half", "dedh", text, flags=re.I)
    text = re.sub(r"two and a half", "dhai", text, flags=re.I)
    words = _words(text.replace(",", ""))
    for size in (4, 3, 2):                                    # drop an immediately repeated phrase: "5 hazaar 5 hazaar" -> "5 hazaar"
        i = 0
        while i + 2 * size <= len(words):
            if words[i:i + size] == words[i + size:i + 2 * size]:
                del words[i + size:i + 2 * size]
            else:
                i += 1
    words = [w for i, w in enumerate(words) if not (i and w == words[i - 1] and re.fullmatch(r"\d+(?:\.\d+)?", w) and float(w) >= minimum)]   # "5000 5000" said twice is 5000
    total, cur, found = 0.0, None, False
    for w in words:
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            cur = float(w)
            if cur >= minimum:                                # plain digits such as 500000
                total, cur, found = total + cur, None, True
        elif w in NUM:
            cur = NUM[w] if (cur is None or w in ("dedh", "dhai", "adhai", "sava")) else cur + NUM[w]
        elif w in MULT and (cur is not None or w in ("lakh", "laakh", "lac", "hazaar", "crore", "karod")):
            total, cur, found = total + (1 if cur is None else cur) * MULT[w], None, True
        else:
            cur = None if w not in NUM and w not in MULT else cur
    return int(total) if found and total >= minimum else None


def yes_no(text: str):
    w = set(_words(text))
    if w & NO or any(x.startswith(("nah", "nhi", "nhn")) for x in w):
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
    fixes = {"sinh": "singh", "sing": "singh", "singha": "singh", "shrma": "sharma", "sarma": "sharma", "varma": "verma", "kumaar": "kumar", "gupta": "gupta", "yadaw": "yadav",
             "patil": "patil", "pateel": "patel", "jain": "jain", "mishr": "mishra", "tripathy": "tripathi", "chouhan": "chauhan", "chohan": "chauhan"}
    toks = [fixes.get(w, w) for w in toks]
    return " ".join(toks[:4]).title() if toks else None


def parse_employment(text: str, asked):
    """salaried | self-employed | pensioner | not-earning, or None. A businessman is self-employed even if he says 'job' nowhere."""
    low = re.sub(r"(salary|sailri|salry|सैलरी)\s*(loan|advance|lone)|advance\s*salary|payday|pay\s*day", " ", text.lower())      # a loan type, not a job
    if re.search(r"pension|retired|retire\b|sevanivrit|रिटायर|सेवानिवृत्त", low):
        return "pensioner"
    if re.search(r"housewife|house wife|homemaker|grihini|student|padhai|studying|unemployed|berozgar|berojgar|not working|naukri nahi|job nahi|kaam nahi|बेरोज़गार|बेरोजगार", low):
        return "not-earning"
    selfish = re.search(SELF + r"|farmer|kisan|kheti|farming|doctor|lawyer|advocate|\bca\b|professional|freelanc|consultant|contractor|trader|vyapari|shopkeeper|dukandar|self\s*-?\s*employed", low)
    if selfish and not re.search(r"business\s+loan", low):
        plain = re.sub(r"self\s*-?\s*employed", " ", low.replace("salary", ""))          # "self employed" must not count as having an employer
        if re.search(SALARIED.replace("company|", ""), plain):
            return "salaried"
        return "self-employed"
    if re.search(SALARIED, re.sub(r"self\s*-?\s*employed", " ", low)):
        return "salaried"
    return None


def parse_duration_years(text: str):
    """'2 saal', 'do saal se', '6 mahine', 'dedh saal' -> years as a number; None if no duration is said."""
    n = None
    for w in _words(text):
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            n = float(w)
        elif w in NUM:
            n = NUM[w]
        elif w in ("saal", "sal", "year", "years", "yr", "yrs", "varsh", "baras") and n is not None:
            return n
        elif w in ("mahine", "mahina", "mahinon", "month", "months") and n is not None:
            return round(n / 12, 2)
    return None


CITY_ALIASES = {"dilli": "Delhi", "bombay": "Mumbai", "mumbay": "Mumbai", "lakhnau": "Lucknow", "luknow": "Lucknow", "banaras": "Varanasi", "kashi": "Varanasi", "calcutta": "Kolkata",
                "madras": "Chennai", "poona": "Pune", "baroda": "Vadodara", "allahabad": "Prayagraj", "bangalore": "Bengaluru", "bengalooru": "Bengaluru", "gurgaon": "Gurugram",
                "jaypur": "Jaipur", "jaipure": "Jaipur", "udaypur": "Udaipur", "udyapur": "Udaipur", "jodhapur": "Jodhpur", "bhopaal": "Bhopal", "indor": "Indore", "ahmedabad": "Ahmedabad", "amdavad": "Ahmedabad"}
PLACE_FILLER = {"mujhe", "me", "mein", "main", "se", "hoon", "hu", "hun", "wo", "haan", "ji", "rehta", "rehti", "rahta", "rahti", "hai", "ka", "ki", "ke", "mera", "meri", "shahar", "sheher", "city", "bol", "raha", "rahi"}


def clean_place(text: str) -> str:
    """'Mujhe Lakhnau Lakhnau me' -> 'Lakhnau': filler words and repeats removed (for a city that is not in the list)."""
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w not in PLACE_FILLER and w not in out:
            out.append(w)
    return " ".join(out[:2]).title()


def parse_city(text: str, fuzzy: bool = True):
    low = text.lower()
    import difflib

    for c in forms.CITIES:
        if re.search(r"\b" + re.escape(c.lower()) + r"\b", low):
            return c
    words = re.findall(r"[a-z]{4,}", low)
    for w in words:
        if w in CITY_ALIASES:
            return CITY_ALIASES[w]
    if not fuzzy:
        return None
    for w in words:
        hit = difflib.get_close_matches(w.title(), forms.CITIES, n=1, cutoff=0.82)
        if hit:
            return hit[0]
        hit = difflib.get_close_matches(w, list(CITY_ALIASES), n=1, cutoff=0.8)
        if hit:
            return CITY_ALIASES[hit[0]]
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
    out += list(EXAMPLES.values())
    for qs in list(INCOME_Q.values()) + list(TENURE_Q.values()):
        out += qs
    out += list(ALT_REPLIES.values())
    out.append(OFF_LINE)
    out += ["ठीक है, रकम पक्की कर दी।", "ठीक है जी, कोई बात नहीं। आप रकम एक बार फिर बोलिए, जैसे पाँच लाख।"]
    out += ["धन्यवाद, नंबर कन्फ़र्म हो गया।", "ठीक है जी, कोई बात नहीं। कृपया अपना मोबाइल नंबर एक बार फिर, धीरे-धीरे बोलिए।",
            "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई।", "जी, लोन के बारे में मैं आपकी पूरी मदद करूँगी।",
            "कृपया नंबर दोबारा, धीरे-धीरे बोलिए।", "पूरा दस अंकों का नंबर चाहिए।",
            "ठीक है जी, मैंने नोट कर लिया, हमारी टीम आपको उसी समय कॉल करेगी।",
            "ठीक है जी, आपकी जानकारी नोट हो गई है और हमारी टीम जल्दी आपसे संपर्क करेगी।", "ठीक है जी, जितनी जानकारी मिली है वो मैंने नोट कर ली है।", "जी, अगर आपको कुछ और पूछना हो तो बताइए, वरना आप कॉल खत्म कर सकते हैं।",
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
        self._off_hit = False
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
        text = re.sub(r"one and a half", "dedh", text, flags=re.I)             # before the sentence is cut at "and"
        text = re.sub(r"two and a half", "dhai", text, flags=re.I)
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

        # --- big-amount read-back answer
        if self.asked == "amount_confirm":
            yn = yes_no(text)
            if yn == "no":
                self.v.pop("loan_amount", None)
                (c.form.get("details") or {}).pop("loan_amount", None)
                self.asked = "loan_amount"
                return "ठीक है जी, कोई बात नहीं। आप रकम एक बार फिर बोलिए, जैसे पाँच लाख।"
            self.asked = None
            if yn == "yes":
                ack = "ठीक है, रकम पक्की कर दी।"

        # --- approved reply for a question or special request
        raw_bank = (replybank.match_hybrid(text) if looks_like_question(text) and not (parse_amount(text) and "?" not in text) and self.asked not in ("callback_time", "phone", "phone_confirm", "consent", "existing_loans", "full_name") else replybank.match(text))
        self._off_hit = any(m["id"] == "off_topic" and m["score"] >= 0.7 for m in raw_bank)
        bank = [m for m in raw_bank if m["score"] >= (0.45 if m["id"] in ("more_to_discuss", "small_talk") else 0.5 if m["entry"].get("require") else 0.6) and m["id"] not in SKIP_IDS]
        if is_ack_only(text):
            bank = []
        bank = [m for m in bank if m["id"] not in LEGACY_IDS or m["score"] >= 0.72]
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
        else:
            if asked == "loan_type" and re.search(r"salar|सैलरी", low):          # one word: "salary"
                details["loan_type"] = "salary"
                captured.append("loan_type")
            elif asked == "loan_type":
                import difflib

                known = {"personal": "personal", "parsanal": "personal", "payday": "payday", "pede": "payday", "salary": "salary", "saalari": "salary", "sailri": "salary", "salri": "salary"}
                for w in re.findall(r"[a-z]{4,}", low):
                    hit = difflib.get_close_matches(w, list(known), n=1, cutoff=0.68)          # "chalary" ~ "salary"
                    if hit:
                        details["loan_type"] = known[hit[0]]
                        captured.append("loan_type")
                        break
        income_re = r"salary|income|kamat|kamai|tankhw|mahin|monthly|महीने|सैलरी|कमाई"
        loan_re = r"loan|lakh|laakh|hazaar|rupe|rs\b|chahiye|chahie|paisa|paise|लोन"
        for clause in re.split(r"\.(?!\d)|[;!?]|\b(?:aur|and|but|lekin|par)\b", text):
            amt = None if asked == "existing_emi" else parse_amount(clause)
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
        emp = parse_employment(text, asked) if (asked == "employment" or ("employment" not in self.v and asked not in ("loan_purpose", "loan_type", "loan_amount", "full_name"))) else None
        if emp and ("employment" not in self.v or asked == "employment"):
            details["employment_type"] = emp
            captured.append("employment")
        city = parse_city(text, fuzzy=(asked == "city"))
        if city and ("city" not in self.v or asked == "city"):
            details["city"] = city
            captured.append("city")
        elif asked == "city" and not city and 0 < len(re.findall(r"[a-z]+", low)) <= 6 and clean_place(low) and not bank and not looks_like_question(text) and not domain_like(text):
            details["city"] = clean_place(low) or " ".join(re.findall(r"[a-z]+", low)).title()
            captured.append("city")
        if asked == "loan_purpose" and text:
            low_p = low
            canon = None
            for word, pat in (("medical", r"medical|ilaj|ilaaj|hospital|dawai|bimar|operation|treatment|doctor"), ("wedding", r"shaadi|shadi|shaaadi|wedding|vivah|marriage|byah"),
                              ("home repair", r"ghar|makaan|repair|renovation|marammat|construction"), ("education", r"education|padhai|padai|fees|school|college|course|study"),
                              ("business", r"business|dukaan|dukan|vyapar|vyapaar|dhandha|stock|machine"), ("travel", r"travel|ghumn|trip|yatra|vacation|holiday"),
                              ("debt repayment", r"karz|karza|purana loan|debt|emi bharn|credit card|bill"), ("emergency", r"emergency|zaroorat|jaruri|urgent|turant")):
                if re.search(pat, low_p):
                    canon = word
                    break
            words_p = _words(text)
            filler = {"main", "mujhe", "hoon", "raha", "rahi", "baat", "kar", "na", "hai", "to", "isse", "aap", "kya", "nahi", "haan", "ji", "ok", "abhi", "yeh", "ye", "woh", "mera", "meri", "mere", "se", "ko", "ka", "ki", "ke"}
            if canon is None and not bank:
                if yes_no(text) == "no" and len(words_p) <= 3:
                    canon = "not shared"
                elif re.fullmatch(r"[a-z ]{3,40}", re.sub(r"[^a-z ]", " ", low_p).strip() or "-") and len(words_p) <= 4 and not (set(words_p) & filler):
                    canon = re.sub(r"[^a-z ]", " ", low_p).strip()[:40]          # a short noun phrase such as "car repair"; never a whole sentence
            if canon:
                details["loan_purpose"] = canon
                captured.append("loan_purpose")
        if asked == "work_tenure" and text:
            yrs = parse_duration_years(text)
            if yrs is not None:
                label = "business_vintage" if self.v.get("employment") == "self-employed" else "time_with_current_employer"
                details[label] = (f"{round(yrs * 12)} months" if yrs < 1 else f"{yrs:g} years")
                captured.append("work_tenure")
        if asked == "existing_emi" and text:
            emi = parse_amount(text, minimum=100)
            w_ = set(_words(text))
            zero = bool(re.fullmatch(r"[0 ,.]+", text.strip())) or bool(w_ & {"zero", "shunya", "shoony"})
            if emi:
                details["existing_emi"] = emi
                captured.append("existing_emi")
            elif zero or yes_no(text) == "no":                              # "no loan is running": the earlier "yes" was a mistake
                details["existing_emi"] = 0
                details["existing_loans"] = "no"
                captured.append("existing_emi")
            elif yes_no(text) == "no" and len(_words(text)) <= 2:
                details["existing_emi"] = 0
                captured.append("existing_emi")
        if asked == "existing_loans":
            yn = yes_no(text)
            w_ = set(_words(text))
            if yn is None and "koi" not in w_ and (w_ & {"ek", "do", "teen", "car", "bike", "home", "personal", "gold", "credit", "card"} or {"chal", "raha"} <= w_ or {"chal", "rahi"} <= w_):
                yn = "yes"
            if yn:
                details["existing_loans"] = yn
                captured.append("existing_loans")
        digits = digits_from_speech(text)
        if asked == "phone_confirm" and len(digits) >= 10:
            self.phone_pending = digits[-10:]
            if forms.clean("phone", self.phone_pending)[0]:
                core["phone"] = self.phone_pending
                captured.append("phone")
        elif asked == "phone" or (len(digits) >= 10 and digits[-10] in "6789" and digits[-10:-5] != digits[-5:]):
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
        when_said = speak_time(text)
        if asked not in ("callback_time", "phone", "phone_confirm") and when_said and re.search(r"call|phone|baat", low) and "callback_time" not in self.v and not looks_like_question(text):
            core["preferred_callback_time"] = " ".join(text.split())[:80]
            core["consent_to_contact"] = "yes"
            captured += ["callback_time", "consent"]
        if asked == "consent" and "consent" not in captured:
            yn = yes_no(text)
            if yn:
                core["consent_to_contact"] = yn
                captured.append("consent")
        if asked == "callback_time" and text and not bank:
            core["preferred_callback_time"] = "any time" if (yes_no(text) == "no" and len(_words(text)) <= 2) else re.sub(r"\s+", " ", text)[:80]
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
                elif k == "work_tenure":
                    self.v[k] = details.get("business_vintage") or details.get("time_with_current_employer")
                elif k == "existing_emi":
                    self.v[k] = details[k]
                    if "existing_loans" in details:
                        self.v["existing_loans"] = details["existing_loans"]
                else:
                    self.v[k] = details[k]
            self._sync_reason()

        if "callback_time" in captured:                                  # the time has been taken: no extra "busy, call later" answer on top
            bank = [m for m in bank if m["id"] != "busy_callback"]
            ids = [m["id"] for m in bank]
        if asked in captured:                                            # the caller answered the question that was asked: only a strong, specific topic may still reply
            bank = [m for m in bank if m["score"] >= 0.9]
            ids = [m["id"] for m in bank]

        # --- the legacy assistant answers existing-customer / complaint / collections topics
        if any(i in LEGACY_IDS for i in ids) and not captured:
            return None

        # --- everything is collected: the caller can talk about anything else
        if self.done and not captured:
            if is_ack_only(text):
                return "जी, अगर आपको कुछ और पूछना हो तो बताइए, वरना आप कॉल खत्म कर सकते हैं।"
            approved = [self._alt(m) for m in bank if m["id"] not in LEGACY_IDS][:2]
            if approved:
                return " ".join(approved)
            if offtopic_like(text) or self._off_hit or (looks_like_question(text) and not domain_like(text) and not self._unsure_ok(text)):
                return OFF_LINE
            answer = self._free(text) if (domain_like(text) or "?" in text) else None
            if answer:
                return answer
            self.unclear_after_done += 1
            if self.unclear_after_done == 1:
                return "जी, मैं ठीक से समझ नहीं पाई। क्या आप अपनी बात एक बार फिर बता सकते हैं?"
            return "जी, आप चाहें तो स्क्रीन पर फ़ॉर्म सबमिट कर दीजिए, हमारी टीम जल्दी आपसे संपर्क करेगी।"

        parts = []
        if "callback_time" in captured and not ack:
            when = speak_time(self.v.get("callback_time", ""))
            if self.v.get("callback_time") == "any time":
                ack = "ठीक है जी, हमारी टीम आपको जल्दी ही कॉल करेगी।"
            elif when:
                ack = f"ठीक है जी, टीम आपको {when} कॉल करेगी।"
            else:
                ack = None
            ack = ack or "ठीक है जी, मैंने नोट कर लिया, टीम आपको उसी समय कॉल करेगी।"
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
            reply = self._alt(m)
            if self._next() is not None:
                reply = _drop_trailing_questions(reply)
            parts.append(reply)
            asked_question = asked_question or reply.rstrip().endswith("?")

        if not captured and not parts:
            if is_ack_only(text):                                        # "ok", "chalo": agreement, not a failure; carry on with the same question
                self.fails[asked] = -1
                parts.append(random.choice(ACKS))
            elif not bank and (offtopic_like(text) or self._off_hit) and asked not in (None, "phone", "phone_confirm"):
                parts.append(OFF_LINE)                                   # then the form question continues
                self.fails[asked] = -1
            elif not bank and asked not in (None, "phone", "phone_confirm") and domain_like(text) and looks_like_question(text):
                answer = self._free(text)                                # a question outside the form: answer it, then continue
                if answer:
                    parts.append(answer)
                    self.fails[asked] = -1

        if c.more_coming:                                               # the caller is still speaking: brief acknowledgement only
            return " ".join(parts[:1]) or random.choice(ACKS)

        if "loan_amount" in captured and (self.v.get("loan_amount") or 0) >= 1_000_000:
            self.asked = "amount_confirm"
            return f"जी, {self.v['loan_amount']} रुपये। क्या यह सही है?"
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
                parts.append(f"ठीक है {self._name()} जी, आपकी सारी जानकारी नोट हो गई है। और कुछ पूछना हो तो पूछ लीजिए, वरना आप स्क्रीन पर फ़ॉर्म देखकर सबमिट कर दीजिए।")
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
        if self.fails.get(nxt, 0) >= 6:                                  # the caller really cannot or will not answer this one: move on
            self.skipped.add(nxt)
            nxt = self._next()
            if nxt is None:
                return " ".join(parts) or random.choice(ACKS)
        self.asked = nxt
        question = self._question(nxt)
        if nxt == self.asked and not captured and not bank and self.fails.get(nxt, 0) >= 1:
            parts.append("माफ़ कीजिए, मैं ठीक से समझ नहीं पाई।")
        if self.fails.get(nxt, 0) >= 2 and nxt in EXAMPLES:               # noise or a hard-to-hear answer: show what a good answer sounds like
            question += " " + EXAMPLES[nxt]
        if nxt == "consent":
            question = f"{self._name()} जी, " + question if self._name() else question
        parts.append(question)
        return " ".join(parts)

    def _question(self, slot: str) -> str:
        """The question for a slot, worded for this caller: a salary for an employee, income for a businessman, pension for a pensioner."""
        et = self.v.get("employment")
        if slot == "monthly_income":
            return random.choice(INCOME_Q.get(et, INCOME_Q["salaried"] if et is None else QUESTIONS["monthly_income"]))
        if slot == "work_tenure":
            return random.choice(TENURE_Q.get(et, TENURE_Q["salaried"]))
        return random.choice(QUESTIONS[slot])

    def _alt(self, m: dict) -> str:
        """An approved answer, or the version written for this caller's work type."""
        return ALT_REPLIES.get((m["id"], self.v.get("employment")), m["entry"]["reply"])

    def _next(self):
        for s in SLOTS:
            if s == "callback_time" and self.v.get("consent") != "yes":
                continue
            if s in self.v or s in self.skipped:
                continue
            if s == "existing_emi" and self.v.get("existing_loans") != "yes":
                continue
            if s == "work_tenure" and self.v.get("employment") not in ("salaried", "self-employed"):
                continue
            if s == "phone" and self.call.form.get("phone") and "phone" in self.call.confirmed:
                continue
            if s == "monthly_income" and self.v.get("employment") is None and False:
                continue
            return s
        return None

    @staticmethod
    def _guard_ok(answer: str, question: str, knowledge: str) -> bool:
        """Runtime check of an AI-written answer before it is spoken: no invented numbers, no promises, no list formatting."""
        if re.search(r"(^|\s)\d+[.)]\s", answer):                              # "1. ..." lists read badly on a phone
            return False
        if re.search(r"गारंटी|पक्का मंज़ूर|पक्का मंजूर|अप्रूव हो जाएगा|मंज़ूर हो जाएगा|मंजूर हो जाएगा|ज़रूर पास", answer):
            return False
        for w in re.findall(r"[ऀ-ॿ]+", answer):                              # an amount or percentage said in words is invented unless the caller said it
            if w in ("लाख", "हज़ार", "हजार", "करोड़", "करोड", "प्रतिशत", "परसेंट") and w not in question:
                return False
        allowed = {n.replace(",", "") for n in re.findall(r"\d[\d,]*", knowledge + " " + question)}
        for n in re.findall(r"\d[\d,]*", answer):
            if n.replace(",", "").rstrip(".") not in allowed:
                return False                                                      # a number that is in neither the approved facts nor the caller's own words
        return True

    def _unsure_ok(self, text: str) -> bool:
        """True when a question sounds like finance even without a keyword (then the honest 'team will confirm' answer is better than the off-topic line)."""
        return bool(re.search(r"(paisa|paise|rupay|rupaye|byaaj|bank|loan|lon|emi|kist|account|khata|fund|money|tax|insurance|scheme|rate|charge|fees?)", text.lower()))

    def _free(self, text: str):
        """_free_raw, plus a local note of every question she could not answer, for the team to review (calls/unanswered.jsonl; nothing leaves this PC)."""
        out = self._free_raw(text)
        if out == UNSURE:
            try:
                import json
                import os
                import time

                folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls")
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, "unanswered.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "question": text, "caller_type": self.v.get("employment"), "loan_type": self.v.get("loan_type")}, ensure_ascii=False) + chr(10))
            except OSError:
                pass
        return out

    def _free_raw(self, text: str):
        """A short grounded answer for anything the flow has no answer for (company, loan details, CIBIL, small talk). None on any problem."""
        import os as _os2

        if _os2.environ.get("FREE_LLM", "0") != "1":                       # default: only approved answers, otherwise the honest "not sure"
            return UNSURE
        try:
            import brain

            form = self.call.form
            facts = {k: v for k, v in form.items() if k in ("full_name", "category", "reason")}
            facts.update({k: v for k, v in (form.get("details") or {}).items() if not str(k).startswith(("crm_", "identity"))})
            known = ", ".join(f"{k}: {v}" for k, v in facts.items() if v)
            system = FREE_RULES + brain.KNOWLEDGE + "\n" + COMPANY_INFO + "\n" + GENERAL_FINANCE + "\nकॉल में अब तक कॉलर ने बताया: " + (known or "कुछ नहीं") + "।"
            msgs = [{"role": "system", "content": system}]
            for m in self.call.history[1:][-8:]:
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"] and not m.get("tool_calls"):
                    msgs.append({"role": m["role"], "content": m["content"]})
            strong = [m for m in replybank.match(text) if m["score"] >= 0.75]
            guide = replybank.hint(text) if strong else ""
            msgs.append({"role": "user", "content": text + ("\n" + guide if guide else "")})
            r = brain._llm.chat.completions.create(model=brain.LLM_MODEL, messages=msgs, max_tokens=90, temperature=0.3, timeout=9)
            out = voice.sanitize_reply((r.choices[0].message.content or "").strip())
            if r.choices[0].finish_reason == "length":
                done_sentences = [x for x in voice.split_sentences(out) if x.rstrip()[-1:] in "।.?!"]
                out = " ".join(done_sentences)
            english = not re.search(r"[ऀ-ॿ]", text) and not re.search(r"\b(hai|hoon|hu|kya|kaise|mujhe|mera|aap|nahi|haan|batao)\b", text.lower())
            if not out or (not english and not re.search(r"[ऀ-ॿ]", out)):
                return UNSURE
            if not self._guard_ok(out, text, brain.KNOWLEDGE + COMPANY_INFO + GENERAL_FINANCE):
                print("   [flow] free answer blocked by the guard:", out[:80], flush=True)
                return UNSURE
            for latin, deva in (("EMI", "ईएमआई"), ("CIBIL", "सिबिल"), ("KYC", "केवाईसी"), ("OTP", "ओटीपी"), ("PAN", "पैन"), ("NBFC", "एनबीएफसी"), ("AI", "एआई")):
                out = out.replace(latin, deva)
            return " ".join(voice.split_sentences(out)[:2])
        except Exception as e:
            print(f"   [flow] free answer failed: {type(e).__name__}: {e}", flush=True)
            return UNSURE

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
