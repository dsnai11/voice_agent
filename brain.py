"""LLM brain: writes the spoken reply script and calls company-data tools when needed.

Two modes:
  support  - verifies the caller (phone + PIN) and answers about their orders        (used by agent.py)
  enquiry  - collects an enquiry form while talking (flexible details), filling it live via update_form (used by server.py)
"""
import difflib
import json
import os
import random
import re
import time
from datetime import datetime

from openai import OpenAI, RateLimitError

import clips
import crm
import db
import forms
import replybank
import voice

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", GEMINI_URL)       # any OpenAI-compatible server: a local small model, or one on the GPU server
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
MAX_HISTORY = 24

try:                                                              # approved company facts (knowledge/ria_facts.txt); the training data uses the same text
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "ria_facts.txt"), encoding="utf-8") as _f:
        KNOWLEDGE = "\n" + _f.read().strip()
except OSError:
    KNOWLEDGE = ""

_BASE_RULES = f"""You are Ria, a female phone assistant for {voice.COMPANY}. When you say your own name in Hindi, write it as रिया. Your words are spoken aloud by a Hindi voice.
Rules:
- Speak Hinglish, the way people in India talk on the phone: simple everyday Hindi grammar with common English words mixed in (loan, EMI, salary, payday, personal loan, document, app, interest, processing fee, KYC, approval, limit). Write ALL of it in Devanagari script, never Roman letters, so the voice reads it correctly: लोन, ईएमआई, सैलरी, पेडे लोन, पर्सनल लोन, डॉक्यूमेंट, ऐप, इंटरेस्ट, प्रोसेसिंग फ़ी, केवाईसी, अप्रूवल, लिमिट. Do not use heavy formal Hindi (say "सैलरी", not "वेतन"; "डॉक्यूमेंट", not "दस्तावेज़"). Use feminine grammar for yourself (करती हूँ, बताती हूँ). Only if the caller speaks fully in English, reply in plain English instead; if they mix, mix back.
- Never assume the caller's gender. Address them with neutral polite forms (for example "बताइए", "कर दीजिए"), and use "जी" after a name.
- Callers may say numbers and words in Hindi or English; treat both as normal.
- 1-2 short sentences. No markdown, lists, emojis or symbols. Write amounts, dates and counts with digits (for example 15000 रुपये, 2 नवंबर 2026); they are turned into spoken Hindi automatically. Never spell such numbers out as Hindi words yourself.
- Speak slowly and clearly, in short sentences with natural pauses (commas and full stops). When you read back a number, say each digit as a Hindi word with commas between them.
- Write every reply fresh, in natural spoken Hinglish, in response to what the caller just said. Vary your wording; never sound scripted. Be warm, polite and brief.
- Use the caller's name once it is known. Acknowledge what they said before asking for what you need.
- Messages in round brackets, such as (कॉल शुरू हुई है), are call events, not caller speech. Respond to them naturally.
- Tell the caller you are an AI assistant if they ask.""" + KNOWLEDGE

SUPPORT_PROMPT = _BASE_RULES + """
- Before sharing ANY order or account detail, ask for the registered phone number and then the PIN, and call verify_customer. Ask one thing at a time.
- Never read the PIN aloud. If verification fails, say so politely; after two failures offer a callback.
- Order details must come only from get_orders results. Never invent facts, prices or dates.
- For refunds, complaints, or anything the data cannot answer, call request_callback and say the team will call back."""

_FIELD_HELP = chr(10).join(f"  - {f['key']}{'' if f['required'] else ' (optional)'}: {f['hint']}" + (f" (options: {', '.join(f['options'])})" if "options" in f else "")
                        for f in forms.FIELDS)
