"""The customer leads: when they ask something, Ria answers THAT and does not push her next form question (owner's request, 2026-11-28).

After an answer she only invites more questions. The form continues when the customer says they have nothing more to ask
("theek hai", "nahi", "aage boliye") or simply gives the detail she still needs. Nothing here states a rate, an EMI figure
or a loan limit: those are not approved.
"""
import re

INVITE_LINE = "और कुछ जानना हो तो पूछिए।"
RESUME_LINE = "जी बिल्कुल।"
RANGE_LINE = "हर लोन में कम से कम और ज़्यादा से ज़्यादा कितनी रकम मिलेगी, ये आपकी एलिजिबिलिटी पर निर्भर करता है, सही रकम टीम बताएगी।"
EMI_LINE = "जी, ईएमआई रकम, इंटरेस्ट और टाइम पर निर्भर करती है, इसलिए अभी सही नंबर नहीं बता सकती। टीम पूरा हिसाब बता देगी।"
SAY_AGAIN_LINE = "माफ़ कीजिए, मैं आपका सवाल ठीक से समझ नहीं पाई। एक बार फिर बताइए।"
BUSINESS_LINE = "ठीक है जी, आपका बिज़नेस {place} में है, नोट कर लिया।"

_EMI = r"\b(?:emi'?s?|e\s*m\s*i|kist|kisht|installment|instalment)\b|ईएमआई|किस्त"
_HOW_MUCH = r"\b(?:ban(?:egi|ega|engi|ti|ta|egee)|kitni|kitna|kitne|aayegi|aaegi|ayegi|aaega|calculate|calculation|hisaab|hisab|how\s+much)\b|बनेगी|कितनी|कितना"
_NOT_AMOUNT = r"\b(?:date|tarikh|tareekh|taarikh|kab|bounce|bounced|late|miss|badal\w*|change|chal\s+rah\w*|chal\s+rhi|kat\s+(?:gayi|gai|gaya)|pending|jama|receipt|raseed)\b|तारीख"

_LOANS = r"\bloans?\b|\blone\b|लोन"
_EVERY = (r"\b(?:sab|sabhi|saare|sare|saari|sari|tamam|all)\b|\bkaun\s*kaun\b|\bkon\s*kon\b|\bjis\s+(?:jis\s+)?(?:type|tarah|prakar)|\b(?:kis|kitne|kitni)\s+(?:type|types|tarah|prakar)\b"
          r"|\bkais[ei]\s+(?:kais[ei]\s+)?loans?\b|\btype\s+ke\s+(?:bhi\s+)?loans?\b|\bwhat\s+(?:kind|type)s?\b|\bsab\s*kuch\b|कौन\s*कौन|सभी|सारे")
_TELL = r"\b(?:bata\w*|bta\w*|dijiye|deti|dete|deta|milte|milta|jaan\w*|jankari|samjha\w*|provide|offer|what|which|tell|explain)\b|बता|देती|देते"
_ONE_KIND = r"\b(?:personal|payday|pay\s*day|salary|gold|home|business|vehicle|car|bike|property|construction)\s+(?:loan|lone)\b"
_RANGE = r"\bminimum\b|\bmaximum\b|\b(?:kam|zyada|jyada|adhik)\s+se\s+(?:kam|zyada|jyada|adhik)\b|\bsab\s*kuch\b|न्यूनतम|अधिकतम"

_NOTHING_MORE = (r"\W*(?:(?:ji|haan|han|ha|nahi|nahin|nai|nhi|no|bas|ok|okay|theek|thik|hai|he|accha|acha|achha|samajh|gaya|gayi|aaya|aayi|aur|kuch|kuchh|nothing|more|ab|abhi|"
                 r"aage|badho|badhiye|badhein|badhte|chaliye|chalo|boliye|bolo|puchiye|poochiye|pooch|puch|lijiye|lo|itna|itni|hi|enough|thats|that|all|thank|thanks|you|dhanyavaad|dhanyawad|shukriya|fine|alright|yes|"
                 r"हाँ|हां|नहीं|बस|ठीक|है|जी|अच्छा|और|कुछ|आगे|बोलिए|धन्यवाद)(?:\W+|$))+")

_WANTS_TELLING = r"\b(?:bata(?:o|iye|ye|do|iyega|ao)?|bata\s+(?:do|dijiye|dun|den?)|btao|bataiye|samjhao|samjhaiye|jaanna|janna|jankari|jaankari|tell\s+me)\b|बताइए|बताओ|बता\s+दीजिए"
_FIRST_TELL_ME = r"\b(?:pehle|pahle|pehele|phle|first)\b.{0,60}\b(?:bata|bta|samjha|tell)"


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text.lower()) is not None


