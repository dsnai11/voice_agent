"""Language detection and dialect understanding.   python train/lang_test.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import lang

DETECT = [("Mahaaron naam arjun singh chhe", "mwr"), ("mharo naam arjun singh chhe", "mwr"), ("maru naam arjun singh chhe", "gu"), ("Maanoo naam raahul mehtaachhe", "gu"), ("Byaj dar ketloche", "gu"), ("Maine baya lakh rupya nahi personal loan jo yeh chhe", "gu"), ("Maaro naam raahul mehta hai", None), ("Byaj ki to lakh si", None), ("mhaaro naam rahul mehta hai", "mwr"), ("Maine do lakh rupyaari loan chaizi", "mwr"), ("mane doo lakh ni personal loan joiye chhe", "gu"), ("vyaj dar ketlo chhe", "gu"), ("maru naam rahul mehta chhe", "gu"), ("mari pagar pachas hajar chhe", "gu"), ("tamari office kya aavi chhe", "gu"),
          ("tame mane paisa kyare aapso", "gu"), ("મને બે લાખ રૂપિયાની લોન જોઈએ છે", "gu"), ("mhane do lakh ri loan chaije", "mwr"), ("byaj kito lagsi", "mwr"), ("mharo naam rahul mehta hai", "mwr"),
          ("mhari tankhwa pachaas hajar hai", "mwr"), ("thaaro office kathe hai", "mwr"), ("thane kai chaije ghano paisa kito milsi", "mwr"), ("What is the interest rate?", "en"),
          ("I need a personal loan of two lakh rupees", "en"), ("My monthly salary is fifty thousand", "en"), ("how much loan can I get", "en"), ("can you tell me the documents required", "en"),
          ("mujhe personal loan chahiye", "hi"), ("aapka interest kitna hai", "hi"), ("Mera naam Rahul hai", "hi"), ("mujhe do lakh ka loan chahiye", "hi"), ("kitne din mein paisa milega", None),
          ("personal loan", None), ("salary 50000 per month", None), ("personal loan chahiye", None), ("my name is Rahul Mehta", "en"), ("I am salaried", "en"), ("haan", None), ("ok", None), ("do lakh", None), ("Jaipur", None), ("pachas hazaar", None)]
SWITCH = [("English mein baat karo", "en"), ("can you speak in english", "en"), ("gujarati ma vaat karo", "gu"), ("marwadi mein bolo", "mwr"), ("rajasthani boli mein baat karo", "mwr"),
          ("hindi mein bolo", "hi"), ("mujhe loan chahiye", None), ("shekhawati me baat kar", "mwr"), ("mewari bolo", "mwr"), ("Gujarati bhasha ma samjavo", "gu")]
HINGLISH = [("Mahaaron naam arjun singh chhe", "mwr", "mera naam arjun singh hai"), ("mane doo lakh ni personal loan joiye chhe", "gu", "mujhe do lakh ki personal loan chahiye hai"), ("vyaj dar ketlo chhe", "gu", "byaj dar kitna hai"),
            ("mari pagar pachas hajar chhe", "gu", "meri salary pachas hazaar hai"), ("મને બે લાખ રૂપિયાની લોન જોઈએ છે", "gu", "mujhe do lakh rupaye ki loan"), ("mhane do lakh ri loan chaije", "mwr", "mujhe do lakh ki loan chahiye"),
            ("byaj kito lagsi", "mwr", "byaj kitna lagega"), ("mhari tankhwa pachaas hajar hai", "mwr", "meri salary pachas hazaar hai"), ("thaaro office kathe hai", "mwr", "aapka office kahan hai")]
bad = 0
for t, w in DETECT:
    got = lang.detect(t)
    if got != w:
        bad += 1
        print(f"FAIL detect {t!r}: got {got}, want {w}")
for t, w in SWITCH:
    got = lang.switch_request(t)
    if got != w:
        bad += 1
        print(f"FAIL switch {t!r}: got {got}, want {w}")
for t, l, w in HINGLISH:
    got = lang.to_hinglish(t, l)
    if w not in got:
        bad += 1
        print(f"FAIL dialect {t!r}: got {got!r}, want it to contain {w!r}")
total = len(DETECT) + len(SWITCH) + len(HINGLISH)
print(f"LANG TEST: {total - bad}/{total} correct")
sys.exit(1 if bad else 0)
