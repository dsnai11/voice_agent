"""The enquiry form, shared by Gemini (what to ask), the server (validation, saving) and the web page (display).

Fixed core fields are asked on every call. After the caller says what they need, Gemini adds a flexible list of
extra "details" (label + value) that depend on the need, e.g. loan_amount, loan_account_number, complaint_description.

Accuracy: values are validated and cleaned here; doubtful values get a flag; important values (mobile number,
account number, amount) are only treated as correct once the caller has confirmed them or the user has verified them.
"""
import difflib
import os
import re

import db

CATEGORIES = ["new_loan_enquiry", "existing_loan_support", "payment_or_emi", "complaint", "other"]

FIELDS = [
    {"key": "full_name", "label": "Full name", "type": "text", "required": True,
     "hint": "caller's full name"},
    {"key": "reason", "label": "What do you need?", "type": "text", "required": True,
     "hint": "why the caller is calling, in one or two clear English sentences"},
    {"key": "category", "label": "Type of request", "type": "choice", "required": True, "options": CATEGORIES,
     "hint": "choose from the caller's need; set it as soon as the need is clear"},
    {"key": "phone", "label": "Mobile number", "type": "phone", "required": True,
     "hint": "10-digit mobile number; convert spoken Hindi/English digits to numerals"},
    {"key": "preferred_callback_time", "label": "Best time to call back", "type": "text", "required": False,
     "hint": "when the caller prefers a callback, in English, e.g. 'tomorrow evening'"},
    {"key": "consent_to_contact", "label": "OK to be contacted", "type": "choice", "required": True,
     "options": ["yes", "no"],
     "hint": "ask clearly whether the company may call them back about this; only 'yes' or 'no'"},
]
KEYS = [f["key"] for f in FIELDS]
REQUIRED = [f["key"] for f in FIELDS if f["required"]]
_BY_KEY = {f["key"]: f for f in FIELDS}

# ----------------------------- accuracy rules (edit to match the company) -----------------------------
LOAN_TYPES = ["personal", "home", "business", "vehicle", "gold"]
CITIES = ["Delhi", "New Delhi", "Mumbai", "Pune", "Nagpur", "Nashik", "Thane", "Bengaluru", "Bangalore", "Mysuru",
          "Hyderabad", "Chennai", "Coimbatore", "Kolkata", "Howrah", "Ahmedabad", "Surat", "Vadodara", "Rajkot",
          "Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner", "Lucknow", "Kanpur", "Agra", "Varanasi",
          "Prayagraj", "Meerut", "Noida", "Ghaziabad", "Gurugram", "Gurgaon", "Faridabad", "Chandigarh", "Ludhiana",
          "Amritsar", "Jalandhar", "Dehradun", "Haridwar", "Bhopal", "Indore", "Gwalior", "Jabalpur", "Patna",
          "Gaya", "Ranchi", "Jamshedpur", "Bhubaneswar", "Cuttack", "Raipur", "Guwahati", "Kochi", "Thiruvananthapuram",
          "Kozhikode", "Visakhapatnam", "Vijayawada", "Madurai", "Mangaluru", "Hubballi", "Goa", "Panaji"]
# Loan account number format: letters/digits, 5 to 20 characters. Set ACCOUNT_REGEX to your real format, e.g. ^LIF[0-9]{8}$
ACCOUNT_REGEX = re.compile(os.environ.get("ACCOUNT_REGEX", r"^[A-Z0-9]{5,20}$"))
# Plausible rupee ranges (min, max). Values outside are kept but flagged for the caller to confirm.
AMOUNT_RANGES = {"loan_amount": (5_000, 50_000_000), "monthly_income": (1_000, 10_000_000), "emi_amount": (100, 5_000_000)}
# Must be confirmed by the caller (or verified by the user on the page) before they count as accurate.
CRITICAL = ["phone", "detail:loan_account_number", "detail:loan_amount"]

_NUMERIC_LABEL = re.compile(r"amount|income|salary|emi|balance|due|price|value")
_NON_ENGLISH = re.compile(r"[ऀ-ॿ]")          # Devanagari
_ENGLISH_ONLY = "must be written in English letters: transliterate names and places, translate the text into English"


