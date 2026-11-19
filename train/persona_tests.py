"""Four kinds of callers go through the flow; the questions and answers must fit who they are.

    python train/persona_tests.py
A businessman must never be asked for a "salary"; a pensioner is asked about pension; a salaried person about salary and time in the company.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

START = ["Arjun Sharma", "Personal loan", "5 lakh", "medical"]
PERSONAS = {
    "salaried":      dict(says="job karta hoon",                       income_word="सैलरी", income_not=[],            tenure_word="कंपनी",  income="50000",  tenure="2 saal", doc_has="सैलरी स्लिप", doc_not=[]),
    "self-employed": dict(says="main apna business karta hoon",        income_word="इनकम",   income_not=["सैलरी"],     tenure_word="बिज़नेस", income="80 hazaar", tenure="5 saal", doc_has="आईटीआर", doc_not=["सैलरी स्लिप"]),
    "pensioner":     dict(says="main retired hoon pension aati hai",   income_word="पेंशन",  income_not=["सैलरी"],     tenure_word=None,      income="20000",  tenure=None,     doc_has="पेंशन", doc_not=["सैलरी स्लिप"]),
    "not-earning":   dict(says="housewife hoon",                       income_word="परिवार", income_not=["सैलरी"],     tenure_word=None,      income="40000",  tenure=None,     doc_has="को-एप्लिकेंट", doc_not=["सैलरी स्लिप"]),
}


def new_call():
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    return c


bad = 0
for kind, p in PERSONAS.items():
    c = new_call()
    for t in START:
        c.reply(t)
    q_income = c.reply(p["says"])                    # the reply to "what do you do" is the income question
    checks = [(p["income_word"] in q_income, f"income question mentions {p['income_word']!r}")]
    checks += [(w not in q_income, f"income question does not say {w!r}") for w in p["income_not"]]
    after_income = c.reply(p["income"])               # the next question: job tenure / business age, or the city
    if p["tenure_word"]:
        checks.append((p["tenure_word"] in after_income, f"then asks about {p['tenure_word']!r}"))
        c.reply(p["tenure"])
        checks.append((c.flow.v.get("work_tenure") is not None, "the time in job / business is saved"))
    else:
        checks.append(("शहर" in after_income, "no job-tenure question; goes on to the city"))
    docs = c.reply("kaun kaun se documents chahiye")
    checks.append((p["doc_has"] in docs, f"documents answer mentions {p['doc_has']!r}"))
    checks += [(w not in docs, f"documents answer does not say {w!r}") for w in p["doc_not"]]
    form = c.form.get("details") or {}
    checks.append((form.get("employment_type") == kind, f"saved as {kind}"))
    print(f"--- {kind}\n  income Q : {q_income}\n  next Q   : {after_income}\n  documents: {docs[:90]}...")
    for ok, what in checks:
        if not ok:
            bad += 1
            print("  FAIL:", what)
print("\nALL PERSONA CHECKS PASS" if not bad else f"\n{bad} CHECK(S) FAILED")
sys.exit(1 if bad else 0)
