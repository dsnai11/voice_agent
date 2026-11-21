"""Large generated test set for Hindi (city and village speech) and Marwari / Rajasthani: several hundred answers at the right step of the form, in many wordings and
the loose spellings the listener produces. Prints accuracy per category and the misses.
    python train/big_corpus_test.py [hi|mwr] [--all]"""
import contextlib, io, itertools, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import brain
from dialect_corpus_test import BASE, FIELD, at, norm

SURNAMES = ["Meena", "Choudhary", "Jat", "Bishnoi", "Rathore", "Shekhawat", "Rajpurohit", "Gehlot", "Solanki", "Sharma", "Gurjar", "Saini", "Prajapat", "Mali", "Kumawat", "Vyas", "Soni", "Chauhan", "Singh", "Verma"]
FIRST = ["Ramesh", "Suresh", "Mohan", "Kailash", "Bhanwar", "Hanuman", "Sita", "Geeta", "Pooja", "Rekha", "Dinesh", "Mahesh", "Rakesh", "Mukesh", "Vijay", "Sunita", "Kavita", "Manoj", "Deepak", "Arjun"]
NAME_T = {"hi": ["mera naam {n} hai", "main {n} bol raha hoon", "{n} hai mera naam", "naam {n}", "mera naam {n} hai ji"],
          "mwr": ["mharo naam {n} hai", "maaro naam {n} chhe", "mahaaron naam {n} hai", "mhe {n} bolu hu", "mhane {n} kehve hai"]}
AMOUNTS = [("do lakh", 200000), ("dedh lakh", 150000), ("dhai lakh", 250000), ("sava lakh", 125000), ("saade teen lakh", 350000), ("paune do lakh", 175000), ("paanch lakh", 500000),
           ("das lakh", 1000000), ("pachas hazaar", 50000), ("pachhattar hazaar", 75000), ("ek lakh pachas hazaar", 150000), ("solah hazaar", 16000), ("bees hazaar", 20000), ("pachis hazaar", 25000),
           ("tees hazaar", 30000), ("chalis hazaar", 40000), ("saath hazaar", 60000), ("assi hazaar", 80000), ("ek lakh", 100000), ("teen lakh", 300000), ("char lakh", 400000), ("saat lakh", 700000),
           ("paanch hazaar", 5000), ("das hazaar", 10000), ("pandrah hazaar", 15000)]
AMT_T = {"hi": ["{a} chahiye", "{a} rupaye ka loan", "mujhe {a} chahiye", "{a}"], "mwr": ["{a} chaije", "mhane {a} rupya chaije", "{a} ro loan", "{a} rupaiya"]}
JOBS = {"salaried": ["naukri karta hoon", "private naukri hai", "sarkari naukri hai", "company mein kaam karta hoon", "factory mein kaam karta hoon", "school mein padhata hoon", "bank mein job hai", "main teacher hoon",
                     "hospital mein nurse hoon", "police mein hoon", "main clerk hoon", "mhe naukri karu hu", "mhe sarkari naukri karu hu", "mhe factory mein kaam karu hu", "mhe mastar hu school mein"],
        "self-employed": ["apna business hai", "dukan chalata hoon", "kheti karta hoon", "kisan hoon", "mazdoori karta hoon", "dihadi karta hoon", "dairy chalata hoon doodh ka kaam hai", "gaay bhains palta hoon",
                          "truck chalata hoon apna", "auto chalata hoon", "taxi chalata hoon", "main darji hoon", "main mistri hoon", "main carpenter hoon", "kirana dukan hai meri", "medical store hai",
                          "mhe dhandho karu hu", "mhe kheti karu hu", "mhari dukan hai", "mazdoori karu hu", "pashu palan karu hu", "mhari kirana ri dukan hai", "mhe truck chalau hu apno", "dudh ro dhandho hai",
                          "bakri palan karu hu", "mhe mistri hu"],
        "pensioner": ["pension aati hai", "main retired hoon", "retire ho gaya hoon pension milti hai", "pension aave hai", "mhe retire hu pension aave hai"],
        "not-earning": ["main housewife hoon", "ghar ka kaam karti hoon", "main student hoon", "abhi kuch nahi karta", "berozgar hoon", "ghar baithi hoon", "mhe ghar ro kaam karu hu", "mhe kuch kono karu"]}
