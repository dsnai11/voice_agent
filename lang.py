"""Languages: Hindi (hi), English (en), Gujarati (gu) and Marwari / Rajasthani village speech (mwr).

* detect(text)   which language the caller used in this sentence (None when it is too short or mixed to tell)
* switch_request(text)   "English mein baat karo", "Gujarati ma vaat karo", "Marwadi mein bolo" -> language code
* to_hinglish(text, lang)   Gujarati / Marwari / Rajasthani words rewritten to the Hinglish the form flow already understands
The listener writes Gujarati and Rajasthani as rough Roman sounds ("Vyajdar kitloch", "Mari tanakhvaah pachaas hazaar"), so every lookup here is
tolerant: a close spelling counts.   No dependencies (spelling.py and flow.py use it).   Test: python train/lang_test.py
"""
import difflib
import re

LANG_NAMES = {"hi": "हिंदी", "en": "English", "gu": "ગુજરાતી", "mwr": "मारवाड़ी"}
TTS_CODE = {"hi": "hi", "en": "en", "gu": "gu", "mwr": "hi"}          # Marwari text is written in Devanagari and spoken by the Hindi voice

_GU_SCRIPT = re.compile(r"[઀-૿]")
_DEV_SCRIPT = re.compile(r"[ऀ-ॿ]")

# ---------------------------------------------------------------------------------------------------------------- word lists
# Words that mark a sentence as Gujarati (Roman, as the listener writes them) ...
GU_MARKERS = set("""mane mare maru maaru mari mara maraa tamaru tamari tamara tame tamne tamara amne amara amaru chhe chhu chho chhie chhiye joiye joie joiy joi shu su kem kemm ketlo ketla ketli kitlo kitla kitli
kyare kyan  kone koni kevi kevu rite nathi nathii haju pachi   aaje  kale savare bapore sanje ratre vagye vage   karvi karvu karvo  aapo apo aapjo batavo batavjo samjayu samajayu
farithi pharithi        saru saaru   pagar pagaar       lidhi lidhu           
        traan                  """.split())
# ... and as Marwari / Rajasthani (Shekhawati, Mewari, Dhundhari, Hadoti, Mewati: the village forms that differ from Hindi)
MWR_MARKERS = set("""mhare mhaare mharo mhaaro mhari mhaari mhara mhaara mhane mhanne mhaane thane thanne thaane thare thaare tharo thaaro thari thaari thara thaara   kain kaain kaaiyan kayi kaayi
kun kuun kunsi kunsa kathe kathai  kiyan kiyaan kyaan kito kitto kitti kiti kadi kadai ghano ghani ghana ghanaa lagsi lagse lagasi hosi hovsi hovegi hove milsi milse milegi chaije chaaije chaiji chaijo
chaijyo dijo deejo dyo dyoji   hukam hukum ri ro ra rai    ona oni  koni konyi konai  hao  saanjh saanj savere dupaar dupar paachho paachhe pachhe baapu bapu  bai bainsa
maaro maari   gaam gaon_ kheti kheto khet dhani dhanyo avo aavo jaavo   karsyu karsi karasi karanga karuun  rahyo rahyi reh rehvo rahvo hunn     """.split())
GU_STRONG = set("mane mare maru maaru tamaru tamari tamne chhe chhu joiye joie ketlo ketla ketli kitlo kyare kem shu nathi pachi aapo batavo farithi pharithi saru  vyaj vyajdar".split())
MWR_STRONG = set("mhare mhaare mharo mhaaro mhari mhaari mhane mhanne thane thanne thare tharo thaaro thari chaije chaaije chaiji chaizi lagsi hosi milsi ghano ghani kito kitto kathe kiyan kunsi hukam".split())
# Hindi markers: a sentence that has them stays Hindi even if one dialect word sneaks in
HI_MARKERS = set("""kya hai hain mujhe mera meri mere aap aapka aapki aapko chahiye nahi nahin haan ji kitna kitni kitne kaise kyun kab kahan kaun hoon ho tha thi hum hame hamara""".split())
EN_WORDS = set("""the is are was were what how why when where who which can could would should will my your i me you we it this that these those and or but not no yes please sorry thank thanks hello hi
name am from live lives living work works working wedding sister brother father mother wife husband son daughter home house shop per salaried employed self employed retired student pension for to in on at with of an a about need want have has had does did get give tell know understand say speak talk repeat again loan rupees rupee rate interest salary income document documents fee fees charge charges apply application
approved approval eligible eligibility much many long time days month months year years branch office address number mobile phone call back later tomorrow today morning evening night amount lakh thousand
personal business job work working company bank account credit score cibil emi pay payment""".split())
# English grammar words: loan vocabulary alone ("personal loan", "salary 50000") is Hinglish, not English
EN_FUNC = set("the is are was were what how why when where who which can could would should will my your i me you we it this that these those and or but not please sorry thank thanks have has had need want get give tell know about from with am does did there here very much many any some also".split())
# Hindi/Hinglish function words that an English sentence never has
HI_ONLY = {"mujhe", "chahiye", "nahi", "aap", "mera", "meri", "mein", "hoon", "tha", "kitna", "kaise", "bhi", "toh", "yeh", "woh"}