def norm_key(key: str) -> str:
    """Core field name, or 'detail:<label>' for an extra detail."""
    key = str(key or "").strip()
    if key in _BY_KEY:
        return key
    key = key[7:] if key.startswith("detail:") else key
    return "detail:" + re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_")[:40]


def clean(key: str, value):
    """Validate one core value. Returns (True, cleaned) or (False, reason the agent can act on)."""
    f = _BY_KEY.get(key)
    if f is None:
        return False, f"unknown field {key}"
    if value is None or str(value).strip() == "":
        return False, "empty value"
    t = f["type"]
    if t == "phone":
        digits = re.sub(r"\D", "", db.spoken_digits(value))[-10:]
        if len(digits) != 10:
            return False, "mobile number must be exactly 10 digits; ask the caller to repeat it"
        if digits[0] not in "6789":
            return False, "an Indian mobile number starts with 6, 7, 8 or 9; ask the caller to repeat it"
        return True, digits
    if t == "choice":
        v = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        return (True, v) if v in f["options"] else (False, f"must be one of {f['options']}")
    text = str(value).strip()[:300]
    if _NON_ENGLISH.search(text):
        return False, _ENGLISH_ONLY
    if key == "full_name":
        text = " ".join(w[:1].upper() + w[1:] for w in text.split())
    return True, text


def clean_detail(label, value):
    """Validate and tidy one flexible detail. Returns (True, (label, value)) or (False, reason)."""
    label = re.sub(r"[^a-z0-9_]+", "_", str(label or "").strip().lower()).strip("_")[:40]
    text = str(value if value is not None else "").strip()[:300]
    if not label or not text:
        return False, "a detail needs a short label and a value"
    if label in _BY_KEY:
        return False, f"'{label}' is a core field; use update_form with {label} directly"
    if _NON_ENGLISH.search(text):
        return False, _ENGLISH_ONLY
    if _NUMERIC_LABEL.search(label):                      # amounts: plain digits only
        digits = db.spoken_digits(text)
        if digits and digits == re.sub(r"\D", "", text):
            text = str(int(digits))
    if label == "city":                                   # correct near-misses against the city list
        match = difflib.get_close_matches(text.title(), CITIES, n=1, cutoff=0.78)
        text = match[0] if match else text.title()
    elif label == "loan_type":                            # 'Business Loan' -> 'business'
        base = re.sub(r"\s*loan\s*", " ", text.lower()).strip().replace(" ", "_")
        match = difflib.get_close_matches(base, LOAN_TYPES, n=1, cutoff=0.7)
        text = match[0] if match else text
    elif "account" in label and ("number" in label or label.endswith("_no")):
        text = re.sub(r"[\s\-]", "", text).upper()
    return True, (label, text)


def detail_flag(label: str, value) -> str:
    """Reason a detail looks doubtful (kept, but the caller should confirm it), or '' if it looks fine."""
    value = str(value)
    if "account" in label and ("number" in label or label.endswith("_no")) and not ACCOUNT_REGEX.match(value):
        return "account number format looks wrong"
    rng = AMOUNT_RANGES.get(label)
    if rng and value.isdigit() and not (rng[0] <= int(value) <= rng[1]):
        return "amount looks unusual - please confirm"
    return ""


def needs_check(values: dict, flags: dict, confirmed) -> dict:
    """Everything that should be checked by a person: doubtful values, plus critical ones nobody has confirmed."""
    out = dict(flags)
    details = values.get("details") or {}
    for key in CRITICAL:
        present = details.get(key[7:]) if key.startswith("detail:") else values.get(key)
        if present not in (None, "") and key not in confirmed and key not in out:
            out[key] = "not confirmed by the caller"
    return out


def missing(values: dict) -> list:
    return [k for k in REQUIRED if values.get(k) in (None, "")]


def public() -> list:
    """Field list for the web page (no model hints)."""
    return [{k: f[k] for k in ("key", "label", "type", "options", "required") if k in f} for f in FIELDS]
