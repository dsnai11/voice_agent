"""Short and full answers for every question the flow asks."""
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

# (slot being asked, how to reach it, answers that must all be understood, expected form key/detail and value test)
BASE = ["Mera naam Arjun Sharma hai"]
FLOWS = {
    "loan_type": ([], ["payday", "Pede", "pay day loan", "salary", "salary loan", "personal", "personal loan chahiye", "mujhe payday loan chahiye", "pe day", "advance salary"], ("loan_type", lambda v: v in ("payday", "salary", "personal"))),
    "loan_amount": (["Personal loan"], ["5 lakh", "paanch lakh", "500000", "5,00,000", "50 hazaar", "50000", "pachas hazaar", "50k", "dhai lakh", "mujhe paanch lakh chahiye", "ek lakh", "1.5 lakh", "2 lakh rupaye"], ("loan_amount", lambda v: str(v).isdigit() and int(v) >= 10000)),
    "loan_purpose": (["Personal loan", "5 lakh"], ["medical", "shaadi ke liye", "ghar ki repair", "bachon ki padhai", "hospital ka kharcha", "business ke liye", "emergency", "travel"], ("loan_purpose", lambda v: bool(v))),
    "employment": (["Personal loan", "5 lakh", "medical"], ["job", "naukri", "salaried", "service", "private job", "business", "self employed", "apna business", "dukaan", "main job karta hoon", "sarkari naukri"], ("employment_type", lambda v: v in ("salaried", "self-employed"))),
    "monthly_income": (["Personal loan", "5 lakh", "medical", "job"], ["5000", "5,000", "5000 rupaye", "5 hazaar", "paanch hazaar", "50000", "50 hazaar", "pachas hazaar", "meri 5000 rupaye salary hai", "25k", "1 lakh", "30 hazar", "40000 rupees", "do lakh"], ("monthly_income", lambda v: str(v).isdigit() and int(v) >= 1000)),
    "work_tenure": (["Personal loan", "5 lakh", "medical", "job", "50000"], ["2 saal", "do saal", "6 mahine", "5 years", "dedh saal", "teen saal se", "10 saal", "1 saal", "mujhe 4 saal ho gaye"], ("time_with_current_employer", lambda v: bool(v))),
    "city": (["Personal loan", "5 lakh", "medical", "job", "50000", "2 saal"], ["Jaipur", "jaipur mein", "main Jaipur se hoon", "Delhi", "Udaipur", "Bhopal", "Kota", "Sikar", "Jodhpur", "Pune"], ("city", lambda v: bool(v))),
    "existing_loans": (["Personal loan", "5 lakh", "medical", "job", "50000", "2 saal", "Jaipur"], ["nahi", "nahin", "koi nahi", "no", "haan", "haan hai", "ek chal raha hai", "ji haan", "bilkul nahi"], ("existing_loans", lambda v: v in ("yes", "no"))),
    "existing_emi": (["Personal loan", "5 lakh", "medical", "job", "50000", "2 saal", "Jaipur", "haan"], ["5000", "5,000 rupaye", "paanch hazaar", "8000", "2 hazaar", "3500", "meri 6000 ki emi jaati hai", "10 hazaar", "1500"], ("existing_emi", lambda v: str(v).isdigit() and int(v) >= 500)),
}


def run():
    bad = total = 0
    for slot, (pre, answers, (key, ok)) in FLOWS.items():
        for ans in answers:
            c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
            c.start_with("नमस्ते")
            for t in BASE + pre:
                c.reply(t)
            asked_before = c.flow.asked
            out = c.reply(ans)
            val = (c.form.get("details") or {}).get(key) or c.form.get(key)
            good = bool(val) and ok(val)
            total += 1
            bad += not good
            if not good:
                print(f"FAIL [{slot}] {ans!r}: asked={asked_before} got {key}={val!r} reply={out[:70]!r}")
    print(f"{total - bad}/{total} short and full answers understood")


run()