def _words(text: str):
    return re.findall(r"[a-zA-Z_]+", text.lower())


# Soft markers: the listener often glues or bends dialect words ("mehtaachhe", "ketloche", "mharo" -> "maro"), so the endings and stems count too
_GU_SOFT = re.compile(r"ketl[oai]|kitl[oai]|joiy?e|chh?e$|chh?u$|chh?o$|nathi|tamar[ui]|tamn[ae]|tamaro|mane$|kyare|vyaj")
_MWR_SOFT = re.compile(r"^ma+h+a+r[oiae]n?$|^mah[aeo]+r|^mh[aeo]+r|^mh[aeo]+n|^thar[eoi]|^thaar|^than[ne]|chaij[eoi]|chaiz|chaaij|lagsi|hosi\b|milsi|ghan[oi]\b|^kitt?o$|^kath[ae]|^kiy[aa]n|hukam")


_GU_SOFT_NOAMB = re.compile(r"ketl[oai]|kitl[oai]|joiy?e|nathi|tamar[ui]|tamn[ae]|tamaro|mane$|kyare|vyaj")


def _soft(words, rx):
    return sum(1 for x in words if rx.search(x))


def detect(text: str):
    """'hi' | 'en' | 'gu' | 'mwr', or None when the sentence is too short / ambiguous to change the call's language."""
    if not text:
        return None
    if _GU_SCRIPT.search(text):
        return "gu"
    w = _words(text)
    if not w:
        return None
    gu = sum(1 for x in w if x in GU_MARKERS)
    mw = sum(1 for x in w if x in MWR_MARKERS)
    hi = sum(1 for x in w if x in HI_MARKERS)
    en = sum(1 for x in w if x in EN_WORDS)
    hi_only = sum(1 for x in w if x in HI_ONLY)
    amb = sum(1 for x in w if x in ("chhe", "chhu", "chho", "chhai") or (len(x) > 5 and re.search(r"chh?[eu]$", x)))      # shared by Gujarati and Marwari, also glued to a word
    gs = max(sum(1 for x in w if x in GU_STRONG and x not in ("chhe", "chhu")), _soft(w, _GU_SOFT_NOAMB))
    ms = max(sum(1 for x in w if x in MWR_STRONG), _soft(w, _MWR_SOFT))
    if ms > gs:
        ms += amb                                                            # "mahaaron naam arjun singh chhe": the "chhe" is Marwari here
    else:
        gs += amb
    if (gs or ms) and hi_only <= 2:
        return "gu" if gs > ms else "mwr"                      # one unmistakable dialect word is enough ("mhane do lakh ri loan chaije")
    ef = sum(1 for x in w if x in EN_FUNC)
    if en >= 2 and en >= len(w) * 0.4 and hi_only == 0 and ef >= 1:
        return "en"
    if len(w) <= 2:
        return None
    if gu >= 2 and gu > mw and gu >= hi:
        return "gu"
    if mw >= 2 and mw >= gu and mw >= hi - 1:
        return "mwr"
    if hi >= 2 and hi_only >= 1:
        return "hi"
    return None


