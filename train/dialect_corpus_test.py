"""Marwari / Rajasthani village speech, Gujarati and English answers at every step of the form, written the way the listener writes them (loose Roman spelling,
Hindi-ised words).   Each case: (step, what the caller says, the value that must be saved or the topic word the answer must contain).
    python train/dialect_corpus_test.py [mwr|gu|en]        (needs Ollama for the question cases)"""
import contextlib, io, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain

BASE = {"full_name": "Mera naam Arjun Singh hai", "loan_type": "personal loan", "loan_amount": "do lakh", "loan_purpose": "shaadi ke liye", "employment": "job karta hoon",
        "monthly_income": "pachas hazaar", "work_tenure": "do saal", "city": "Jaipur", "existing_loans": "nahi", "existing_emi": "paanch hazaar", "phone": "9876543210",
        "phone_confirm": "haan sahi hai", "consent": "haan", "callback_time": "kal subah 10 baje"}
FIELD = {"full_name": "full_name", "loan_type": "loan_type", "loan_amount": "loan_amount", "loan_purpose": "loan_purpose", "employment": "employment", "monthly_income": "monthly_income",
         "work_tenure": "work_tenure", "city": "city", "existing_loans": "existing_loans", "consent": "consent", "callback_time": "callback_time", "phone": "phone"}

