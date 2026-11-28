"""The customer can change anything at any time ("paanch lakh nahi, teen lakh chahiye"), and can ask who is calling (owner's request, 2026-11-28).

apply(flow, text) looks for a change to a detail that is ALREADY noted. It saves the new value and returns what Ria says,
or None when the sentence changes nothing (it is then handled as before). Nothing is guessed: no clear new value = she asks for it.
"""
import re

import ask

# ------------------------------------------------------------------ lines
CHANGED = {"loan_amount": "ठीक है जी, लोन की रकम बदलकर {v} रुपये कर दी है।", "monthly_income": "ठीक है जी, महीने की इनकम बदलकर {v} रुपये कर दी है।",
           "city": "ठीक है जी, आपका शहर बदलकर {v} कर दिया है।"}
UPDATED_LINE = "ठीक है जी, मैंने आपकी जानकारी अपडेट कर दी है।"
SAME_AMOUNT = "जी, लोन की रकम {v} रुपये ही नोट है।"
NOTED_LINE = "ठीक है जी, नोट कर लिया।"
WHAT_TO_CHANGE = "जी बिल्कुल, बताइए, क्या बदलना है?"
NEW_VALUE = {"loan_amount": "जी बिल्कुल, नई रकम बता दीजिए।", "monthly_income": "जी बिल्कुल, सही इनकम बता दीजिए।", "city": "जी बिल्कुल, सही शहर का नाम बता दीजिए।",
             "loan_type": "जी बिल्कुल, कौन सा लोन रखना है, बता दीजिए।", "loan_purpose": "जी बिल्कुल, लोन किस काम के लिए है, बता दीजिए।",
             "full_name": "जी बिल्कुल, अपना सही नाम बता दीजिए।", "phone": "जी बिल्कुल, नया मोबाइल नंबर धीरे-धीरे बोलिए।"}
ANYTHING_ELSE = "और कुछ बदलना हो तो बताइए।"
WHO_LINE = "जी, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड से।"
ASSISTANT_LINE = "जी, मैं इंसान या टेलीकॉलर नहीं, लक्ष्मी इंडिया फाइनेंस की ऑटोमेटेड असिस्टेंट हूँ।"

_CHANGE = r"\b(?:badal\w*|change\w*|chenj|update\w*|sudhar\w*|galat|galti|wrong|correct\s+kar\w*)\b|\bki\s+jag[ah]h?\b|बदल|गलत|ग़लत"
_NOT = r"(?:nahi|nahin|nai|nhi|नहीं)"
_AMOUNT_CUE = r"\b(?:loan|lone|rakam|raqam|amount)\b|\bkardo\b|\bkar\s*(?:do|dijiye|dena|dijiyega)\b|\bkariye\b|\bnahi\s+nahi\b|लोन"
_INCOME_CUE = r"\b(?:salary(?!\s+loan)|income|aamdani|kamai|kamaa?ta|kamaa?ti|kama\s+(?:leta|leti|lete)|tankh\w*|turnover)\b|इनकम|कमाई"
_OTHER_MONEY = r"\b(?:emi|kist|kisht|down\s*payment|kharch\w*|keemat|kimat|price|keemti|jama|bakaya|fee|charge|cibil|score)\b"
_ASKING = r"\?|\b(?:kya|kitn\w*|kaise|milega|milegi|mil\s+(?:sakta|sakti|jayega|jaega)|kab)\b"


def _has(pattern: str, low: str) -> bool:
    return re.search(pattern, low) is not None


def plain(text: str) -> str:
    """"teen lakh ka kar do teen lakh": that "do" belongs to "kar do", it is not the number two."""
    return re.sub(r"\b(kar|de|likh|rakh|badal)\s+do\b(?!\s+(?:lakh|laakh|lac|hazaar|hazar|hajar|crore|karod|sau|saal|mahine))", r"\1do", text, flags=re.I)


