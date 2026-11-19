"""Checks that new wordings (not copied from the bank) reach the right reply: python train/test_replybank.py"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import replybank

CASES = [   # (what the caller says, ids that must all be found; [] means nothing should match)
    ("aap kaun bol rahe ho", ["who_are_you"]),
    ("मेरा नंबर आपको कहाँ से मिला", ["number_source"]),
    ("main abhi kaam pe hoon baad me phone karo", ["busy_callback"]),
    ("मुझे लोन नहीं चाहिए", ["not_interested"]),
    ("mujhe loan chahiye", ["how_apply"]),
    ("dobara phone mat karna", ["stop_calling"]),
    ("kya aap robot ho", ["are_you_robot"]),
    ("interest rate kitna rahega", ["interest_rate"]),
    ("इंटरेस्ट कितना लगेगा", ["interest_rate"]),
    ("processing fees kitni lagti hai", ["processing_fee"]),
    ("kaun kaun se documents chahiye", ["documents"]),
    ("डॉक्यूमेंट क्या क्या लगेंगे", ["documents"]),
    ("meri salary 12000 hai kya mujhe loan milega", ["low_salary"]),
    ("mera cibil score kharab hai", ["low_cibil"]),
    ("paisa kitne din me aa jayega", ["disbursal_time"]),
    ("payday loan ke baare me batao", ["payday_loan"]),
    ("पेडे लोन क्या होता है", ["payday_loan"]),
    ("salary advance mil sakta hai", ["salary_loan"]),
    ("late fee kitni lagti hai", ["late_fee"]),
    ("लेट फ़ीस माफ़ कर दो", ["late_fee"]),
    ("mera emi bounce ho gaya charge kyun laga", ["late_fee"]),
    ("kitna overdue hai mera", ["overdue_collections"]),
    ("abhi paise nahi hain kuch din ruk jao", ["hardship"]),
    ("mujhe naukri se nikal diya", ["hardship"]),
    ("main otp bata deta hoon", ["otp_safety"]),
    ("complaint kaise karun", ["complaint"]),
    ("tum log mujhe dhamki de rahe ho", ["harassment"]),
    ("maine ye loan liya hi nahi", ["dispute_loan"]),
    ("mere loan ka status kya hai", ["status_check"]),
    ("toll free number batao", ["office_info"]),
    ("आप कितने बजे तक खुले रहते हो", ["office_info"]),
    ("hello hello awaaz nahi aa rahi", ["not_heard"]),
    ("main soch ke batata hoon", ["think_about_it"]),
    ("whatsapp pe details bhej do", ["whatsapp_sms"]),
    ("interest kitna hai aur documents kya lagenge", ["interest_rate", "documents"]),
    ("processing fee kitni hai aur kitne din me paisa milega", ["processing_fee", "disbursal_time"]),
    ("abhi paise nahi hain, late fee bhi zyada laga hai", ["hardship", "late_fee"]),
    ("aaj mausam kaisa hai", ["off_topic"]),
    ("company ke baare mein batao", ["company_about"]),
    ("civil score kya hota hai", ["what_is_cibil"]),
    ("kitna cibil score chahiye", ["cibil_required"]),
    ("emi kya hota hai", ["what_is_emi"]),
    ("mujhe kuch aur baat karni hai", ["more_to_discuss"]),
    ("aap kaise ho", ["small_talk"]),
    ("interest bahut zyada hai", ["rate_too_high"]),
    ("meri salary kyun poochh rahe ho", ["details_why"]),
    ("office ka pata batao", ["office_address"]),
    ("sun raha hoon thik hai", []),
]

ok = 0
for text, want in CASES:
    got = [m["id"] for m in replybank.match(text)]
    good = all(w in got for w in want) and (bool(want) or not got)
    ok += good
    if not good:
        print("FAIL", repr(text), "wanted", want, "got", [(m["id"], m["score"]) for m in replybank.match(text)])
print(f"{ok}/{len(CASES)} pass")
sys.exit(0 if ok == len(CASES) else 1)
