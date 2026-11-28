"""Checks the demo collection conversation: python train/test_collection.py (no servers needed)."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collection

CASES = [   # (what the customer says, turn by turn, in the listener's Hinglish; expected outcome; expected finished)
    (["Haan ji bol raha hoon", "Nahi abhi jama nahi ki", "Kal tak kar dunga"], "promise_to_pay"),
    (["Haan", "Paanch tarikh tak bhar dunga"], "promise_to_pay"),
    (["Ji haan", "Maine to jama kar di hai", "Kal PhonePe se ki thi"], "paid_claimed"),
    (["Haan", "Haan", "Do tarikh ko branch mein"], "paid_claimed"),
    (["Haan boliye", "Meri kist account se kati nahi", "Kal tak balance rakh dunga"], "debit_issue"),
    (["Haan", "Abhi paise nahi hai, bahut dikkat hai", "Pata nahi, abhi nahi ho payega"], "hardship"),
    (["Haan", "Abhi paise nahi hain", "Agle mahine ki das tarikh ko"], "promise_to_pay"),
    (["Haan", "Penalty kitni lagegi", "Parson jama kar dunga"], "promise_to_pay"),
    (["Haan", "Online kaise jama karun", "Aaj shaam ko"], "promise_to_pay"),
    (["Haan", "Kitni kist hai meri", "Kal kar dunga"], "promise_to_pay"),
    (["Haan ji", "Main Ram hi bol raha hoon", "Nahi abhi jama nahi ki", "Kal kar dunga"], "promise_to_pay"),
    (["Haan", "Haan main hi bol raha hoon", "Haan jama kar di hai", "Kal online se"], "paid_claimed"),
    # the owner's own call, 2026-11-27: confirming and asking in one sentence must move on to the EMI
    (["Haan mohan ji se ho rahi hai bataiye aap kaun?", "Bataiye, kya kaam tha aapko mere se?", "Nahi abhi jama nahi ki", "Kal kar dunga"], "promise_to_pay"),
    (["Haan ram ji bol raha hoon", "Aap EMI ke baare mein bataiye", "Kis liye call kiya hai", "Kal tak jama kar dunga"], "promise_to_pay"),
    (["Aap kaun?", "Ji main Ram bol raha hoon", "Nahi", "Paanch tarikh ko dunga"], "promise_to_pay"),
    (["Nahi, galat number hai"], "wrong_person"),
    (["Nahi"], "wrong_person"),
    (["Woh ghar pe nahi hain", "Shaam ko saat baje"], "not_available"),
    (["Abhi main busy hoon, baad mein call karo", "Kal gyarah baje"], "callback"),
    (["Haan", "Maine koi loan nahi liya"], "dispute"),
    (["Haan", "Mujhe call mat karo"], "stop_calling"),
    (["Aap kaun bol rahe ho", "Haan main bol raha hoon", "Kal tak ho jayega, jama kar dunga"], "promise_to_pay"),
    # the owner-approved lines C1-C6 (2026-11-27): answered, then the call goes on to a date
    (["Haan", "Maine aaj subah account mein paise daale hain kist abhi tak nahi kati", "Kal tak balance rakh dunga"], "promise_to_pay"),
    (["Haan", "Penalty maaf kar dijiye", "Parson jama kar dunga"], "promise_to_pay"),
    (["Haan", "Mujhe loan number yaad nahi hai", "Mohan ke naam se hai number nau aath saat", "Kal kar dunga"], "promise_to_pay"),
    (["Haan", "Kya main branch mein cash jama kar sakta hoon", "Kal kar dunga"], "promise_to_pay"),
    (["Haan", "Meri NOC kab milegi", "Paanch tarikh ko dunga"], "promise_to_pay"),
    (["Haan", "Kal tak branch mein jama kar dunga"], "promise_to_pay"),
    (["Haan", "Kal jama kar dunga par penalty maaf kar dena"], "promise_to_pay"),
]
bad = 0
for said_, want_key in [("Maine aaj paise daale hain emi nahi kati", "deposited_today"), ("charge hata dijiye", "penalty_waiver"), ("penalty kyon lagi hai", "penalty"),
                        ("loan number mere paas nahi hai", "no_loan_number"), ("cash de sakte hain kya", "pay_branch"), ("meri noc nahi mili", "noc_pending"),
                        ("लोन नंबर याद नहीं है", "no_loan_number"), ("पेनल्टी माफ़ कर दीजिए", "penalty_waiver")]:
    call = collection.CollectionCall(collection.customer("ram"))
    call.reply("Haan")
    got = call.reply(said_)
    ok = got == call.say[want_key] and not call.finished
    bad += not ok
    print(("ok  " if ok else "BAD ") + f"{said_!r} -> {want_key}")
# a customer who said yes and carried on (the reply that followed was cut off): stays confirmed, unless the new words say otherwise
for new_words, want in [("Mujhe loan number yaad nahi hai", True), ("Penalty maaf kar dijiye", True), ("Nahi abhi maine jama nahi ki", True), ("Samajh nahi aaya phir se bolo", True),
                        ("Maine to jama kar di hai", True), ("Abhi paise nahi hain", True), ("लोन नंबर याद नहीं है", True),
                        ("Main uska bhai bol raha hoon", False), ("Nahi main Ram nahi hoon", False), ("Ram nahi hai ghar pe", False), ("Main Ram nahi bol raha", False),
                        ("Galat number hai", False), ("Nahi", False), ("Nahi ji", False), ("Haan ji", False), ("Main Ram hi bol raha hoon", False), ("Aap kaun bol rahe ho", False)]:
    call = collection.CollectionCall(collection.customer("ram"))
    got = call.keeps_confirmation(new_words)
    bad += got != want
    print(("ok  " if got == want else "BAD ") + f"stays confirmed after {new_words!r}: {got} (wanted {want})")
# after C4 the name and mobile number are noted and not taken as a payment date
call = collection.CollectionCall(collection.customer("ram"))
for x in ("Haan", "loan number nahi pata"):
    call.reply(x)
got = call.reply("Ram ke naam se, number 9000000000")
ok = got == call.say["after_details"] and not call.finished
bad += not ok
print(("ok  " if ok else "BAD ") + "name and mobile number after C4 are not read as a date")
for turns, want in CASES:
    call = collection.CollectionCall(collection.customer("ram"))
    said = [call.opening()]
    for t in turns:
        if call.finished:
            break
        said.append(call.reply(t))
    ok = call.outcome == want and call.finished
    bad += not ok
    print(("ok  " if ok else "BAD ") + " | ".join(turns) + f"  -> {call.outcome} (wanted {want})")

# Safety checks: nothing about the loan before the person says they are the customer, and never to another person
for first in ["Aap kaun bol rahe ho", "Kya kaam hai", "Nahi", "Galat number", "Woh ghar pe nahi hain", "Hmm", "Ji aap kaun", "Boliye aap kaun", "Haan main uska bhai bol raha hoon", "Kya aap robot ho"]:
    call = collection.CollectionCall(collection.customer("ram"))
    text = call.opening() + " " + call.reply(first)
    leak = "4500" in text or "किस्त" in text or "लोन की" in text
    bad += leak
    print(("BAD " if leak else "ok  ") + f"no loan detail after {first!r}")
for c in collection.customers():
    text = " ".join(collection.lines(c).values())
    forbidden = [w for w in ("कानूनी", "पुलिस", "जेल", "माफ़ कर देंगे", "छूट") if w in text]
    bad += bool(forbidden)
    print(("BAD " if forbidden else "ok  ") + f"no threat or waiver in the lines for {c['name_en']}")
# the owner's exact sentence reaches the EMI at once, and the introduction is not repeated
call = collection.CollectionCall(collection.customer("mohan"))
call.opening()
first_reply = call.reply("Haan mohan ji se ho rahi hai bataiye aap kaun?")
ok = "12500" in first_reply and "रिया" not in first_reply
bad += not ok
print(("ok  " if ok else "BAD ") + "confirm + 'who are you' goes straight to the EMI")
spoken = [t for c in collection.customers() for t in collection.lines(c).values()]
ok = not any(w in t for t in spoken for w in ("एआई", "AI ", "आर्टिफिशियल"))
bad += not ok
print(("ok  " if ok else "BAD ") + "no collection line says AI")
print("COLLECTION TEST: ALL OK" if not bad else f"COLLECTION TEST: {bad} FAILED")