def asks_emi_amount(text: str) -> bool:
    """"meri EMI kya banegi?" asks for the amount, not for the due date."""
    return _has(_EMI, text) and _has(_HOW_MUCH, text) and not _has(_NOT_AMOUNT, text)


def asks_all_loans(text: str) -> bool:
    """"aap jis type ke bhi loan dete ho, sab bata do"."""
    return _has(_LOANS, text) and _has(_EVERY, text) and _has(_TELL, text) and not _has(_ONE_KIND, text) and not _has(_EMI, text)


def asks_range(text: str) -> bool:
    return _has(_RANGE, text)


def nothing_more(text: str) -> bool:
    """After "ask me if you want to know more": the customer has nothing to ask, so the form goes on."""
    low = text.lower().strip()
    return len(low.split()) <= 8 and re.fullmatch(_NOTHING_MORE, low) is not None


def wants_telling(text: str) -> bool:
    """"... bata dijiye": the customer wants to hear something; this is not an answer to a form question."""
    return _has(_WANTS_TELLING, text)


def first_tell_me(text: str) -> bool:
    """"nahi, pehle aap mujhe ye bataiye": the "nahi" is not an answer to her question."""
    return _has(_FIRST_TELL_ME, text)


def business_place(text: str) -> str:
    """"main Jaipur se hoon par mera business Bhilwara mein hai" -> "Bhilwara" (only places in the branch list)."""
    import branches

    low = text.lower()
    if not re.search(r"\b(?:business|bijness|bizness|dukaan|dukan|shop|factory|vyapar|dhandha)\b", low) or re.search(r"\b(?:branch\w*|office|address|pincode|pin\s*code|kahan|kaha)\b", low):
        return ""
    parts = [p for p in re.split(r"[,.;]|\b(?:but|lekin|magar|jabki)\b", low) if p.strip()]
    for i, part in enumerate(parts):
        if re.search(r"\b(?:business|bijness|bizness|dukaan|dukan|shop|factory|vyapar|dhandha)\b", part):
            for piece in (part, parts[i + 1] if i + 1 < len(parts) else ""):
                if re.search(r"\b(?:mein|me|main|may|in)\b", piece):
                    after = re.split(r"\b(?:business|bijness|bizness|dukaan|dukan|shop|factory|vyapar|dhandha)\b", piece)
                    for chunk in (after[-1], piece):                   # the place named after the word "business" comes first
                        place = branches.find_place(chunk)
                        if place:
                            return place[0]
                        state = branches.find_state(chunk)
                        if state:
                            return state
    return ""


# question -> the approved answer that belongs to it (None = nothing approved: she says the team will confirm)
_TOPICS = (
    ("emi_bounce_effect", r"\b(?:emi|e\s*m\s*i|kist|kisht)\b.{0,30}\b(?:late|bounce\w*|miss\w*|chook\w*|na\s+bhar\w*|nahi\s+bhar\w*)\b|\b(?:late|bounce|miss)\b.{0,20}\b(?:emi|kist)\b"),
    ("age_limit", r"\b(?:meri|mera|my)\s+(?:age|umar|umr)\b.{0,60}\b(?:loan|milega|milegi|chalega)\b|\bage\s+limit\b|\b(?:umar|umr|age)\s+kitni\s+(?:honi|chahiye)"),
    ("office_info", r"\b(?:branch|office|ofis|shakha)\b.{0,25}\b(?:kab\s+(?:khul\w*|band)|khul(?:ti|ta|te)|timing\w*|kitne\s+baje|time\s+kya)\b|\b(?:timing\w*|kitne\s+baje)\b.{0,25}\b(?:branch|office)\b"),
    ("payment_how", r"\b(?:emi|kist|kisht)\b.{0,25}\b(?:kaise|kahan|kaha|kidhar)\b.{0,15}\b(?:bhar\w*|jama|pay|de(?:ni|na|te|nge)?)\b|\b(?:emi|kist)\b.{0,15}\bpayment\s+kaise\b"),
    ("language", r"\b(?:hindi\s+ke\s+(?:alawa|alava|siva)|kaun\s*s[ie]\s+(?:bhasha|language)|(?:bhasha|language)\w*\s+(?:aati|bol\s+sakt))"),
    ("company_doing", r"\bcompany\b.{0,20}\b(?:kab\s+se|kitni\s+purani|kitne\s+saal)\b"),
    ("how_apply", r"\b(?:online\s+)?apply\b.{0,20}\bkaise\b|\bkaise\b.{0,20}\bapply\b"),
    (None, r"\b(?:kisan|kisaan|farmer|mahila|women|woman|ladies|student)\w*\b.{0,30}\b(?:loan|scheme|yojana)\b|\b(?:loan|scheme|yojana)\b.{0,20}\b(?:kisan|kisaan|farmer|mahila|women|ladies|student)\w*\b"),
)


