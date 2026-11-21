"""The wait before Ria answers is longer when the caller trails off ("... aur", "... ki", "... matlab").   python train/end_of_turn_test.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STT_ENGINE", "hinglish")
import server

class Fake(server.CallSession):
    def __init__(self, texts, asked=None):
        self.turn_texts = texts
        class F: pass
        c = F(); c.flow = F(); c.flow.asked = asked; c.flow.phone_buf = ""
        self.call = c

bad = 0
for texts, want_longer in [(["Mujhe loan chahiye aur"], True), (["Mera kaam ye hai ki"], True), (["Mera naam Arjun hai."], False), (["Do lakh ka loan chahiye"], False), (["haan"], False), (["Mujhe wo matlab"], True)]:
    t = Fake(texts)._turn_silence()
    ok = (t > server.TURN_SILENCE_S) == want_longer
    bad += not ok
    print("ok  " if ok else "FAIL", texts, f"-> waits {t:.1f}s")
print("END OF TURN TEST: ALL OK" if not bad else f"END OF TURN TEST: {bad} FAILED")
sys.exit(1 if bad else 0)
