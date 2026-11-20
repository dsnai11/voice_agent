"""Second honest hold-out: new topics (written after the first hold-out) with wording that is NOT in the approved-answer examples.
   python train/bank_holdout2.py       (needs the local Ollama running for the hybrid matcher)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import replybank

CASES = [
    ("kal ipl ka final hai kaun jeetega", ["off_topic"]), ("mera favourite hero kaun hai bataoge", ["off_topic"]), ("aaj subah se sar dard kar raha hai koi dawai batao", ["off_topic"]),
    ("tum kisse shaadi karogi", ["off_topic"]), ("kya aaj holiday hai", ["off_topic"]), ("bitcoin kharidna chahiye kya", ["invest_advice", "off_topic"]), ("mujhe ek kahani sunao", ["off_topic"]),
    ("ai ka full form kya hota hai", ["what_is_ai"]), ("tum robot ho ya ai", ["what_is_ai", "are_you_robot"]), ("tumhe chalata kaun hai", ["what_is_ai", "are_you_robot"]),
    ("aur batao aaj kya plan hai", ["what_doing", "small_talk"]), ("khaali ho kya abhi", ["what_doing", "small_talk"]),
    ("tumhari company ka naam market mein kaisa hai", ["company_doing"]), ("company ko shuru hue kitne saal hue", ["company_doing"]), ("company ka turnover kitna hai", ["company_doing", "company_facts_unknown"]),
    ("kya main apna paisa aapke paas rakh sakta hoon byaaj ke liye", ["company_deposit"]), ("aap log fixed deposit lete ho kya", ["company_deposit"]),
    ("mere gaon ke paas koi dukaan office hai kya aapka", ["branch_near"]), ("surat mein aapki shakha hai", ["branch_near"]), ("kya mujhe office jaana padega", ["branch_near"]),
    ("loan dilwane ke naam par agent paise maang raha hai", ["advance_fee"]), ("pehle kuch rakam bharni padegi kya tab loan sanction hoga", ["advance_fee"]), ("approval ke liye kuch dena lena hota hai kya", ["advance_fee"]),
    ("loan lene se pehle sab shartein kagaz par milengi kya", ["kfs_agreement"]), ("baad mein koi chhupa hua kharcha nahi aayega na", ["kfs_agreement", "hidden_charges"]), ("agreement par sign karne se pehle padhne ko milega kya", ["kfs_agreement"]),
    ("har mahine ki kaun si tarikh ko kist kategi", ["emi_due_date"]), ("pehli kist kis date ko dena hai", ["emi_due_date"]),
    ("meri complaint ka koi jawab nahi aaya ab kise likhun", ["complaint_escalation", "complaint"]), ("rbi ombudsman ke paas kaise jaate hain", ["complaint_escalation"]), ("shikayat ke liye upar kaun hai", ["complaint_escalation"]),
    ("mujhe kisi sir se baat karni hai", ["talk_to_human"]), ("kisi asli aadmi ko phone do", ["talk_to_human"]), ("aap nahi koi aur baat karega", ["talk_to_human"]),
    ("ye baatcheet record ho rahi hai kya", ["call_recording"]), ("meri awaaz save ho rahi hai", ["call_recording"]),
    ("din mein kitne baje call karte ho", ["calling_hours"]), ("raat ko phone mat kiya karo", ["calling_hours", "harassment"]),
    ("aadhaar ka number abhi bol doon kya", ["share_docs_on_call"]), ("pan card ki photo abhi bhej doon kya", ["share_docs_on_call"]),
    ("maine aaj tak koi loan nahi liya mera cibil nahi hoga", ["new_to_credit"]), ("mera credit history bilkul nahi hai", ["new_to_credit"]),
    ("main ghar sambhalti hoon kya mujhe loan milega", ["not_earning"]), ("college mein padhta hoon kya loan mil sakta hai", ["not_earning"]),
    ("pichli baar bank ne mera loan nahi diya", ["loan_rejected_before"]), ("meri application pehle decline ho gayi thi", ["loan_rejected_before"]),
    ("emi halki ho sakti hai kya", ["reduce_emi"]), ("kisht kam karwani hai kya karun", ["reduce_emi"]),
    ("mudra yojana ka loan milega kya", ["govt_scheme"]), ("sarkari subsidy wala loan chahiye", ["govt_scheme"]),
    ("sarkar ne jo loan maafi ki hai uska fayda milega kya", ["loan_waiver"]), ("ek baar mein settlement karke loan band karwa dijiye", ["loan_waiver"]),
    ("main apni bike ke liye loan lena chahta hoon", ["vehicle_loan_info"]), ("truck kharidna hai uska loan milega kya", ["vehicle_loan_info"]),
    ("apne dhandhe ko badhane ke liye loan chahiye", ["business_loan_info", "self_employed"]), ("msme wala loan batao", ["business_loan_info"]),
    ("zameen par makaan banane ke liye loan chahiye", ["construction_loan_info"]), ("ghar banwana hai uska loan hai kya", ["construction_loan_info"]),
    ("meri tankhwah nakad mein milti hai", ["salary_account", "no_salary_slip"]), ("itr nahi bharta main loan milega", ["salary_account"]),
    ("wife ko saath mein jod sakte hain kya loan mein", ["co_applicant"]), ("do log milkar loan le sakte hain kya", ["co_applicant"]),
    ("loan par bima hota hai kya", ["loan_insurance"]), ("insurance zabardasti lena padta hai kya", ["loan_insurance"]),
    ("tum log roz call kyun karte ho", ["repeat_call", "harassment"]), ("aap baar baar phone mat kiya karo", ["repeat_call", "stop_calling", "harassment"]),
    ("ye to bas marketing wali call hai na", ["spam_worry"]), ("mujhe roz loan ke call aate hain", ["spam_worry"]),
    ("35000 salary mein kitna loan mil jayega", ["loan_amount_ask", "how_much_loan"]), ("meri income par kitne ka loan banta hai", ["loan_amount_ask", "how_much_loan"]),
    ("emi kahan se bharni hai", ["payment_how"]), ("rbi registered ho kya aap", ["rbi_registered"]),
    ("ji haan", ["NONE"]), ("theek hai", ["NONE"]), ("ramesh gupta", ["NONE"]), ("teen lakh", ["NONE"]), ("jodhpur", ["NONE"]), ("main business karta hoon", ["NONE"]), ("kal shaam 5 baje", ["NONE"]),
]
ok = 0
misses = []
for q, wants in CASES:
    got = [m["id"] for m in replybank.match_hybrid(q) if m["score"] >= (0.5 if m["entry"].get("require") else 0.6)]
    good = (not got) if wants == ["NONE"] else (bool(got) and got[0] in wants)
    ok += good
    if not good:
        misses.append((q, wants, [(m["id"], m["score"]) for m in replybank.match_hybrid(q)][:2]))
print(f"HOLD-OUT 2 accuracy (new topics, unseen wording): {ok}/{len(CASES)} ({100 * ok / len(CASES):.0f}%)")
for q, wants, got in misses:
    print(f"  MISS {q!r}  wanted {wants}  got {got}")
