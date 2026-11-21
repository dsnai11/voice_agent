"""Simulated customers: hundreds of random callers with KNOWN facts answer Ria's questions in varied Hinglish, with listener-style mistakes added
(garbled spellings, fragments, repeats). Afterwards every fact she saved is compared with the truth, so the weak spots show up as numbers.

    python train/stress_test.py [number_of_calls] [seed]        (default 200 calls, seed 1)
Shows the accuracy of each fact, the share of calls that finished, and a list of the worst failures to learn from.
"""
import os
import random
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)

HI_NUM = {1: "ek", 2: "do", 3: "teen", 4: "chaar", 5: "paanch", 10: "das"}
NAMES = ["Arjun Sharma", "Priya Verma", "Rohan Singh", "Sunita Gupta", "Amit Kumar", "Neha Patel", "Rahul Yadav", "Pooja Joshi", "Suresh Meena", "Kavita Jain", "Vikram Chauhan", "Anjali Mishra"]
CITIES = ["Jaipur", "Delhi", "Mumbai", "Pune", "Udaipur", "Kota", "Indore", "Lucknow", "Bhopal", "Jodhpur", "Ajmer", "Surat"]
AMOUNTS = {50000: ["50000", "pachas hazaar", "50 hazaar", "pachaas hazaar ka loan", "fifty thousand"], 100000: ["1 lakh", "ek lakh", "1 lakh rupaye", "ek laakh ka"],
           200000: ["2 lakh", "do lakh", "do laakh ka loan chahiye", "200000"], 300000: ["teen lakh", "3 lakh", "3 laakh rupe"], 500000: ["5 lakh", "paanch lakh", "paanch laakh rupe", "500000", "5,00,000"],
           150000: ["dedh lakh", "1.5 lakh", "150000", "one and a half lakh"]}
AMOUNTS[50000] += ["around 50000", "approximately fifty thousand rupees"]
AMOUNTS[100000] += ["one lakh", "1 lac"]
AMOUNTS[200000] += ["two lakh", "around 2 lakh rupees", "do lakh rupaye chahiye"]
AMOUNTS[300000] += ["three lakh", "teen lakh rupaye ka"]
AMOUNTS[500000] += ["five lakh", "around five lakh", "5 lakh ke aaspaas"]
INCOMES = {25000: ["25000", "25 hazaar", "pachees hazaar", "25k"], 40000: ["40000", "40 hazaar", "chalis hazaar"], 60000: ["60000", "60 hazaar", "saath hazaar"], 100000: ["1 lakh", "ek lakh", "100000"],
           15000: ["15000", "15 hazaar", "pandrah hazaar"]}
INCOMES[25000] += ["twenty five thousand", "around 25000", "25 hazaar ke aaspaas"]
INCOMES[40000] += ["forty thousand", "40 hazaar approximately"]
INCOMES[60000] += ["sixty thousand", "60 hazar mahina"]
INCOMES[100000] += ["one lakh", "ek lakh ke around"]
LOAN = {"personal": ["personal loan", "personal", "mujhe personal loan chahiye", "parsanal loan"], "payday": ["payday loan", "pe day loan", "payday", "pede loan chahiye", "PD loan"],
        "salary": ["salary loan", "salary", "saalari", "salary advance chahiye", "mujhe salary loan chaahie"]}
PURPOSE = {"medical": ["medical", "ilaj ke liye", "hospital ka kharcha", "medical emergency"], "wedding": ["shaadi ke liye", "wedding", "shadi", "meri shaadi hai"],
           "business": ["business ke liye", "dhandha", "dukaan ke liye"], "home repair": ["ghar ki repair", "ghar ki marammat", "renovation"], "education": ["padhai ke liye", "bachon ki fees", "education"]}
EMPLOY = {"salaried": ["job", "naukri", "main job karta hoon", "private naukri", "salaried", "service karta hoon", "company mein kaam karta hoon"],
          "self-employed": ["business", "apna business", "main business karta hoon", "dukaan hai meri", "self employed", "dhandha karta hoon"],
          "pensioner": ["pension aati hai", "main retired hoon", "pensioner"], "not-earning": ["housewife hoon", "student hoon", "abhi kuch nahi karta"]}
