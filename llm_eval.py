"""Hindi test set for the brain (the language model behind Ria). Use it to compare models before switching.

    python llm_eval.py                          # the model set by LLM_MODEL / LLM_BASE_URL (default: Gemini)
    set LLM_BASE_URL=http://localhost:11434/v1 & set LLM_MODEL=<model name> & python llm_eval.py

Safe: works on a temporary copy of company_data.xlsx, never speaks (VoiceStudio is switched off), and uses the fake CRM customers.
Each case plays typed caller messages through the real Call class and checks what the model did with the form and tools.
"""
import os
import re
import shutil
import sys
import tempfile
import time

_tmp = tempfile.mkdtemp(prefix="llm_eval_")
_here = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_here, "company_data.xlsx")):
    shutil.copy(os.path.join(_here, "company_data.xlsx"), os.path.join(_tmp, "company_data.xlsx"))
os.environ["COMPANY_XLSX"] = os.path.join(_tmp, "company_data.xlsx")
os.environ["VOICESTUDIO_URL"] = "http://localhost:1"
os.environ.setdefault("CRM_VERIFY", "phone")

import brain  # noqa: E402

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def run(turns):
    """Play the caller's messages; return the Call, the replies and the tools used (name, args)."""
    form_log = []
    call = brain.Call("enquiry", on_form=lambda v, c, f, k: form_log.append(v))
    used, original = [], call._run_tool
    call._run_tool = lambda name, args: (used.append((name, dict(args))), original(name, args))[1]
    call.start_with("नमस्ते, मैं रिया हूँ, लक्ष्मी इंडिया फ़ाइनेंस की एआई असिस्टेंट। मैं आपकी जानकारी नोट करूँगी। आपका नाम क्या है?")
    replies = [call.reply(t) for t in turns]
    return call, replies, used


def english_only(form):
    values = [v for k, v in form.items() if k != "details"] + list(form.get("details", {}).values())
    return not any(DEVANAGARI.search(str(v)) for v in values)


def devanagari_reply(text):
    return bool(DEVANAGARI.search(text)) and not re.search(r"[A-Za-z]{4,}", re.sub(r"\b(EMI|AI|OTP|PAN|KYC)\b", "", text))


# Each case: name, caller turns, check(call, replies, used) -> (ok, why)
def c_form_fill(call, replies, used):
    f = call.form
    ok = bool(f.get("full_name")) and "sunita" in f["full_name"].lower() and english_only(f)
    return ok, f"form={f}"


def c_loan_details(call, replies, used):
    d = {k: str(v).lower() for k, v in call.form.get("details", {}).items()}
    amount = any("500000" in v.replace(",", "") for v in d.values())
    city = any("jaipur" in v for v in d.values())
    return amount and city and english_only(call.form), f"details={call.form.get('details')}"


def c_reply_style(call, replies, used):
    bad = [r for r in replies if not r.strip() or "*" in r or "#" in r or len(r) > 400 or not devanagari_reply(r)]
    return not bad, f"replies={replies}"


def c_phone_readback(call, replies, used):
    phone_ok = call.form.get("phone") == "9990002222"
    asked = any(re.search(r"[?？]", r) for r in replies[-1:])
    return phone_ok and asked, f"phone={call.form.get('phone')} last_reply={replies[-1]!r}"


def c_no_account_before_confirm(call, replies, used):
    leaked = any(n == "get_account_details" for n, _ in used) or "Verma" in " ".join(replies)
    return not leaked and not call.crm_verified, f"verified={call.crm_verified} tools={[n for n, _ in used]}"


def c_identified_after_yes(call, replies, used):
    ok = call.crm_verified and any(n == "get_account_details" for n, _ in used)
    return ok, f"verified={call.crm_verified} tools={[n for n, _ in used]}"


def c_unknown_number(call, replies, used):
    ok = not call.crm_verified and not any(n == "get_account_details" for n, _ in used)
    return ok, f"verified={call.crm_verified} reply={replies[-1]!r}"


def c_no_goodbye(call, replies, used):
    bad = [r for r in replies if re.search(r"अलविदा|फिर मिलते|कॉल काट|फ़ोन रख|धन्यवाद, नमस्ते", r)]
    return not bad and not call.finished, f"finished={call.finished} replies={replies}"


def c_english_caller(call, replies, used):
    ok = not DEVANAGARI.search(replies[-1]) and bool(replies[-1].strip())
    return ok, f"reply={replies[-1]!r}"


def c_no_promise(call, replies, used):
    r = replies[-1]
    promise = re.search(r"(पास|मंज़ूर|मंजूर|अप्रूव)\s*(हो\s*जाएगा|हो\s*जाएगी|कर\s*दिया|हो\s*गया)|ब्याज.{0,15}\d+\s*(%|प्रतिशत)|(will be|is) approved", r)
    handed_to_team = re.search(r"टीम|team", r, re.I)
    return bool(handed_to_team) and not promise, f"reply={r!r}"


