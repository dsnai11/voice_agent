"""The honest test: customer questions that were NOT used to write or tune any approved-answer example. Several acceptable topics are listed for
questions where two answers would both be right.   python train/bank_holdout.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import replybank

CASES = [
    ("aap ne call kisliye kiya", ["why_call"]), ("mera mobile number aapke paas kaise aaya", ["number_source"]), ("kisne bataya aapko mera number", ["number_source"]),
    ("abhi bahar hoon shaam ko call karna", ["busy_callback"]), ("thodi der baad phone karo main busy hoon", ["busy_callback"]), ("mujhe is sab mein dilchaspi nahi hai", ["not_interested"]),
    ("mera number apni list se nikal do", ["stop_calling"]), ("aage se phone nahi aana chahiye", ["stop_calling"]), ("dnd lagwa do mere number par", ["stop_calling"]),
    ("kya main kisi computer se baat kar raha hoon", ["are_you_robot"]), ("aap asli insaan ho kya", ["are_you_robot"]), ("aap sach bol rahe ho na ye thagi to nahi", ["fraud_check"]),
    ("kaise pata chalega ki ye asli company hai", ["fraud_check"]), ("agar koi otp maange to de dun kya", ["otp_safety"]), ("otp kisi ko batana chahiye kya", ["otp_safety"]),
    ("kitne rupaye tak ka loan de dete ho", ["how_much_loan"]), ("mujhe zyada se zyada kitna loan mil jayega", ["how_much_loan"]), ("loan lene ke liye kya shartein hain", ["eligibility"]),
    ("main eligible hoon ya nahi kaise pata chalega", ["eligibility", "will_i_get_loan"]), ("meri tankhwah bahut kam hai kya fir bhi loan milega", ["low_salary"]), ("10000 ki salary par loan milta hai kya", ["low_salary"]),
    ("main dukandar hoon kya mujhe milega loan", ["self_employed"]), ("business wale logon ko loan dete ho kya", ["self_employed"]), ("abhi 3 mahine hue naukri lage hue loan mil sakta hai kya", ["new_job"]),
    ("kitni age tak loan de dete ho", ["age_limit"]), ("main 58 saal ka hoon mil sakta hai kya", ["age_limit"]), ("papers kya kya chahiye honge", ["documents"]),
    ("mujhe kaun se kagzaat dene padenge", ["documents"]), ("aadhar pan ke alawa kya lagega", ["documents"]), ("loan ki processing mein kitna paisa kat jayega", ["processing_fee"]),
    ("fees kitni hogi file ki", ["processing_fee"]), ("koi aur kharcha to nahi hai na", ["hidden_charges"]), ("aur kya kya charges lagte hain", ["hidden_charges", "processing_fee"]),
    ("kitna byaaj lagega mujh par", ["interest_rate"]), ("interest ka percent kya hai", ["interest_rate"]), ("kitne mahine mein chukana padega", ["tenure"]), ("loan ki avadhi kitni hoti hai", ["tenure"]),
    ("3 lakh ki emi kitni aayegi", ["emi_amount"]), ("har mahine kitna dena padega", ["emi_amount"]), ("time se pehle loan khatam karne par kuch katega kya", ["prepayment"]),
    ("poora loan ek saath chuka du to", ["prepayment"]), ("kya kisi ko saath mein dena padega", ["guarantor", "what_is_guarantor"]), ("zamin chahiye kya", ["guarantor"]),
    ("loan lena hai kya karna hoga", ["how_apply"]), ("kaise apply kar sakta hoon", ["how_apply"]), ("paisa kab tak mil jayega", ["disbursal_time"]), ("kitne din lagte hain loan aane mein", ["disbursal_time"]),
    ("payday loan mein kya hota hai", ["payday_loan"]), ("pay day loan ka matlab samjhao", ["payday_loan"]), ("salary loan kya hai", ["salary_loan"]), ("salary ke against loan milta hai kya", ["salary_loan"]),
    ("personal ya salary loan konsa lena chahiye", ["which_loan"]), ("kaun sa loan sabse accha rahega mere liye", ["which_loan"]), ("meri details koi aur dekhega to nahi", ["data_safety"]),
    ("mera personal data surakshit hai kya", ["data_safety"]), ("kya aap rbi ke under aate ho", ["rbi_registered"]), ("company ka licence hai kya", ["rbi_registered"]),
    ("main baad mein sochkar batata hoon", ["think_about_it"]), ("abhi hum soch rahe hain", ["think_about_it"]), ("bajaj finance mein kam interest hai", ["compare_lender"]),
    ("dusri jagah sasta mil raha hai", ["compare_lender"]), ("mera ek loan pehle se chal raha hai kya dusra milega", ["existing_loan"]), ("mere upar already loan hai", ["existing_loan"]),
    ("mere loan ka kya hua", ["status_check"]), ("application ki sthiti batao", ["status_check"]), ("emi kaise bharni padti hai", ["payment_how"]), ("kist kahan jama karni hai", ["payment_how"]),
    ("emi late hone par kitna charge", ["late_fee"]), ("payment miss hone par penalty kitni", ["late_fee"]), ("mera kitna paisa baki hai", ["overdue_collections", "status_check"]),
    ("meri kitni emi pending hai", ["overdue_collections", "status_check"]), ("abhi paisa nahi hai thoda time chahiye", ["hardship"]), ("business band ho gaya emi nahi de sakta", ["hardship"]),
    ("ye loan mera nahi hai", ["dispute_loan"]), ("maine ye loan nahi liya", ["dispute_loan"]), ("mujhe shikayat darj karwani hai", ["complaint"]), ("complaint kaise karun", ["complaint"]),
    ("dhamkiyan mat do mujhe", ["harassment"]), ("customer care ka phone number kya hai", ["office_info"]), ("office timing batao", ["office_info"]), ("kya aap english mein baat kar sakti ho", ["language"]),
    ("hindi mein baat karo", ["language"]), ("aapki awaaz nahi aa rahi", ["not_heard"]), ("hello hello kuch sunai nahi de raha", ["not_heard"]), ("mujhe samajh nahi aaya dobara batao", ["not_understood"]),
    ("thoda aaram se samjhao", ["not_understood"]), ("app khul nahi raha", ["app_issue"]), ("app mein error aa raha hai", ["app_issue"]), ("loan close hone ke baad noc kaise milega", ["closure_papers"]),
    ("no due certificate chahiye", ["closure_papers"]), ("link bhej do whatsapp par", ["whatsapp_sms"]), ("message mein bhej dena", ["whatsapp_sms"]),
    ("annual percentage rate matlab", ["what_is_apr"]), ("flat interest sasta hai ya reducing", ["flat_vs_reducing"]), ("kyc kyun karni padti hai", ["what_is_kyc"]), ("auto debit kaise hota hai", ["what_is_nach"]),
    ("emi miss hui to cibil par kya asar padega", ["emi_bounce_effect", "late_fee", "cibil_impact"]), ("fixed deposit kya hoti hai", ["what_is_fd"]), ("nbfc aur bank mein kya antar hai", ["nbfc_vs_bank"]),
    ("neft aur rtgs mein kya fark hai", ["upi_neft"]), ("free cibil report kahan se milegi", ["free_credit_report"]), ("cibil score kaise theek karein", ["improve_cibil"]),
    ("loan lene ke baad wapas kar sakte hain kya", ["cooling_off"]), ("online thagi ho gayi kahan complaint karun", ["report_fraud"]), ("bank mein jama paisa surakshit hai kya", ["deposit_safe"]),
    ("sone par loan kya hota hai", ["gold_loan_info"]), ("credit card ya loan kaun sa sahi hai", ["card_vs_loan"]), ("overdraft kya hai", ["what_is_overdraft"]),
    ("mujhe top up chahiye purane loan par", ["top_up"]), ("mujhe bank account khulwana hai", ["open_account"]), ("kuch discount ya offer hai kya", ["offers"]), ("mera cibil score kya chal raha hai", ["my_credit_score"]),
    ("meri file approve karwa do", ["file_clear"]), ("mujhe aaj hi loan chahiye", ["instant_loan"]), ("company ke director ka naam kya hai", ["company_facts_unknown"]), ("aaj sona kitne ka hai", ["live_rates_unknown"]),
    ("share market mein paisa lagaun kya", ["invest_advice"]), ("aap kaisi hain", ["small_talk"]), ("mujhe aapse aur kuch poochna tha", ["more_to_discuss"]), ("aapka head office kahan par hai", ["office_address"]),
    ("emi ka matlab kya hota hai", ["what_is_emi"]), ("cibil score kya cheez hai", ["what_is_cibil"]), ("kitne cibil par loan milta hai", ["cibil_required", "low_cibil"]),
    ("ji haan", ["NONE"]), ("theek hai", ["NONE"]), ("arjun sharma", ["NONE"]), ("do lakh", ["NONE"]), ("udaipur", ["NONE"]), ("main job karta hoon", ["NONE"]), ("kal subah 10 baje", ["NONE"]),
]
ok = 0
misses = []
for q, wants in CASES:
    got = [m["id"] for m in replybank.match_hybrid(q) if m["score"] >= (0.5 if m["entry"].get("require") else 0.6) and m["id"] not in ("off_topic",)]
    good = (not got) if wants == ["NONE"] else (bool(got) and got[0] in wants)
    ok += good
    if not good:
        misses.append((q, wants, [(m["id"], m["score"]) for m in replybank.match_hybrid(q)][:2]))
print(f"HOLD-OUT accuracy (questions never used for training): {ok}/{len(CASES)} ({100 * ok / len(CASES):.0f}%)")
for q, wants, got in misses:
    print(f"  MISS {q!r}  wanted {wants}  got {got}")
sys.exit(0)
