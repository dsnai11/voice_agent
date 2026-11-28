"""DEMO collection calls: Ria reminds a demo-CRM customer about a due EMI and notes the answer.

The conversation is fixed (no language model): every sentence Ria can say is listed here, so she answers quickly and never invents
an amount, a charge or a promise. Rules kept in code:
  * No loan detail is said until the person confirms they are the customer. Another person hears nothing about the loan.
  * No threats, no waiver, no new due date is promised; charges and settlement are left to the team or branch.
  * "Do not call me" and disputes are noted and the call ends politely.
Results go to demo_crm/results.json only (never into the company's lead or query sheets).
"""
import json
import os
import re
import threading
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CUSTOMERS_FILE = os.path.join(HERE, "demo_crm", "customers.json")
RESULTS_FILE = os.path.join(HERE, "demo_crm", "results.json")
_LOCK = threading.Lock()

OUTCOMES = {"promise_to_pay": "Promised to pay", "paid_claimed": "Says already paid (team to check)", "hardship": "Money problem (team to follow up)",
            "debit_issue": "EMI not debited (team to check)", "callback": "Asked to be called back", "wrong_person": "Wrong person",
            "not_available": "Customer not available", "dispute": "Disputes the loan or amount", "stop_calling": "Asked not to be called",
            "team_followup": "Team to follow up", "incomplete": "Call ended early"}


