import sys, time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

QUESTIONS = [
    "flat rate aur reducing rate mein kya fark hai", "APR kya hota hai", "free credit report kaise milti hai", "CIBIL score kaise badhaye", "agar EMI bounce ho gayi to kya hoga",
    "NACH kya hota hai", "KYC kya hota hai", "secured aur unsecured loan me kya difference hai", "UPI aur NEFT me kya fark hai", "FD kya hoti hai",
    "NBFC aur bank me kya fark hai", "cooling off period kya hota hai", "guarantor kya hota hai", "loan jaldi band karna ho to kya karna padega",
    "fraud call aaye to kahan complaint karun", "bank deposit safe hai kya", "gold loan kya hota hai", "credit card ya personal loan kaun sa better hai",
    "aapki company ka turnover kitna hai", "mera exact interest rate kya hoga", "RBI ne aaj repo rate kitna kiya", "mutual fund me paisa lagana chahiye kya",
    "aaj mausam kaisa hai", "cricket match kaun jeeta", "mujhe tax kaise bachana chahiye",
]


def done_call():
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    for t in ["Arjun Sharma", "Personal loan", "5 lakh", "medical", "job", "50000", "2 saal", "Jaipur", "nahi", "Nau nau nau shunya shunya shunya do do do do", "haan", "haan", "kal subah 10 baje"]:
        c.reply(t)
    assert c.flow.done, "call should be complete"
    return c


c = done_call()
for q in QUESTIONS:
    t = time.time()
    r = c.reply(q)
    print(f"Q: {q}\nA: {r}  ({time.time() - t:.1f}s)\n")