_SWITCH = [
    ("en", r"english\s*(mein|me|mai|main|ma|bolo|bol|baat|speak|please)|speak\s+(in\s+)?english|in\s+english|angrezi|angreji|english\s*(language)?\s*(please|only)|can\s+you\s+(speak|talk)\s+(in\s+)?english"),
    ("gu", r"gujarati|gujrati|gujarathi|gujrathi|ગુજરાતી"),
    ("mwr", r"marwadi|marwari|marvadi|marvari|rajasthani|rajasthaani|rajasthni|mewari|shekhawati|dhundhari|hadoti|mewati|village\s+(language|boli)|desi\s+boli|gaon\s+ki\s+boli|मारवाड़ी|राजस्थानी"),
    ("hi", r"hindi\s*(mein|me|mai|main|bolo|bol|baat|please)|speak\s+(in\s+)?hindi|in\s+hindi|हिंदी\s*(में|मे)"),
]


def is_strong(text: str, code: str) -> bool:
    """Enough evidence to change the call's language on the very first sentence (otherwise two sentences in a row are needed)."""
    w = _words(text)
    amb = sum(1 for x in w if x in ("chhe", "chhu", "chho", "chhai") or (len(x) > 5 and re.search(r"chh?[eu]$", x)))      # shared by Gujarati and Marwari, also glued to a word
    gs = max(sum(1 for x in w if x in GU_STRONG and x not in ("chhe", "chhu")), _soft(w, _GU_SOFT_NOAMB))
    ms = max(sum(1 for x in w if x in MWR_STRONG), _soft(w, _MWR_SOFT))
    if code == "gu":
        return bool(_GU_SCRIPT.search(text)) or gs + (amb if gs >= ms else 0) >= 2 or any(x in GU_STRONG and x not in ("chhe", "chhu") for x in w)
    if code == "mwr":
        return ms + (amb if ms > gs else 0) >= 2 or any(x in MWR_STRONG for x in w)         # one unmistakable word (mharo, mhane, thane, chaije ...) is enough
    if code == "en":
        return len(w) >= 4 and sum(1 for x in w if x in EN_FUNC) >= 2 and not any(x in HI_ONLY for x in w)
    if code == "hi":
        return sum(1 for x in w if x in HI_MARKERS) >= 3
    return False


def switch_request(text: str):
    """The caller asks for a language ('English mein baat karo', 'Gujarati ma vaat karo', 'Marwadi mein bolo')."""
    low = text.lower()
    if not re.search(r"bol|baat|vaat|vat|speak|talk|mein|me\b|mai\b|main\b|\bma\b|please|plz|chahiye|joiye|chaije|language|boli|samjh|samaj|karo|kar", low):
        return None
    for code, pat in _SWITCH:
        if re.search(pat, low):
            return code
    return None


