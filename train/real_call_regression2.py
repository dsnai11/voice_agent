"""Replays the SECOND real customer call (19 Nov 2026, businessman asking for a salary-type loan), word for word as the listener wrote it.

    python train/real_call_regression2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain
import stt

c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c.start_with("नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड की एआई असिस्टेंट। कृपया अपना पूरा नाम बताइए।")
bad = 0


def step(said, must=(), must_not=(), why=""):
    global bad
    reply = c.reply(said)
    fails = [f"missing {m!r}" for m in must if not any(alt in reply for alt in m.split("|"))] + [f"should not say {m!r}" for m in must_not if any(alt in reply for alt in m.split("|"))]
    print(("FAIL " if fails else "ok   ") + f"{said[:58]!r}\n       -> {reply[:120]}" + (f"\n       !! {why}: {'; '.join(fails)}" if fails else ""))
    bad += bool(fails)
    return reply


# the listener's "nan" for silence must never reach her
assert stt.fix_terms("nan") == "nan" and "nan" in stt._PHANTOM, "'nan' must be filtered as a phantom word"

step("Mera naam mistri hai.", ["धन्यवाद"], why="name")
step("Saalari", ["रकम|रुपये"], why="'saalari' (garbled 'salary') = salary loan")
step("Do karod ka.", ["सही"], why="2 crore is read back before it is trusted")
step("Nahin.", ["रकम"], why="a wrong amount is dropped and asked again")
step("Do laakh ka.", ["किस"], why="2 lakh, then the purpose")
step("Dhandha dhandha karoonga dhandha.", ["बिज़नेस"], ["कमाई|इनकम"], why="a business plan is not his job: the job is still asked")
assert c.flow.v.get("loan_purpose") == "business", c.flow.v.get("loan_purpose")
assert "employment" not in c.flow.v, "his job must not be guessed from the purpose"
step("Main business karta hoon.", ["कमाई|इनकम"], ["सैलरी"], why="businessman: income, not salary")
step("Do laakh rupe.", ["कितने साल"], why="business age")
step("Do saal.", ["शहर"], why="then the city")
step("Jaypur, jaypur, jaypur.", ["लोन|ईएमआई"], ["कितनी"], why="existing loans question")
step("Mitra.", ["लोन|ईएमआई"], ["कितनी"], why="garbage is not an answer")
step("Chal raha koi loan.", ["लोन|ईएमआई"], ["कितनी"], why="'koi loan' is ambiguous: ask again, never assume yes")
step("Mera koi loan nahin chal raha hai abhi.", ["मोबाइल"], ["कॉलबैक"], why="a clear 'no loan' goes straight on to the phone number")
assert c.flow.v.get("existing_loans") == "no"
step("9 828273712.", ["9828273712"])
step("Haan, yah sahi hai.", ["कॉल"], why="consent question")
step("Thik hai, aap mere ko kal call karna.", ["कल", "और कुछ पूछना"], why="'call me tomorrow' is understood as consent and time")
form = c.form
assert form.get("consent_to_contact") == "yes", form.get("consent_to_contact")

# a loan that was wrongly marked "yes" is corrected, and "0 0" means no EMI
c2 = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c2.start_with("नमस्ते")
for t in ["Arjun Sharma", "Personal loan", "5 lakh", "medical", "job", "50000", "2 saal", "Jaipur", "haan"]:
    c2.reply(t)
r = c2.reply("0 0.")
print(("ok   " if "मोबाइल" in r else "FAIL ") + f"'0 0.' (no EMI)\n       -> {r[:100]}")
bad += "मोबाइल" not in r
assert c2.flow.v.get("existing_loans") == "no"
c3 = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c3.start_with("नमस्ते")
for t in ["Arjun Sharma", "Personal loan", "5 lakh", "medical", "job", "50000", "2 saal", "Jaipur", "haan"]:
    c3.reply(t)
r = c3.reply("Thik hai, kal subah call karna.")
print(("ok   " if "कल सुबह" in r else "FAIL ") + f"'kal subah call karna' in the middle of the form\n       -> {r[:110]}")
bad += "कल सुबह" not in r
print("\nSECOND REAL-CALL REGRESSION: ALL OK" if not bad else f"\n{bad} STEP(S) FAILED")
sys.exit(1 if bad else 0)