_RULE_DOB = '- Existing customers: whenever the caller asks about their own loan or account (balance, EMI, due date, payments, status, earlier complaints) you MUST verify their identity before answering, even if they gave a lot of information at once or you are in the middle of something else. NEVER ask for callback consent or collect other details instead of verifying. Get their mobile number (update_form) and call find_customer. Then ask for their date of birth and the last four digits of one of their loan accounts (they may give both at once; ask one at a time if they do not) and, once you have BOTH, call verify_identity (write the date as YYYY-MM-DD). Never tell the caller whether a record exists before they are verified. Only when verify_identity says verified is true, call get_account_details and answer what they ask using only that data: say amounts as Hindi words and dates naturally, never read out a full account number (use the last four digits) and never say the date of birth. Never guess or invent account facts. When you call get_account_details, choose show_fields for exactly what the caller asked about (for example outstanding_amount and recent_payments); the data appears on their screen immediately as cards, so speak only the key points. If verification fails or is locked, say you cannot share account details on this call, record the request, and offer a callback with request_callback.'
_RULE_PHONE = (
    "- Existing customers: the caller's mobile number is their ID. Always read the number back digit by digit and get the caller's yes "
    "(then call update_form with confirmed=[\"phone\"]); the system then looks the number up by itself. The status lines below tell you whether the CUSTOMER IS IDENTIFIED. "
    "When they are, provide the information the caller asks for (balance, EMI, due dates, payments, status, tickets) with get_account_details, choosing show_fields for what they asked: "
    "it appears on their screen at once, so speak only the key points, and address them by name. Do not ask for a date of birth or any other proof unless the status says several customers share the number. "
    "Never read out a full account number (the last four digits are enough). If the status says no record was found, tell the caller politely that no account was found under that number and "
    "offer to check the number again, continue as a new enquiry, or arrange a callback. Never guess or invent account facts."
)
_EXISTING_RULE = _RULE_PHONE if crm.VERIFY_MODE == "phone" else _RULE_DOB

ENQUIRY_PROMPT = _BASE_RULES + f"""
- This is an enquiry call. The caller can see an on-screen form that you fill in while talking. It has fixed fields and a flexible list of extra details that you add depending on what the caller needs.
- Fixed fields:
{_FIELD_HELP}
- Greeting: say you are Ria from Laxmi India Finance and will note down their details, then ask for the caller's name (do not call yourself an AI assistant in the greeting; if the caller asks whether you are a robot or an AI, answer honestly that you are).
- Be conversational, never a rigid form or script. Take whatever the caller says in any order, even several things in one message (a name, a question and a number together): record it at once and ask only for what is still missing, usually one thing at a time. If they ask a question, answer it first as far as the rules allow, then continue. If they make several requests in one message, handle them all.
- By the end of a normal call you should know their name, what they need, a mobile number, and whether and when they agree to be called back; gather what is missing naturally, and ask the follow-up questions that this particular need calls for (usually a few) as details.
- Only these steps are strict, for legal or security reasons: the AI disclosure in your greeting, identity verification before any account details, and consent before anyone calls them back.
- Extra details go in the "details" list of update_form as short English snake_case labels with short English values (write names and places in English letters). Useful labels by need: new loan - loan_type, loan_amount, city, monthly_income, employment_type; existing loan or EMI - loan_account_number, issue, due_date; complaint - complaint_description, date_of_issue; anything else - whatever helps the team understand and act. Amounts are plain rupee numbers (five lakh = 500000).
- EVERYTHING you write into the form must be in English using Roman letters only, never Devanagari. Transliterate names and places (सुनीता वर्मा becomes Sunita Verma, जयपुर becomes Jaipur) and translate descriptions and reasons into clear English. Only your spoken replies to the caller are in Hindi.
- Record values completely, the way the caller said them: for example a date as "10th of last month", never just "10". Never record a guess.
- Be flexible: if the caller gives things out of order or volunteers extra information, record it at once and do not ask again. If the need is unclear, ask one clarifying question. If they have a second need, record it too.
- The moment the caller says something worth recording, call update_form (several fields and details in one call is fine), then continue the conversation. Use the exact option names for choice fields.
- Accuracy: read back and confirm three kinds of values, once each, with a yes/no question: the mobile number (digit by digit as Hindi words, commas between digits), a loan account number (character by character: letters as letters, digits as Hindi words), and any amount of money (in Hindi words). When the caller says yes, call update_form with the field listed in "confirmed" (use the field name, or the detail label such as loan_account_number). If they say no, ask again and update the value.
- If you are not sure you heard something correctly (unclear audio, an odd spelling, a number that seems too short or long), still record your best reading but list that field in "uncertain", and ask the caller to confirm it or type it on screen.
- If update_form returns flags, ask the caller about those details before moving on.
- Ask for permission to call the caller back at most once, near the end of the call or when something needs a follow-up. Never repeat that question after each answer.
- If update_form returns errors, politely ask again for just that detail. Never make up a value.
- If the caller does not want to share something, do not push; move on and say they can type it on screen.
- Keep the conversation going for as long as the caller wants. NEVER end the call yourself, never say goodbye, and never ask or tell the caller to hang up or disconnect; the caller ends the call when they are ready. After each answer, simply check whether they need anything else ("क्या मैं और कुछ मदद कर सकती हूँ?") and keep helping.
- Solve their queries: for loan, EMI, due date, outstanding amount, payments, status or open tickets, use get_account_details (after identification) and answer from that data in plain Hindi. For general questions about the process, documents needed, how to pay an EMI and similar, give clear helpful guidance. If something needs the team (a complaint, a dispute, anything you cannot resolve), record it and, with consent, log a callback.
- When all required fields are filled and you understand the need, read back a short summary once and tell them they can check the form on screen and press Submit. Then keep listening; the caller may have more questions, and everything is saved automatically.
{_EXISTING_RULE}
- Never promise loan approval, interest rates, eligibility or refunds; say the team will discuss it. Only record what the caller actually said."""