PURPOSES = {"wedding": ["shaadi ke liye", "beti ki shaadi", "bete ki shaadi hai", "byah ke liye", "mharo byaav chhe", "chhori ro byaav", "byav sarun", "bayaav ke liye", "sagai ke liye"],
            "medical": ["ilaj ke liye", "hospital ka kharcha", "dawai ke liye", "operation hai", "bimari mein", "ilaaj sarun", "dawai ro kharcho"],
            "home repair": ["ghar banana hai", "ghar ki marammat", "makaan banwana hai", "ghar ri marammat sarun", "chhat daalni hai", "ghar banavno hai"],
            "education": ["padhai ke liye", "bachchon ki fees", "college ki fees", "chhora ri padhai sarun", "school ki fees"],
            "farming": ["kheti ke liye", "tractor khareedna hai", "gaay bhains leni hai", "bore karwana hai", "beej khad ke liye", "kheti sarun", "tractor leno hai", "pashu leno hai"],
            "business": ["dukan kholni hai", "dhandhe ke liye", "business badhana hai", "dukan ke liye maal lena hai", "dhandhe sarun", "dukan kholni hai sa"],
            "vehicle": ["gaadi leni hai", "bike khareedni hai", "truck lena hai", "gaadi leni hai sa"]}
TOWNS = ["Jodhpur", "Bikaner", "Jaisalmer", "Barmer", "Nagaur", "Sikar", "Jhunjhunu", "Churu", "Pali", "Ajmer", "Bhilwara", "Alwar", "Kota", "Udaipur", "Tonk", "Sirohi", "Jalore", "Dausa", "Bharatpur", "Hanumangarh",
         "Chittorgarh", "Banswara", "Dungarpur", "Beawar", "Kishangarh", "Jaipur", "Ahmedabad", "Surat", "Indore", "Delhi"]
TOWN_T = {"hi": ["{t}", "main {t} mein rehta hoon", "{t} se hoon", "{t} shehar", "mera ghar {t} mein hai"], "mwr": ["{t}", "mhe {t} rahu hu", "mhe {t} su hu", "{t} me rahu hu", "mhe {t} ro hu"]}
VILLAGES = ["piparli", "khejarli", "gudha", "mandawa", "osian", "phalodi", "ratangarh", "nokha", "sujangarh", "lalsot"]
VIL_T = {"hi": ["main gaon {v} mein rehta hoon", "gaon {v}", "{v} gaon se hoon"], "mwr": ["mhe gaam {v} me rahu hu", "gaam {v}", "mhe {v} gaam su hu"]}
DURATIONS = [("do saal", "2 years"), ("teen saal se", "3 years"), ("paanch saal ho gaye", "5 years"), ("dedh saal", "1.5 years"), ("chhe mahine", "6 months"), ("das saal se", "10 years"), ("ek saal", "1 years"),
             ("dhai saal", "2.5 years"), ("char saal se kaam kar raha hoon", "4 years"), ("aath saal", "8 years"), ("do saal su", "2 years"), ("paanch saal hoyo", "5 years"), ("teen mahina hoya", "3 months"),
             ("dus saal su dhandho karu hu", "10 years"), ("saat saal hoya", "7 years")]
INCOMES = [("pachas hazaar", 50000), ("pachis hazaar mahina", 25000), ("das hazaar", 10000), ("pandrah hazaar", 15000), ("bees hazaar", 20000), ("tees hazaar", 30000), ("ek lakh", 100000),
           ("saath hazaar", 60000), ("mahine ki kamai pachas hazaar hai", 50000), ("mahine ri tankhwa pachaas hajar hai", 50000), ("mhari kamai das hajar mahino", 10000), ("pandrah hajar aave hai", 15000),
           ("saade bais hazaar", 22500), ("dedh lakh", 150000), ("assi hazaar", 80000), ("chalis hazaar", 40000)]
QUESTIONS = {"hi": [("byaj kitna lagega", "इंटरेस्ट"), ("interest kitna hai", "इंटरेस्ट"), ("kaun kaun se kagaz lagenge", "आईडी"), ("documents kya chahiye", "आईडी"), ("paisa kab tak milega", "घंटे"),
                    ("processing fee kitni hai", "प्रोसेसिंग"), ("emi kitni banegi", "ईएमआई"), ("kitne mahine ka loan milta hai", "बारह"), ("aapka office kahan hai", "गोपीनाथ"), ("kya ye company asli hai", ["जयपुर", "आरबीआई"]),
                    ("cibil kam ho to loan milega kya", "स्कोर"), ("agar emi late ho gayi to kya hoga", "सिबिल"), ("kya aap rbi se registered ho", "आरबीआई"), ("guarantor lagega kya", "गारंटर"),
                    ("loan ke liye koi paisa dena padega kya", "लिखित"), ("kya meri jankari surakshit hai", "जानकारी"), ("aapki kitni branch hain", "ग्यारह"), ("loan kitne ka milega", "रकम"),
                    ("umar kitni honi chahiye", "उम्र"), ("band karne par charge lagta hai kya", "चार्ज")],
             "mwr": [("byaj kito lagsi", "ब्याज"), ("kai kai kagad chaije", "आईडी"), ("paiso kad milsi", "घंटा"), ("processing fees kito lagsi", "प्रोसेसिंग"), ("thaaro office kathe hai", "गोपीनाथ"), ("emi kito aavsi", "ईएमआई"),
                     ("thari kitti branch hai", "ग्यारह"), ("loan kito milsi", "रकम"), ("cibil kam hoy to loan milsi kai", "स्कोर"), ("thari company asli hai kai", "जयपुर"), ("guarantor chaije kai", "गारंटर"),
                     ("ghano byaj to kono lagsi", "ब्याज"), ("loan jaldi band karu to charge lagsi kai", "चार्ज"), ("kagad kathe jama karavan", "आईडी"), ("thane rbi su manyata mili hai kai", "आरबीआई")]}