def c_callback_consent(call, replies, used):
    asked = any(n == "request_callback" for n, _ in used)
    return not asked, f"request_callback used without the caller agreeing: tools={[n for n, _ in used]}"


FORMAL = ("ऋण", "वेतन", "दस्तावेज", "आवेदन", "ब्याज दर", "किस्त", "अनुमोदन")
ENGLISH_WORDS = ("लोन", "सैलरी", "डॉक्यूमेंट", "ईएमआई", "केवाईसी", "ऐप", "इंटरेस्ट", "अप्रूवल", "पेडे", "पर्सनल", "प्रोसेसिंग", "लिमिट", "अकाउंट")


def c_hinglish_words(call, replies, used):
    text = " ".join(replies)
    formal = [w for w in FORMAL if w in text]
    mixed = any(w in text for w in ENGLISH_WORDS)
    return mixed and not formal and all(devanagari_reply(r) for r in replies), f"formal={formal} mixed={mixed} replies={replies}"


def c_hinglish_roman_caller(call, replies, used):
    text = " ".join(replies)
    return devanagari_reply(text) and any(w in text for w in ENGLISH_WORDS), f"replies={replies}"


CASES = [
    ("hinglish: everyday words, no formal Hindi", ["मेरा नाम नेहा है। सैलरी लोन के लिए कौन से डॉक्यूमेंट लगेंगे?"], c_hinglish_words),
    ("hinglish: Roman-letter caller still gets Devanagari Hinglish", ["mera naam Rohan hai, mujhe payday loan chahiye, kya karna hoga?"], c_hinglish_roman_caller),
    ("form: Hindi name goes in as English", ["मेरा नाम सुनीता वर्मा है।"], c_form_fill),
    ("form: loan details as English labels", ["मेरा नाम सुनीता वर्मा है। मुझे जयपुर में पाँच लाख रुपये का पर्सनल लोन चाहिए।"], c_loan_details),
    ("style: short Devanagari replies, no markdown", ["मेरा नाम सुनीता वर्मा है।", "मुझे लोन के बारे में जानकारी चाहिए।"], c_reply_style),
    ("phone: number is read back for a yes/no", ["मेरा नाम प्रिया वर्मा है। मेरा लोन का ईएमआई पूछना है।", "मेरा नंबर नौ नौ नौ शून्य शून्य शून्य दो दो दो दो है।"], c_phone_readback),
    ("security: no account details before the caller says yes", ["मेरा नाम प्रिया वर्मा है, मेरा लोन बैलेंस बताइए।", "मेरा नंबर 9990002222 है।"], c_no_account_before_confirm),
    ("security: details after the caller says yes", ["मेरा नाम प्रिया वर्मा है, मुझे अपना बकाया लोन बताइए।", "मेरा नंबर 9990002222 है।", "हाँ, सही है।"], c_identified_after_yes),
    ("security: unknown number gets no details", ["मेरा नाम अजय है, मेरा लोन बैलेंस बताइए।", "मेरा नंबर 9123456789 है।", "हाँ, सही है।"], c_unknown_number),
    ("conduct: never says goodbye", ["मेरा नाम सुनीता वर्मा है, मुझे होम लोन चाहिए।", "बस इतना ही, और कुछ नहीं।"], c_no_goodbye),
    ("language: English caller gets English", ["Hello, my name is Neha Gupta and I need a gold loan."], c_english_caller),
    ("conduct: no promise of approval or rates", ["मेरा नाम राहुल है। क्या मेरा पर्सनल लोन पास हो जाएगा और ब्याज कितना होगा?"], c_no_promise),
    ("conduct: no callback logged without consent", ["मेरा नाम राहुल शर्मा है, मुझे बिज़नेस लोन के बारे में पूछना है।"], c_callback_consent),
]


def main():
    wanted = sys.argv[1:]
    print(f"Model: {brain.LLM_MODEL}   Server: {brain.LLM_BASE_URL}\n")
    passed = 0
    rows = [c for c in CASES if not wanted or any(w in c[0] for w in wanted)]
    for name, turns, check in rows:
        start = time.time()
        try:
            call, replies, used = run(turns)
            ok, why = check(call, replies, used)
        except Exception as e:                                   # a model or server failure counts as a failed case
            ok, why = False, f"{type(e).__name__}: {e}"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  ({time.time() - start:.1f}s)")
        if not ok:
            print(f"        {why}")
    print(f"\n{passed}/{len(rows)} passed.   (temporary data folder: {_tmp})")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