TIME = ["kal subah 10 baje", "abhi", "aadhe ghante baad", "kal shaam", "parso dopahar 2 baje", "aaj shaam 5 baje"]
QUESTIONS = ["interest kitna lagega", "documents kya lagenge", "CIBIL score kya hota hai", "processing fee kitni hai", "company ke baare mein batao", "loan kitne din me milega", "NACH kya hota hai", "emi kya hota hai",
             "office kahan hai", "kya ye safe hai", "guarantor chahiye kya", "aap kaise ho"]
ASR_SWAPS = [("chahiye", ["chaahie", "chahie", "chaiye"]), ("nahi", ["nahin", "nhi"]), ("lakh", ["laakh", "lac"]), ("hazaar", ["hazar", "hajar"]), ("saal", ["sal"]), ("mein", ["me", "main"]), ("hai", ["he", "hain"]),
             ("karta", ["karata"]), ("loan", ["lone"])]


MISSPELL = {"Jaipur": ["Jaypur", "Jaipur", "Jaipure"], "Udaipur": ["Udaypur", "Udyapur"], "Lucknow": ["Lakhnau", "Luknow"], "Indore": ["Indor"], "Bhopal": ["Bhopaal"], "Mumbai": ["Bombay", "Mumbay"], "Jodhpur": ["Jodhapur"], "Delhi": ["Dilli", "Delhi"]}


def noisy(text: str, p: float = 0.5) -> str:
    """What the listener might write: swapped spellings, a leading fragment, a repeat, a full stop."""
    if rng.random() > p:
        return text
    for word, alts in ASR_SWAPS:
        if word in text and rng.random() < 0.6:
            text = text.replace(word, rng.choice(alts), 1)
    if rng.random() < 0.25:
        text = rng.choice(["Mujhe. ", "Haan. ", "Main. ", "Wo. "]) + text
    if rng.random() < 0.15 and len(text.split()) <= 3:
        text = text + " " + text
    return text + ("." if rng.random() < 0.6 else "")


def phone_forms(number: str):
    digits = " ".join(number)
    words = {"0": "shunya", "1": "ek", "2": "do", "3": "teen", "4": "chaar", "5": "paanch", "6": "chhe", "7": "saat", "8": "aath", "9": "nau"}
    return [number, f"{number[:5]} {number[5:]}", digits, " ".join(words[d] for d in number)]


def new_customer():
    et = rng.choices(list(EMPLOY), weights=[50, 30, 10, 10])[0]
    t = {"name": rng.choice(NAMES), "loan_type": rng.choice(list(LOAN)), "amount": rng.choice(list(AMOUNTS)), "purpose": rng.choice(list(PURPOSE)), "employment": et,
         "income": rng.choice(list(INCOMES)), "years": rng.choice([1, 2, 3, 5, 10]), "city": rng.choice(CITIES), "loans": rng.choice(["yes", "no", "no"]), "emi": rng.choice([3000, 5000, 8000]),
         "phone": rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9)), "time": rng.choice(TIME)}
    return t


def answer(slot: str, t: dict):
    """What this customer says to the question about `slot`, or None if the question should not be asked."""
    if slot == "full_name":
        return rng.choice([f"Mera naam {t['name']} hai", t["name"], f"main {t['name']} bol raha hoon", f"naam {t['name']} hai"])
    if slot == "loan_type":
        return noisy(rng.choice(LOAN[t["loan_type"]]))
    if slot in ("loan_amount", "amount_confirm"):
        return noisy(rng.choice(AMOUNTS[t["amount"]])) if slot == "loan_amount" else "haan sahi hai"
    if slot == "loan_purpose":
        return noisy(rng.choice(PURPOSE[t["purpose"]]))
    if slot == "employment":
        return noisy(rng.choice(EMPLOY[t["employment"]]))
    if slot == "monthly_income":
        v = rng.choice(INCOMES[t["income"]])
        return noisy(rng.choice([v, f"meri {v} hai", f"mahine ka {v}", f"lagbhag {v}"]))
    if slot == "work_tenure":
        n = t["years"]
        return noisy(rng.choice([f"{n} saal", f"{n} years", f"{HI_NUM.get(n, n)} saal se", f"{n} saal ho gaye"]))
    if slot == "city":
        c = rng.choice(MISSPELL.get(t["city"], [t["city"]]))
        return noisy(rng.choice([c, f"{c} mein", f"main {c} se hoon", f"{c} {c}"]))
    if slot == "existing_loans":
        return noisy(rng.choice(["haan", "haan hai", "ek chal raha hai", "yes"] if t["loans"] == "yes" else ["nahi", "nahin", "koi nahi", "no", "koi loan nahi hai"]))
    if slot == "existing_emi":
        return noisy(rng.choice([str(t["emi"]), f"{t['emi']} ki emi", f"{t['emi'] // 1000} hazaar"]))
    if slot in ("phone",):
        return rng.choice(phone_forms(t["phone"]))
    if slot == "phone_confirm":
        return rng.choice(["haan sahi hai", "haan", "yes", "ji sahi hai"])
    if slot == "consent":
        return rng.choice(["haan", "haan kar sakte hain", "ok", "theek hai", "yes"])
    if slot == "callback_time":
        return noisy(t["time"])
    return None


