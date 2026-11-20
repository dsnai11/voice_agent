"""How well does Ria pick the right approved answer for a question she has never seen? A fresh set of customer questions (not copied from the
bank's own examples), each with the topic that should answer it ("NONE" = no approved answer should fire).

    python train/bank_eval.py            shows accuracy and every miss, so the bank can be improved from real phrasings
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import replybank

CASES = [
    # who / why / trust
    ("aap kis company se bol rahe ho", "who_are_you"), ("aap kaun hain kahan se call kar rahe ho", "who_are_you"), ("kis wajah se phone kiya aapne", "why_call"), ("mujhe call kyun aaya hai", "why_call"),
    ("mera number aapko kisne diya", "number_source"), ("ye number kahan se mila aapko", "number_source"), ("abhi main driving kar raha hoon baad mein baat karte hain", "busy_callback"), ("meeting mein hoon thodi der baad call karna", "busy_callback"),
    ("mujhe koi loan nahi chahiye", "not_interested"), ("mujhe isme koi interest nahi hai", "not_interested"), ("meri koi zaroorat nahi hai", "not_interested"),
    ("mujhe aur call mat karna", "stop_calling"), ("mera number list se hata do", "stop_calling"), ("galat number laga hai maine loan liya hi nahi", "wrong_number"),
    ("kya aap insaan ho ya machine", "are_you_robot"), ("ye bot hai kya", "are_you_robot"), ("kya ye fraud call hai", "fraud_check"), ("aap sach mein lakshmi finance se ho na", "fraud_check"),
    ("kya main apna otp bata dun", "otp_safety"), ("aap otp maangoge kya", "otp_safety"),
    # eligibility
    ("kitna loan mil sakta hai mujhe", "how_much_loan"), ("maximum kitne ka loan milega", "how_much_loan"), ("kya mera loan pass ho jayega", "will_i_get_loan"), ("mujhe loan milega ya nahi", "will_i_get_loan"),
    ("loan ke liye kya eligibility hai", "eligibility"), ("kaun log loan le sakte hain", "eligibility"), ("meri salary sirf 12000 hai kya loan milega", "low_salary"), ("kam salary par loan milta hai kya", "low_salary"),
    ("mera cibil bahut kam hai kya loan milega", "low_cibil"), ("credit score kharab hai loan ho sakta hai", "low_cibil"), ("mera apna dhandha hai kya mujhe loan mil sakta hai", "self_employed"),
    ("main abhi naye job mein hoon", "new_job"), ("kitni umar tak loan milta hai", "age_limit"), ("meri age 62 saal hai loan milega", "age_limit"),
    # documents, charges, rate
    ("loan ke liye kaun kaun se papers dene honge", "documents"), ("kya kya kagaz chahiye apply karne ke liye", "documents"), ("salary slip nahi hai to kya karun", "no_salary_slip"),
    ("processing fees kitna katega", "processing_fee"), ("file charge kitna lagta hai", "processing_fee"), ("koi chhipe hue charges to nahi hain na", "hidden_charges"), ("aur koi extra charge lagega kya", "hidden_charges"),
    ("byaaj dar kitni hai", "interest_rate"), ("kitne percent interest lagega", "interest_rate"), ("loan kitne mahine ke liye milta hai", "tenure"), ("kitne saal mein chukana hoga", "tenure"),
    ("emi kitni banegi 5 lakh par", "emi_amount"), ("mahine ki kist kitni hogi", "emi_amount"), ("loan pehle band kar du to charge lagega kya", "prepayment"), ("foreclosure charges kitne hain", "prepayment"),
    ("is loan se mere cibil par kya asar padega", "cibil_impact"), ("kya guarantor dena padega", "guarantor"), ("kisi ko zamanat deni hogi kya", "guarantor"),
    ("apply kaise karna hai", "how_apply"), ("loan lene ka process batao", "how_apply"), ("paisa kitne ghante mein aata hai", "disbursal_time"), ("loan kitni jaldi mil jata hai", "disbursal_time"),
    # products
    ("payday loan kya hota hai", "payday_loan"), ("salary advance wala loan hai kya", "salary_loan"), ("kaun sa loan mere liye theek rahega", "which_loan"), ("personal loan aur payday loan mein farak kya hai", "which_loan"),
    # safety / trust
    ("meri jaankari safe rahegi na", "data_safety"), ("mera data kahin share to nahi hoga", "data_safety"), ("kya aapki company rbi se registered hai", "rbi_registered"), ("rbi ka registration number kya hai", "rbi_registered"),
    ("main thoda soch ke batata hoon", "think_about_it"), ("mujhe sochne ka time chahiye", "think_about_it"), ("dusri company kam interest de rahi hai", "compare_lender"),
    # existing customers
    ("mere pehle se loan chal rahe hain", "existing_loan"), ("mera loan ka status kya hai abhi", "status_check"), ("mera loan approve hua ki nahi", "status_check"), ("emi kaise bharni hai", "payment_how"), ("emi ka payment kahan karun", "payment_how"),
    ("late fee kitni lagti hai", "late_fee"), ("emi bounce hone par kitna charge hai", "late_fee"), ("paise nahi hain abhi emi nahi bhar sakta", "hardship"), ("meri naukri chali gayi hai", "hardship"),
    ("mujhe baar baar call karke pareshan mat karo", "harassment"), ("aap log dhamki de rahe ho", "harassment"), ("meri complaint kahan darj karun", "complaint"), ("shikayat karni hai kisse baat karun", "complaint"),
    ("customer care ka number do", "office_info"), ("office kitne baje tak khula rehta hai", "office_info"), ("loan band karne ka no dues certificate chahiye", "closure_papers"),
    ("whatsapp par details bhej do", "whatsapp_sms"), ("sms mein bhej dijiye", "whatsapp_sms"), ("app mein login nahi ho raha", "app_issue"),
    # general finance
    ("apr kya hota hai", "what_is_apr"), ("flat aur reducing rate mein kya fark", "flat_vs_reducing"), ("kyc ka matlab kya hai", "what_is_kyc"), ("e nach kya hota hai", "what_is_nach"), ("emi miss ho jaye to kya hoga", "emi_bounce_effect"),
    ("fd kya hoti hai", "what_is_fd"), ("nbfc ka matlab kya hai", "nbfc_vs_bank"), ("upi aur imps mein kya farak hai", "upi_neft"), ("free credit report kaise nikalte hain", "free_credit_report"),
    ("cibil score ko kaise sudhaare", "improve_cibil"), ("cooling off period ka kya matlab hai", "cooling_off"), ("online fraud ho jaye to kahan report karen", "report_fraud"),
    ("gold loan kaise milta hai", "gold_loan_info"), ("credit card better hai ya personal loan", "card_vs_loan"), ("overdraft ka matlab kya hai", "what_is_overdraft"),
    ("top up loan kya hota hai", "top_up"), ("account kholna hai mujhe", "open_account"), ("koi offer hai kya abhi", "offers"), ("mera credit score kitna hai", "my_credit_score"), ("meri file jaldi clear kar do", "file_clear"),
    ("mujhe urgent paisa chahiye aaj hi", "instant_loan"), ("aapki company ka malik kaun hai", "company_facts_unknown"), ("sensex aaj kitna hai", "live_rates_unknown"), ("mutual fund kharidna chahiye kya", "invest_advice"),
    ("aap kaise ho", "small_talk"), ("mujhe ek aur sawal poochna hai", "more_to_discuss"), ("aapka office kahan hai address batao", "office_address"),
    # nothing should answer these
    ("haan theek hai", "NONE"), ("mera naam rahul hai", "NONE"), ("5 lakh", "NONE"), ("jaipur", "NONE"), ("aaj mausam bahut accha hai", "NONE"), ("main office ja raha hoon", "NONE"),
]
ok = 0
misses = []
for q, want in CASES:
    got = [m["id"] for m in replybank.match(q) if m["score"] >= (0.5 if m["entry"].get("require") else 0.6)]
    good = (not got) if want == "NONE" else (want in got[:1])
    ok += good
    if not good:
        misses.append((q, want, [(m["id"], m["score"]) for m in replybank.match(q)][:2]))
print(f"approved-answer accuracy on {len(CASES)} fresh customer questions: {ok}/{len(CASES)} ({100 * ok / len(CASES):.0f}%)")
for q, want, got in misses:
    print(f"  MISS {q!r}\n       wanted {want}, got {got}")
sys.exit(0)
