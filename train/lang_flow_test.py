"""Whole calls in English, Gujarati and Marwari / Rajasthani village speech: the form must fill correctly, every reply must be in the caller's language and script,
questions must be answered at any step, and "speak in X" must switch language.   python train/lang_flow_test.py   (needs Ollama)"""
import contextlib, io, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

DEV, GU, LAT = re.compile(r"[ऀ-ॿ]"), re.compile(r"[઀-૿]"), re.compile(r"[A-Za-z]")
SCRIPTS = {
    "en": dict(turns=["My name is Rahul Mehta", "I need a personal loan", "two lakh rupees", "for my sister's wedding", "I am salaried, I do a job", "fifty thousand a month", "three years", "Jaipur", "no other loan",
                      "9876543210", "yes that is correct", "yes you can call", "tomorrow morning at 10"],
               want=dict(full_name="Rahul Mehta", loan_type="personal", loan_amount=200000, loan_purpose="wedding", employment="salaried", monthly_income=50000, city="Jaipur", existing_loans="no", phone="9876543210", consent="yes"),
               questions=[("What is the interest rate?", "interest"), ("Which documents do I need?", "ID proof"), ("where is your office", "Gopinath"), ("how many branches do you have", "eleven branches")],
               script=lambda t: bool(LAT.search(t)) and not DEV.search(t) and not GU.search(t)),
    "gu": dict(turns=["maru naam rahul mehta chhe", "mane personal loan joiye chhe", "be lakh rupiya", "lagn mate", "hu nokri karu chhu", "mari pagar pachas hajar chhe", "tran varsh thi", "ahmedabad", "bija koi loan nathi",
                      "9876543210", "ha barabar chhe", "ha tame call kari shako", "kale savare dasa vagye"],
               want=dict(full_name="Rahul Mehta", loan_type="personal", loan_amount=200000, loan_purpose="wedding", employment="salaried", monthly_income=50000, city="Ahmedabad", existing_loans="no", phone="9876543210", consent="yes"),
               questions=[("vyaj dar ketlo chhe", "વ્યાજ"), ("kya kya documents joiye", "આઈડી"), ("tamari office kya chhe", "ગોપીનાથ"), ("tamari kitli branch chhe", "બસો અગિયાર")],
               script=lambda t: bool(GU.search(t)) and not DEV.search(t)),
    "mwr": dict(turns=["mharo naam rahul mehta hai", "mhane personal loan chaije", "do lakh rupya", "ghar ri marammat sarun", "mhe naukri karu hu", "mhari tankhwa pachaas hajar hai", "teen saal su", "jodhpur", "dujo koi loan kono",
                       "9876543210", "ha sahi hai", "ha sa call kar sako", "kaal savere das baje"],
                want=dict(full_name="Rahul Mehta", loan_type="personal", loan_amount=200000, loan_purpose="home repair", employment="salaried", monthly_income=50000, city="Jodhpur", existing_loans="no", phone="9876543210", consent="yes"),
                questions=[("byaj kito lagsi", "ब्याज"), ("kai kai kagad chaije", "आईडी"), ("thaaro office kathe hai", "गोपीनाथ"), ("thari kitti branch hai", "दो सौ ग्यारह")],
                script=lambda t: bool(DEV.search(t)) and not GU.search(t)),
}


def new():
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    return c


def say(c, t):
    with contextlib.redirect_stdout(io.StringIO()):
        return c.reply(t)


bad = 0
n = 0


def check(ok, label, info=""):
    global bad, n
    n += 1
    if not ok:
        bad += 1
        print("FAIL", label, "->", str(info)[:170].replace("\n", " "))


for lg, sc in SCRIPTS.items():
    c = new()
    replies = []
    for t in sc["turns"]:
        replies.append(say(c, t))
    for k, v in sc["want"].items():
        check(c.flow.v.get(k) == v, f"[{lg}] form field {k}", f"got {c.flow.v.get(k)!r} want {v!r}")
    check(c.flow.lang == lg, f"[{lg}] call language", c.flow.lang)
    for i, r in enumerate(replies):
        stray = [x for x in re.split(r"(?<=[।?!.])\s+", r) if DEV.search(x) and lg == "en"] if lg == "en" else []
        check(sc["script"](r) or not r, f"[{lg}] reply {i + 1} is in the caller's language", r)
    for q, must in sc["questions"]:
        c2 = new()
        for t in sc["turns"][:5]:                                                      # in the middle of the form
            say(c2, t)
        asked, before = c2.flow.asked, dict(c2.flow.v)
        a = say(c2, q)
        check(must in a, f"[{lg}] question {q!r} answered", a)
        check(c2.flow.v == before and c2.flow.asked == asked, f"[{lg}] question {q!r} changed the form", a)
        check(sc["script"](a), f"[{lg}] answer to {q!r} in the right script", a)
# switching on request, from any language to any language
for ask, want in (("English mein baat karo", "en"), ("gujarati ma vaat karo", "gu"), ("marwadi mein bolo", "mwr"), ("rajasthani boli mein baat karo", "mwr"), ("can you speak in english", "en")):
    c = new()
    say(c, "Mera naam Raj Shah hai")
    a = say(c, ask)
    check(c.flow.lang == want, f"switch '{ask}'", f"{c.flow.lang}: {a}")
c = new()
say(c, "English please, can you speak English")
a = say(c, "Hello")
check(c.flow.lang == "en" and a.startswith("Hello") or "name" in a.lower(), "greeting after switching to English", a)
a = say(new(), "hello")
check("नमस्ते" in a and "नाम" in a, "Hindi greeting at the name step", a)
# a language change by the caller themselves, and back
c = new()
say(c, "mera naam raj hai")
say(c, "mane personal loan joiye chhe")
check(c.flow.lang == "gu", "caller moves to Gujarati by themselves", c.flow.lang)
say(c, "mujhe do lakh ka loan chahiye aur kitna interest lagega")
check(c.flow.lang == "hi", "caller moves back to Hindi", c.flow.lang)
print(f"LANGUAGE FLOW TEST: {'ALL OK' if not bad else str(bad) + ' FAILED'} ({n} checks)")
sys.exit(1 if bad else 0)