# ---------------------------------------------------------------------------------------------------------------- dialect -> Hinglish
# Gujarati (Roman, loose spelling) -> the Hinglish word the flow knows
GU = {
    "kyan_chhe": "kahan hai", "tamaro": "aapka", "tamaro_naam": "aapka naam", "ketlu": "kitna", "kaay": "kya", "kasu": "kuch", "bija": "doosra", "biju": "doosra", "biji": "doosri", "koi_nathi": "koi nahi",
    "nokri_karu": "naukri karta", "karu": "karta", "chhu_hu": "hoon", "dasa": "das", "dash": "das", "varsh_thi": "saal se", "thi": "se", "thii": "se", "mate_": "ke liye", "lagn": "shaadi", "lagna": "shaadi", "lagan": "shaadi",
    "mane": "mujhe", "mare": "mujhe", "maru": "mera", "maaru": "mera", "mari": "meri", "mara": "mere", "maraa": "mere", "doo": "do", "lon": "loan", "lone": "loan", "loon": "loan", "tamaru": "aapka", "tamari": "aapki", "tamara": "aapke", "tame": "aap", "tamne": "aapko",
    "amne": "hume", "amara": "hamara", "amaru": "hamara", "amari": "hamari", "hu": "main", "hun": "main", "chhe": "hai", "chhu": "hoon", "chho": "ho", "chhie": "hain", "chhiye": "hain", "che": "hai", "chhey": "hai",
    "joiye": "chahiye", "joie": "chahiye", "joiy": "chahiye", "joi": "chahiye", "joiye_chhe": "chahiye", "shu": "kya", "su": "kya", "shun": "kya", "kem": "kaise", "ketlo": "kitna", "ketla": "kitne", "ketli": "kitni",
    "kitlo": "kitna", "kitla": "kitne", "kitli": "kitni", "kyare": "kab", "kyan": "kahan", "kyaan": "kahan", "kone": "kisko", "kon": "kaun", "koni": "kiski", "kevi": "kaisi", "kevu": "kaisa", "rite": "tarah",
    "nathi": "nahi", "nathii": "nahi", "na": "na", "naa": "nahi", "ha": "haan", "haa": "haan", "haji": "haan ji", "haju": "abhi", "pachi": "baad", "pehla": "pehle", "pela": "pehle", "aaje": "aaj", "kale": "kal",
    "savare": "subah", "bapore": "dopahar", "sanje": "shaam", "ratre": "raat", "vagye": "baje", "vage": "baje", "vaat": "baat", "vat": "baat", "karvi": "karna", "karvu": "karna", "karvo": "karna", "karo": "karo",
    "karu": "karun", "karshu": "karenge", "aapo": "dijiye", "apo": "dijiye", "aapjo": "dijiye", "batavo": "bataiye", "batavjo": "bataiye", "samjayu": "samajh aaya", "samajayu": "samajh aaya", "farithi": "phir se",
    "pharithi": "phir se", "fari": "phir", "ane": "aur", "pan": "bhi", "saru": "theek", "saaru": "theek", "barabar": "theek", "barobar": "theek", "pagar": "salary", "pagaar": "salary", "vyaj": "byaj",
    "vyajdar": "byaj dar", "dhandho": "business", "dhandha": "business", "nokri": "job", "nokari": "job", "lidhi": "li", "lidhu": "liya", "levi": "lena", "levu": "lena", "leva": "lene", "madad": "madad",
    "madat": "madad", "jarur": "zaroor", "jaroor": "zaroor", "taklif": "dikkat", "mushkel": "mushkil", "hajar": "hazaar", "hajaar": "hazaar", "rupiya": "rupaye", "rupiyaa": "rupaye", "rupia": "rupaye",
    "krupiya": "rupaye", "krupiyani": "rupaye ki", "rupiyani": "rupaye ki", "ni": "ki", "nu": "ka", "athva": "ya", "athawa": "ya", "to": "toh", "tya": "wahan",
    "ahiya": "yahan", "ahi": "yahan", "kyathi": "kahan se", "kyathi_": "kahan se", "ketlama": "kitne mein", "kyarey": "kab", "mate": "ke liye", "maate": "ke liye", "sathe": "ke saath", "vagar": "bina", "vina": "bina",
    "kai": "kuch", "kaik": "kuch", "badhu": "sab", "badha": "sab", "badhi": "sab", "thay": "hota hai", "thase": "hoga", "thashe": "hoga", "malse": "milega", "malshe": "milega", "male": "milta hai", "aavshe": "aayega",
    "aavjo": "aana", "jaaje": "jaana", "kaho": "kaho", "kahevu": "kehna", "kahe": "kehta", "bolo": "bolo", "boli": "boli", "bolvu": "bolna", "puchhvu": "puchna", "pushvu": "puchna", "puchu": "puchun", "jovu": "dekhna",
    "jaanvu": "jaanna", "janvu": "jaanna", "jaanvu_chhe": "jaanna", "jano": "jaanna", "khabar": "pata", "khabar_nathi": "pata nahi", "nahi": "nahi", "hatu": "tha", "hati": "thi", "hata": "the", "hoy": "hota", "hovu": "hona",
    "bhai": "bhai", "ben": "behen", "behn": "behen", "kaka": "kaka", "dikra": "beta", "dikri": "beti", "dost": "dost", "gam": "gaon", "gaam": "gaon", "shahar": "shehar", "sheher": "shehar", "ghare": "ghar par",
    "dukan": "dukan", "dukaan": "dukan", "kharidvu": "kharidna", "kharid": "kharid", "vechvu": "bechna", "bhadu": "kiraya", "ugharani": "vasooli", "hapto": "kist", "hapta": "kist", "haptao": "kist", "emi": "EMI",
    "kapay": "kat", "kapaay": "kat", "kapat": "katauti", "dastavej": "dastavez", "dastavejo": "dastavez", "kagal": "kagaz", "kagalo": "kagaz", "pura": "pura", "vadhu": "zyada", "ochhu": "kam", "ochha": "kam",
    "moto": "bada", "nano": "chhota", "saaro": "accha", "saro": "accha", "kharab": "kharab", "navu": "naya", "juno": "purana", "jaldi": "jaldi", "turant": "turant", "dhire": "dheere", "dhire_dhire": "dheere dheere",
    "aavta": "aate", "aavo": "aaiye", "aavu": "aana", "javu": "jana", "jaay": "jaata", "jauu": "jaun", "bethu": "baitha", "raheto": "rehta", "rahyo": "raha", "rahi": "rahi",
    "kari": "kar", "kariye": "karte", "kare": "karta", "kartu": "karta", "karto": "karta", "karti": "karti", "kaam": "kaam", "nokariya": "naukri", "mahino": "mahina", "mahina": "mahina", "mahinana": "mahine ki",
    "varsh": "saal", "varas": "saal", "saal": "saal", "divas": "din", "divasma": "din mein", "kalak": "ghanta", "kalakma": "ghante mein", "minit": "minute", "ardho": "aadha", "adhi": "aadhi", "paun": "paun",
    "sava": "sava", "doda": "dedh", "dedh": "dedh", "adhi_": "dhai",
}
GU_NUM = {"ek": "ek", "be": "do", "bey": "do", "tran": "teen", "traan": "teen", "chaar": "char", "char": "char", "paanch": "paanch", "panch": "paanch", "chha": "chhe", "chhah": "chhe", "saat": "saat", "aath": "aath", "nav": "nau", "nau": "nau",
          "das": "das", "agiyar": "gyarah", "bar": "barah", "ter": "terah", "chaud": "chaudah", "pandar": "pandrah", "sol": "solah", "satar": "satrah", "athar": "atharah", "ogani": "unnis", "vees": "bees", "ekvis": "ikkis",
          "bavis": "bais", "trevis": "teis", "chovis": "chaubis", "pachis": "pachis", "chhavis": "chhabbis", "satavis": "sattais", "athavis": "atthais", "ogantris": "unatis", "tris": "tees", "chalis": "chalis",
          "pachas": "pachas", "pachaas": "pachas", "saath": "saath", "sattar": "sattar", "sitter": "sattar", "eshi": "assi", "nevu": "nabbe", "so": "sau", "sau": "sau", "hajar": "hazaar", "hazar": "hazaar", "lakh": "lakh"}