def amounts(text: str, minimum: int = 1000) -> list:
    """Every amount in the sentence as (value, refused): in "paanch lakh nahi teen lakh" the five is refused."""
    import flow

    low = plain(text.lower())
    word = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, flow.NUM), key=len, reverse=True)) + r"|dedh|dhai|adhai|sava|sawa|saadhe|sadhe|paune)"
    unit = r"(?:lakh|laakh|lac|lacs|lakhs|crore|karod|cr|hazaar|hazar|hajar|thousand|sau|लाख|हज़ार|हजार|करोड़)"
    out = []
    for m in re.finditer(rf"(?<![a-z]){word}(?:\s+{word})?\s*(?<![a-z]){unit}(?![a-z])(?:\s+{word}\s+(?:hazaar|hazar|hajar|sau))?|\b\d{{4,8}}\b", low):
        value = flow.parse_amount(m.group(0), minimum=minimum)
        if value:
            after = low[m.end():]
            refused = re.match(rf"\s*(?:rupa?ye?\s+|rupees?\s+|ka\s+|ki\s+|ke\s+|wala\s+|waala\s+)*{_NOT}\b", after) is not None
            out.append((value, refused))
    return out


def wanted_amount(text: str):
    kept = [v for v, refused in amounts(text) if not refused]
    return kept[-1] if kept else None


def identity(text: str) -> list:
    """"aap kaun ho, kahan se bol rahe ho, call kyun kiya, AI ho ya telecaller?" -> the lines that answer each of these."""
    low = text.lower()
    out = []
    ai = _has(r"\b(?:ai|a\.i\.?|ay\s*aai|robot|machine|bot|computer|tele\s*-?\s*(?:caller|collar|kaller|color)|collar|caller|recording|insaan|insan|human|real\s+person|aadmi)\b", low) \
        and _has(r"\b(?:aap|tum|you)\b|\bho\b|\bho\s*\?", low) and _has(r"\b(?:ho|hain|hai|are\s+you)\b", low) and not _has(r"\b(?:loan|emi|branch|business|baat\s+kara\w*)\b", low)
    who = _has(r"\baap\s+(?:kaun|kon|kun)\b(?!\s*s[aei]\b)|\b(?:kaun|kon)\s+(?:ho|hain|bol\s+rah\w*|baat\s+kar\s+rah\w*)\b|\bkahan\s+se\s+(?:bol|baat|call|phone)|\bkis\s+company\s+se\b|\bwho\s+(?:are\s+you|is\s+this)\b", low)
    why = _has(r"\b(?:call|phone|fon)\b[^.?]{0,25}\b(?:kyun|kyu|kyo|kyon|kis\s*liye)\b|\b(?:kyun|kyu|kyo|kyon|kis\s*liye)\b[^.?]{0,25}\b(?:call|phone|fon)\b|\bwhy\s+(?:did\s+you|are\s+you)\s+call", low)
    doing = _has(r"\bkya\s+kar\s+rah[ei]\s+ho\b", low)
    if who or doing or (ai and _has(r"\baap\s+(?:kaun|kon)\b", low)):
        out.append(WHO_LINE)
    if ai:
        out.append(ASSISTANT_LINE)
    if why:
        entry = __import__("replybank").entry("why_call")
        if entry:
            out.append(entry["reply"])
    elif doing:
        out.append("मेरा काम लोन की पूछताछ नोट करना और आपके सवालों में मदद करना है।")
    return out


# ------------------------------------------------------------------ changes
def _save(f, key, value, detail=True):
    if detail:
        f._save(details={key: value})
    else:
        f._save({key: value})


def _then(f, said: str) -> str:
    """After a change: back to where the call was. She does not lose the question she was on."""
    if f.done:
        return said + " " + ANYTHING_ELSE
    if f.asked == "phone_confirm" and f.phone_pending:
        return f"{said} आपका नंबर {f.phone_pending} है, क्या यह सही है?"
    if f.asked in (None, "amount_confirm"):
        return f._carry_on(said)
    if f.asked in f.v or f.asked in f.skipped:                     # the change also answered what she was asking
        return f._carry_on(said)
    question = f._question(f.asked)
    if f.asked == "consent" and f._name():
        question = f"{f._name()} जी, " + question
    return f"{said} {question}"


def _ask_new(f, slot: str) -> str:
    f.v.pop(slot, None)
    f.skipped.discard(slot)
    f.asked, f.done = slot, False
    if slot == "phone":
        f.phone_buf, f.phone_pending = "", None
        f.call.confirmed.discard("phone")
        f.call.form.pop("phone", None)
    return NEW_VALUE[slot]


