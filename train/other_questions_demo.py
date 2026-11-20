"""Shows how Ria answers off-topic / small-talk / company questions in the middle of the form and after it.   python train/other_questions_demo.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
c.start_with("नमस्ते")
for t in ["Arjun Sharma", "personal loan", "aaj ka mausam kaisa hai", "ai kya hota hai", "tum kya kar rahi ho", "company kitni purani hai", "kisi insaan se baat karao",
          "loan ke liye pehle paisa dena padega kya", "cricket kaun jeeta", "5 lakh", "ye call record ho rahi hai kya", "aadhaar number bata du kya", "mere gaon mein branch hai kya", "mudra loan milta hai kya"]:
    print("CALLER:", t); print("RIA   :", c.reply(t)[:330]); print()
