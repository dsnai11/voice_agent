"""Callers can ask a loan question at ANY step of the form (start, middle, end). Ria must answer it, keep what was already noted, and come back
to the pending question. "Ek minute ruko" makes her wait; thinking aloud ("hmm wo kya hai na") gets "boliye"; noise gets "samajh nahi aaya,
phir se boliye".   python train/interjection_test.py      (needs Ollama for the topic picker)
"""
import contextlib, io, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain, flow

ANS = {"full_name": "Mera naam Gaurav Sharma hai", "loan_type": "personal loan", "loan_amount": "do lakh", "loan_purpose": "shaadi ke liye", "employment": "job karta hoon",
       "monthly_income": "pachas hazaar", "work_tenure": "do saal", "city": "Jaipur", "existing_loans": "nahi", "existing_emi": "paanch hazaar", "phone": "9876543210",
       "phone_confirm": "haan sahi hai", "consent": "haan", "callback_time": "kal subah 10 baje"}
QUESTIONS = [("interest kitna lagega", "इंटरेस्ट"), ("documents kya kya chahiye", "प्रूफ"), ("aapka office kahan hai", "गोपीनाथ"), ("processing fee kitni hai", "प्रोसेसिंग"),
             ("kitne din mein paisa milega", "घंटे"), ("cibil kam hai to milega kya", "स्कोर")]
STEPS = ["full_name", "loan_type", "loan_amount", "loan_purpose", "employment", "monthly_income", "city", "existing_loans", "phone", "consent", "callback_time", None]
bad = 0


def check(ok, label, reply):
    global bad
    bad += not ok
    if not ok:
        print("FAIL", label, "->", reply[:160])


def at(step):
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(20):
            if c.flow.asked == step or c.flow.asked is None:
                break
            c.reply(ANS[c.flow.asked])
    return c


def say(c, text):
    with contextlib.redirect_stdout(io.StringIO()):
        return c.reply(text)


n = 0
for step in STEPS:
    for q, must in QUESTIONS:
        c = at(step)
        before, asked = dict(c.flow.v), c.flow.asked
        a = say(c, q)
        n += 1
        check(must in a, f"[{step}] {q!r}: answer missing '{must}'", a)
        check(c.flow.v == before, f"[{step}] {q!r}: something was saved from a question {set(c.flow.v.items()) ^ set(before.items())}", a)
        check(c.flow.asked == asked, f"[{step}] {q!r}: Ria moved on instead of coming back to the question", a)
    for text, line in (("ek minute ruko", flow.HOLD_LINE), ("hmm wo kya hai na", flow.LISTENING_LINE), ("umm matlab", flow.LISTENING_LINE)):
        c = at(step)
        before, asked = dict(c.flow.v), c.flow.asked
        a = say(c, text)
        n += 1
        check(a == line and c.flow.v == before and c.flow.asked == asked, f"[{step}] {text!r}", a)
# the same question twice: answered both times
c = at("loan_amount")
say(c, "interest kitna lagega")
a = say(c, "interest kitna lagega")
n += 1
check("इंटरेस्ट" in a, "the same question asked twice is answered again", a)
# not understood: ask to repeat, in the middle and at the end
for step in ("loan_type", "employment", "phone", None):
    c = at(step)
    a = say(c, "blah garbage xyz qwerty")
    n += 1
    check("समझ नहीं आया" in a and "फिर से" in a, f"[{step}] noise -> 'please say it again'", a)
c = at(None)
a1, a2 = say(c, "blah garbage xyz"), say(c, "qwerty asdf zxcv")
n += 1
check("समझ नहीं आया" in a1 and "समझ नहीं आया" in a2 and "नोट हो गई" not in a2, "after the form, two unclear turns: both ask to repeat", a2)
# short acknowledgements never become a name or a city
for step, text in (("full_name", "hmm"), ("full_name", "nahi"), ("city", "hmm"), ("city", "na")):
    c = at(step)
    say(c, text)
    n += 1
    check(step not in c.flow.v, f"[{step}] {text!r} must not be saved as {step}", str(c.flow.v.get(step)))
print(f"INTERJECTION TEST: {'ALL OK' if not bad else str(bad) + ' FAILED'} ({n} cases)")
sys.exit(1 if bad else 0)
