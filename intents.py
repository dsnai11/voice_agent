"""What the customer MEANS when the answer is not the value Ria asked for (owner's request, 2026-11-28).

A customer may refuse ("niji hai, bata nahi sakta"), not know, not want the loan, be busy, not understand the question, or ask for
money in their own words. These are recognised here, before anything is saved as an answer. Every sentence Ria says in reply was
already in her call script or saved answers. Rules:
  * What the customer will not or cannot say is skipped and noted for the team; it is never asked again and again.
  * A refusal is never recorded as consent to be called.
  * Someone who does not want the loan, or does not want calls, is thanked and the call ends.
"""
import re

SKIP_LINE = "कोई बात नहीं जी।"
WHY_LINE = "जी, ये जानकारी सिर्फ़ इसलिए चाहिए कि टीम आपके लिए सही लोन ऑप्शन देख सके। जो आप न बताना चाहें, उसे छोड़ सकते हैं।"
AGAIN_LINE = "कोई बात नहीं जी, मैं आसान शब्दों में फिर से बताती हूँ।"
NO_THANKS_LINE = "ठीक है जी, कोई बात नहीं। आपका टाइम देने के लिए शुक्रिया, आपका दिन अच्छा रहे।"
STOP_LINE = "ठीक है जी, मैंने नोट कर लिया है, आपको दोबारा कॉल नहीं आएगा। परेशानी के लिए सॉरी।"
BUSY_LINE = "कोई बात नहीं जी। आपको किस दिन और किस टाइम पर कॉल करूँ?"
HELP_LINE = "जी, लोन के बारे में मैं आपकी पूरी मदद करूँगी।"
AMOUNT_LINE = "जी, लोन की रकम आपकी एलिजिबिलिटी पर निर्भर करती है।"

_NO = r"(?:nahi|nahin|nai|nhi|नहीं)"

STOP = (r"\b(?:call|phone|fon)\b[^.?]{0,12}\b(?:mat|na)\b\s*(?:kiya\s+)?(?:kar|karo|karna|kijiye|kijiyega|kare)|\bmat\s+(?:kar\w*\s+)?(?:call|phone)\b|(?:dobara|phir|fir)\s+(?:call|phone)\s+(?:mat|nahi)"
        r"|call\s+(?:band|nahi\s+chahiye)|do\s+not\s+call|don'?t\s+call|कॉल\s+मत")
LEAVE = (rf"\b(?:loan|lone)\b[^.?]{{0,20}}\b{_NO}\s+(?:chahiye|chahie|chaiye|lena|leni|karvana|karwana)|\b{_NO}\s+(?:lena|leni)\b(?:\s+(?:hai|mujhe))*\s*$"
         rf"|\b(?:zaroorat|zarurat|jarurat|jaroorat|requirement)\s+(?:hi\s+)?{_NO}\b|\bnot\s+interested\b|\binterest(?:ed)?\s+{_NO}\b|{_NO}\s+interest(?:ed)?\b"
         rf"|^\W*(?:ji\s+|rehne\s+do\s+)?(?:mujhe\s+|hame\s+|humein\s+)?(?:ab\s+|abhi\s+|kuch\s+)?(?:bhi\s+)?{_NO}\s+(?:chahiye|chahie|chaiye)(?:\s+(?:ji|sir|madam|abhi|ab|kuch|thank\s*you))*\W*$|लोन\s+नहीं\s+चाहिए|ज़रूरत\s+नहीं|जरूरत\s+नहीं")
BUSY = (r"\b(?:busy|vyast)\b|\bbaa?d\s+(?:mein|me|m)\s+(?:call|phone|baat)|\babhi\s+baat\s+nahi|\babhi\s+(?:time|samay)\s+nahi|\b(?:meeting|driving)\b|gaadi\s+chala\s+rah"
        r"|(?:call|phone)\s+(?:baad\s+(?:mein|me)|later)|व्यस्त|बाद\s+में\s+(?:कॉल|फ़ोन|फोन|बात)")
WHY = (r"\bbatana\s+(?:zaroori|jaruri|zaruri|jaroori)\b|\b(?:zaroori|jaruri|zaruri)\s+hai\s+(?:kya\s+)?(?:batana|ye)|\b(?:aapko|aap\s+ko)\s+(?:kyun|kyu|kyo)\s+bata"
       r"|\b(?:kyun|kyu|kyo)\s+bata(?:u|un|oon|ye|yen|na)\w*|क्यों\s+बताऊ")
REFUSE = (rf"{_NO}\s+(?:bata|bta|bol)(?!\s+rah|\s+rh)(?:\s|$|u|n|oo|na|ya|\w*(?:ga|gi|ge))|\b(?:bata|bta)a?\s+{_NO}\s+(?:sak|paa?u|paa?o|chah)|\b{_NO}\s+(?:batana|bataana|btana)\b|\bbatana\s+{_NO}"
          r"|\bniji\b|\bprivate\s+(?:hai|baat|matter|cheez)|\bpersonal\s+(?:hai|baat|matter|cheez|reason|views?)\b|\b(?:chhod\w*|chod\w*|rehne)\s+(?:do\s+|dijiye\s+)?(?:isko|ise|ye|yeh|isse)\b"
          r"|\b(?:isko|ise|ye|yeh)\s+(?:chhod\w*|chod\w*|rehne\s+d\w*)|\baage\s+badh\w*|\bbaad\s+(?:mein|me)\s+bata\w*|\bskip\b|नहीं\s+बता|बता\s+नहीं|निजी")