def apply(f, text: str):
    import flow

    low = plain(text.lower())
    asked = f.asked
    if asked in ("full_name",) and "full_name" not in f.v:
        return None
    changing = _has(_CHANGE, low)
    question = _has(_ASKING, low) and not changing
    done_slots = []

    # ---- loan amount
    new = wanted_amount(low)
    running = _has(r"\bchal\s*(?:raha|rahi|rahe|rha|rhi)\b|\bpehle\s+se\b|\bliya\s+hua\b|\bpuran[aei]\b|\bchalu\b", low) or asked == "existing_loans" and not (changing or _has(r"\bkardo\b|\bkar\s*(?:do|dijiye|dena)\b|\b(?:chahiye|chaahiye|chahie|chaiye)\b|\bnahi\b[^.?]{0,20}\b(?:lakh|hazaar)\b", low))
    if "loan_amount" in f.v and asked != "loan_amount" and new and not question and not running and not _has(_INCOME_CUE, low) and not _has(_OTHER_MONEY, low):
        cue = changing or _has(_AMOUNT_CUE, low) or (_has(r"\b(?:chahiye|chaahiye|chahie|chaiye)\b", low) and asked not in ("monthly_income", "existing_emi")) or asked == "amount_confirm" \
            or any(refused and value == f.v["loan_amount"] for value, refused in amounts(low))
        if cue:
            if new != f.v["loan_amount"]:
                f.v["loan_amount"] = new
                _save(f, "loan_amount", new)
                f._sync_reason()
                said = CHANGED["loan_amount"].format(v=new)
                if new >= 1_000_000:
                    f.asked = "amount_confirm"
                    return f"{said} क्या यह सही है?"
                return _then(f, said)
            other = _has(r"\b(?:instant|turant|jaldi|urgent|abhi|aaj|kal|din|document\w*|interest|byaaj|byaj|branch|time|kab)\b", low)   # they ask for something more
            if asked not in ("amount_confirm", "monthly_income", "existing_emi") and not other and not f.done:
                return _then(f, SAME_AMOUNT.format(v=new))
            return None

    # ---- monthly income
    if "monthly_income" in f.v and asked != "monthly_income" and new and not question and _has(_INCOME_CUE, low) and not _has(r"\bemi\b|\bkist\b", low):
        if new != f.v["monthly_income"]:
            f.v["monthly_income"] = new
            _save(f, "monthly_income", new)
            return _then(f, CHANGED["monthly_income"].format(v=new))

    # ---- what the loan is for: "yeh loan mujhe apne personal kaam ke liye chahiye"
    personal = _has(r"\bpersonal\s+(?:views?|use|kaam|reason|zaroorat|kharch)", low)              # "apne personal kaam ke liye" is a purpose, not a refusal
    at_phone = asked in ("phone", "phone_confirm") and len(flow.digits_from_speech(low)) >= 4
    if (asked not in ("loan_purpose", "loan_type", "full_name") and not at_phone or asked == "loan_purpose" and personal) and not question and _has(r"\b(?:loan|lone)\b", low) and _has(r"\b(?:ke|ki)\s+(?:liye|lie)\b", low):
        part = re.split(rf"\b{_NOT}\b", low)[-1]                    # "shaadi nahi, medical ke liye": what follows the "nahi" counts
        what = "personal use" if personal else next((name for source in (part, low) for name, pat in flow.PURPOSE_PATTERNS if re.search(pat, source)), None)
        if what and what != f.v.get("loan_purpose") and not _has(rf"\b{_NOT}\s+(?:bata|bta)", low):
            said = UPDATED_LINE if "loan_purpose" in f.v else NOTED_LINE
            f.v["loan_purpose"] = what
            f.skipped.discard("loan_purpose")
            _save(f, "loan_purpose", what)
            return _then(f, said)

    # ---- loan type: only when a change is clearly meant
    if "loan_type" in f.v and asked != "loan_type" and (changing or _has(rf"\b(?:loan|lone)\s+{_NOT}\b|\bkardo\b", low)) and not question:
        kinds = [m for m in re.finditer(rf"\b(personal|payday|pay\s*day|salary|home|business|vehicle|gold)\s+(?:loan|lone)\b(?!\s+{_NOT}\b)", low)]
        if kinds:
            kind = kinds[-1].group(1).replace(" ", "")
            if kind != f.v["loan_type"]:
                f.v["loan_type"] = kind
                _save(f, "loan_type", kind)
                f._sync_reason()
                return _then(f, UPDATED_LINE)

    # ---- the rest need a clear word of change
    correcting = changing or _has(rf"\b{_NOT}\s*,|\bactually\b|\bsorry\b", low)
    kept = re.split(rf"\b{_NOT}\b", low)[-1]                   # "Jaipur nahi, Ajmer": what follows the "nahi"
    if "city" in f.v and asked != "city" and correcting and _has(r"\b(?:city|shahar|sheher|shehar|reht[ai]|raht[ai]|rehne|rahne|gaon|gaanv)\b|शहर", low):
        city = flow.parse_city(kept, fuzzy=False) or flow.parse_city(low, fuzzy=False)
        if city and city != f.v["city"]:
            f.v["city"] = city
            _save(f, "city", city)
            f._sync_reason()
            return _then(f, CHANGED["city"].format(v=city))
    if "employment" in f.v and asked != "employment" and correcting and _has(r"\b(?:job|naukri|nokri|business|salary\s+wal\w*|dukaan|kheti)\b", low) and not _has(r"\b(?:loan|lone)\b", low):
        work = flow.parse_employment(kept, "employment")
        if work and work != f.v["employment"]:
            f.v["employment"] = work
            _save(f, "employment_type", work)
            return _then(f, UPDATED_LINE)
    if "work_tenure" in f.v and asked != "work_tenure" and correcting and _has(r"\b(?:saal|sal|mahine|mahina|year|month)\w*\b", low):
        years = flow.parse_duration_years(kept)
        if years is not None:
            value = f"{round(years * 12)} months" if years < 1 else f"{years:g} years"
            if value != f.v["work_tenure"]:
                f.v["work_tenure"] = value
                _save(f, "business_vintage" if f.v.get("employment") == "self-employed" else "time_with_current_employer", value)
                return _then(f, UPDATED_LINE)

    # ---- name
    if "full_name" in f.v and _has(r"\b(?:naam|name)\b|नाम", low) and (changing or _has(rf"\b(?:naam|name)\b[^.?]*\b{_NOT}\b", low)) and not _has(r"\b(?:kya|aapka|aap\s+ka|tumhara|company)\b", low):
        after = re.split(r"\b(?:naam|name)\b", low)[-1]
        after = re.split(rf"\b{_NOT}\b", after)[-1]
        name = flow.parse_name("mera naam " + after, strict=True) if re.sub(r"\b(?:galat|hai|he|badal\w*|change|karna|karo|kar|do|likha|gaya|sahi)\b|\W", "", after) else None
        if name and name.lower() != f.v["full_name"].lower():
            f.v["full_name"] = name
            _save(f, "full_name", name, detail=False)
            return _then(f, UPDATED_LINE)
        if changing:
            return _ask_new(f, "full_name")

    # ---- mobile number
    if asked not in ("phone", "phone_confirm") and "phone" in f.v and _has(r"\b(?:number|nambar|mobile|phone)\b|नंबर", low) \
            and (changing or _has(r"\b(?:doosra|dusra|naya|alag)\b", low)) and not _has(r"\bhelp\s*line|toll|office|branch|company\b", low):
        digits = flow.digits_from_speech(low)
        if len(digits) >= 10 and digits[-10] in "6789":
            f.v.pop("phone", None)
            f.call.confirmed.discard("phone")
            f._save({"phone": digits[-10:]})
            f.phone_pending, f.asked, f.done = digits[-10:], "phone_confirm", False
            return f"आपका नंबर {f.phone_pending} है, क्या यह सही है?"
        return _ask_new(f, "phone")

    # ---- "amount badalni hai" without the new value, or just "kuch change karna hai"
    if changing and not question and _has(r"\b(?:karn[aie]|karo|kar\s*do|kardo|karwa\w*|karva\w*|chahiye|hai|he|dena|dijiye|likh\w*)\b", low):
        for slot, words in (("loan_amount", r"\b(?:amount|rakam|raqam)\b"), ("monthly_income", r"\b(?:income|salary|kamai)\b"), ("city", r"\b(?:city|shahar|sheher|shehar)\b"),
                            ("loan_purpose", r"\b(?:purpose|wajah)\b"), ("loan_type", r"\bloan\s+(?:ka\s+)?(?:type|prakar)\b")):
            if slot in f.v and _has(words, low) and not new:
                return _ask_new(f, slot)
        if _has(r"\b(?:detail\w*|jaa?n?kaa?ri|information|form|entry|data|kuch|kuchh|cheez)\b|जानकारी", low) and len(low.split()) <= 14 and not new:
            f.paused = True
            return WHAT_TO_CHANGE
    return None


def all_lines() -> list:
    return [UPDATED_LINE, NOTED_LINE, WHAT_TO_CHANGE, ANYTHING_ELSE, WHO_LINE, ASSISTANT_LINE] + list(NEW_VALUE.values())
