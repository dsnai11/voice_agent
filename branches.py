"""Branch answers from the company's branch list ("kya Sikar mein aapki branch hai?").

The list lives in knowledge/branches.json, which stays on this PC (not on GitHub). Make it from the spreadsheet with
    python branches.py "C:\\path\\Branches.xlsx"
Only name, city (district), state, address and pincode are copied. Nothing is invented: a place that is not in the list is
never said to have a branch. A language model is not involved.
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "knowledge", "branches.json")

STATES = {"Rajasthan": ("राजस्थान", r"raja?sthaa?n|राजस्थान"),
          "Madhya Pradesh": ("मध्य प्रदेश", r"madhya?\s*pradesh|\bm\s*\.?\s*p\b|एमपी|मध्य\s*प्रदेश"),
          "Gujarat": ("गुजरात", r"guj+a?raa?t(?!i)|गुजरात(?!ी)"),
          "Uttar Pradesh": ("उत्तर प्रदेश", r"uttar?\s*pradesh|\bu\s+p\b|\bu\.p\b|\bup\s+(?:mein|me|main|wali|wala|vali|vala)\b|यूपी|उत्तर\s*प्रदेश"),
          "Chhattisgarh": ("छत्तीसगढ़", r"chh?att?isga?rh?|\bc\s*g\s+(?:mein|me|main)\b|छत्तीसगढ़"),
          "Maharashtra": ("महाराष्ट्र", r"maharash?th?ra|महाराष्ट्र")}
_STATE_CODE = {"mp": "Madhya Pradesh", "up": "Uttar Pradesh", "cg": "Chhattisgarh", "gj": "Gujarat", "gujarat": "Gujarat", "rajasthan": "Rajasthan", "raj": "Rajasthan",
               "maharastra": "Maharashtra", "maharashtra": "Maharashtra"}
# spreadsheet spelling -> the usual spelling
_FIX = {"ahemadabad": "Ahmedabad", "jalgoan": "Jalgaon", "dulhe": "Dhule", "shri ganganagar": "Sri Ganganagar", "ganganagar": "Sri Ganganagar", "nagour": "Nagaur"}
# other names callers use -> the name in the list
_ALIAS = {"vadodara": "Baroda", "allahabad": "Prayagraj", "narmadapuram": "Hoshangabad", "ganganagar": "Sri Ganganagar", "shriganganagar": "Sri Ganganagar",
          "sriganganagar": "Sri Ganganagar", "chittor": "Chittorgarh", "chitor": "Chittorgarh", "ahemdabad": "Ahmedabad", "amdavad": "Ahmedabad", "jhunjunu": "Jhunjhunu",
          "jhujhunu": "Jhunjhunu", "rae bareli": "Raebareli", "banaras": "Varanasi", "benaras": "Varanasi", "abu road": "Abu Road", "aburoad": "Abu Road",
          "madhopur": "Sawai Madhopur", "nagor": "Nagaur", "bhilvara": "Bhilwara", "sikkar": "Sikar", "pilvada": "Bhilwara", "pilvara": "Bhilwara", "bhelvada": "Bhilwara", "dilvara": "Bhilwara", "dilvada": "Bhilwara", "jhalawad": "Jhalawar", "mahesana": "Mehsana"}

BRANCH_WORDS = r"\b(?:branch|branches|branchon|branche|braanch|braanches|branchh|shakha|saakha|office|ofis|offis|daftar)\b|ब्रांच|ऑफिस|ऑफ़िस|शाखा|દફતર|બ્રાંચ"
HEAD_OFFICE = r"\b(?:head|main|corporate|registered)\s+office\b|\bheadoffice\b|मुख्य\s+(?:ऑफिस|ऑफ़िस|कार्यालय)"
ASK_AGAIN = r"\b(?:address|adress|pata|pin\s*code|pincode|location|kahan\s+(?:par\s+)?(?:hai|he|padti|padta))\b|पता|पिन\s*कोड"
# "give me all of them": every branch she just listed, or every branch of the place named
EVERY = r"\b(?:dono|donon|donno|dono[n]?\s+ka|sab|sabhi|saare|sare|saari|sari|tamam|all|both)\b|\b(?:jo\s+jo|jis\s+jo|jo\s+bhi|jitn[ei])\b|\bjo\s+(?:\w+\s+)?branch\w*|दोनों|सभी|सारे|सारी"
PIN_WORDS = r"\bpin\s*-?\s*code\w*|\bpin\s+kod\w*|पिन\s*कोड"
WANTS_ADDRESS = r"\b(?:address\w*|adress|pata|location|kahan\s+(?:par\s+)?(?:jaun|jau|jaaun|jaye|jana))\b|पता"
WANTS_ADDRESS = WANTS_ADDRESS.replace(r"|pata|", r"|pata(?!\s+(?:nahi|nahin|nhi|nai|hai|he|chal\w*|kar\w*|ho\w*|lag\w*|tha))|")      # "pata nahi" = "do not know"
ASKING = r"\bbata\w*|\bbta\w*|\b(?:do|dijiye|chahiye|chahie|kya|what|tell|give|jaun|jau|jaaun|jana)\b|\?|बता"
OWN_ADDRESS = r"\b(?:mera|meri|mere|hamara|hamari|my)\b(?:\s+\w+){0,2}?\s+(?:address|adress|pata|pin\s*code|pincode)\b"
READ_ALL_MAX = 3                  # more than this is too much to read out on a call: she asks which one
# words that are never the name of a place the caller asks about
_NOT_PLACE = set("""aapki aapka aapke apki apka apni hamare hamara mere mera meri kya koi kahi kahin kaha kahan kahaan kidhar kitni tamari tamaro thari tharo kathe yahanyaha wahan waha idhar udhar hai hain he ho tha thi nahi nahin
mein me main par pe ki ka ke ko se tak aur bhi to toh ji sir madam haan han na city shahar shehar sheher gaon gaav gaanv village jila zila district state area ilaka town
branch branches office shakha loan lone lena chahiye chahie batao bataiye bataye bata do dijiye de please aap tum hum main mai kis kaun konsi kaunsi sa si nazdik najdik nazdeek paas pass
near nearest nagar colony road marg wali wala vali vala company finance laxmi lakshmi india limited address pata pincode pin code number kitni kitne total sab sabhi there any is are do you have your in at the of my our""".split())


def _norm(text: str) -> str:
    """One spelling for matching: the listener writes "Jaypur", "Seekar", "Bheelwaada"."""
    t = re.sub(r"[^a-z ]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    for a, b in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("ay", "ai"), ("w", "v"), ("z", "j"), ("ph", "f")):
        t = t.replace(a, b)
    return re.sub(r"(.)\1", r"\1", t)


def _title(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split())


def _town(name: str) -> str:
    """'AGAR MALWA (MP)' -> 'Agar Malwa'."""
    t = re.sub(r"\([^)]*\)?", " ", str(name))
    t = re.sub(r"[-_/]+", " ", t)
    return _title(re.sub(r"\s+", " ", t).strip().lower())


def build(xlsx: str) -> list:
    import openpyxl

    ws = openpyxl.load_workbook(xlsx, read_only=True, data_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if any(r)]
    head = [str(h or "").lower() for h in rows[0]]
    col = {k: next(i for i, h in enumerate(head) if k in h) for k in ("name", "city", "state", "address", "pincode")}
    out = []
    for r in rows[1:]:
        city = re.sub(r"\s+", " ", str(r[col["city"]]).strip()).lower()
        state = str(r[col["state"]]).strip().lower()
        address = re.sub(r"\s+", " ", str(r[col["address"]]).strip())
        address = re.sub(r"\s+([,.])", r"\1", address)
        pin = re.sub(r"\D", "", str(r[col["pincode"]]))
        out.append({"town": _town(r[col["name"]]), "city": _FIX.get(city, _title(city)), "state": _STATE_CODE.get(state, _title(state)), "address": address, "pincode": pin})
    return out


_cache = None


def load() -> list:
    global _cache
    if _cache is None:
        try:
            with open(DATA, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = []
    return _cache


def _places() -> dict:
    """normalised name -> (shown name, [branches in that town], [branches in that district])"""
    out = {}
    for b in load():
        for key, kind in ((b["town"], 1), (b["city"], 2)):
            n = _norm(key)
            entry = out.setdefault(n, [key, [], []])
            entry[kind].append(b)
    for b in load():
        for short in short_names(b["town"])[1:]:
            entry = out.setdefault(_norm(short), [short, [], []])
            if b not in entry[1]:
                entry[1].append(b)
    for said, real in list(_heard_names().items()) + list(_ALIAS.items()):
        if _norm(real) in out:
            out.setdefault(_norm(said), out[_norm(real)])
    return out


def find_place(text: str):
    """The town or district named in the sentence, or None. Short names (Dhar, Guna, Kota) must be said exactly."""
    places = _places()
    words = _norm(text).split()
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            part = " ".join(words[i:i + size])
            if part in places and part not in _NOT_PLACE:
                return places[part]
    best, score = None, 0.0
    for size in (2, 1):
        for i in range(len(words) - size + 1):
            part = " ".join(words[i:i + size])
            if len(part) < 5 or part in _NOT_PLACE or any(w in _NOT_PLACE for w in part.split()):
                continue
            for key in places:
                if len(key) < 5:
                    continue
                s = difflib.SequenceMatcher(None, part, key).ratio()
                if s > score:
                    best, score = key, s
    return places[best] if score >= 0.86 else None


def find_state(text: str):
    low = text.lower()
    return next((s for s, (_hi, pat) in STATES.items() if re.search(pat, low)), None)


def _unknown_name(text: str) -> str:
    """The place the caller named that is not in the list: the word before "mein" / "me", or after "in"."""
    low = re.sub(r"[^a-z ]", " ", text.lower())
    for pat in (r"\b([a-z]{3,})\s+(?:mein|me|mai|may)\b", r"\b([a-z]{3,})\s+(?:wali|vali|ki|ka)\s+(?:branch|office)\b", r"\b(?:branch|office)\s+in\s+([a-z]{3,})\b"):
        for w in re.findall(pat, low):
            if w not in _NOT_PLACE:
                return w.capitalize()
    return ""


DIGITS = ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"]


def spoken_pin(pin: str) -> str:
    return " ".join(DIGITS[int(d)] for d in pin)


def one_branch(b: dict) -> str:
    address = re.sub(r"[।?!]", ",", b["address"]).rstrip(" .,-")
    address = re.sub(r"[\s,-]*(?:pin\s*(?:code)?\s*[-:]?\s*)?\b\d{6}\b", "", address, flags=re.I).rstrip(" .,-")       # the pincode is said once, on its own
    address = re.sub(r"(?<=[a-z0-9])\.(?=\s)", ",", address, flags=re.I)                    # "Near Bank. Main Road": one sentence
    return (f"जी हाँ, {b['town']} में हमारी ब्रांच है, ज़िला {b['city']}, {STATES[b['state']][0]}। "
            f"पता है, {address}। पिनकोड है {spoken_pin(b['pincode'])}।")


def pin_of(b: dict) -> str:
    return f"{b['town']} ब्रांच का पिनकोड है {spoken_pin(b['pincode'])}।"


def _read(found: list, text: str, memory: dict) -> str:
    """Every branch in `found`: only the pincodes when only the pincode was asked, else each address."""
    low = text.lower()
    memory["waiting"], memory["last"], memory["shown"] = False, found[-1], found
    if len(found) > 1 or not memory.get("pool") or found[0] not in memory["pool"]:
        memory["pool"] = found
    memory["group"] = []
    if re.search(PIN_WORDS, low) and not re.search(WANTS_ADDRESS, low):
        return " ".join(pin_of(b) for b in found)
    return " ".join(one_branch(b) for b in found)


def _plain(name: str) -> str:
    """For comparing with a place already talked about: the listener mixes d / r and e / i ("Dilvaara", "Bhelvaada")."""
    return _norm(name).replace("d", "r").replace("e", "i").replace(" ", "")


def _heard_as(text: str, known: str) -> bool:
    """A word that is very probably `known` heard wrongly. Used only for the place this call is already about."""
    if not known:
        return False
    target = _plain(known)
    for w in _norm(text).split():
        if len(w) >= 6 and w not in _NOT_PLACE and difflib.SequenceMatcher(None, _plain(w), target).ratio() >= 0.72:
            return True
    return False


# ------------------------------------------------------------- names as the listener writes them
HEARD = os.path.join(HERE, "knowledge", "heard_places.json")      # stays on this PC, like the branch list: {"what the listener wrote": "name in the list"}
READ_ALL_ASKED = 6                # "jitni bhi hain, sab ka pata": up to this many addresses are read out
_SUFFIX = r"\s+(?:ajmer|renwal|city|ho)$|city$"
_extra = None


def _heard_names() -> dict:
    global _extra
    if _extra is None:
        try:
            with open(HEARD, encoding="utf-8") as f:
                _extra = json.load(f)
        except (OSError, ValueError):
            _extra = {}
    return _extra


def short_names(town: str) -> list:
    """"Kishangarh Ajmer" is also called "Kishangarh"; "Sojat City" is "Sojat"."""
    out = [town]
    cut = re.sub(_SUFFIX, "", town, flags=re.I).strip()
    if cut and cut.lower() != town.lower() and cut.lower() != "jaipur":
        out.append(cut)
    return out


def sound(name: str) -> str:
    """The consonants as heard: "Kishangarh", "kishan ghar" and "Kishnagadh" give one key."""
    t = re.sub(r"[^a-z]", "", name.lower()).replace("w", "v").replace("z", "j").replace("ph", "f").replace("q", "k")
    t = re.sub(r"([bcdgjkpt])h", r"\1", t)
    t = t[:1] + re.sub(r"[aeiouyh]", "", t[1:])
    t = t[:1] + t[1:].replace("d", "r")
    return re.sub(r"(.)\1+", r"\1", t)


def _grams(text: str):
    words = [w for w in re.sub(r"[^a-z ]", " ", text.lower()).split()]
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            part = words[i:i + size]
            if part[0] in _NOT_PLACE or part[-1] in _NOT_PLACE:
                continue
            yield " ".join(part)


def match_among(text: str, pool: list, strict: bool = False) -> list:
    """The branches of `pool` whose town is named in the sentence, as heard. Strict is used when searching the whole list."""
    scored = {}
    heard = _heard_names()
    grams = list(_grams(text))
    for i, b in enumerate(pool):
        names = short_names(b["town"])
        names += [said for said, real in heard.items() if real.lower() in [n.lower() for n in names]]
        best = 0.0
        for gram in grams:
            joined = gram.replace(" ", "")
            if len(joined) < 4:
                continue
            for name in names:
                target = name.lower().replace(" ", "")
                ratio = difflib.SequenceMatcher(None, _plain(joined), _plain(target)).ratio()
                key = sound(joined)
                if key == sound(target) and len(key) >= (4 if strict else 2) and ratio >= 0.6:
                    ratio = max(ratio, 0.9 + ratio / 100)
                if _plain(joined) == _plain(target):
                    ratio = 1.0
                best = max(best, ratio)
        if best >= (0.9 if strict else 0.78):
            scored[i] = best
    if not scored:
        return []
    own = [i for i in scored if pool[i]["town"].lower() == pool[i]["city"].lower()]
    if len(scored) > len(own):                       # "Ajmer mein Kishangarh": the district's own name only says where to look
        for i in own:
            del scored[i]
    top = max(scored.values())
    return [pool[i] for i, s in scored.items() if s >= top - 0.03]


_LIVES = r"\b(?:rehti|rehta|rahti|rahta|rahte|rehte|se\s+(?:hoon|hun|hu)|business|bijness|dukaan|dukan)\b"
_WANTED = r"\b(?:address\w*|adress|pata|branch\w*|pin\s*code\w*|pincode\w*|chahiye|chahie|chaiye|shakha)\b"


def wanted_part(text: str) -> str:
    """"I live in Jaipur, my business is in Bhilwara, but I want the Ajmer address": only the last part names the place asked for."""
    parts = [p.strip() for p in re.split(r"[.,;!?]|\b(?:lekin|magar|but|par\s+mujhe|jabki)\b", text, flags=re.I) if p and p.strip()]
    if len(parts) < 2:
        return text
    asked = [p for p in parts if re.search(_WANTED, p.lower()) and find_place(p) and not (re.search(_LIVES, p.lower()) and not re.search(r"address|pata|branch|pin", p.lower()))]
    return asked[-1] if asked else text


def misheard_branch(text: str) -> str:
    """The listener sometimes writes "branches" as "bounce" or "baat": "Ajmer mein kaun kaun si baat", "Bhilwara mein kitne total bounce hai"."""
    low = text.lower()
    if re.search(r"\b(?:emi|kist|cheque|check|ecs|nach|charge\w*|fee|fees|penalty)\b", low) or not re.search(r"\b(?:mein|me|main|may)\b", low):
        return text
    return re.sub(r"(\b(?:kaun\s*kaun\s*s[aei]|kon\s*kon\s*s[aei]|total|kitn[aei]\s+total)\s+)(?:bounce|baat|bat|brunch|bench|banch)\b", r"\1branches", text, flags=re.I)


NAME_AGAIN = "माफ़ कीजिए, ब्रांच का नाम ठीक से समझ नहीं आया। नाम एक बार फिर बताइए।"


def _several(name: str, found: list) -> str:
    names = [b["town"] for b in found]
    towns = [f"{b['town']} (ज़िला {b['city']})" if names.count(b["town"]) > 1 else b["town"] for b in found]      # two branches with one name
    shown = ", ".join(towns)
    return f"जी हाँ, {name} में हमारी {len(towns)} ब्रांच हैं: {shown}। आप किस जगह की ब्रांच का पता चाहेंगे?"


def answer(text: str, memory: dict):
    """(reply, True if the reply ends with her own question) for a branch question, else None.
    `memory` is kept for the call: {"waiting": True after she asked which place, "last": the branch she last described}."""
    if not load():
        return None
    text = misheard_branch(text)
    low = text.lower()
    asks_branch = bool(re.search(BRANCH_WORDS, low))
    waiting = memory.get("waiting")
    if re.search(HEAD_OFFICE, low):
        return None
    every, pin, address = (bool(re.search(p, low)) for p in (EVERY, PIN_WORDS, WANTS_ADDRESS))
    scope = wanted_part(text)                                         # the part that says which place is wanted
    shown = memory.get("shown") or []
    context = memory.get("district") or memory.get("home") or ""
    if (re.search(OWN_ADDRESS, low) and not asks_branch) or not re.search(ASKING, low):
        pin_asked, address_asked = False, False          # "mera pata Jaipur ka hai", "mera pincode ... hai": the caller's own
    else:
        pin_asked, address_asked = pin, address
    wants_detail = asks_branch or waiting or pin_asked or address_asked
    pool = memory.get("pool") or []
    short = len(low.split()) <= 4
    own = bool(re.search(OWN_ADDRESS, low)) or (bool(re.search(_LIVES, low)) and not asks_branch and not address_asked and not pin_asked)
    if pool and not own and (wants_detail or (short and memory.get("step") not in ("city", "full_name"))):
        hit = match_among(scope, pool)                                # one of the branches just talked about: "Kishangarh", "Chaumoo branch"
        district_name = len(hit) == 1 and hit[0]["town"] == hit[0]["city"] and sum(b["city"] == hit[0]["city"] for b in load()) > 1      # "Ajmer ki branches" names the district
        if hit and len(hit) <= READ_ALL_MAX and not every and not district_name:
            return _read(hit, text, memory), False
    place = find_place(scope) if (wants_detail or (shown and every)) else None
    state = find_state(scope) if (asks_branch or waiting) else None
    if not place and not state and wants_detail and not own:
        hit = match_among(scope, load(), strict=True)                 # a town as the listener wrote it, anywhere in the list
        if hit and len(hit) <= READ_ALL_MAX:
            if len(hit) == 1:
                return _read(hit, text, memory), False
            memory["waiting"], memory["group"], memory["pool"] = True, hit, hit
            return _several(hit[0]["town"].split()[0], hit), True
    if not place and not state and context and (wants_detail or len(low.split()) <= 3) and _heard_as(text, context):
        place = find_place(context)
        asks_branch = True
    if not place and not state and shown and len(shown) <= READ_ALL_MAX and not re.search(r"\b(?:loan|lone|emi|document\w*|interest|byaaj)\b", low):
        # "dono ka bata dijiye", "pin code bata do", "dono branchon ka address": about the branches just listed
        told = re.search(r"\bbata\w*|\bbta\w*|बता", low) and len(low.split()) <= 8           # "aap dono ka bata dijiye"
        if (every and (waiting or address or pin or asks_branch or told)) or (pin and (waiting or len(low.split()) <= 14)) or (address and asks_branch and re.search(r"\b(?:in|un|dono|donon)\b", low)):
            return _read(shown, text, memory), False
    if place and (pin_asked or address_asked or every) and (asks_branch or waiting or pin_asked or address_asked or shown):
        name, in_town, in_city = place
        among = in_city if (every or len(in_city) > 1 and (not in_town or name == in_city[0]["city"])) else (in_town or in_city)
        if among and len(among) <= (READ_ALL_ASKED if address_asked or pin_asked else READ_ALL_MAX):       # asked for: say it, do not ask "which one?"
            memory["district"] = among[0]["city"]
            return _read(among, text, memory), False
    if place and not asks_branch and not waiting and not pin_asked and not address_asked:
        place = None
    if not asks_branch and not waiting and not place:
        # "address / pincode batao" right after a branch was described
        if memory.get("last") and re.search(ASK_AGAIN, low) and len(low.split()) <= 8 and re.search(WANTS_ADDRESS + "|" + PIN_WORDS, low) and not re.search(OWN_ADDRESS, low):
            if pin and not address:
                return pin_of(memory["last"]), False
            return one_branch(memory["last"]), False
        return None
    if place:
        name, in_town, in_city = place
        if in_city:
            memory["district"] = in_city[0]["city"]
            if len(in_city) > 1:
                memory["shown"] = memory["pool"] = in_city
        memory["waiting"] = False
        group = memory.get("group") or []
        picked = in_town
        if group:                                                     # she asked "which one?": look among those first, by town, then by district ("Sikar wali")
            picked = [b for b in in_town if b in group] or [b for b in in_city if b in group] or in_town
            if len(picked) > 1 and re.search(r"\b(?:zila|jila|zile|jile|district)\b|ज़िला|जिला", low):
                picked = [b for b in picked if b in in_city] or picked
        if waiting and len(picked) == 1:                              # "which one?" - "Reengus"
            memory["last"], memory["group"] = picked[0], []
            return one_branch(picked[0]), False
        if len(in_city) > 1 and (not in_town or name == in_city[0]["city"]):
            memory["waiting"], memory["group"] = True, in_city
            return _several(name, in_city), True
        found = in_town or in_city
        if len(found) == 1:
            memory["last"], memory["group"] = found[0], []
            return one_branch(found[0]), False
        memory["waiting"], memory["group"] = True, found
        return _several(name, found), True
    if state:
        among = [b for b in memory.get("group") or [] if b["state"] == state] if waiting else []
        if len(among) == 1:                                           # "UP wali" to "which one?"
            memory["waiting"], memory["last"], memory["group"] = False, among[0], []
            return one_branch(among[0]), False
        found = [b for b in load() if b["state"] == state]
        memory["waiting"], memory["group"], memory["pool"] = True, [], found
        return (f"जी हाँ, {STATES[state][0]} में हमारी {len(found)} ब्रांच हैं। आप किस शहर या गाँव में रहते हैं?", True)
    if (memory.get("pool") and asks_branch and len(low.split()) <= 4 and not _unknown_name(text) and not own
            and any(w not in _NOT_PLACE and len(w) >= 4 for w in re.findall(r"[a-z]+", low))
            and not re.search(r"\b(?:jama|bhar\w*|pay\w*|paise|paisa|cash|emi|kist|loan|jaa?na|aana|aa\s+sakt\w*|visit|timing|time|khul\w*|band|kitn\w*)\b", low)):
        memory["waiting"], memory["group"] = True, memory["pool"]                  # "Jammoo branch ka" after a list: the name was not caught
        return (NAME_AGAIN, True)
    if asks_branch:
        unknown = _unknown_name(text)
        if unknown:
            memory["waiting"] = False
            return (f"माफ़ कीजिए, हमारी ब्रांच लिस्ट में अभी {unknown} की ब्रांच नहीं दिख रही है। टीम आपको सबसे पास की ब्रांच बता देगी।", False)
        # without a place she asks for one only when the NEAREST branch is asked for: "where is your office" and "how many branches" keep their saved answers
        if re.search(r"\b(?:branch\w*|braanch\w*|shakha)\b|ब्रांच|शाखा", low) and (address_asked or pin_asked) and not own:
            memory["waiting"] = True
            return ("जी, आप किस शहर या गाँव की ब्रांच के बारे में पूछ रहे हैं?", True)
        if re.search(r"\b(?:branch|braanch|shakha)\b|ब्रांच|शाखा", low) and re.search(r"\b(?:nazdik|najdik|nazdeek|nazdiki|najdeek|near|nearest|paas|pass)\b|नज़दीक|पास", low):
            memory["waiting"] = True
            return ("जी, आप किस शहर या गाँव की ब्रांच के बारे में पूछ रहे हैं?", True)
        return None
    # she had asked for the place, and the answer names none that is in the list
    if len(low.split()) <= 4 and not memory.get("group") and not re.search(r"\?|\bkya\b|\bkitn|\bnahi\b", low):
        words = [w for w in re.findall(r"[a-z]{3,}", low) if w not in _NOT_PLACE]
        memory["waiting"] = False
        if words:
            return (f"माफ़ कीजिए, हमारी ब्रांच लिस्ट में अभी {words[0].capitalize()} की ब्रांच नहीं दिख रही है। टीम आपको सबसे पास की ब्रांच बता देगी।", False)
    memory["waiting"] = False
    return None


def all_answers() -> list:
    """What she can say about branches, for preparing the voice: states and district lists first (asked first in a call), then each branch."""
    out = []
    for state in sorted({b["state"] for b in load()}):
        reply = answer(f"{state} mein branch", {})
        out += [reply[0]] if reply else []
    for city in sorted({b["city"] for b in load()}, key=lambda c: -sum(b["city"] == c for b in load())):      # biggest districts first
        found = [b for b in load() if b["city"] == city]
        if len(found) > 1:
            out.append(_several(city, found))
    return [NAME_AGAIN] + out + [one_branch(b) for b in load()] + [pin_of(b) for b in load()]


if __name__ == "__main__":
    data = build(sys.argv[1])
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} branches written to {DATA}")