# Marwari / Rajasthani village forms -> Hinglish
MWR = {
    "mahaaron": "mera", "mahaaro": "mera", "mahaaran": "mere", "mahaari": "meri", "mahro": "mera", "mahri": "meri", "chhe": "hai", "chhai": "hai", "chhu": "hoon", "chho": "ho", "chhaa": "hain",
    "kono": "nahi", "kono_hai": "nahi hai", "kanai": "nahi", "dujo": "doosra", "duji": "doosri", "duja": "doosre", "su": "se", "sun": "se", "sursi": "se", "sarun": "ke liye", "sarau": "ke liye", "saaru": "ke liye", "sarus": "ke liye",
    "mhe": "main", "mhaan": "main", "karu": "karta hoon", "kar_sako": "kar sakte", "sako": "sakte", "sakoo": "sakte", "ho_ji": "ji", "marammat": "marammat", "ghar_ri": "ghar ki", "ri_marammat": "ki marammat", "kaal": "kal", "das": "das", "bajyo": "baje", "baje": "baje",
    "mhare": "mere", "mhaare": "mere", "mharo": "mera", "mhaaro": "mera", "mhari": "meri", "mhaari": "meri", "mhara": "mere", "mhaara": "mere", "maaro": "mera", "maari": "meri", "mari": "meri", "maro": "mera", "maru": "mera", "doo": "do", "lon": "loan", "lone": "loan", "loon": "loan", "mhane": "mujhe", "mhanne": "mujhe",
    "mhaane": "mujhe", "manne": "mujhe", "mane": "mujhe", "thane": "aapko", "thanne": "aapko", "thaane": "aapko", "thare": "aapke", "thaare": "aapke", "tharo": "aapka", "thaaro": "aapka", "thari": "aapki", "thaari": "aapki",
    "thara": "aapke", "thaara": "aapke", "thaa": "aap", "thame": "aap", "kai": "kya", "kain": "kya", "kaain": "kya", "kaaiyan": "kya", "kayi": "kya", "kaayi": "kya", "kaaN": "kya", "kun": "kaun", "kuun": "kaun", "kunsi": "kaunsi",
    "kunsa": "kaunsa", "kathe": "kahan", "kathai": "kahan", "kaathe": "kahan", "kiyan": "kaise", "kiyaan": "kaise", "kyaan": "kaise", "kito": "kitna", "kitto": "kitna", "kitti": "kitni", "kiti": "kitni", "kitta": "kitne",
    "kadi": "kab", "kadai": "kab", "ghano": "bahut", "ghani": "bahut", "ghana": "bahut", "ghanaa": "bahut", "lagsi": "lagega", "lagse": "lagega", "lagasi": "lagega", "hosi": "hoga", "hovsi": "hoga", "hovegi": "hoga",
    "hove": "hota hai", "milsi": "milega", "milse": "milega", "milegi": "milega", "chaije": "chahiye", "chaaije": "chahiye", "chaiji": "chahiye", "chaijo": "chahiye", "chaijyo": "chahiye", "chaizi": "chahiye", "chahije": "chahiye",
    "dijo": "dijiye", "deejo": "dijiye", "dyo": "dijiye", "dyoji": "dijiye", "hukam": "ji", "hukum": "ji", "sa": "", "saa": "", "ri": "ki", "ro": "ka", "ra": "ke", "re": "ke", "rai": "ki", "ae": "yeh", "ona": "uska", "oni": "uski",
    "koni": "nahi", "konyi": "nahi", "konai": "nahi", "nai": "nahi", "naain": "nahi", "hao": "haan", "haanji": "haan ji", "saanjh": "shaam", "saanj": "shaam", "savere": "subah", "dupaar": "dopahar", "dupar": "dopahar",
    "paachho": "baad", "paachhe": "baad", "pachhe": "baad", "baapu": "pitaji", "bapu": "pitaji", "bai": "behen", "bainsa": "behen", "gaam": "gaon", "kheti": "kheti", "kheto": "kheti", "khet": "khet", "dhani": "dhani",
    "avo": "aaiye", "aavo": "aaiye", "jaavo": "jaiye", "karsyu": "karenge", "karsi": "karega", "karasi": "karega", "karanga": "karenge", "karuun": "karun", "rahyo": "raha", "rahyi": "rahi", "reh": "reh", "rehvo": "rehna",
    "rahvo": "rehna", "hunn": "hoon", "hu": "hoon", "hoon": "hoon", "tankhwa": "salary", "tankha": "salary", "tankhwah": "salary", "tanakhvaah": "salary", "tanka": "salary", "byaj": "byaj", "biaaj": "byaj", "pagaar": "salary",
    "kamai": "kamai", "paisa": "paisa", "paisaa": "paisa", "rupiya": "rupaye", "rupiyaa": "rupaye", "rupya": "rupaye", "rupyaa": "rupaye", "krupeari": "rupaye ki", "rupyaari": "rupaye ki", "rupeari": "rupaye ki",
    "lugai": "patni", "dhaaniya": "dhani", "bhaayo": "bhai", "bhayo": "bhai", "chhora": "bete", "chhori": "beti", "chhoro": "beta", "mhaaraj": "ji", "dhanyawad": "dhanyavad", "ram_ram": "namaste", "khamma": "namaste",
    "ghani_khamma": "namaste", "jaisi": "ji", "kai_ke": "kya", "ladli": "beti", "karaj": "kaam", "karaaj": "kaam", "kaaj": "kaam", "kaamkaaj": "kaam", "dhandho": "business", "dhandha": "business",
    "naukri": "naukri", "nokri": "naukri", "chaakri": "naukri", "chaakari": "naukri", "jamin": "zameen", "zamin": "zameen", "jameen": "zameen", "makaan": "makan", "ghar": "ghar", "bechno": "bechna", "kharidno": "kharidna",
    "udhaar": "udhaar", "udhar": "udhaar", "bhaav": "bhav", "bhao": "bhav", "byajdar": "byaj dar", "kist": "kist", "kisat": "kist", "kisht": "kist", "hapto": "kist", "hapta": "kist", "dastavej": "dastavez", "kaagad": "kagaz",
    "kagad": "kagaz", "kaagaz": "kagaz", "patro": "kagaz", "pura": "pura", "ghat": "kam", "ghatto": "kam", "ghani_kam": "bahut kam", "vadhu": "zyada", "badho": "bada", "chhoto": "chhota", "naayo": "naya", "puraano": "purana",
    "ajkal": "aajkal", "aaj": "aaj", "kaal": "kal", "parsu": "parso", "parsaa": "parso", "ek_ghanto": "ek ghanta", "ghanto": "ghanta", "aadho": "aadha", "dedh": "dedh", "dhai": "dhai", "sunyo": "suna", "samjhyo": "samjha",
    "samjhi": "samjhi", "samjhyaa": "samjha", "samjhaayo": "samjhaya", "bolo": "bolo", "bolyo": "bola", "bataavo": "bataiye", "batavo": "bataiye", "batao": "bataiye", "bataadyo": "bata do", "dekho": "dekhiye", "dekhyo": "dekha",
}
MWR_NUM = {"ek": "ek", "do": "do", "dho": "do", "teen": "teen", "tin": "teen", "chaar": "char", "char": "char", "paanch": "paanch", "panch": "paanch", "chhah": "chhe", "chha": "chhe", "saat": "saat", "aath": "aath",
           "nau": "nau", "das": "das", "gyaarah": "gyarah", "baarah": "barah", "pachaas": "pachas", "pachas": "pachas", "saath": "saath", "sau": "sau", "hajar": "hazaar", "hajaar": "hazaar", "lakh": "lakh", "laakh": "lakh"}

