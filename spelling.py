"""Spelling clean-up for what the caller said (Roman Hinglish from the listener).

The listening model writes Hindi in a formal romanisation ("nahin", "laakh", "rupe", "chaahie", "kuchh", "yah", "lie", "Jaypur") and sometimes a
sound-alike for a loan word ("Chalary" for "salary"). Everyone writes Hinglish the everyday way ("nahi", "lakh", "rupaye", "chahiye", "kuch", "yeh",
"liye", "Jaipur"), so every word below is rewritten to that spelling: in the transcript shown on screen and in the text the flow reads.
No dependencies, so stt.py and flow.py can both use it.   Test: python train/spelling_check.py
"""
import difflib
import re

# variant -> everyday spelling (all lower case; capitals of the original are kept)
WORDS = {
    # no / yes / politeness
    "nahin": "nahi", "nahee": "nahi", "nahii": "nahi", "nhin": "nahi", "haa": "haan", "haanji": "haan ji", "jee": "ji", "theek": "theek", "thik": "theek", "thiik": "theek",
    "accha": "accha", "achha": "accha", "acha": "accha", "achchha": "accha", "bilkul": "bilkul", "bilkool": "bilkul", "dhanyavaad": "dhanyavad", "dhanyawaad": "dhanyavad", "shukriyaa": "shukriya",
    # pronouns, verbs, small words
    "yah": "yeh", "ye": "yeh", "vah": "woh", "wah": "woh", "vo": "woh", "wo": "woh", "hamen": "hume", "hamein": "hume", "humein": "hume", "mujhey": "mujhe", "mainne": "maine", "mainnay": "maine",
    "ismen": "ismein", "usmen": "usmein", "inmen": "inmein", "unmen": "unmein", "isme": "isme", "tumhen": "tumhe", "aapko": "aapko", "aapkaa": "aapka", "aapki": "aapki", "kyaa": "kya", "kyon": "kyun", "kion": "kyun",
    "lie": "liye", "liey": "liye", "liyay": "liye", "islie": "isliye", "uslie": "isliye", "isliye": "isliye", "kuchh": "kuch", "kuchch": "kuch", "kuchha": "kuch", "kuchhh": "kuch", "kaha": "kaha",
    "chaahie": "chahiye", "chaahiye": "chahiye", "chahie": "chahiye", "chahiey": "chahiye", "chaiye": "chahiye", "chahiyee": "chahiye", "chaahiyae": "chahiye", "chahiyae": "chahiye",
    "dijie": "dijiye", "dijiyae": "dijiye", "kijie": "kijiye", "kijiyae": "kijiye", "boliye": "boliye", "bataiye": "bataiye", "bataie": "bataiye", "batayiye": "bataiye", "batayie": "bataiye",
    "shaayad": "shayad", "shayed": "shayad", "dvaara": "dwara", "dwaara": "dwara", "chiz": "cheez", "cheej": "cheez", "chij": "cheez", "savaal": "sawal", "savaalon": "sawalon", "sawaal": "sawal", "sawaalon": "sawalon",
    "puchh": "puch", "poochh": "puch", "poochha": "puchha", "poochhana": "puchna", "poochhna": "puchna", "puchhna": "puchna", "puchhana": "puchna", "poochhne": "puchne", "puchhne": "puchne", "poochhana": "puchna",
    "poochhane": "puchne", "puchhane": "puchne", "poochhta": "puchta", "poochhti": "puchti", "poochhunga": "puchunga", "poochhoon": "puchun", "poochhna": "puchna", "poochhana": "puchna",
    "karoonga": "karunga", "karoongi": "karungi", "karoon": "karun", "karoo": "karu", "doonga": "dunga", "doongi": "dungi", "doon": "dun", "bataoon": "bataun", "batadoon": "batadun", "sakoon": "sakun", "sakoonga": "sakunga",
    "jaaoon": "jaun", "jaoon": "jaun", "aaoon": "aaun", "chaloon": "chalun", "dekhoon": "dekhun", "bolun": "bolun", "boloon": "bolun", "bhejoon": "bhejun", "karen": "karein", "karenge": "karenge", "kariye": "kijiye",
    "jaegi": "jayegi", "jaega": "jayega", "jaenge": "jayenge", "aegi": "ayegi", "aega": "ayega", "aenge": "ayenge", "milegaa": "milega", "milegii": "milegi", "hogaa": "hoga", "hogii": "hogi",
    "rahaa": "raha", "rahii": "rahi", "kiyaa": "kiya", "gayaa": "gaya", "gayii": "gayi", "huaa": "hua", "hui": "hui", "huii": "hui", "karvaana": "karwana", "karvana": "karwana", "karva": "karwa", "karvao": "karwao",
    "karvaa": "karwa", "bhijvaa": "bhijwa", "bhijva": "bhijwa", "bhijvana": "bhijwana", "bhijvaana": "bhijwana", "mangvaa": "mangwa", "mangva": "mangwa", "mangvana": "mangwana", "bataana": "batana", "dikhaana": "dikhana",
    "samjhaao": "samjhao", "samajhao": "samjhao", "samajh": "samajh", "samjhaana": "samjhana", "samjhaiye": "samjhaiye", "samajhaiye": "samjhaiye", "samjhao": "samjhao", "baaten": "baatein", "baatein": "baatein",
    "rahta": "rehta", "rahti": "rehti", "rahte": "rehte", "rahtaa": "rehta", "rahtii": "rehti", "rukne": "rukne", "ruko": "ruko", "chalie": "chaliye", "chaliye": "chaliye", "chalo": "chalo", "dekh": "dekh",
    "donon": "dono", "dono": "dono", "dusra": "doosra", "doosra": "doosra", "dusri": "doosri", "doosri": "doosri", "isse": "isse", "jisse": "jisse", "uska": "uska", "uski": "uski", "parson": "parso", "parsoon": "parso",
    "aaj": "aaj", "kal": "kal", "abhee": "abhi", "abhii": "abhi", "baadme": "baad mein", "baadmein": "baad mein", "mein": "mein", "main": "main", "meiN": "mein", "mai": "main", "mae": "main",
    "hai": "hai", "hain": "hain", "hein": "hain", "hei": "hai", "hun": "hoon", "hu": "hoon", "huun": "hoon", "hoo": "hoon", "hoon": "hoon", "ho": "ho", "raha": "raha", "rhe": "rahe", "rhi": "rahi", "rha": "raha",
    "hameshaa": "hamesha", "hamesha": "hamesha", "sirph": "sirf", "sirf": "sirf", "kewal": "sirf", "kewalaa": "sirf",
    # money and numbers
    "laakh": "lakh", "laakhs": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh", "laaakh": "lakh", "lakkh": "lakh", "lakhh": "lakh", "hazar": "hazaar", "hajar": "hazaar", "hajaar": "hazaar", "hazaarr": "hazaar", "hazaaar": "hazaar",
    "karod": "crore", "karor": "crore", "karore": "crore", "crores": "crore", "cr": "crore", "rupe": "rupaye", "rupay": "rupaye", "rupaiya": "rupaye", "rupaiye": "rupaye", "rupaya": "rupaye", "rupees": "rupaye", "rupaye": "rupaye",
    "paisaa": "paisa", "paise": "paise", "dhan": "dhan", "kist": "kist", "kisht": "kist", "kiston": "kiston", "kishton": "kiston", "kistein": "kistein", "ek": "ek", "eik": "ek", "do": "do", "doh": "do", "teen": "teen", "tin": "teen", "teeen": "teen",
    "chaar": "char", "chaar": "char", "chaarr": "char", "chhah": "chhe", "chhe": "chhe", "chheh": "chhe", "chhey": "chhe", "chhah": "chhe", "chhai": "chhe", "chhaa": "chhe", "chha": "chhe", "saat": "saat", "saath": "saath", "aath": "aath", "aathh": "aath",
    "nau": "nau", "naw": "nau", "daas": "das", "gyaarah": "gyarah", "gyarah": "gyarah", "baarah": "barah", "baarahh": "barah", "terah": "terah", "teraah": "terah", "chaudah": "chaudah", "chaudaah": "chaudah",
    "pandrah": "pandrah", "pandraah": "pandrah", "solah": "solah", "satrah": "satrah", "athaarah": "atharah", "atharah": "atharah", "unnees": "unnis", "unnis": "unnis", "bees": "bees", "tees": "tees", "chaalees": "chalis", "chaalis": "chalis",
    "chalees": "chalis", "pachaas": "pachas", "pachas": "pachas", "pachaash": "pachas", "saath": "saath", "saathh": "saath", "sattar": "sattar", "sattaar": "sattar", "assi": "assi", "nabbe": "nabbe", "nabbay": "nabbe", "sau": "sau",
    "ikkees": "ikkis", "ikkis": "ikkis", "bais": "bais", "baees": "bais", "paintees": "paintis", "paintis": "paintis", "chhattees": "chhattis", "chhattis": "chhattis", "adhai": "dhai", "dhaai": "dhai",
    "dedh": "dedh", "derh": "dedh", "saade": "saade", "sade": "saade", "paune": "paune", "pauna": "pauna", "sava": "sava", "savaa": "sava", "aadha": "aadha", "aadhaa": "aadha", "aadhi": "aadhi", "aadhee": "aadhi",
    # time
    "taarikh": "tarikh", "taareekh": "tarikh", "tarikh": "tarikh", "ghantaa": "ghanta", "ghante": "ghante", "ghanta": "ghanta", "minat": "minute", "minit": "minute", "mahina": "mahina", "mahinaa": "mahina", "maheena": "mahina",
    "saal": "saal", "saalon": "saalon", "varsh": "saal", "baje": "baje", "subah": "subah", "subha": "subah", "shaam": "shaam", "sham": "shaam", "dopahar": "dopahar", "dophar": "dopahar", "raat": "raat", "raath": "raat",
    "somvaar": "somvar", "mangalvaar": "mangalvar", "budhvaar": "budhvar", "guruvaar": "guruvar", "shukravaar": "shukravar", "shanivaar": "shanivar", "ravivaar": "ravivar",
    # work / loan words
    "naukari": "naukri", "naukree": "naukri", "naukrii": "naukri", "naukri": "naukri", "berozgaar": "berozgar", "virozgaar": "berozgar", "berojgaar": "berozgar", "berojgar": "berozgar", "rozgaar": "rozgar", "rojgar": "rozgar",
    "vyapaar": "vyapar", "vyaapar": "vyapar", "vyapaar": "vyapar", "dhanda": "dhandha", "dhandhaa": "dhandha", "dukaan": "dukan", "dukaanh": "dukan", "dookan": "dukan", "tankhwah": "tankhwa", "tankhvaah": "tankhwa", "tankhwaah": "tankhwa",
    "tankhwa": "tankhwa", "vetan": "vetan", "pension": "pension", "penshan": "pension", "pensan": "pension", "kamaayi": "kamai", "kamaai": "kamai", "kamai": "kamai", "kamaee": "kamai", "aay": "aay", "aamdani": "aamdani", "aamdanee": "aamdani",
    "karza": "karz", "karj": "karz", "karzaa": "karz", "byaaj": "byaj", "byaj": "byaj", "vyaaj": "byaj", "vyaj": "byaj", "brij": "byaj", "bajaj": "bajaj", "dastavez": "dastavez", "dastaavez": "dastavez", "kaagaz": "kagaz", "kagzaat": "kagzat",
    "kaagzaat": "kagzat", "prooph": "proof", "pruf": "proof", "pruph": "proof", "aadhaar": "Aadhaar", "adhaar": "Aadhaar", "aadhar": "Aadhaar", "adhar": "Aadhaar", "adhaar": "Aadhaar", "aadhaarcard": "Aadhaar card",
    "pancard": "PAN card", "paincard": "PAN card", "paincard": "PAN card", "kyc": "KYC", "keyc": "KYC", "kay": "kay", "nbfc": "NBFC", "rbi": "RBI", "aarbiai": "RBI", "upi": "UPI", "nach": "NACH", "neft": "NEFT", "rtgs": "RTGS",
    "gst": "GST", "itr": "ITR", "msme": "MSME", "aum": "AUM", "apr": "APR", "kfs": "KFS", "otp": "OTP", "pin": "PIN", "cvv": "CVV", "atm": "ATM", "sms": "SMS", "fd": "FD", "rd": "RD", "ai": "AI", "hr": "HR",
    "paydae": "payday", "payday": "payday", "pede": "payday", "peday": "payday", "pedey": "payday", "paidloan": "payday loan", "salari": "salary", "salaari": "salary", "salaree": "salary", "salarii": "salary", "sailary": "salary", "sallary": "salary", "salaary": "salary", "saalari": "salary",
    "chalary": "salary", "chalari": "salary", "chaleri": "salary", "salri": "salary", "sailri": "salary", "pursonal": "personal", "persnal": "personal", "pesonal": "personal", "parsanal": "personal", "personel": "personal",
    "lone": "loan", "lown": "loan", "loon": "loan", "emmi": "EMI", "aimi": "EMI", "sibil": "CIBIL", "cibil": "CIBIL", "sivil": "CIBIL", "cybil": "CIBIL",
    "bankk": "bank", "bainks": "bank", "bainka": "bank", "baink": "bank", "company": "company", "kampani": "company", "kampni": "company", "kampany": "company", "lakshmi": "Lakshmi", "laxmi": "Laxmi",
    "lakshymi": "Lakshmi", "lakshyap": "Lakshmi", "lakshami": "Lakshmi", "luxmi": "Laxmi", "lucksmi": "Laxmi", "luxmee": "Laxmi",
    "finaance": "finance", "finans": "finance", "phinance": "finance", "faainans": "finance", "fainans": "finance", "limitid": "limited", "limitad": "limited", "limted": "limited",
    "jaankari": "jankari", "jaankaari": "jankari", "jaankaree": "jankari", "jankaari": "jankari", "jaanakari": "jankari", "mulakat": "mulakat", "sampark": "sampark", "samparka": "sampark",
    "address": "address", "adress": "address", "addres": "address", "pata": "pata", "pataa": "pata", "patta": "pata", "location": "location", "lokation": "location", "lokeshan": "location", "locashan": "location", "lokeshun": "location",
    "mail": "mail", "mel": "mail", "meil": "mail", "email": "email", "imail": "email", "emal": "email", "id": "ID", "aidi": "ID", "number": "number", "nambar": "number", "namber": "number", "nanbar": "number", "nambr": "number", "nmbr": "number",
    "mobaail": "mobile", "mobail": "mobile", "mobil": "mobile", "mobaile": "mobile", "phon": "phone", "fon": "phone", "foon": "phone", "kol": "call", "kawl": "call", "kaat": "kaat", "kato": "kaato",
    "naam": "naam", "nam": "naam", "naamm": "naam", "naaam": "naam", "pareshaan": "pareshan", "pareshani": "pareshani", "pareshaani": "pareshani", "pareshanee": "pareshani", "dikkat": "dikkat", "dikkaat": "dikkat", "dikat": "dikkat",
    "shikaayat": "shikayat", "shikayat": "shikayat", "shikaayatt": "shikayat", "sikayat": "shikayat", "sikaayat": "shikayat", "ghar": "ghar", "gher": "ghar", "makaan": "makan", "makan": "makan", "makaann": "makan",
    "shaadi": "shaadi", "shadi": "shaadi", "shaadee": "shaadi", "shaaadi": "shaadi", "ilaaj": "ilaj", "ilaj": "ilaj", "ilaz": "ilaj", "padhaai": "padhai", "padhai": "padhai", "padhaee": "padhai", "padai": "padhai", "fees": "fees", "fis": "fees", "feez": "fees",
    "doctar": "doctor", "daaktar": "doctor", "daktar": "doctor", "doktar": "doctor", "aspataal": "aspatal", "haspital": "hospital", "haaspital": "hospital", "hospitl": "hospital", "kharcha": "kharcha", "kharchaa": "kharcha", "kharch": "kharch",
    "business": "business", "bizness": "business", "biznes": "business", "bijnes": "business", "bijnis": "business", "bijniss": "business", "misnesh": "business", "missnes": "business", "bisnes": "business", "bisness": "business", "bijness": "business",
    "emargency": "emergency", "emergensi": "emergency", "emerjensi": "emergency", "karyaalay": "karyalay", "karyalay": "karyalay", "daftar": "daftar", "daphtar": "daftar", "daftr": "daftar", "office": "office", "ofis": "office", "ofice": "office",
    "branch": "branch", "braanch": "branch", "branchh": "branch", "braunch": "branch", "shaakha": "shakha", "shakha": "shakha", "shaakhaa": "shakha", "shakhaa": "shakha",
    "dopahaar": "dopahar", "sandhya": "shaam", "savere": "subah", "kitnaa": "kitna", "kitnii": "kitni", "kitne": "kitne", "kitna": "kitna", "kitni": "kitni", "kyaa": "kya", "kaise": "kaise", "kaisa": "kaisa", "kaisi": "kaisi", "kahaan": "kahan",
    # common names and surnames
    "raam": "ram", "sinh": "singh", "sing": "singh", "singha": "singh", "shyaam": "shyam", "kumaar": "kumar", "shaarma": "sharma", "sharmaa": "sharma", "vermaa": "verma", "guptaa": "gupta", "meena": "meena", "mishraa": "mishra", "yaadav": "yadav", "yadaav": "yadav",
    "mistri": "mistry", "jaain": "jain", "gaurava": "gaurav", "arjuna": "arjun", "rohitt": "rohit", "amitt": "amit", "sumit": "sumit", "poojaa": "pooja", "priyaa": "priya", "ankitaa": "ankita", "sunitaa": "sunita",
    "kahan": "kahan", "kidhar": "kidhar", "kaun": "kaun", "kaunsa": "kaunsa", "kaunsi": "kaunsi", "konsa": "kaunsa", "konsi": "kaunsi", "koun": "kaun", "kon": "kaun",
}