def topic_of(text: str):
    """(True, answer id or None) for a question of one of the kinds above, else (False, None). Only for questions."""
    low = text.lower()
    if not re.search(r"\?|\b(?:kya|kaise|kab|kitn\w*|kaun|kahan|kaha|milega|milegi|milta|milti|hai\s+kya|hoga|chalega)\b", low):
        return False, None
    if re.search(r"\b(?:cibil|sibil|civil|score)\b", low):        # a CIBIL question that also mentions a late EMI stays a CIBIL question
        return False, None
    for key, pattern in _TOPICS:
        if re.search(pattern, low):
            return True, key
    return False, None


def all_lines() -> list:
    return [INVITE_LINE, RESUME_LINE, RANGE_LINE, EMI_LINE, SAY_AGAIN_LINE]


# words every sentence has: sharing only these with a saved question does not make them about the same thing
_COMMON = set("""aap aapka aapki aapke apka apki apke main mai mera meri mere mujhe muje hum hame humein tum tumhara kya kyu kyun kyon kaise kaisa kaisi kab kahan kaha kidhar kitna kitni kitne
kaun kon kis kisi koi kuch kuchh woh wo voh yeh ye yah is us isme ismein usme uska uski unka iska iski jo jis jaise waise aise bhi hi to toh na nahi nahin haan han ji sir madam
hai hain he ho hoon hun hu tha thi the hoga hogi honge hota hoti hote raha rahi rahe rha rhi rhe kar karo karna karni karne karta karti karte kiya kiye kijiye de do den dena deta deti dete dijiye diya
le lo lena leni lete liya liye ke ki ka ko se me mein par pe aur ya lekin magar phir fir ab abhi agar kyunki isliye bata batao bataiye bataye batana bataya btao bol bolo bolna bolte boliye bola bolti
kaha kahna kehna sun suno sunna sunte pooch poochh poocha pucha puchna poochna baat baatein jaan jaana jaanna janna chahiye chahie chaiye sakta sakti sakte paas pass saath wala wali vala vali
matlab sawal sawaal savaal jawab javab javaab jawaab accha acha achha theek thik sahi galat ek aur do teen sab bahut thoda zara jara please pls ok okay hello namaste you your the a an is are am do does can will what how why
when where which who tell me my i we it this that there of to in on for and or not no yes""".split())


def shares_topic(text: str, entry: dict) -> bool:
    """A weakly matched saved answer is used only if the sentence has a real topic word of that question."""
    mine = {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _COMMON}
    if not mine:
        return False
    theirs = {w for ex in entry.get("examples", []) for w in re.findall(r"[a-z]{3,}", ex.lower()) if w not in _COMMON}
    return any(a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]) for a in mine for b in theirs)


_WRONG_ANSWER = (r"\b(?:galat|wrong)\s+(?:ja[vw]aa?b|answer|reply|bata\w*|bol\w*)|\bjo\s+(?:maine|mene|main\s+ne)\s+(?:poocha|pucha|puchha|poochha)\b[^.?]{0,30}\b(?:jawab|bata|batao|bataiye|uska)"
                 r"|\b(?:maine|mene)\s+(?:kuch\s+(?:aur|or)|ye\s+nahi|yeh\s+nahi|woh\s+nahi)\s+(?:poocha|pucha|puchha|poochha|kaha|bola)|\bmera\s+(?:matlab|sawaa?l)\s+(?:woh|wo|ye|yeh)\s+nahi")
_LISTENING_CHECK = r"\b(?:aap\s+)?(?:sun|suun)\s+(?:rahe|rahi|rhe|rhi|pa\s+rahe|paa\s+rahe|pa\s+rahi)\s+(?:ho|hain|hai)\b|\bsunai\s+(?:de|aa)\s+rah"


def says_wrong_answer(text: str) -> bool:
    return _has(_WRONG_ANSWER, text)


def asks_if_listening(text: str) -> bool:
    return len(text.split()) <= 10 and _has(_LISTENING_CHECK, text)