DONT_KNOW = rf"\b(?:pata|pta|maloom|malum|yaad|idea)\s+(?:hi\s+|bhi\s+)?{_NO}\b|\b{_NO}\s+(?:pata|pta|maloom|malum|yaad)\b|\bsocha\s+{_NO}\b|\baap\s+(?:hi\s+)?bata\s*(?:o|do|iye|dijiye|dena)\b|पता\s+नहीं|मालूम\s+नहीं"
UNSURE = rf"\bsamajh\w*\s+(?:mein\s+|me\s+)?{_NO}|\b{_NO}\s+samajh|\bkya\s+matlab\b|\bkya\s+(?:poocha|pucha|puchha|kaha|bola)\b|\b(?:dobara|phir\s+se|fir\s+se)\s+(?:bol|puch|pooch|bata)|समझ\s+नहीं"
NEED_MONEY = r"\bpais\w*\b[^.?]{0,25}\b(?:chahiye|chahie|chaiye|zaroorat|zarurat|jarurat|jaroorat)\b|\b(?:zaroorat|zarurat|jarurat|jaroorat)\b[^.?]{0,25}\bpais|\b(?:rupaye|rupees|rupay|rupe|udhaar|udhar|karz|karja|karza)\b[^.?]{0,15}\b(?:chahiye|chahie|chaiye)\b|पैसे\s+चाहिए"
ANY_LOAN = r"\bkoi\s*(?:sa\s+)?bhi\b|\bjo\s+(?:bhi\s+)?mil\s*(?:jaye|jae|sake|jay)|\bkuch\s+bhi\b"
MAX_AMOUNT = r"\bjitna\s+(?:bhi\s+)?(?:mil|ho)\s*\w*|\b(?:zyada|jyada|adhik)\s+se\s+(?:zyada|jyada|adhik)\b|\bmaximum\b|\bjitna\s+aap\b"
VARIES = rf"\bfix(?:ed)?\s+{_NO}|\bupar\s+(?:neeche|niche)\b|\bpakk?a\s+{_NO}|\bkam\s+zyada\s+hoti"
HOME = r"\bghar\s+(?:par|pe|per)\s+(?:rehti|rehta|rahti|rahta|hi)\b|\bhouse\s*wife\b|\bgrihini\b|\bkuch\s+nahi\s+(?:karta|karti)\b|\bberozgar\b|\bstudent\b|\bpadhai\s+kar"
ANY_TIME = r"\bkabhi\b|\bjab\s+(?:aapka\s+man|chaho|chahe|aap\s+chah|marzi|bhi)|\bke\s+baad\b|\bany\s*time\b|\bkisi\s+bhi\s+(?:time|din)|\bfree\s+(?:hoon|hun|rahunga|rahungi)\b|कभी\s+भी"

# words that name an actual time for a callback ("abhi" and "baad mein" do not)
REAL_TIME = (r"(?:kal|parson|parso|aaj|shaam|sham|subah|dopahar|dopeher|raat|baje|ghante|ghanta|minute\s+baad|din\s+baad|hafte|week|mahine|somvaar|somwar|mangalvaar|mangalwar|budhvaar|budhwar|"
             r"guruvaar|guruwar|shukravaar|shukrawar|shanivaar|shaniwar|ravivaar|itvaar|itwar|monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|evening|morning)|कल|आज|परसों|शाम|सुबह|बजे")
# the value itself was said as well ("paanch lakh, baaki nahi bata sakta"): then it is an answer, and the usual reading takes it
_NAMES_LOAN = r"\b(?:personal|payday|pay\s*day|salary|gold|home|business|vehicle|car|bike)\s+(?:loan|wala)\b"


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def words(text: str) -> int:
    return len(re.findall(r"[a-zऀ-ॿ0-9]+", text))


def read(text: str, asked, has_value: bool) -> str:
    """What the customer means, or "" for an ordinary answer or question (handled as before).
    One of: stop, leave, busy, why, unsure, refuse, dont_know, need_money, any_loan, max_amount, varies, home, any_time."""
    low = " " + text.lower().strip() + " "
    if has(STOP, low):
        return "stop"
    if has(LEAVE, low.strip()) and not has_value and not has(r"\b(?:chahiye|chahie|chaiye)\b.*\b(?:chahiye|chahie|chaiye)\b", low):
        return "leave"
    if asked == "callback_time":
        if has(REFUSE, low) or has(DONT_KNOW, low):
            return "any_time"
        if has(ANY_TIME, low):
            return "any_time"
    if has(BUSY, low):
        return "busy"
    if has(UNSURE, low):
        return "unsure"
    if has(WHY, low):
        return "why"
    if asked is None or has_value:
        return ""
    if asked == "loan_type":
        if has(_NAMES_LOAN, low) or has(r"\b(?:personal|payday|salary|salari|पर्सनल|सैलरी)\b", low) and not has(REFUSE.replace("personal", "persona_l"), low):
            return ""
        if has(ANY_LOAN, low) or has(r"\bkaun\s*sa\b.*\b(?:pata\s+nahi|nahi\s+pata)|\b(?:pata\s+nahi|nahi\s+pata)\b.*\bkaun\s*sa\b", low):
            return "any_loan"
        if has(NEED_MONEY, low):
            return "need_money"
    if asked == "loan_amount" and has(MAX_AMOUNT, low):
        return "max_amount"
    if asked in ("monthly_income", "existing_emi") and has(VARIES, low):
        return "varies"
    if asked == "employment" and has(HOME, low):
        return "home"
    if has(REFUSE, low) and not has(r"\b(?:kya\s+aap|aap\s+(?:kyun\s+)?bata\s+nahi\s+sakt)", low):
        return "refuse"
    if has(DONT_KNOW, low) and words(low) <= 8:
        return "dont_know"
    return ""