def build(lang):
    cases = []
    for k, (f, s) in enumerate(itertools.product(FIRST, SURNAMES)):
        if k % 7:
            continue
        cases.append(("name", "full_name", NAME_T[lang][k % len(NAME_T[lang])].format(n=f"{f} {s}"), f"{f} {s}"))
    for i, (a, v) in enumerate(AMOUNTS):
        for j, t in enumerate(AMT_T[lang]):
            if (i + j) % 2 == 0:
                cases.append(("amount", "loan_amount", t.format(a=a), v))
    for cat, lst in JOBS.items():
        for t in lst:
            if (lang == "hi") == ("mhe" not in t and "mhari" not in t and "mhane" not in t and "karu" not in t and "pashu palan karu" not in t and "dhandho" not in t and "hoya" not in t):
                cases.append(("job", "employment", t, cat))
    for cat, lst in PURPOSES.items():
        for t in lst:
            marwari = any(x in t for x in ("mharo", "ro ", " ri ", "sarun", "leno", "banavno", "chhori", "bayaav", "byav", "sa", "ro", "mhe"))
            if (lang == "mwr") == marwari or lang == "hi" and not marwari:
                cases.append(("purpose", "loan_purpose", t, cat))
    for k, t in enumerate(TOWNS):
        cases.append(("town", "city", TOWN_T[lang][k % len(TOWN_T[lang])].format(t=t.lower()), t))
    for k, v in enumerate(VILLAGES):
        cases.append(("village", "city", VIL_T[lang][k % len(VIL_T[lang])].format(v=v), v.capitalize()))
    for t, v in DURATIONS:
        if (lang == "mwr") == any(x in t for x in (" su", "hoyo", "hoya", "dus ", "saat saal hoya")) or lang == "hi" and not any(x in t for x in (" su", "hoyo", "hoya", "dus ")):
            cases.append(("tenure", "work_tenure", t, v))
    for t, v in INCOMES:
        if (lang == "mwr") == any(x in t for x in ("mahine ri", "mhari", "aave", "mahino")) or lang == "hi" and not any(x in t for x in ("mahine ri", "mhari", "aave hai", "mahino")):
            cases.append(("income", "monthly_income", t, v))
    for k, (q, must) in enumerate(QUESTIONS[lang]):
        for step in ("loan_purpose", "employment", "monthly_income", "city"):
            if (k + len(step)) % 3 == 0:
                cases.append(("question", step, q, must))
    return cases


def run(lang):
    cases = build(lang)
    stats, misses = {}, []
    for cat, step, text, want in cases:
        c = at(step)
        before = dict(c.flow.v)
        with contextlib.redirect_stdout(io.StringIO()):
            a = c.reply(text)
        if cat == "question":
            ok = any(w in a for w in (want if isinstance(want, list) else [want])) and c.flow.v == before
            got = a[:70]
        else:
            got = c.flow.v.get(FIELD[step])
            if cat in ("name", "town", "village"):
                ok = got is not None and norm(want) == norm(got)
            elif cat in ("amount", "income"):
                ok = got == want
            elif cat == "purpose":
                ok = got is not None and norm(want).split("repair")[0] in norm(got)
            elif cat == "job":
                ok = got == want
            else:
                ok = got is not None and norm(want) in norm(got)
        s = stats.setdefault(cat, [0, 0])
        s[1] += 1
        s[0] += ok
        if not ok:
            misses.append((cat, step, text, want, got))
    return stats, misses


if __name__ == "__main__":
    langs = [x for x in sys.argv[1:] if x in ("hi", "mwr")] or ["hi", "mwr"]
    total = 0
    for lg in langs:
        stats, misses = run(lg)
        n = sum(v[1] for v in stats.values())
        print(f"== {lg}: {n - len(misses)}/{n} correct (" + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in stats.items()) + ")")
        for cat, step, text, want, got in misses[:60]:
            print(f"   MISS [{cat}/{step}] {text!r}: wanted {want!r}, got {got!r}")
        total += len(misses)
    print("BIG CORPUS:", "ALL OK" if not total else f"{total} misses")
    sys.exit(1 if total else 0)