# step, utterance, expected (a value, or a list of acceptable values; for "Q" cases the answer must contain the Devanagari / Gujarati word)
MWR = [
    ("full_name", "mharo naam ramesh meena hai", "Ramesh Meena"), ("full_name", "Maaro naam arjun singh hai", "Arjun Singh"), ("full_name", "mahaaron naam bhanwar lal chhe", "Bhanwar Lal"),
    ("full_name", "mharo naam sita devi hai", "Sita Devi"), ("full_name", "naam mharo kailash chaudhary hai", "Kailash Chaudhary"), ("full_name", "mhane hanuman ram kehve hai", "Hanuman Ram"),
    ("full_name", "mhe mohan lal bolu hu", "Mohan Lal"),
    ("loan_type", "mhane personal loan chaije", "personal"), ("loan_type", "mhane salary loan chaije sa", "salary"), ("loan_type", "mhaare pede loan chaije", "payday"), ("loan_type", "mhane personal lone chaiji", "personal"),
    ("loan_amount", "do lakh rupya", 200000), ("loan_amount", "dho lakh chaije", 200000), ("loan_amount", "dedh lakh", 150000), ("loan_amount", "pachas hajar", 50000), ("loan_amount", "ek lakh pachas hajar", 150000),
    ("loan_amount", "teen lakh rupaiya chaije", 300000), ("loan_amount", "dhai lakh", 250000), ("loan_amount", "paanch lakh", 500000), ("loan_amount", "mhane pachaas hazaar rupiya chaije", 50000),
    ("loan_purpose", "maharo bayaav chhe", "wedding"), ("loan_purpose", "byav sarun", "wedding"), ("loan_purpose", "chhori ro byaav karno hai", "wedding"), ("loan_purpose", "kheti sarun", "farming"),
    ("loan_purpose", "gaay bhains leni hai", "farming"), ("loan_purpose", "tractor leno hai", "farming"), ("loan_purpose", "ghar banavno hai", "home"), ("loan_purpose", "ghar ri marammat sarun", "home"),
    ("loan_purpose", "ilaaj sarun", "medical"), ("loan_purpose", "dawai ro kharcho", "medical"), ("loan_purpose", "chhora ri padhai sarun", "education"), ("loan_purpose", "dukan kholni hai", "business"),
    ("loan_purpose", "dhandhe sarun", "business"), ("loan_purpose", "bore karvano hai", "farming"),
    ("employment", "mhe naukri karu hu", "salaried"), ("employment", "main naukri karo chaahoon", "salaried"), ("employment", "mhe dhandho karu hu", "self-employed"), ("employment", "kheti karu hu", "self-employed"),
    ("employment", "mazdoori karu hu", "self-employed"), ("employment", "mhari dukan hai", "self-employed"), ("employment", "pashu palan karu hu", "self-employed"), ("employment", "sarkari naukri hai", "salaried"),
    ("employment", "mhe driver hu gaadi chalau hu", ["salaried", "self-employed"]), ("employment", "pension aave hai", "pensioner"), ("employment", "mhe ghar ro kaam karu hu", "not-earning"),
    ("monthly_income", "mari pachas hazaar aage chhe", 50000), ("monthly_income", "mahine ri tankhwa pachaas hajar hai", 50000), ("monthly_income", "mhari kamai das hajar mahino", 10000),
    ("monthly_income", "pandrah hajar aave hai", 15000), ("monthly_income", "bees hajar", 20000), ("monthly_income", "dedh lakh mahino", 150000), ("monthly_income", "mahino pachis hajar ri kamai hai", 25000),
    ("work_tenure", "do saal su", "2 years"), ("work_tenure", "paanch saal hoyo", "5 years"), ("work_tenure", "chhe mahina hoya", "6 months"), ("work_tenure", "dus saal su dhandho karu hu", "10 years"),
    ("work_tenure", "ek saal", "1 years"), ("work_tenure", "teen saal su", "3 years"),
    ("city", "jodhpur", "Jodhpur"), ("city", "mhe bikaner rahu hu", "Bikaner"), ("city", "barmer", "Barmer"), ("city", "mhe jaisalmer su hu", "Jaisalmer"), ("city", "nagaur", "Nagaur"), ("city", "sikar me rahu hu", "Sikar"),
    ("city", "mhe gaam piparli me rahu hu", "Piparli"), ("city", "udaypur", "Udaipur"), ("city", "jaypur", "Jaipur"),
    ("existing_loans", "kono", "no"), ("existing_loans", "koi loan kono", "no"), ("existing_loans", "na", "no"), ("existing_loans", "dujo koi loan kono", "no"), ("existing_loans", "ek loan chalu hai", "yes"),
    ("existing_loans", "hao ek chale hai", "yes"), ("existing_loans", "dho loan chale hai", "yes"),
    ("consent", "ha sa", "yes"), ("consent", "hao kar do", "yes"), ("consent", "jarur sa", "yes"), ("consent", "na mat karo", "no"), ("consent", "kar sako ho", "yes"),
    ("callback_time", "kaal savere", ["kal", "kaal"]), ("callback_time", "sanjh ne call karjyo", "sanjh"), ("callback_time", "raat ne", "raat"), ("callback_time", "abhi kar do", "abhi"), ("callback_time", "do ghanta paachho", "ghanta"),
    # questions in the middle of the form (the answer must be in Marwari and the form must not change)
    ("loan_purpose", "byaj kito lagsi", "ब्याज", "Q"), ("loan_purpose", "kai kai kagad chaije", "आईडी", "Q"), ("loan_purpose", "paiso kad milsi", "घंटा", "Q"), ("loan_purpose", "processing fees kito lagsi", "प्रोसेसिंग", "Q"),
    ("employment", "thaaro office kathe hai", "गोपीनाथ", "Q"), ("employment", "thari company safe hai kai", "जयपुर", "Q"), ("monthly_income", "emi kito aavsi", "ईएमआई", "Q"), ("city", "thari kitti branch hai", "ग्यारह", "Q"),
    ("loan_amount", "mhane ghano paiso chaije kito milsi", "रकम", "Q"), ("work_tenure", "cibil kam hai to loan milsi kai", "स्कोर", "Q"), ("consent", "ghar baithe kagad bhej dyo", ["लिंक", "आईडी"], "Q"),
]
GU = [
    ("full_name", "maru naam rahul mehta chhe", "Rahul Mehta"), ("full_name", "mara naam jigar patel chhe", "Jigar Patel"), ("full_name", "mane hiren shah kahe chhe", "Hiren Shah"),
    ("loan_type", "mane personal loan joiye chhe", "personal"), ("loan_type", "mare salary loan joie", "salary"),
    ("loan_amount", "be lakh rupiya", 200000), ("loan_amount", "pachas hajar", 50000), ("loan_amount", "doda lakh", 150000), ("loan_amount", "tran lakh joiye chhe", 300000), ("loan_amount", "ek lakh", 100000),
    ("loan_purpose", "lagn mate", "wedding"), ("loan_purpose", "dikri na lagn mate", "wedding"), ("loan_purpose", "kheti mate", "farming"), ("loan_purpose", "ghar banavva mate", "home"), ("loan_purpose", "dava mate", "medical"),
    ("loan_purpose", "bhanvva mate", "education"), ("loan_purpose", "dhandha mate", "business"), ("loan_purpose", "dukan kholva mate", "business"),
    ("employment", "hu nokri karu chhu", "salaried"), ("employment", "mari pase potano dhandho chhe", "self-employed"), ("employment", "hu kheti karu chhu", "self-employed"), ("employment", "mari dukan chhe", "self-employed"),
    ("employment", "hu retire thayo chhu pension aave chhe", "pensioner"), ("employment", "hu gruhini chhu", "not-earning"),
    ("monthly_income", "mari pagar pachas hajar chhe", 50000), ("monthly_income", "mahine vees hajar kamau chhu", 20000), ("monthly_income", "pandar hajar", 15000),
    ("work_tenure", "tran varsh thi", "3 years"), ("work_tenure", "pach varsh thi", "5 years"), ("work_tenure", "chha mahina thi", "6 months"),
    ("city", "ahmedabad", "Ahmedabad"), ("city", "hu surat ma rahu chhu", "Surat"), ("city", "rajkot", "Rajkot"), ("city", "vadodara", "Vadodara"), ("city", "bhavnagar ma", "Bhavnagar"),
    ("existing_loans", "nathi", "no"), ("existing_loans", "koi loan nathi", "no"), ("existing_loans", "ek loan chalu chhe", "yes"), ("existing_loans", "ha ek chale chhe", "yes"),
    ("consent", "ha barabar", "yes"), ("consent", "ha kari do", "yes"), ("consent", "na nai", "no"),
    ("callback_time", "kale savare", "kal"), ("callback_time", "sanje call karjo", ["shaam", "sanje"]), ("callback_time", "ratre", ["raat", "ratre"]),
    ("loan_purpose", "vyaj dar ketlo chhe", "વ્યાજ", "Q"), ("loan_purpose", "kya kya documents joiye", "આઈડી", "Q"), ("loan_purpose", "paisa kyare malse", "કલાક", "Q"), ("employment", "tamari office kya chhe", "ગોપીનાથ", "Q"),
    ("monthly_income", "emi ketli aavshe", "ઈએમઆઈ", "Q"), ("city", "tamari ketli branch chhe", "અગિયાર", "Q"),
]
EN = [
    ("full_name", "my name is Rahul Mehta", "Rahul Mehta"), ("full_name", "this is Priya Shah speaking", "Priya Shah"), ("full_name", "I am Amit Kumar", "Amit Kumar"), ("full_name", "call me Raj", "Raj"),
    ("loan_type", "I need a personal loan", "personal"), ("loan_type", "I want a salary loan", "salary"), ("loan_type", "payday loan please", "payday"),
    ("loan_amount", "two lakh rupees", 200000), ("loan_amount", "five hundred thousand", 500000), ("loan_amount", "fifty thousand", 50000), ("loan_amount", "one and a half lakh", 150000), ("loan_amount", "3 lakhs", 300000),
    ("loan_amount", "I need ten lakh", 1000000), ("loan_amount", "about two and a half lakh", 250000),
    ("loan_purpose", "for my sister's wedding", "wedding"), ("loan_purpose", "medical expenses", "medical"), ("loan_purpose", "to repair my house", "home"), ("loan_purpose", "for my son's education", "education"),
    ("loan_purpose", "to expand my business", "business"), ("loan_purpose", "to buy a tractor", "farming"),
    ("employment", "I am salaried", "salaried"), ("employment", "I run my own business", "self-employed"), ("employment", "I work at a private company", "salaried"), ("employment", "I am a farmer", "self-employed"),
    ("employment", "I am retired and get pension", "pensioner"), ("employment", "I am a housewife", "not-earning"), ("employment", "I own a shop", "self-employed"),
    ("monthly_income", "fifty thousand a month", 50000), ("monthly_income", "my salary is 35000", 35000), ("monthly_income", "about one lakh per month", 100000), ("monthly_income", "twenty five thousand", 25000),
    ("work_tenure", "three years", "3 years"), ("work_tenure", "about five years", "5 years"), ("work_tenure", "six months", "6 months"), ("work_tenure", "two and a half years", "2.5 years"),
    ("city", "Jaipur", "Jaipur"), ("city", "I live in Ahmedabad", "Ahmedabad"), ("city", "near Jodhpur", "Jodhpur"), ("city", "Pune", "Pune"),
    ("existing_loans", "no", "no"), ("existing_loans", "no other loan", "no"), ("existing_loans", "I have one loan running", "yes"), ("existing_loans", "none", "no"), ("existing_loans", "yes I do", "yes"),
    ("consent", "yes you can call", "yes"), ("consent", "sure", "yes"), ("consent", "no please do not call", "no"),
    ("callback_time", "tomorrow morning", "tomorrow"), ("callback_time", "in an hour", "hour"), ("callback_time", "this evening", "evening"), ("callback_time", "any time", "any"),
    ("loan_purpose", "What is the interest rate?", "interest", "Q"), ("loan_purpose", "Which documents do I need?", "ID proof", "Q"), ("employment", "where is your office", "Gopinath", "Q"),
    ("monthly_income", "how long does it take to get the money", "hours", "Q"), ("city", "how many branches do you have", "branches", "Q"), ("work_tenure", "is there any processing fee", "processing", "Q"),
    ("consent", "is my data safe with you", "information", "Q"), ("loan_amount", "what if my CIBIL score is low", "score", "Q"),
]
SETS = {"mwr": MWR, "gu": GU, "en": EN}
ORDER = ["full_name", "loan_type", "loan_amount", "loan_purpose", "employment", "monthly_income", "work_tenure", "city", "existing_loans", "phone", "phone_confirm", "consent", "callback_time"]