# city spellings are kept in flow.CITY_ALIASES (one list for parsing and for display)
_CITY_FIX = None


def _cities():
    global _CITY_FIX
    if _CITY_FIX is None:
        import flow
        _CITY_FIX = {k: v for k, v in flow.CITY_ALIASES.items() if len(k) >= 4 and k != v.lower()}
    return _CITY_FIX


def _match_case(src: str, out: str) -> str:
    if src.isupper() and len(src) > 1:
        return out.upper() if not any(c.isupper() for c in out) else out
    if src[:1].isupper() and not any(c.isupper() for c in out):
        return out[:1].upper() + out[1:]
    return out


# some everyday words are listed above only so that they pass through unchanged; keep only real changes
WORDS = {k: v for k, v in WORDS.items() if k != v.lower() or v != v.lower()}


def normalize(text: str) -> str:
    """The caller's sentence with every word in its everyday Hinglish spelling (letters only; digits and punctuation untouched)."""
    if not text:
        return text
    cities = None

    def one(m):
        nonlocal cities
        w = m.group(0)
        lw = w.lower()
        if lw in WORDS:
            return _match_case(w, WORDS[lw])
        if len(lw) >= 4:
            if cities is None:
                try:
                    cities = _cities()
                except Exception:
                    cities = {}
            if lw in cities:
                return cities[lw]
        return w

    out = re.sub(r"[A-Za-z]+", one, text)
    out = re.sub(r"\b[Pp][Aa][Nn]\s*[Cc]ard\b", "PAN card", out)    # "pan card" is always the tax card here
    try:
        import forms
        out = re.sub(r"[A-Za-z]{6,}", lambda m: (lambda hit: hit[0] if hit and hit[0].lower() != m.group(0).lower() else m.group(0))(
            difflib.get_close_matches(m.group(0).title(), forms.CITIES, n=1, cutoff=0.88)), out)
    except Exception:
        pass
    return out
