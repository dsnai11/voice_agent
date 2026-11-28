"""DEMO sales calls: Ria asks an existing (made-up) customer whether they need a top-up and notes the answers for the team.

Wording S1 was approved by the owner on 2026-11-27. The conversation is fixed (no language model); the other sentences are the
ones already used in the demo collection call. Rules kept in code:
  * The running loan is mentioned only after the person confirms they are the customer.
  * No amount, interest, charge or approval is promised; the team decides.
Results go to demo_crm/results.json only. Kept apart from collection.py: this is sales, that is collection.
"""
import json
import os
import re

import collection
from collection import _has

CUSTOMERS_FILE = os.path.join(collection.HERE, "demo_crm", "sales_customers.json")
collection.OUTCOMES.update({"topup_interest": "Interested in a top-up (team to call)", "not_interested": "Not interested"})

NOT_WANT = (r"(zaroorat|zarurat|jarurat|jaroorat|chahiye|chaahiye|chaahie|lena)\s*(hi )?(nahi|nahin)|(nahi|nahin|no)\s*(chahiye|chaahiye|chaahie|lena|karna|karvana|karwana)"
            r"|interested nahi|not interested|नहीं चाहिए|ज़रूरत नहीं|जरूरत नहीं|नहीं लेना")
BUSY = r"busy|vyast|abhi baat nahi|baad m(e|ei)n? (call|phone|baat)|meeting|driving|gaadi chala rah|व्यस्त|बाद में"
MACHINE = r"robot|machine|recording|insaan|asli (aurat|ladki|aadmi)|real (person|human)|computer (ho|hai kya|bol)|रोबोट|मशीन|इंसान"
WHO = r"(aap|tum)\s*kaun|kaun (bol|baat)|kis company|kahan se bol|आप कौन|कौन बोल|कहाँ से"
UNSURE = collection.UNSURE
_TOPIC = r"(byaj|byaaj|interest|\brate\b|charge|\bfees?\b|document|kagaz|kaagaz|\bemi\b|kist|ब्याज|चार्ज|फीस|किस्त)"
_ASK = r"(\bkya\b|kitn|kaise|\bkab\b|\?|कित|क्या|कैसे)"
ASKS = _TOPIC + r"[^.]{0,30}" + _ASK + "|" + _ASK + r"[^.]{0,30}" + _TOPIC + r"|kitn\w* (tak )?(milega|milenge|mil sakta|lagega|ho sakta|ho jaega)|कितना मिल"
AMOUNT_SAID = r"\d|lakh|\blac\b|hazar|hazaar|thousand|लाख|हज़ार|हजार"
ONLY_FILLER = r"^\s*((ha+n?|haanji|hanji|ji|yes|hello|hmm+|achha|accha|thik|theek|ok|okay|boliye|bolo|hai|हाँ|हां|जी|अच्छा|ठीक|है|हेलो|बोलिए)\s*[?]?\s*)+$"


