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
          "madhopur": "Sawai Madhopur", "nagor": "Nagaur", "bhilvara": "Bhilwara", "sikkar": "Sikar", "jhalawad": "Jhalawar", "mahesana": "Mehsana"}

BRANCH_WORDS = r"\b(?:branch|branches|braanch|branchh|shakha|saakha|office|ofis|offis|daftar)\b|ब्रांच|ऑफिस|ऑफ़िस|शाखा|દફતર|બ્રાંચ"
HEAD_OFFICE = r"\b(?:head|main|corporate|registered)\s+office\b|\bheadoffice\b|मुख्य\s+(?:ऑफिस|ऑफ़िस|कार्यालय)"
ASK_AGAIN = r"\b(?:address|adress|pata|pin\s*code|pincode|location|kahan\s+(?:par\s+)?(?:hai|he|padti|padta))\b|पता|पिन\s*कोड"
# words that are never the name of a place the caller asks about
_NOT_PLACE = set("""aapki aapka aapke apki apka apni hamare hamara mere mera meri kya koi kahi kahin kaha kahan kahaan kidhar kitni tamari tamaro thari tharo kathe yahanyaha wahan waha idhar udhar hai hain he ho tha thi nahi nahin
mein me main par pe ki ka ke ko se tak aur bhi to toh ji sir madam haan han na city shahar shehar sheher gaon gaav gaanv village jila zila district state area ilaka town
branch branches office shakha loan lone lena chahiye chahie batao bataiye bataye bata do dijiye de please aap tum hum main mai kis kaun konsi kaunsi sa si nazdik najdik nazdeek paas pass
near nearest wali wala vali vala company finance laxmi lakshmi india limited address pata pincode pin code number kitni kitne total sab sabhi there any is are do you have your in at the of my our""".split())


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
    for said, real in _ALIAS.items():
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


def _several(name: str, found: list) -> str:
    names = [b["town"] for b in found]
    towns = [f"{b['town']} (ज़िला {b['city']})" if names.count(b["town"]) > 1 else b["town"] for b in found]      # two branches with one name
    shown = ", ".join(towns[:5]) + (" और दूसरी जगहें" if len(towns) > 5 else "")
    return f"जी हाँ, {name} में हमारी {len(towns)} ब्रांच हैं: {shown}। आप किस जगह की ब्रांच का पता चाहेंगे?"


def answer(text: str, memory: dict):
    """(reply, True if the reply ends with her own question) for a branch question, else None.
    `memory` is kept for the call: {"waiting": True after she asked which place, "last": the branch she last described}."""
    if not load():
        return None
    low = text.lower()
    asks_branch = bool(re.search(BRANCH_WORDS, low))
    waiting = memory.get("waiting")
    if re.search(HEAD_OFFICE, low):
        return None
    place = find_place(text) if (asks_branch or waiting) else None
    state = find_state(text) if (asks_branch or waiting) else None
    if not asks_branch and not waiting:
        # "address / pincode batao" right after a branch was described
        if memory.get("last") and re.search(ASK_AGAIN, low) and len(low.split()) <= 8:
            return one_branch(memory["last"]), False
        return None
    if place:
        name, in_town, in_city = place
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
        memory["waiting"], memory["group"] = True, []
        return (f"जी हाँ, {STATES[state][0]} में हमारी {len(found)} ब्रांच हैं। आप किस शहर या गाँव में रहते हैं?", True)
    if asks_branch:
        unknown = _unknown_name(text)
        if unknown:
            memory["waiting"] = False
            return (f"माफ़ कीजिए, हमारी ब्रांच लिस्ट में अभी {unknown} की ब्रांच नहीं दिख रही है। टीम आपको सबसे पास की ब्रांच बता देगी।", False)
        # without a place she asks for one only when the NEAREST branch is asked for: "where is your office" and "how many branches" keep their saved answers
        if re.search(r"\b(?:branch|braanch|shakha)\b|ब्रांच|शाखा", low) and re.search(r"\b(?:nazdik|najdik|nazdeek|nazdiki|najdeek|near|nearest|paas|pass)\b|नज़दीक|पास", low):
            memory["waiting"] = True
            return ("जी, आप किस शहर या गाँव की ब्रांच के बारे में पूछ रहे हैं?", True)
        return None
    # she had asked for the place, and the answer names none that is in the list
    if len(low.split()) <= 4 and not re.search(r"\?|\bkya\b|\bkitn|\bnahi\b", low):
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
    return out + [one_branch(b) for b in load()]


if __name__ == "__main__":
    data = build(sys.argv[1])
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} branches written to {DATA}")