_GU_ALL = {**GU, **GU_NUM}
_MWR_ALL = {**MWR, **MWR_NUM}


def _fuzzy(word: str, table: dict):
    if word in table:
        return table[word]
    if word in HI_MARKERS or word in EN_WORDS:
        return None
    if len(word) >= 6:
        hit = difflib.get_close_matches(word, list(table), n=1, cutoff=0.88)
        if hit:
            return table[hit[0]]
    return None


def to_hinglish(text: str, lang: str) -> str:
    """Gujarati / Marwari words -> Hinglish; every other word is kept."""
    if lang not in ("gu", "mwr") or not text:
        return text
    if lang == "gu" and _GU_SCRIPT.search(text):
        text = transliterate_gu(text)
    table = _GU_ALL if lang == "gu" else _MWR_ALL
    if lang == "gu":
        text = re.sub(r"\bkya\s+(?=chh?e\b|aav|hati\b|hato\b)", "kahan ", text, flags=re.I)

    protect = {"n": 0}                                                      # the two words after "naam" are a name: never translate them

    def one(m):
        w = m.group(0)
        lw = w.lower()
        if lw in ("naam", "nam", "name"):
            protect["n"] = 2
            return w
        if protect["n"] > 0 and lw not in ("chhe", "hai", "che", "hu", "chu", "hoon"):
            protect["n"] -= 1
            return w
        protect["n"] = 0
        out = _fuzzy(lw, table)
        if out is None:
            return w
        return out
    out = re.sub(r"[A-Za-z_]+", one, text)
    return re.sub(r"\s{2,}", " ", out).strip()


