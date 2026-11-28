"""Checks the demo top-up sales conversation: python train/test_sales_topup.py (no servers needed)."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sales_topup

CASES = [   # (what the customer says, turn by turn; expected outcome)
    (["Haan ji bol raha hoon", "Haan chahiye", "Do lakh", "Ghar ki marammat ke liye", "Dukaan hai, mahine ka pachees hazaar", "Kal shaam ko paanch baje"], "topup_interest"),
    (["Haan", "Haan ji", "Teen lakh", "Business ke liye", "Naukri karta hoon bees hazaar salary", "Baad mein call karna shaam ko"], "topup_interest"),
    (["Haan", "Do lakh chahiye", "Shaadi ke liye", "Computer ki dukaan hai tees hazaar", "Kal"], "topup_interest"),
    (["Haan", "Byaaj kitna lagega", "Haan chahiye", "Kitna milega", "Do lakh", "Gaadi lene ke liye", "Kheti karta hoon", "Somvaar ko"], "topup_interest"),
    (["Haan", "Nahi"], "not_interested"),
    (["Haan", "Abhi zaroorat nahi hai"], "not_interested"),
    (["Haan", "Haan", "Nahi chahiye rehne do"], "not_interested"),
    (["Haan", "Haan chahiye", "Mujhe call mat karo"], "stop_calling"),
    (["Haan", "Main abhi busy hoon", "Kal subah"], "callback"),
    (["Haan", "Maine koi loan nahi liya"], "dispute"),
    (["Nahi, galat number hai"], "wrong_person"),
    (["Woh ghar pe nahi hain", "Shaam ko"], "not_available"),
    (["Haan", "Hmm", "Hmm", "Hmm", "Hmm"], "team_followup"),
]
bad = 0
for turns, want in CASES:
    call = sales_topup.TopUpCall(sales_topup.customer("vijay"))
    call.opening()
    for t in turns:
        if call.finished:
            break
        call.reply(t)
    ok = call.outcome == want and call.finished
    bad += not ok
    print(("ok  " if ok else "BAD ") + " | ".join(turns) + f"  -> {call.outcome} (wanted {want})")

# the running loan is mentioned only to the confirmed customer
for first in ["Aap kaun bol rahe ho", "Kya kaam hai", "Nahi", "Galat number", "Woh ghar pe nahi hain", "Hmm", "Ji aap kaun", "Haan main uska bhai bol raha hoon", "Kya aap robot ho"]:
    call = sales_topup.TopUpCall(sales_topup.customer("vijay"))
    text = call.opening() + " " + call.reply(first)
    leak = "लोन चल रहा" in text or "टॉप-अप" in text
    bad += leak
    print(("BAD " if leak else "ok  ") + f"no loan detail after {first!r}")
call = sales_topup.TopUpCall(sales_topup.customer("vijay"))
call.reply("Haan")
ok = call.reply("Byaaj kitna lagega") == call.say["team_offer"] and not call.finished
bad += not ok
print(("ok  " if ok else "BAD ") + "a question is left to the team and the open question is asked again")
spoken = " ".join(t for c in sales_topup.customers() for t in sales_topup.lines(c).values())
ok = not any(w in spoken for w in ("एआई", "AI ", "गारंटी", "पक्का मिलेगा", "किस्त"))
bad += not ok
print(("ok  " if ok else "BAD ") + "no 'AI', no promise, no collection wording in the sales call")
print("SALES TOP-UP TEST: ALL OK" if not bad else f"SALES TOP-UP TEST: {bad} FAILED")
