"""Spelling of what the caller said: each pair is (what the listener wrote, how it must be shown).   python train/spelling_check.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import spelling

CASES = [
    ("Jaypur.", "Jaipur."), ("Ahmadaabaad.", "Ahmedabad."), ("Chalary.", "Salary."), ("Mera naam raam sharma hai.", "Mera naam ram sharma hai."), ("Arjun Sinh", "Arjun Singh"),
    ("Nahin.", "Nahi."), ("To koi EMI nahin chal rahi hai.", "To koi EMI nahi chal rahi hai."), ("Mujhe ek laakh ka loan chaahie.", "Mujhe ek lakh ka loan chahiye."),
    ("Pachaas hazaar.", "Pachas hazaar."), ("Chaar saal.", "Char saal."), ("Aath saal.", "Aath saal."), ("Mujhe aapse kuchh aur bhi poochhana hai.", "Mujhe aapse kuch aur bhi puchna hai."),
    ("Mujhe aapse aur bhi kuchh savaal puchh", "Mujhe aapse aur bhi kuch sawal puch"), ("Yah sahi number hai.", "Yeh sahi number hai."), ("Aap vah kitna time ho gaya", "Aap woh kitna time ho gaya"),
    ("Misnesh ke lie.", "Business ke liye."), ("Business ke lie.", "Business ke liye."), ("Do laakh ka.", "Do lakh ka."), ("Pachaas rupe", "Pachas rupaye"), ("Kar sakti hai.", "Kar sakti hai."),
    ("Udaypur", "Udaipur"), ("Dilli mein rehta hoon", "Delhi mein rehta hoon"), ("Lakshymi India", "Lakshmi India"), ("Bombay", "Mumbai"), ("Lakhnau", "Lucknow"),
    ("Jab aapka man karen.", "Jab aapka man karein."), ("Ek ghante baad call kar lena mujhe.", "Ek ghante baad call kar lena mujhe."), ("Aapke office ki mail ID hai kya?", "Aapke office ki mail ID hai kya?"),
    ("adhaar card aur pan card", "Aadhaar card aur PAN card"), ("kyc kya hota hai", "KYC kya hota hai"), ("sibil score kitna chahiye", "CIBIL score kitna chahiye"), ("mera emmi kitni hogi", "mera EMI kitni hogi"),
    ("Haan, mujhe kuchh aur bhi poochhana hai aapse.", "Haan, mujhe kuch aur bhi puchna hai aapse."), ("Mainne salaari bataayi", "Maine salary bataayi"), ("Hamen byaaj kitna dena hoga", "Hume byaj kitna dena hoga"),
    ("Gaurav Sharma", "Gaurav Sharma"), ("Mera naam Pooja hai", "Mera naam Pooja hai"), ("Kota", "Kota"), ("Pune", "Pune"), ("Ramesh Kumar", "Ramesh Kumar"),
]
bad = 0
for raw, want in CASES:
    got = spelling.normalize(raw)
    ok = got == want
    bad += not ok
    if not ok:
        print(f"FAIL {raw!r}\n     got  {got!r}\n     want {want!r}")
print(f"SPELLING CHECK: {len(CASES) - bad}/{len(CASES)} correct")
sys.exit(1 if bad else 0)