# --- Gujarati script -> Roman (so a transcript written in Gujarati letters can be understood too)
_GU_V = {"અ": "a", "આ": "aa", "ઇ": "i", "ઈ": "i", "ઉ": "u", "ઊ": "u", "એ": "e", "ઐ": "ai", "ઓ": "o", "ઔ": "au", "ઍ": "e", "ઑ": "o", "ઋ": "ru"}
_GU_M = {"ા": "a", "િ": "i", "ી": "i", "ુ": "u", "ૂ": "u", "ે": "e", "ૈ": "ai", "ો": "o", "ૌ": "au", "ૅ": "e", "ૉ": "o", "ૃ": "ru"}
_GU_C = {"ક": "k", "ખ": "kh", "ગ": "g", "ઘ": "gh", "ચ": "ch", "છ": "chh", "જ": "j", "ઝ": "jh", "ટ": "t", "ઠ": "th", "ડ": "d", "ઢ": "dh", "ણ": "n", "ત": "t", "થ": "th", "દ": "d", "ધ": "dh", "ન": "n",
         "પ": "p", "ફ": "f", "બ": "b", "ભ": "bh", "મ": "m", "ય": "y", "ર": "r", "લ": "l", "વ": "v", "શ": "sh", "ષ": "sh", "સ": "s", "હ": "h", "ળ": "l", "ક્ષ": "ksh", "જ્ઞ": "gn"}
