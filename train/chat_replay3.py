"""Third live chat (Gaurav, 21 Nov): misheard "Salary", "personal kaam se", city spelling, one 'about me' answer.   python train/chat_replay3.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain, stt

bad = 0
def check(name, ok, info=""):
    global bad
    bad += not ok
    print("ok  " if ok else "FAIL", name, info[:150].replace("\n", " "))

for word in ["Saturday donon.", "Chalie.", "Chalary.", "Salari."]:
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None); c.start_with("नमस्ते")
    c.reply("Mera naam gaurav hai."); a = c.reply(word)
    check(f"loan type from {word!r}", c.flow.v.get("loan_type") == "salary", a)
c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None); c.start_with("नमस्ते")
for t in ["Mera naam gaurav hai.", "Chalary.", "Ek laakh ka."]:
    c.reply(t)
a = c.reply("Personal kaam se.")
check("purpose 'Personal kaam se'", "loan_purpose" in c.flow.v, a)
for city_said, want in [("Jaypur.", "Jaipur"), ("Ahmadaabaad.", "Ahmedabad"), ("Dilli.", "Delhi"), ("Udaypur.", "Udaipur")]:
    check(f"city spelling {city_said!r}", want in stt.fix_terms(city_said), stt.fix_terms(city_said))
c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None); c.start_with("नमस्ते")
ANS = {"full_name": "Mera naam gaurav hai.", "loan_type": "Chalary.", "loan_amount": "Ek laakh ka.", "loan_purpose": "Personal news.", "employment": "Business hai.", "monthly_income": "Pachaas hazaar.",
       "work_tenure": "Aath saal.", "city": "Jaipur.", "existing_loans": "Nahin.", "phone": "9198282737.", "phone_confirm": "Haan, yah sahi hai.", "consent": "Kar sakti hai.", "callback_time": "Jab aapka man karen."}
for _ in range(20):
    if c.flow.asked is None:
        break
    c.reply(ANS[c.flow.asked])
a = c.reply("Aapka naam kya hai? Kya varg hai aapka?")
check("one 'about me' answer", a.count("एआई असिस्टेंट") <= 1 and "मेरा नाम रिया" in a, a)
print("CHAT REPLAY 3: ALL OK" if not bad else f"CHAT REPLAY 3: {bad} FAILED")
sys.exit(1 if bad else 0)
