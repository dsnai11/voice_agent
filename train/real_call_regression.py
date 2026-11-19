"""Replays a real customer call (19 Nov 2026), word for word as the listener wrote it, and checks that every problem found in it stays fixed.

    python train/real_call_regression.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c.start_with("नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड की एआई असिस्टेंट। कृपया अपना पूरा नाम बताइए।")
bad = 0


def step(said, must=(), must_not=(), why=""):
    global bad
    reply = c.reply(said)
    fails = [f"missing {m!r}" for m in must if not any(alt in reply for alt in m.split("|"))] + [f"should not say {m!r}" for m in must_not if m in reply]      # "a|b" = either wording
    print(("FAIL " if fails else "ok   ") + f"{said[:58]!r}\n       -> {reply[:120]}" + (f"\n       !! {why}: {'; '.join(fails)}" if fails else ""))
    bad += bool(fails)
    return reply


step("Mera naam raam sinh hai.", ["राम"], why="name heard as 'raam sinh'")
step("Mujhe. Salary loan chaahie.", ["रकम|रुपये"], why="loan type, then the amount")
step("Mujhe. Do laakh ka loan chaahie.", ["200000", "किस"], why="amount saved, then the purpose")
r = step("Mujhe. Meri shaadi ho giri chaahie.", ["बिज़नेस"], ["घंटे"], why="purpose = wedding, then job-or-business (not a 24-48 hour answer)")
assert c.flow.v.get("loan_purpose") == "wedding", c.flow.v.get("loan_purpose")
step("Main naukri karta hoon.", ["सैलरी"], why="a salaried person is asked about salary")
step("Paanch hazaar.", ["कंपनी"], why="then how long in the company")
step("Tin saal.", ["शहर"], ["समझ नहीं"], why="'tin saal' = 3 years must be understood")
step("Jaipur.")
step("Nahin.")
step("9 828273712.", ["9828273712"], why="the number is read back")
step("Haan, yah sahi hai.")
step("Haan, kar sakte ho.")
step("Abhi karva do instant.", ["अभी कॉल"], why="'right now' is a valid callback time")
print("--- after the form is done: the questions that went wrong")
step("Haan, mujhe aapse baat karni hai kuchh.", ["बताइए"])
step("Mujhe bank mein khaata khulvaana hai mera.", ["एनबीएफसी"], ["सरल"], why="she cannot open bank accounts, and must say so")
step("Mujhe ek naya loan aur chaahie iske oopar top up.", ["टॉप"], why="top-up loan")
step("Mujhe top up loan lena hai to uska process kya hoga?", ["टॉप"], why="top-up process")
step("Aapke office ka MD kaun hai?", ["पक्की जानकारी नहीं"], ["सिर्फ़ लोन से"], why="honest: she does not know")
step("Aapke office ka address kahaan par hai?", ["गोपीनाथ"], why="the address")
step("Aapke company mein abhi koi offer chal raha hai kya customers?", ["ऑफ़र"], ["नॉन-बैंकिंग"], why="offers, not the company introduction")
step("To mera abhi credit score kya hai? Yah batao?", ["नहीं देख सकती"], why="she cannot see his score")
step("Aapka rate of interest kya hai company ka?", ["प्रोफ़ाइल"], why="no rate is quoted")
step("Meri file clear kar doge aap.", ["वादा नहीं"], why="no promise")
step("Mujhe instant do laakh ka loan chaahie.", ["वादा नहीं"], ["लाख"], why="she must never invent an amount")
step("Customer helpline number chaahie.", ["टोल"], why="helpline number")
step("Thik hai call cut karo.", ["नोट हो गई"], why="the call ends")
assert c.finished, "the call should be finished"
print("\nREAL-CALL REGRESSION: ALL OK" if not bad else f"\n{bad} STEP(S) FAILED")
sys.exit(1 if bad else 0)