_GU_D = {"૦": "0", "૧": "1", "૨": "2", "૩": "3", "૪": "4", "૫": "5", "૬": "6", "૭": "7", "૮": "8", "૯": "9"}


def transliterate_gu(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch in _GU_C or text[i:i + 2] in _GU_C:
            c = _GU_C.get(text[i:i + 2]) or _GU_C[ch]
            i += 2 if text[i:i + 2] in _GU_C else 1
            nxt = text[i] if i < len(text) else ""
            if nxt in _GU_M:
                out.append(c + _GU_M[nxt])
                i += 1
            elif nxt == "્":
                out.append(c)
                i += 1
            elif nxt in ("ં", "ઁ"):
                out.append(c + "a" + "n")
                i += 1
            else:
                out.append(c + "a")                                         # inherent vowel (dropped again at the end of a word below)
        elif ch in _GU_V:
            out.append(_GU_V[ch])
            i += 1
        elif ch in _GU_D:
            out.append(_GU_D[ch])
            i += 1
        elif ch in ("ં", "ઁ"):
            out.append("n")
            i += 1
        else:
            out.append(ch)
            i += 1
    s = "".join(out)
    return re.sub(r"([bcdfghjklmnpqrstvwxyz])a(?=\b)", r"\1", s)       # no inherent vowel at the end of a word