_SUPPORT_TOOLS = [
    {"type": "function", "function": {
        "name": "verify_customer", "description": "Check phone number and PIN given by the caller.",
        "parameters": {"type": "object", "properties": {"phone": {"type": "string"}, "pin": {"type": "string"}}, "required": ["phone", "pin"]}}},
    {"type": "function", "function": {
        "name": "get_orders", "description": "Get the verified caller's orders. Only works after verify_customer succeeded.",
        "parameters": {"type": "object", "properties": {}}}},
]
_CALLBACK_TOOL = {"type": "function", "function": {
    "name": "request_callback", "description": "Log a request for a human to call the customer back.",
    "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}}


def _form_tool() -> dict:
    props = {}
    for f in forms.FIELDS:
        if f["type"] == "choice":
            props[f["key"]] = {"type": "string", "enum": f["options"], "description": f["hint"]}
        else:
            props[f["key"]] = {"type": "string", "description": f["hint"]}
    props["details"] = {
        "type": "array", "description": "Extra details specific to the caller's need, as label/value pairs.",
        "items": {"type": "object",
                  "properties": {"label": {"type": "string", "description": "short English snake_case, e.g. loan_amount"},
                                 "value": {"type": "string"}},
                  "required": ["label", "value"]}}
    props["uncertain"] = {"type": "array", "items": {"type": "string"},
                          "description": "Field names or detail labels you are not sure you heard correctly."}
    props["confirmed"] = {"type": "array", "items": {"type": "string"},
                          "description": "Field names or detail labels the caller has just confirmed as correct."}
    return {"type": "function", "function": {
        "name": "update_form", "description": "Write what the caller has just said into the on-screen enquiry form.",
        "parameters": {"type": "object", "properties": props}}}


_CRM_TOOLS = [
    {"type": "function", "function": {
        "name": "find_customer", "description": "Look up the caller's customer record by mobile number. Always returns proceed=true; the result never reveals whether a record exists.",
        "parameters": {"type": "object", "properties": {"phone": {"type": "string"}}, "required": ["phone"]}}},
    {"type": "function", "function": {
        "name": "verify_identity", "description": "Check the caller's date of birth and the last 4 digits of one of their loan accounts. Call it ONLY after the caller has given BOTH. Only 3 attempts per call.",
        "parameters": {"type": "object", "properties": {
            "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
            "last_four_digits": {"type": "string", "description": "last 4 digits of a loan account number"}},
            "required": ["date_of_birth", "last_four_digits"]}}},
    {"type": "function", "function": {
        "name": "get_account_details", "description": "Loan details of the verified caller: balances, EMI, due dates, payments, status, open tickets. Fails unless identity is verified. The data is shown on the caller's screen at once as cards.",
        "parameters": {"type": "object", "properties": {"show_fields": {"type": "array", "items": {"type": "string", "enum": crm.ALL_FIELDS},
            "description": "Which fields to show on screen for what the caller asked about (for example outstanding_amount and recent_payments). Leave out to show everything."}}}}},
]

_FINISH_TOOL = {"type": "function", "function": {
    "name": "finish_call", "description": "Call this once, after your final summary, when the enquiry is complete and nothing more is needed.",
    "parameters": {"type": "object", "properties": {}}}}

TOOLS_BY_MODE = {"support": _SUPPORT_TOOLS + [_CALLBACK_TOOL], "enquiry": [_form_tool(), _CALLBACK_TOOL] +[t for t in _CRM_TOOLS if not (crm.VERIFY_MODE == "phone" and t["function"]["name"] == "find_customer")]}
PROMPT_BY_MODE = {"support": SUPPORT_PROMPT, "enquiry": ENQUIRY_PROMPT}


def _api_key() -> str:
    """LLM_API_KEY if set; a server that is not Gemini (local small model) usually needs none.
    Gemini: GEMINI_API_KEY from the environment, or from the Windows user settings (setx) if this terminal predates it."""
    if os.environ.get("LLM_API_KEY"):
        return os.environ["LLM_API_KEY"]
    if LLM_BASE_URL != GEMINI_URL:
        return "not-needed"
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "GEMINI_API_KEY")[0]
        except OSError:
            pass
    if not key:
        raise SystemExit('GEMINI_API_KEY is not set. Run: setx GEMINI_API_KEY "your-key" and open a new terminal.')
    return key


_llm = OpenAI(base_url=LLM_BASE_URL, api_key=_api_key(), timeout=40)


class Call:
    """One call = one Call object. Holds the conversation, who was verified and (enquiry mode) the form.

    on_form(values, changed_keys, flags, confirmed_keys) is called from the worker thread whenever the form changes.
    """

    def __init__(self, mode: str = "support", on_form=None, on_cards=None):
        self.mode = mode
        self.on_form = on_form
        self.on_cards = on_cards      # on_cards(list of cards) shows account data on the caller's screen
        self.system_prompt = PROMPT_BY_MODE[mode]
        self.tools = TOOLS_BY_MODE[mode]
        self.history = [{"role": "system", "content": self.system_prompt}]
        self.customer_id = None
        self.phone = None
        self.form = {}
        self.turn_no = 0              # caller turns so far (the chunks of one spoken turn count as one)
        self._turn_open = False
        self.phone_turn = -1          # the turn in which the current mobile number was given
        self.no_record_told = False   # the caller has been told that no account exists under their number
        self.crm_phone = None         # the number the CRM was last asked about
        self.crm_error = False        # the CRM could not be reached
        self.crm_candidates = []      # every CRM record that has the caller's number (normally one)
        self.crm = None               # the caller's CRM record (kept on the server; never sent to the page)
        self.crm_verified = False
        self.crm_attempts = 0         # identity checks used in this call (3 allowed)
        self.crm_lookups = 0
        self.more_coming = False      # the caller is still speaking: answer this part briefly and ask nothing yet
        self.previous = []            # earlier saved requests for the caller's number (kept on the server)
        self.previous_phone = None
        self.audit = []               # every CRM access in this call, without personal data
        self.finished = False         # Gemini has called finish_call: the app plays the recorded goodbye
        self.flags = {}               # key -> reason a value looks doubtful
        self.confirmed = set()        # keys the caller (or the user on the page) has confirmed
        self.flow = None              # guided new-loan enquiry flow (flow.py); FLOW=0 switches it off
        if mode == "enquiry" and os.environ.get("FLOW", "1") != "0":
            import flow
            self.flow = flow.Flow(self)

    def _run_tool(self, name, args):
        # The model never chooses whose data to read: we use the verified customer only.
        if name == "verify_customer":
            res = db.verify_customer(args.get("phone", ""), args.get("pin", ""))
            if res.get("ok"):
                self.customer_id, self.phone = res["customer_id"], args.get("phone", "")
                return {"ok": True, "name": res.get("name")}
            return {"ok": False}
        if name == "get_orders":
            if not self.customer_id:
                return {"error": "caller not verified"}
            return db.get_orders(self.customer_id)
        if name == "update_form" and self.mode == "enquiry":
            saved, errors = {}, {}
            details = args.pop("details", None) or []
            uncertain = args.pop("uncertain", None) or []
            confirmed = args.pop("confirmed", None) or []
            for key, value in args.items():
                ok, result = forms.clean(key, value)
                if ok:
                    if self.form.get(key) != result:
                        self.confirmed.discard(key)          # a changed value must be confirmed again
                    saved[key] = result
                else:
                    errors[key] = result
            if "phone" in saved and saved["phone"] != self.form.get("phone"):
                self.phone_turn = self.turn_no                          # a new number: it still has to be read back and confirmed
            self.form.update(saved)
            for item in details if isinstance(details, list) else []:
                ok, result = forms.clean_detail(item.get("label"), item.get("value")) if isinstance(item, dict) else (False, "bad detail")
                if not ok:
                    errors["detail"] = result
                    continue
                label, value = result
                key = "detail:" + label
                if self.form.get("details", {}).get(label) != value:
                    self.confirmed.discard(key)
                self.form.setdefault("details", {})[label] = value
                saved[key] = value
                flag = forms.detail_flag(label, value)
                if flag:
                    self.flags[key] = flag
                else:
                    self.flags.pop(key, None)
            touched = list(saved)
            for item in uncertain if isinstance(uncertain, list) else []:
                key = forms.norm_key(item)
                self.flags[key] = "heard unclearly - please check"
                touched.append(key)
            for item in confirmed if isinstance(confirmed, list) else []:
                key = forms.norm_key(item)
                if key == "phone" and self.turn_no <= self.phone_turn:    # no read-back could have happened yet
                    errors["confirmed"] = "the mobile number cannot be confirmed in the same turn it was given: read it back and wait for the caller's answer"
                    continue
                self.confirmed.add(key)
                self.flags.pop(key, None)
                touched.append(key)
            if "phone" in saved and saved["phone"] != self.previous_phone:
                self._load_previous(saved["phone"])
            touched += [k for k in self._update_identity() if k not in touched]
            if touched and self.on_form:
                self.on_form(json.loads(json.dumps(self.form)), touched, dict(self.flags), sorted(self.confirmed))
            return {"saved": saved, "errors": errors, "flags": dict(self.flags), "still_missing": forms.missing(self.form)}
        if name == "find_customer" and self.mode == "enquiry":
            ok, phone = forms.clean("phone", args.get("phone"))
            if not ok:
                return {"error": phone}
            if self.crm_lookups >= 3:
                return {"proceed": False, "locked": True}
            if phone == self.crm_phone:                              # already looked up: keep any identification
                return {"proceed": True}
            self.crm_phone = phone
            self._load_crm(phone)
            return {"proceed": True}
        if name == "verify_identity" and self.mode == "enquiry":
            if self.crm_attempts >= crm.MAX_ATTEMPTS:
                self._audit("verify_identity", "locked")
                return {"verified": False, "locked": True}
            dob = crm.parse_dob(args.get("date_of_birth"))
            last4 = re.sub(r"\D", "", db.spoken_digits(args.get("last_four_digits")))[-4:]
            if dob is None or len(last4) != 4:     # an incomplete check is not an attempt: ask the caller for what is missing
                return {"error": "ask the caller for BOTH their date of birth and the last 4 digits of a loan account, then call this again. This did not use up an attempt."}
            if self.crm is None and self.crm_lookups == 0 and self.form.get("phone"):
                self._load_crm(self.form["phone"])            # the model skipped find_customer: do not depend on it
            self.crm_attempts += 1
            match = crm.match_identity(self.crm_candidates, args.get("date_of_birth"), args.get("last_four_digits"))
            ok = match is not None
            if ok:
                self.crm = match
            self.crm_verified = ok
            self._audit("verify_identity", "verified" if ok else f"failed (attempt {self.crm_attempts})")
            if ok:
                for label, value in (("crm_customer_id", self.crm.get("customer_id")), ("identity_verified", "yes - date of birth and last 4 digits of loan account")):
                    self.form.setdefault("details", {})[label] = str(value)
                if self.on_form:
                    self.on_form(json.loads(json.dumps(self.form)), ["detail:crm_customer_id", "detail:identity_verified"], dict(self.flags), sorted(self.confirmed))
                return {"verified": True}
            return {"verified": False, "attempts_left": crm.MAX_ATTEMPTS - self.crm_attempts, "locked": self.crm_attempts >= crm.MAX_ATTEMPTS}
        if name == "get_account_details" and self.mode == "enquiry":
            if not (self.crm and self.crm_verified):
                return {"error": "the caller's identity is not verified"}
            view = crm.public_view(self.crm)
            shown = crm.cards(view, args.get("show_fields"))
            self._audit("get_account_details", f"returned {len(view['loans'])} loan(s), {len(view['tickets'])} ticket(s); showed {args.get('show_fields') or 'all fields'}")
            if shown and self.on_cards:
                self.on_cards(shown)
            return {**view, "note": "These details are now on the caller's screen. Say the key points they asked for and tell them the rest is on screen; do not read everything out."}
        if name == "finish_call" and self.mode == "enquiry":
            self.finished = True
            return {"ok": True, "say_goodbye": not clips.available("closing")}   # if no goodbye is recorded, say it yourself
        if name == "request_callback":
            return db.request_callback(self.phone or self.form.get("phone") or "unverified", args.get("note", ""))
        return {"error": "unknown tool"}

    def _load_previous(self, phone: str) -> None:
        """Earlier requests saved for this number. Nothing is said about them until the caller's name matches."""
        self.previous_phone = phone
        try:
            self.previous = db.previous_requests(phone)
        except Exception as e:                      # saved data unavailable: carry on as a new caller
            self.previous = []
            self._audit("previous_requests", f"lookup failed ({type(e).__name__})")
            return
        self._audit("previous_requests", f"{len(self.previous)} earlier request(s) saved for this number")

    @staticmethod
    def _same_person(a, b) -> bool:
        """Loose name match (spelling and transliteration vary): same full name, or the same first name."""
        norm = lambda x: re.sub(r"[^a-z ]", "", str(x or "").lower()).split()
        ta, tb = norm(a), norm(b)
        if not ta or not tb:
            return False
        if difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= 0.75:
            return True
        return len(ta[0]) >= 3 and difflib.SequenceMatcher(None, ta[0], tb[0]).ratio() >= 0.85

    def _earlier_for_caller(self) -> list:
        """Earlier requests that belong to the person on this call: same number AND matching name (or identity verified)."""
        if self.crm_verified:
            return self.previous
        return [r for r in self.previous if self._same_person(self.form.get("full_name"), r["saved_name"])]

    def _state_hint(self) -> str:
        """What must happen next, worked out in code every turn so it does not depend on the model remembering the rules."""
        hints, phone = [], self.form.get("phone")
        if self.more_coming:
            hints.append("THE CALLER IS STILL SPEAKING: this is only one part of what they are saying. Answer or acknowledge just this part in one short sentence and do NOT ask any question yet; the next part follows.")
        earlier = self._earlier_for_caller()
        if earlier:
            lines = "; ".join(f"{r['reference']} ({r['topic']}, {r['status']}, {crm.pretty_date(r['created_at'][:10])}): {r['summary'][:140]}" for r in earlier[:3])
            hints.append("RETURNING CALLER. Saved records of earlier requests from this person: " + lines + ". Welcome them back, mention the most relevant earlier request ONCE (by its reference: say the letters in Devanagari such as क्यू आर, then the digits as words, and never say the word dash; give dates naturally, never like 2026-10-28), ask whether this call is about it, and continue from it. Do not ask again for details you already have. If you have already mentioned it, just continue.")
        needs_account = self.form.get("category") in ("existing_loan_support", "payment_or_emi")
        if not phone and not needs_account:
            hints.append("The caller's mobile number is their unique customer ID. If you do not have it yet, ask for it soon (right after their name or first need) and confirm it once.")
        if crm.VERIFY_MODE == "phone":
            n, phone_ok = len(self.crm_candidates), "phone" in self.confirmed and self.crm_phone == phone
            if self.crm_verified:
                hints.insert(0, f"CUSTOMER IDENTIFIED from the confirmed mobile number: {self.crm.get('name')}. Provide the account information the caller asks for with get_account_details (it appears on their screen at once) and address them by name. Do not ask for any other proof.")
            elif self.crm_error:
                hints.insert(0, "The customer records cannot be reached right now. Say so politely, do not guess any account facts, and offer a callback with request_callback.")
            elif phone and not phone_ok:
                hints.insert(0, "MANDATORY NEXT STEP: read the mobile number back digit by digit and ask the caller to confirm it. When they say yes, call update_form with confirmed=[\"phone\"]; the customer is then identified and you can give them the information they asked for.")
            elif phone_ok and n > 1:
                hints.insert(0, "Several customers share this mobile number, so it cannot identify the caller alone: ask for their date of birth and the last four digits of one of their loan accounts (they may say both at once), then call verify_identity." + (" Verification is LOCKED: share no account details and offer a callback." if self.crm_attempts >= crm.MAX_ATTEMPTS else ""))
            elif phone_ok and n == 0:
                hints.insert(0, "MANDATORY, SAY THIS FIRST: NO LOAN ACCOUNT was found under the confirmed mobile number (earlier saved enquiries are not loan accounts). If the caller asked about an existing loan or account, tell them politely that no account was found under this number before anything else, then offer to check the number again, continue as a new enquiry, or arrange a callback. You may mention an earlier request afterwards.")
            elif needs_account and not phone:
                hints.insert(0, "The caller needs help with their own loan. Ask for their mobile number now: it identifies them.")
        else:
            if self.crm_verified:
                hints.append("The caller is VERIFIED. Answer their loan questions with get_account_details (the data appears on their screen). Do not ask them to verify again.")
            elif self.crm_attempts >= crm.MAX_ATTEMPTS:
                hints.append("Identity verification is LOCKED. Share no account details; offer a callback with request_callback.")
            elif needs_account and not phone:
                hints.append("The caller needs help with their own loan. Ask for their mobile number now.")
            elif needs_account:
                hints.append("MANDATORY NEXT STEP: to share any loan details the caller must verify. Ask for their date of birth and the last four digits of one of their loan accounts (they may say both at once), then call verify_identity. Do NOT ask about callback consent or anything else first.")
        return "\n".join(hints)

    def _update_identity(self) -> list:
        """Phone mode: look the number up as soon as it is saved, and once the caller has confirmed it and it belongs to exactly
        one CRM customer, that customer is identified. Returns the form keys that changed."""
        if crm.VERIFY_MODE != "phone" or self.mode != "enquiry":
            return []
        phone = self.form.get("phone")
        if not phone:
            return []
        if phone != self.crm_phone and self.crm_lookups < 3:
            self.crm_phone, self.crm_error, self.no_record_told = phone, False, False
            try:
                self._load_crm(phone)
            except Exception as e:                                  # the CRM is down: do not guess, tell the caller
                self.crm_candidates, self.crm, self.crm_verified, self.crm_error = [], None, False, True
                self._audit("find_customer", f"CRM unavailable ({type(e).__name__})")
        if (not self.crm_verified and "phone" in self.confirmed and self.crm_phone == phone
                and len(self.crm_candidates) == 1 and not self.crm_error):
            self.crm, self.crm_verified = self.crm_candidates[0], True
            for label, value in (("crm_customer_id", self.crm.get("customer_id")),
                                 ("identity_verified", "yes - mobile number, confirmed by read-back")):
                self.form.setdefault("details", {})[label] = str(value)
            self._audit("identified", "customer identified by the confirmed mobile number")
            return ["detail:crm_customer_id", "detail:identity_verified"]
        return []

    def _load_crm(self, phone: str) -> None:
        """Look the caller up by mobile number (at most 3 lookups per call). The model is never told whether a record exists."""
        self.crm_lookups += 1
        self.crm_candidates = crm.find_all_by_phone(phone)
        self.crm, self.crm_verified = (self.crm_candidates[0] if len(self.crm_candidates) == 1 else None), False
        n = len(self.crm_candidates)
        self._audit("find_customer", "record found" if n == 1 else "no record" if n == 0 else f"{n} records share this number: the identity check must pick one")

    @staticmethod
    def _drop_questions(text: str) -> str:
        """While the caller is still speaking, a question would cut across them: keep only the statements. May return ''."""
        return " ".join(p for p in voice.split_sentences(text) if "?" not in p and "？" not in p)

    def _audit(self, action: str, result: str) -> None:
        self.audit.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "action": action, "result": result})

    def _trim(self):
        """Drop the oldest exchanges, always cutting at a user message so tool calls stay paired with their results."""
        while len(self.history) > MAX_HISTORY:
            nxt = next((i for i in range(2, len(self.history)) if self.history[i]["role"] == "user"), None)
            if nxt is None:
                break
            del self.history[1:nxt]

    def _complete(self):
        """One Gemini call. On the free tier's per-minute limit, wait and retry instead of failing the call."""
        for attempt in range(3):
            try:
                return _llm.chat.completions.create(
                    model=LLM_MODEL, messages=self.history, tools=self.tools, max_tokens=500, temperature=0.4
                ).choices[0].message
            except RateLimitError:
                if attempt == 2:
                    raise
                print("Gemini free-tier limit reached; waiting 20 s", flush=True)
                time.sleep(20)

    def start_with(self, text: str) -> None:
        """The greeting was played from a recording: remember it as something the assistant already said."""
        self.history.append({"role": "user", "content": "(कॉल शुरू हुई है।)"})
        self.history.append({"role": "assistant", "content": text})

    def opening(self) -> str:
        """Greeting, written by Gemini when the call connects."""
        return self.reply("(कॉल शुरू हुई है। कॉलर का स्वागत करो, बताओ कि तुम रिया हो, और पूछो कि कैसे मदद कर सकती हो।)")

    def not_heard(self) -> str:
        """Reply when speech-to-text heard nothing usable."""
        return self.reply("(कॉलर की आवाज़ साफ़ सुनाई नहीं दी। विनम्रता से दोबारा बोलने को कहो, लिंग-निरपेक्ष शब्दों में (जैसे 'कृपया दोहराइए'), 'सकती/सकते' के बिना।)")

    _MORE_COMING_NOTE = "\n(कॉलर अभी और बोल रहे हैं। इस हिस्से पर सिर्फ़ एक छोटा वाक्य बोलिए: पुष्टि या सीधा जवाब। कोई सवाल मत पूछिए।)"
    _ACKS = ["जी।", "ठीक है।", "जी, समझ गई।"]

    def reply(self, user_text: str) -> str:
        """The reply to what the caller just said (one chunk of their speech)."""
        if not self._turn_open:
            self.turn_no, self._turn_open = self.turn_no + 1, True
        if self.flow is not None and not user_text.startswith("("):       # guided flow first: exact values, one question at a time
            try:
                out = self.flow.handle(user_text)
            except Exception as e:                                         # a flow bug must never silence the call: fall back to the assistant
                print(f"   [flow] error {type(e).__name__}: {e}", flush=True)
                out = None
            if out is not None:
                print("   [flow]", {k: v for k, v in self.flow.v.items()}, "| asked:", self.flow.asked, flush=True)
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": out})
                self._trim()
                if not self.more_coming:
                    self._turn_open = False
                return out
        note = self._MORE_COMING_NOTE if (self.more_coming and self.mode == "enquiry") else ""
        if self.mode == "enquiry" and not user_text.startswith("("):          # internal prompts are not caller speech
            guide = replybank.hint(user_text)
            if guide:
                print("   [reply bank]", [m["id"] for m in replybank.match(user_text)], flush=True)
                note += "\n" + guide
        self.history.append({"role": "user", "content": user_text + note})
        self._trim()
        user_idx = len(self.history) - 1
        try:
            return self._reply_loop()
        finally:
            if not self.more_coming:
                self._turn_open = False
            if note and user_idx < len(self.history) and self.history[user_idx]["role"] == "user":
                self.history[user_idx]["content"] = user_text            # the note was only for this one reply

    def _reply_loop(self) -> str:
        for _ in range(6):  # tool loop
            if self.mode == "enquiry":   # tell the model what the form already holds (history may have been trimmed)
                state = json.dumps(self.form, ensure_ascii=False)
                self.history[0]["content"] = f"{self.system_prompt}\n\nForm so far: {state}\nStill missing: {forms.missing(self.form)}\n{self._state_hint()}"
            msg = self._complete()
            entry = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                entry["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            self.history.append(entry)
            if not msg.tool_calls:
                text = voice.sanitize_reply((msg.content or "").strip())
                if text:
                    if not self.more_coming:
                        return text
                    return self._drop_questions(text) or random.choice(self._ACKS)     # a statement for this part, never a question
                self.history.pop()                       # an empty reply would leave the caller in silence: ask for a real one
                self.history.append({"role": "user", "content": "(कॉलर को अभी तक आपका जवाब सुनाई नहीं दिया। अब उन्हें बोलकर जवाब दीजिए।)"})
                continue
            for tc in msg.tool_calls:
                try:
                    out = self._run_tool(tc.function.name, json.loads(tc.function.arguments or "{}"))
                except Exception as e:  # data source down -> fail safe
                    out = {"error": f"data source unavailable: {type(e).__name__}"}
                self.history.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out, ensure_ascii=False)})
            self._add_event_notes()
        return voice.LINES["system_problem"]

    def _add_event_notes(self) -> None:
        """System events that must shape the very next reply. A note placed right before the reply is followed far more
        reliably than a general instruction."""
        if (crm.VERIFY_MODE == "phone" and self.mode == "enquiry" and not self.no_record_told and not self.crm_verified
                and not self.crm_error and "phone" in self.confirmed and self.crm_phone == self.form.get("phone")
                and len(self.crm_candidates) == 0 and self.form.get("category") in ("existing_loan_support", "payment_or_emi")):
            self.no_record_told = True
            self.history.append({"role": "user", "content": "(सिस्टम: इस कन्फ़र्म किए गए नंबर पर कोई लोन अकाउंट नहीं मिला। अपने जवाब की शुरुआत विनम्रता से यही बताकर कीजिए, फिर विकल्प दीजिए: नंबर दोबारा जाँचें, नई पूछताछ करें, या कॉलबैक।)"})


if __name__ == "__main__":   # text-only test: python brain.py [enquiry]
    import sys

    call = Call(sys.argv[1] if len(sys.argv) > 1 else "support", on_form=lambda v, c, f, k: print("   [form]", v, "| flags:", f, "| confirmed:", k))
    while True:
        print("Agent:", call.reply(input("You: ")))
