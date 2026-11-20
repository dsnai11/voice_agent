"""Replays the second live chat (Ram Sharma, 20 Nov) and checks the problems found in it are fixed.   python train/chat_replay2.py"""
import datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c.start_with("नमस्ते")
ANS = {"full_name": "Mera naam raam sharma hai.", "loan_type": "Chalary.", "loan_amount": "Do laakh ka.", "loan_purpose": "Business ke lie.", "employment": "Main business karta hoon.", "monthly_income": "2 lakhs.",
       "work_tenure": "Chaar saal.", "city": "Jaipur.", "existing_loans": "Nahin.", "phone": "9192428642.", "phone_confirm": "Yah sahi number hai.", "consent": "Kar sakti hai.", "callback_time": "Aaj karva doon raat ko."}
for _ in range(20):
    a = c.flow.asked
    if a is None:
        break
    c.reply(ANS[a])
# "Main business karta hoon" is an answer: no extra eligibility speech is allowed -> checked in a fresh call below
CHECKS = [("Mujhe kuchh aur bhi poochhana hai aapse.", "बताइए", ["नोट हो गई"]),
          ("Ab kya karna hai?", "कुछ करने की ज़रूरत नहीं", ["आराम से सोचिए"]),
          ("Aapka naam kya hai?", "मेरा नाम रिया", ["दो मिनट"]),
          ("Aap baat karo na mere se aap.", "बताइए", ["नोट करना और"]),
          ("India ka AUM kitna hai?", "एक हज़ार आठ सौ तैंतालीस", ["चौबीस"]),
          ("Aur employees kitne hain lakshymi India ke andar?", "दो हज़ार एक सौ", ["एयूएम"]),
          ("Kitne customers hain aapke?", "चालीस हज़ार", []),
          ("Aap vah kitna time ho gaya lakshyap India mein kaam karte hue?", "एआई असिस्टेंट", ["नोट हो गई"]),
          ("Aaj kaun sa saal chal raha hai?", str(datetime.date.today().year) and "दो हज़ार", []),
          ("Aaj kya date hai?", "आज", []),
          ("Aapki kitni branch hain?", "दो सौ ग्यारह", ["दो सौ नौ"])]
bad = 0
for q, must, mustnot in CHECKS:
    a = c.reply(q)
    ok = must in a and not any(m in a for m in mustnot)
    bad += not ok
    print("ok  " if ok else "FAIL", q, "->", a[:170].replace("\n", " "))
# business answer must not trigger an eligibility lecture
c2 = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c2.start_with("नमस्ते")
for t in ["Mera naam raam sharma hai.", "Personal loan", "Do laakh ka.", "Business ke lie."]:
    c2.reply(t)
a = c2.reply("Main business karta hoon.")
ok = "उम्र इक्कीस" not in a
bad += not ok
print("ok  " if ok else "FAIL", "Main business karta hoon. ->", a[:150])
print("CHAT REPLAY 2: ALL OK" if not bad else f"CHAT REPLAY 2: {bad} FAILED")
sys.exit(1 if bad else 0)