def customers() -> list:
    with open(CUSTOMERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def customer(cid: str):
    return next((c for c in customers() if c["id"] == cid), None)


def lines(c: dict) -> dict:
    """Everything Ria can say on this call."""
    n = c["name"]
    base = collection.lines({"name": n, "emi": 0, "due": ""})
    keep = ("opening", "who_before", "robot", "confirm_again", "wrong_person", "ask_when_available", "available_noted",
            "ask_callback", "callback_noted", "dispute_noted", "stop_noted", "team_followup")
    q = {   # S1, owner-approved
        "offer": "क्या आपको और रकम, यानी टॉप-अप, की ज़रूरत है?",
        "amount": "आपको लगभग कितनी रकम चाहिए?",
        "purpose": "ये रकम किस काम के लिए चाहिए?",
        "work": "अभी आप क्या काम करते हैं, और महीने की इनकम लगभग कितनी है?",
        "when": "आपको किस टाइम पर कॉल करवाऊँ?",
    }
    say = {k: base[k] for k in keep}
    say["emi_info"] = f"{n} जी, आपका हमारे यहाँ लोन चल रहा है। {q['offer']}"      # the key the identity step moves on to
    say["amount"], say["purpose"], say["work"] = q["amount"], q["purpose"], q["work"]
    say["close"] = f"ठीक है जी। टॉप-अप मिलेगा या नहीं और कितना, ये टीम आपकी प्रोफ़ाइल और रीपेमेंट देखकर बताएगी। {q['when']}"
    say["no_thanks"] = "ठीक है जी, कोई बात नहीं। आपका टाइम देने के लिए शुक्रिया।"
    # asked something in the middle: answer with a sentence she already uses, then ask the open question again
    prefix = {"who": "जी, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस से।", "robot": "जी, मैं रिया हूँ, कंपनी की ऑटोमेटेड असिस्टेंट।",
              "team": "जी, इसकी सही जानकारी हमारी टीम आपको देगी।", "sorry": "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई।"}
    for stage, question in q.items():
        for name, start in prefix.items():
            say[f"{name}_{stage}"] = f"{start} {question}"
    return say


class TopUpCall(collection.CollectionCall):
    """Same face as CollectionCall (the server drives it the same way); the identity step is shared."""

    def __init__(self, c: dict):
        super().__init__({**c, "emi": 0, "due": ""})            # the shared set-up; its collection lines are replaced on the next line
        self.say = lines(c)

    def _always(self, t: str, raw: str):
        if _has(t, collection.STOP):
            return self._end("stop_noted", "stop_calling", raw)
        if _has(t, BUSY):
            return self._go("callback", "ask_callback", raw)
        return None

    def _side(self, t, raw, question):
        """What can happen while Ria waits for the answer to `question`. None = this is the answer."""
        hit = self._always(t, raw)
        if hit:
            return hit
        if _has(t, collection.DISPUTE):
            return self._end("dispute_noted", "dispute", raw)
        if _has(t, NOT_WANT):
            return self._end("no_thanks", "not_interested", raw)
        if _has(t, MACHINE):
            return self._again(f"robot_{question}")
        if _has(t, WHO):
            return self._again(f"who_{question}")
        if _has(t, ASKS):
            self.notes.append(raw)                                # the team sees what was asked
            return self._again(f"team_{question}")
        if _has(t, UNSURE) or re.match(ONLY_FILLER, " ".join(t.split())):
            return self._again(f"sorry_{question}")
        return None

    def _emi(self, t, raw):                                       # the top-up question (stage name shared with the identity step)
        if _has(t, collection.WRONG):
            return self._end("wrong_person", "wrong_person")
        filler = re.match(ONLY_FILLER, " ".join(t.split()))
        if filler:                                                # "haan ji" to "do you need a top-up?" is a yes
            if _has(t, r"\b(haan?|han|haanji|hanji|yes)\b|हाँ|हां"):
                return self._go("amount", "amount")
            return self._again("sorry_offer")
        side = self._side(t, raw, "offer")
        if side:
            return side
        if _has(t, collection.NO_W):
            return self._end("no_thanks", "not_interested", raw)
        if _has(t, AMOUNT_SAID):                                  # "do lakh chahiye": the amount is already said
            return self._go("purpose", "purpose", raw)
        if _has(t, collection.YES_W) or _has(t, r"chahiye|chaahiye|zaroorat hai|चाहिए"):
            return self._go("amount", "amount", raw)
        return self._again("sorry_offer")

    def _amount(self, t, raw):
        return self._side(t, raw, "amount") or self._go("purpose", "purpose", raw)

    def _purpose(self, t, raw):
        return self._side(t, raw, "purpose") or self._go("work", "work", raw)

    def _work(self, t, raw):
        return self._side(t, raw, "work") or self._go("when", "close", raw)

    def _when(self, t, raw):                                      # here "baad mein / shaam ko" is the answer, not "I am busy"
        if _has(t, collection.STOP):
            return self._end("stop_noted", "stop_calling", raw)
        if _has(t, BUSY) and not _has(t, collection.DATE) and not _has(t, r"baje|subah|shaam|dopahar|बजे|सुबह|शाम"):
            return self._again("sorry_when")
        side = None if _has(t, BUSY) else self._side(t, raw, "when")
        return side or self._end("callback_noted", "topup_interest", raw)


def all_lines() -> list:
    """For preparing the voice: the usual path of every demo sales customer first, then the rest."""
    out = []
    for c in customers():
        say = lines(c)
        out += [say[k] for k in ("opening", "emi_info", "amount", "purpose", "work", "close", "callback_noted", "no_thanks")]
    for c in customers():
        out += list(lines(c).values())
    return list(dict.fromkeys(out))