def at(step):
    c = brain.Call("enquiry", on_form=lambda v, ch, f, k: None)
    c.start_with("नमस्ते")
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(25):
            if c.flow.asked == step or c.flow.asked is None:
                break
            c.reply(BASE[c.flow.asked])
    return c


def norm(x):
    return str(x).lower().replace(" ", "")


def run(name):
    bad, n = [], 0
    for case in SETS[name]:
        step, text, want = case[:3]
        q = len(case) > 3
        c = at(step)
        before = dict(c.flow.v)
        with contextlib.redirect_stdout(io.StringIO()):
            a = c.reply(text)
        n += 1
        if q:
            ok = any(w in a for w in (want if isinstance(want, list) else [want])) and c.flow.v == before
        else:
            got = c.flow.v.get(FIELD[step])
            wants = want if isinstance(want, list) else [want]
            ok = any((norm(w) in norm(got)) if isinstance(w, str) else got == w for w in wants) if got is not None else False
            if step == "loan_purpose" and want in ("home", "farming") and got:
                ok = norm(want) in norm(got) or (want == "home" and "repair" in norm(got))
        if not ok:
            got = a[:90] if q else c.flow.v.get(FIELD[step])
            bad.append((step, text, want, got))
    return n, bad


if __name__ == "__main__":
    names = [x for x in sys.argv[1:] if x in SETS] or list(SETS)
    total_bad = 0
    for nm in names:
        n, bad = run(nm)
        print(f"{nm}: {n - len(bad)}/{n} correct")
        for step, text, want, got in bad:
            print(f"   MISS [{step}] {text!r}: wanted {want!r}, got {got!r}")
        total_bad += len(bad)
    print("DIALECT CORPUS:", "ALL OK" if not total_bad else f"{total_bad} misses")
    sys.exit(1 if total_bad else 0)