def years_of(text):
    m = re.match(r"([0-9.]+) (years|months)", str(text or ""))
    return None if not m else (float(m.group(1)) if m.group(2) == "years" else float(m.group(1)) / 12)


stats, fails, finished, turns_total, unclear_total = defaultdict(lambda: [0, 0]), [], 0, 0, 0
for n in range(N):
    t = new_customer()
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    said = []
    distract = rng.random() < 0.3
    for turn in range(45):
        asked = c.flow.asked
        if c.flow.done or c.finished:
            break
        if distract and turn in (3, 7):
            q = rng.choice(QUESTIONS)
            said.append(q)
            reply = c.reply(q)
            unclear_total += ("समझ नहीं पाई" in reply or "समझ नहीं आया" in reply)
            continue
        text = answer(asked, t) if asked else None
        if text is None:
            break
        said.append(f"[{asked}] {text}")
        reply = c.reply(text)
        turns_total += 1
        unclear_total += ("समझ नहीं पाई" in reply or "समझ नहीं आया" in reply)
    form, d = c.form, c.form.get("details") or {}
    et = t["employment"]
    expect = {"name": (form.get("full_name", "").lower(), t["name"].lower()), "loan_type": (d.get("loan_type"), t["loan_type"]), "amount": (d.get("loan_amount"), str(t["amount"])),
              "purpose": (d.get("loan_purpose"), t["purpose"]), "employment": (d.get("employment_type"), et), "income": (d.get("monthly_income"), str(t["income"])), "city": (d.get("city"), t["city"]),
              "existing_loans": (d.get("existing_loans"), t["loans"]), "phone": (form.get("phone"), t["phone"]), "consent": (form.get("consent_to_contact"), "yes")}
    if et in ("salaried", "self-employed"):
        expect["tenure"] = (years_of(d.get("business_vintage") or d.get("time_with_current_employer")), float(t["years"]))
    if t["loans"] == "yes":
        expect["emi"] = (d.get("existing_emi"), str(t["emi"]))
    bad = []
    for k, (got, want) in expect.items():
        ok = (abs(got - want) < 0.01) if isinstance(want, float) and got is not None else (got == want)
        stats[k][0] += ok
        stats[k][1] += 1
        if not ok:
            bad.append(f"{k}: got {got!r}, wanted {want!r}")
    stats["callback_time saved"][0] += bool(form.get("preferred_callback_time"))
    stats["callback_time saved"][1] += 1
    finished += bool(c.flow.done)
    if bad or not c.flow.done:
        fails.append((n, t, bad, said))

print(f"\n{N} simulated customers, {turns_total} answers, {unclear_total} times she said 'did not understand'\n")
print(f"calls that reached the end of the form: {finished}/{N} ({100 * finished / N:.0f}%)\n")
for k, (ok, tot) in sorted(stats.items(), key=lambda kv: kv[1][0] / max(kv[1][1], 1)):
    print(f"  {k:20s} {ok:4d}/{tot:<4d} {100 * ok / max(tot, 1):5.1f}%")
by_kind = Counter(b.split(":")[0] for _, _, bad, _ in fails for b in bad)
print("\nmost common failures:", dict(by_kind.most_common(8)))
print(f"\n{len(fails)} imperfect calls. First 12:")
for n, t, bad, said in fails[:12]:
    print(f"\n--- call {n}: {t['employment']}, {t['loan_type']}, {t['city']}")
    for b in bad:
        print("   ", b)
    print("    said:", " | ".join(said[:14]))
sys.exit(0)
