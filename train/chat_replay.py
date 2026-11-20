"""Replays the 20 Nov live chat (Gaurav Sharma) and checks the problems found in it are fixed.   python train/chat_replay.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c.start_with("नमस्ते")
STEPS = ["Mera naam gaurav sharma hai.", "Mujhe personal loan chaahie.", "Mujhe ek laakh ka loan chaahie.", "College ki fees bhani hai.", "Job karta hoon.", "Pachaas hazaar.", "Do saal se.", "Ahmadaabaad.",
         "To koi EMI nahin chal rahi hai.", "9192827263.", "Yah sahi hai.", "Haan, chalega.", "Abhi ek ghante baad."]
for t in STEPS:
    last = c.reply(t)
CHECKS = [("Mujhe aapse kuchh aur hi baat karni hai.", None, ["स्क्रीन", "फ़ॉर्म"]),
          ("Abhi kya karte ho aap?", "एआई असिस्टेंट", ["स्क्रीन"]),
          ("Aapka kaam kya hai? Kya aap job profile par ho aap?", "एआई असिस्टेंट", ["नोट कर लेती"]),
          ("Aapka office kahaan par hai?", "गोपीनाथ", []),
          ("Office ki location.", "गोपीनाथ", ["पक्का नहीं"]),
          ("Aapne khaana khaa liya kya?", "लक्ष्मी इंडिया फाइनेंस और लोन-बैंकिंग", []),
          ("Aapka aap ghar kitne baje jaate ho aap?", "लक्ष्मी इंडिया फाइनेंस और लोन-बैंकिंग", ["आठ बजे"]),
          ("Ek ghante baad call kar lena mujhe.", "एक घंटे", ["एआई असिस्टेंट"]),
          ("Aapki company ka naam kya hai?", "जयपुर", []),
          ("Is company ka AUM kitna hai?", "एयूएम", ["पक्की जानकारी नहीं है, मैं इसे टीम से कन्फ़र्म करवा दूँगी।"]),
          ("Aapka loan ka interest kya hai?", "इंटरेस्ट", []),
          ("Thik hai call cut karo.", "टीम", ["स्क्रीन"])]
bad = 0
for q, must, mustnot in CHECKS:
    a = c.reply(q)
    ok = (must is None or must in a) and not any(m in a for m in mustnot)
    bad += not ok
    print("ok  " if ok else "FAIL", q, "->", a[:150].replace("\n", " "))
print("CHAT REPLAY: ALL OK" if not bad else f"CHAT REPLAY: {bad} FAILED")
sys.exit(1 if bad else 0)