def customers() -> list:
    with open(CUSTOMERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def customer(cid: str):
    return next((c for c in customers() if c["id"] == cid), None)


def results() -> list:
    try:
        with open(RESULTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def lines(c: dict) -> dict:
    """Everything Ria can say to this customer."""
    n = c["name"]
    emi = f"आपकी लोन की किस्त {c['emi']} रुपये की, जिसकी तारीख़ {c['due']} थी, अभी बाकी दिख रही है।"
    ask_date = "आप किस तारीख़ तक किस्त जमा कर पाएँगे?"
    ask_paid = "क्या आपने ये किस्त जमा कर दी है?"
    return {
        "opening": f"नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड से। क्या मेरी बात {n} जी से हो रही है?",
        "who_before": f"जी, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस से। क्या आप {n} जी बोल रहे हैं?",
        "who_after": "जी, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस से। " + ask_paid,
        "robot": f"जी, मैं रिया हूँ, कंपनी की ऑटोमेटेड असिस्टेंट। क्या आप {n} जी बोल रहे हैं?",
        "robot_after": "जी, मैं रिया हूँ, कंपनी की ऑटोमेटेड असिस्टेंट। " + ask_paid,
        "confirm_again": f"माफ़ कीजिए, क्या आप {n} जी बोल रहे हैं? कृपया हाँ या ना बताइए।",
        "wrong_person": "माफ़ कीजिए, आपको तकलीफ़ हुई। धन्यवाद।",
        "ask_when_available": f"कोई बात नहीं जी। {n} जी से किस समय बात हो सकती है?",
        "available_noted": "ठीक है जी, मैंने नोट कर लिया है। धन्यवाद।",
        "emi_info": f"धन्यवाद {n} जी। {emi} {ask_paid}",
        "emi_repeat": f"जी, {emi} {ask_paid}",
        "ask_paid_again": f"माफ़ कीजिए, मैं ठीक से समझ नहीं पाई। {ask_paid}",
        "ask_paid_detail": "धन्यवाद जी। आपने किस तारीख़ को और किस तरीक़े से किस्त जमा की थी?",
        "paid_noted": "ठीक है जी, मैंने नोट कर लिया है। टीम आपका अकाउंट चेक करके कन्फ़र्म करेगी।",
        # not paid yet: authoritative wording (owner's choice, 2026-11-26) - direct, states possible consequences as "may"; no threat, no insult
        "ask_date": f"{n} जी, आपकी किस्त की तारीख़ निकल चुकी है और किस्त अभी तक जमा नहीं हुई है। इसे तुरंत जमा करना होगा। देरी से लेट चार्ज लग सकता है और आपके सिबिल स्कोर पर असर पड़ सकता है। बताइए, आप किस तारीख़ को जमा करेंगे?",
        "ask_date_again": f"{n} जी, टालने से काम नहीं चलेगा। मुझे अभी एक पक्की तारीख़ चाहिए। आप ये किस्त किस तारीख़ को जमा करेंगे?",
        "hardship_ask": f"जी, मैं समझ सकती हूँ। {ask_date}",
        "hardship_noted": "ठीक है जी, मैंने आपकी परेशानी नोट कर ली है। हमारी टीम आपसे बात करेगी।",
        "debit_ask": "जी, किस्त आपके बैंक अकाउंट से कटती है। कृपया अकाउंट में पूरा बैलेंस रखिए, टीम चेक करके बताएगी। आप किस तारीख़ तक बैलेंस रख पाएँगे?",
        "promise_noted": "ठीक है, मैंने आपकी बताई हुई तारीख़ नोट कर ली है। ध्यान रखिए, उस दिन तक किस्त ज़रूर जमा होनी चाहिए।",
        # C1-C6: wording approved by the owner on 2026-11-27; Ria answers and then asks for the payment date again
        "deposited_today": f"जी, बैंक किस समय किस्त काटेगा, ये मैं पक्का नहीं बता सकती। अगर पैसा बैंक की कोशिश के बाद जमा हुआ है, तो किस्त बाउंस हो सकती है। अकाउंट में पूरा बैलेंस रखिए, और आज ही ब्रांच से सही जानकारी ले लीजिए। {ask_date}",
        "penalty_waiver": f"जी, चार्ज हटाने या कम करने का वादा मैं नहीं कर सकती। आपकी बात मैं नोट कर लेती हूँ, टीम या ब्रांच इसे देखेगी। {ask_date}",
        "penalty": f"जी, चार्ज कितना है और क्यों लगा है, ये आपका लोन अकाउंट देखकर ही बताया जा सकता है। ब्रांच से आप पूरा हिसाब ले सकते हैं। {ask_date}",
        "no_loan_number": "कोई बात नहीं जी। लोन किसके नाम पर है, और आपका रजिस्टर्ड मोबाइल नंबर क्या है, ये बता दीजिए। मैं नोट कर लेती हूँ।",       # waits for the answer; the date is asked after it
        "after_details": f"जी। {ask_date}",
        "pay_branch": f"जी, आप ब्रांच में जाकर जमा कर सकते हैं, और रसीद ज़रूर लीजिए। बिना रसीद के किसी को पैसे मत दीजिए। {ask_date}",
        "noc_pending": f"जी, मैं आपकी रिक्वेस्ट नोट कर लेती हूँ। टीम या ब्रांच आपका अकाउंट और बाकी चार्ज चेक करके एन ओ सी की स्थिति बताएगी। {ask_date}",
        "how_pay": f"जी, किस्त जमा करने का सही तरीक़ा आपकी ब्रांच बता देगी, आप ब्रांच में जाकर भी जमा कर सकते हैं। {ask_date}",
        "other_question": f"जी, इसकी सही जानकारी हमारी टीम आपको देगी। {ask_date}",
        "ask_callback": "कोई बात नहीं जी। मैं आपको किस समय कॉल करवाऊँ?",
        "callback_noted": "ठीक है जी, टीम आपको उसी समय कॉल करेगी।",
        "dispute_noted": "जी, मैंने आपकी बात नोट कर ली है। टीम आपका अकाउंट चेक करके आपसे संपर्क करेगी।",
        "stop_noted": "ठीक है जी, मैंने आपकी बात नोट कर ली है। आपको हुई परेशानी के लिए माफ़ी चाहती हूँ।",
        "team_followup": "ठीक है जी, हमारी टीम आपसे बात करेगी।",
    }


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


WRONG = r"wrong number|galat number|rong number|गलत नंबर|ग़लत नंबर"
STOP = r"(call|phone|fon|कॉल|फोन|फ़ोन)\s*(mat|na |nahi|मत|न )|mat karo call|band karo call|pareshan mat|परेशान मत"
DISPUTE = r"loan (hi )?(nahi|nahin) liya|maine koi loan|galat amount|amount galat|galat hai|fraud|fraad|लोन नहीं लिया|ग़लत है|गलत है"
BUSY = r"busy|vyast|baad m(e|ei)n? (call|phone|baat)|baad me|abhi baat nahi|gaadi chala|driving|meeting|व्यस्त|बाद में"
AWAY = r"(ghar|yahan|yaha)\s*(pe |par )?(nahi|nahin)|bahar (gaye|gaya|hai)|so rahe|available nahi|घर पर नहीं|बाहर गए|नहीं हैं"
DEBIT = r"(kati|kata|katta|katti|debit|cut)\s*(hi )?(nahi|nahin)|(nahi|nahin)\s*(kati|kata|cut|debit)|auto ?debit|mandate|nach|कटी नहीं|नहीं कटी|नहीं कटा"
FUTURE = r"dung[aie]|doonga|denge|karung[aie]|karoong[aie]|karenge|kar dega|bharung[aie]|bhar d(u|oo)ng|de d(u|oo)ng|hojaega|ho jaega|ho jayega|करूँगा|करूंगा|दूँगा|दूंगा|देंगे|करेंगे|भर दूं|भर दूँ|हो जाएगा"
DATE = r"\bkal\b|\baaj\b|parso|tarik|taarik|tareekh|salary (aate|aane|ke baad)|hafte|week|mahine|month|somvaar|somwar|mangal|budh|guru|shukr|shanivar|ravivar|monday|tuesday|wednesday|thursday|friday|saturday|sunday|din (me|mein|baad)|january|february|march|april|may\b|june|july|august|september|october|november|december|\d+\s*(tak|ko|date)|कल|आज|परसों|तारीख|तारीख़|हफ्ते|महीने|नवंबर|दिसंबर"
PAID = r"(jama|bhar|pay|paid|payment|kist|emi|installment)[^.?!]{0,25}(kar d[iy]|kar chuk|ho gay|ho chuk|di thi|diya tha|bhar di|chuka)|already|kar di hai|kar diya hai|bhar di|bhar diya|jama kar di|de diya|de di |paid|जमा कर दी|जमा कर दिया|भर दी|भर दिया|जमा हो गई|कर चुका"
HARD = r"pais[ae]\s*(nahi|nahin|nai)|nahi hai pais|dikkat|problem|pareshani|naukri|job (chali|chhut)|bimaar|bimar|hospital|nuksaan|kaam band|tangi|पैसे नहीं|दिक्कत|परेशानी|बीमार|नौकरी"
PENALTY = r"penalty|penlty|charge|late fee|jurmana|byaj|byaaj|पेनल्टी|चार्ज|जुर्माना|ब्याज"
HOWPAY = r"kaise (jama|bhar|pay|de)|kahan (jama|bhar|pay|de)|kidhar jama|online|upi|phone ?pe|google ?pay|link bhej|कैसे जमा|कहाँ जमा|ऑनलाइन"
AMOUNT = r"kitn[ie]\s*(kist|emi|rupe|rupa|paise|amount|ki hai|hai)|kitna\s*(amount|paisa|rupaya|baaki|dena|bharna)|amount kya|kaun si kist|konsi kist|kab ki (kist|thi)|कितनी किस्त|कितना|कितने रुपये|कौन सी किस्त"
MACHINE = r"robot|machine|computer|recording|\bai\b|insaan|asli (aurat|ladki|aadmi)|real (person|human)|human|रोबोट|मशीन|इंसान|एआई"
RELATIVE = r"(uska|uski|unka|unki|inka|inke) (bhai|beta|beti|papa|pita|maa|mata|wife|pati|patni|dost|rishtedar)|(bhai|beta|beti|papa|wife|pati|patni|dost) (bol|hoon|hu |hun)|उनका|उनकी|का भाई|का बेटा|की पत्नी|के पापा"
CONFIRM = r"\bha+n?\b|haanji|hanji|\byes\b|\bhao\b|bol rah[aie] h(oo|u)n|hi bol|se (hi )?(ho rah[ie]|baat ho)|speaking|हाँ|हां|बोल रहा हूँ|बोल रही हूँ|से हो रही"
ABOUT = r"kya (kaam|baat)|kaam (tha|hai|kya)|kis (liye|kaam|baare|silsile)|ky(un|on)? (call|phone|fon)|(emi|kist|loan)[^.?]{0,20}(baare|bare|batai|bataiye|batao|detail|jaankari)|(batai|bataiye|batao)[^.?]{0,20}(emi|kist|loan)|क्या काम|किस लिए|क्यों कॉल|के बारे में"
WHO = r"(aap|tum)\s*kaun|kaun (bol|baat)|kahan se|kis (company|kaam|liye|baare)|kyun? (call|phone)|kya kaam|robot|machine|ai ho|आप कौन|कौन बोल|कहाँ से|किस लिए|क्यों कॉल"
UNSURE = r"samajh (nahi|nahin)|sunai nahi|dobara|phir se bol|repeat|kya bola|समझ नहीं|दोबारा|फिर से"
# the questions of the owner-approved lines C1-C6
TODAY = r"\baaj\b|subah|आज|सुबह"
PUT_IN = r"daal|\bdal(a|e|i|ya|wa|va|aa|va)|dalv|dalw|jama|deposit|डाल|जमा"
CUT = r"\bkat|\bcut|bounce|कट|बाउंस"
WILL_I = r"dung[aie]|doonga|karung[aie]|karoong[aie]|d(aa|a)lung|दूँगा|दूंगा|करूँगा|करूंगा|डालूँगा|डालूंगा"
WAIVE = r"maaf|\bmaf\b|hata|waive|kam kar|kam ki|mat lag|na lagao|nahi lagao|माफ़|माफ|हटा|कम कर|कम की|मत लगा"
NO_LOAN_NO = r"(loan|लोन)\s*(account\s*|अकाउंट\s*)?(number|नंबर)[^?]{0,25}(nahi|nahin|bhool|नहीं|भूल)|(nahi|nahin|नहीं)[^?]{0,15}(loan|लोन)\s*(number|नंबर)"
BRANCH = r"branch|\bcash\b|naqad|nakad|ब्रांच|कैश|नकद"
MAY_I = r"sakt|sakat|chalega|lete h|loge|\b(du|doon|dun|karu|karoon)\b|सकत|चलेगा|(दूँ|दूं|करूँ|करूं)(?=\s|\?)"
NOC = r"\bnoc\b|\bn o c\b|एनओसी|एन ओ सी"
PAPERS = r"kagaz|kaagaz|kagaj|\bpapers?\b|document|कागज़|कागज|पेपर"
NOT_GOT = r"(nahi|nahin) (mil|aa)|kab (mil|aa)|vaapas|wapas|waapas|नहीं मिल|कब मिल|वापस|नहीं आ"
# a customer who has just confirmed and carries on talking (see keeps_confirmation)
NOT_ME = r"\b(main|mai)\b[^?]{0,20}\b(nahi|nahin|nai)\s*(hoon|hu\b|hun|bol)|(मैं)[^?]{0,20}नहीं\s*(हूँ|हूं|बोल)"
ACK_WORDS = set("haan han ha haanji hanji ji jee yes hao main mai me hi bol raha rahi rha rhi hoon hu hun boliye bolo bataiye batao hello accha achha acha theek thik ok okay se ho speaking sir madam "
                "हाँ हां जी मैं ही बोल रहा रही हूँ हूं बोलिए बताइए हेलो अच्छा ठीक है से हो hai".split())
NO_ONLY = {"nahi", "nahin", "nahee", "nai", "no", "naa", "na", "नहीं", "ना"}
IDENTITY = r"bol rah[aie]|bol rha|bol rhi|speaking|hi h(oo|u)n|बोल रहा|बोल रही"
YES_W = r"\b(haan?|han|haanji|hanji|ji|yes|bilkul|sahi|bol raha|bol rahi|boliye|bolo|speaking|hao)\b|हाँ|हां|जी|बोलिए|बोल रहा|बोल रही"
NO_W = r"\b(nahi|nahin|nahee|nai|no|naa|koni)\b|नहीं|ना\b"


class CollectionCall:
    """Has the same face as brain.Call, so the server drives it the same way."""
    collection = True

    def __init__(self, c: dict):
        self.customer = c
        self.say = lines(c)
        self.stage = "identity"
        self.finished = False
        self.more_coming = False
        self.flow = None                       # no loan-enquiry form in a collection call
        self.form, self.flags, self.confirmed, self.audit = {}, {}, set(), []
        self.outcome = "incomplete"
        self.notes = []                        # what the customer said that matters (dates, reasons)
        self.unclear = 0
        self.introduced = False                 # she has already said again who she is

    # --- the face the server uses
    def opening(self) -> str:
        return self.say["opening"]

    def start_with(self, text: str) -> None:
        pass

    def not_heard(self) -> str:
        return "माफ़ कीजिए, आपकी आवाज़ साफ़ नहीं आई। कृपया दोहराइए।"

    def reply(self, user_text: str) -> str:
        t = " " + re.sub(r"[^\w\sऀ-ॿ?]", " ", user_text.lower()) + " "
        return getattr(self, "_" + self.stage)(t, user_text.strip())

    # --- helpers
    def _end(self, key: str, outcome: str, note: str = "") -> str:
        self.finished, self.stage, self.outcome = True, "done", outcome
        if note:
            self.notes.append(note)
        return self.say[key]

    def _go(self, stage: str, key: str, note: str = "") -> str:
        self.stage, self.unclear = stage, 0
        if note:
            self.notes.append(note)
        return self.say[key]

    def _again(self, key: str) -> str:
        self.unclear += 1
        if self.unclear >= 4:                              # four times in a row without an answer: the team takes over
            return self._end("team_followup", "team_followup")
        return self.say[key]

    def _always(self, t: str, raw: str):
        """Things that matter at any point of the call."""
        if _has(t, STOP):
            return self._end("stop_noted", "stop_calling", raw)
        if _has(t, BUSY):
            return self._go("callback", "ask_callback", raw)
        return None

    # --- stages
    def _identity(self, t, raw):
        name = self.customer["name_en"].lower()
        if _has(t, WRONG):
            return self._end("wrong_person", "wrong_person")
        hit = self._always(t, raw)
        if hit:
            return hit
        if _has(t, AWAY) or _has(t, RELATIVE):              # someone else of the family: nothing about the loan
            return self._go("other_time", "ask_when_available")
        if _has(t, MACHINE):
            return self._again("robot")                      # a sincere question: never claim to be a person
        named = name in t or self.customer["name"] in t
        asked_who = _has(t, WHO)
        if not _has(t, NO_W):
            # "haan, mohan ji se ho rahi hai, aap kaun?" confirms AND asks: confirm first, and move on to the reason of the call.
            # With a "who are you?" in it, a bare "ji" or "boliye" is not enough - it must be a clear yes or the name.
            confirmed = _has(t, CONFIRM) or named or (not asked_who and _has(t, YES_W))
            if confirmed:
                return self._go("emi", "emi_info")
        if asked_who or _has(t, ABOUT):
            self.unclear += 1                                # she introduces herself once; after that only the short question
            if self.unclear >= 4:
                return self._end("team_followup", "team_followup")
            if asked_who and not self.introduced:
                self.introduced = True
                return self.say["who_before"]
            return self.say["confirm_again"]
        if _has(t, NO_W):
            return self._end("wrong_person", "wrong_person")
        return self._again("confirm_again")

    def _other_time(self, t, raw):
        return self._end("available_noted", "not_available", raw)

    def _callback(self, t, raw):
        return self._end("callback_noted", "callback", raw)

    def _approved(self, t, raw):
        """The questions answered with the owner-approved lines C1, C2, C4, C5 and C6 (C3, the plain charge question, is in _question)."""
        if _has(t, FUTURE) and _has(t, DATE) and not _has(t, CUT):
            return None                                       # "kal jama kar dunga" is a promise, whatever else was said
        if _has(t, NO_LOAN_NO):
            return self._go("loan_id", "no_loan_number", raw)
        if _has(t, TODAY) and _has(t, PUT_IN) and _has(t, CUT) and not _has(t, WILL_I):
            return self._go("date", "deposited_today", raw)
        if _has(t, PENALTY) and _has(t, WAIVE):
            return self._go("date", "penalty_waiver", raw)
        if _has(t, NOC) or (_has(t, PAPERS) and _has(t, NOT_GOT)):
            return self._go("date", "noc_pending", raw)
        if _has(t, BRANCH) and _has(t, MAY_I) and not _has(t, FUTURE):
            return self._go("date", "pay_branch", raw)
        return None

    def keeps_confirmation(self, text: str) -> bool:
        """The customer said yes, Ria began the next line, and they carried on with `text`. True: they stay confirmed and `text` is
        answered on its own. False: both are judged together at the identity step again - for anything that may mean this is not
        the customer, and for a mere second "yes" or "who are you?", after which Ria says her line again."""
        t = " " + re.sub(r"[^\w\sऀ-ॿ?]", " ", text.lower()) + " "
        names = (self.customer["name_en"].lower(), self.customer["name"])
        if any(_has(t, p) for p in (WRONG, AWAY, RELATIVE, NOT_ME)):
            return False
        if any(_has(t, re.escape(n) + r"\s*(ji\s*|जी\s*)?(nahi|nahin|नहीं)") for n in names):
            return False
        if _has(t, WHO) or _has(t, ABOUT) or _has(t, MACHINE):
            return False
        left = [w for w in t.replace("?", " ").split() if w not in ACK_WORDS and w not in names]
        return bool(left) and not set(left) <= NO_ONLY

    def _loan_id(self, t, raw):
        """After C4: whatever they say (name, mobile number) is noted for the team; then the date is asked."""
        hit = self._always(t, raw)
        if hit:
            return hit
        if _has(t, DISPUTE):
            return self._end("dispute_noted", "dispute", raw)
        if _has(t, FUTURE) and _has(t, DATE):
            return self._end("promise_noted", "promise_to_pay", raw)
        return self._go("date", "after_details", raw)

    def _question(self, t, raw):
        if _has(t, PENALTY):
            return self._go("date", "penalty", raw)
        if _has(t, HOWPAY):
            return self._go("date", "how_pay", raw)
        if _has(t, AMOUNT) or _has(t, UNSURE) or _has(t, WHO):
            return self._again("emi_repeat")
        return None

    def _emi(self, t, raw):
        if _has(t, WRONG):
            return self._end("wrong_person", "wrong_person")
        hit = self._always(t, raw)
        if hit:
            return hit
        if _has(t, DISPUTE):
            return self._end("dispute_noted", "dispute", raw)
        answer = self._approved(t, raw)
        if answer:
            return answer
        if _has(t, DEBIT):
            return self._go("debit_date", "debit_ask", raw)
        if _has(t, HARD):
            return self._go("hard_date", "hardship_ask", raw)
        if _has(t, FUTURE):
            if _has(t, DATE):
                return self._end("promise_noted", "promise_to_pay", raw)
            return self._go("date", "ask_date", raw)
        if _has(t, PAID) and not _has(t, NO_W):
            return self._go("paid_detail", "ask_paid_detail", raw)
        if _has(t, MACHINE):
            return self._again("robot_after")
        if _has(t, ABOUT) and not _has(t, PENALTY) and not _has(t, HOWPAY):
            return self._again("emi_repeat")                # "bataiye, kya kaam tha / EMI ke baare mein bataiye"
        if _has(t, WHO):
            return self._again("who_after")
        question = self._question(t, raw)
        if question:
            return question
        if _has(t, NO_W):
            return self._go("date", "ask_date", raw)
        if _has(t, DATE):
            return self._end("promise_noted", "promise_to_pay", raw)
        if _has(t, IDENTITY) or self.customer["name"] in t or self.customer["name_en"].lower() in t:
            return self._again("emi_repeat")                # "haan, main hi bol raha hoon" says who is speaking, not that it is paid
        if _has(t, YES_W):                                  # "haan" to "have you paid?"
            return self._go("paid_detail", "ask_paid_detail", raw)
        return self._again("ask_paid_again")

    def _paid_detail(self, t, raw):
        hit = self._always(t, raw)
        return hit or self._end("paid_noted", "paid_claimed", raw)

    def _date(self, t, raw, no_date_key="team_followup", no_date_outcome="team_followup"):
        hit = self._always(t, raw)
        if hit:
            return hit
        if _has(t, DISPUTE):
            return self._end("dispute_noted", "dispute", raw)
        answer = self._approved(t, raw)
        if answer:
            return answer
        if _has(t, PAID) and not _has(t, NO_W) and not _has(t, FUTURE):
            return self._go("paid_detail", "ask_paid_detail", raw)
        if _has(t, DATE) or re.search(r"\d", t):
            return self._end("promise_noted", "promise_to_pay", raw)
        if _has(t, HARD) and self.stage != "hard_date":
            return self._go("hard_date", "hardship_ask", raw)
        question = self._question(t, raw)
        if question:
            return question
        self.unclear += 1
        if self.unclear >= 2:
            return self._end(no_date_key, no_date_outcome, raw)
        self.notes.append(raw)
        return self.say["ask_date_again"]

    def _hard_date(self, t, raw):
        if _has(t, NO_W) or _has(t, HARD):
            if not _has(t, DATE):
                return self._end("hardship_noted", "hardship", raw)
        return self._date(t, raw, "hardship_noted", "hardship")

    def _debit_date(self, t, raw):
        answer = self._approved(t, raw)
        if answer:
            return answer
        if _has(t, DATE) or re.search(r"\d", t):
            return self._end("promise_noted", "debit_issue", raw)
        return self._date(t, raw, "team_followup", "debit_issue")

    def _done(self, t, raw):
        return self.say["team_followup"]


def save_result(call: CollectionCall, transcript: list, call_id: str, started: float) -> None:
    """One row per call in demo_crm/results.json (saved again as the call goes on)."""
    row = {"call_id": call_id, "customer_id": call.customer["id"], "started_at": datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S"),
           "outcome": call.outcome, "outcome_text": OUTCOMES.get(call.outcome, call.outcome), "customer_said": call.notes,
           "transcript": [{"who": "Ria" if r == "agent" else "Customer", "text": x} for r, x in transcript]}
    with _LOCK:
        rows = [r for r in results() if r["call_id"] != call_id] + [row]
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(rows[-200:], f, ensure_ascii=False, indent=1)


def all_lines() -> list:
    """Every sentence of every demo customer, so the voice can prepare them before the first call."""
    out = []
    for c in customers():
        say = lines(c)
        out += [say[k] for k in ("opening", "emi_info")]
    for c in customers():
        out += list(lines(c).values())
    return list(dict.fromkeys(out))
