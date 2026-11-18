"""Existing-customer data from the company's CRM / loan system, used live during a call.

Flow in a call (see brain.py): mobile number -> find_customer -> caller proves who they are (date of birth + last 4
digits of a loan account) -> get_account_details -> Ria answers from that data only.

Safety rules enforced here, in code (not left to the model):
  * Nothing about a customer is returned until the caller has passed identity verification.
  * Verification has 3 attempts per call, then the call is locked out of CRM details.
  * Only a sanitized view is returned: loan accounts are masked, and date of birth / PAN / address are never returned.
  * Read-only. Every access is written to the call's audit trail.

Backends (CRM_BACKEND):
  excel  (default) - demo data in crm_demo.xlsx (fake customers; create it with: python crm.py --make-demo)
  api              - the company's CRM over REST. Set CRM_API_URL and CRM_API_KEY, then adapt LOOKUP_PATH and the
                     FIELD MAPS below to the CRM's real field names (marked >>> ADAPT).
"""
import os
import re
import sys
from datetime import date, datetime

import requests

import db

BACKEND = os.environ.get("CRM_BACKEND", "excel").lower()
CRM_XLSX = os.environ.get("CRM_XLSX", os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm_demo.xlsx"))
API_URL = os.environ.get("CRM_API_URL", "").rstrip("/")
API_KEY = os.environ.get("CRM_API_KEY", "")
MAX_ATTEMPTS = 3
# How a caller is identified before account details are shared:
#   "phone"      - a mobile number the caller has confirmed (read back, answered yes) that belongs to exactly ONE customer
#   "dob_last4"  - stricter: also the date of birth and the last 4 digits of a loan account
# A number shared by several customers always needs the date of birth + loan digits to tell them apart.
VERIFY_MODE = os.environ.get("CRM_VERIFY", "phone").lower()

# >>> ADAPT: how to look a customer up by 10-digit mobile number in the company's CRM (GET, JSON back, 404 if none)
LOOKUP_PATH = os.environ.get("CRM_LOOKUP_PATH", "/customers?phone={phone}")
# >>> ADAPT: the CRM's field names for each thing we need (dotted paths like "profile.dob" are allowed)
CUSTOMER_MAP = {"customer_id": "customer_id", "name": "name", "dob": "dob"}
LOANS_PATH = "loans"
LOAN_MAP = {"loan_account": "loan_account", "loan_type": "loan_type", "outstanding_amount": "outstanding_amount",
            "emi_amount": "emi_amount", "next_due_date": "next_due_date", "last_payment_date": "last_payment_date",
            "last_payment_amount": "last_payment_amount", "last_payment_status": "last_payment_status",
            "loan_status": "loan_status", "tenure_left_months": "tenure_left_months"}
LOAN_MAP["recent_payments"] = "recent_payments"          # a list of the loan's latest payments, newest first
PAYMENT_MAP = {"date": "date", "amount": "amount", "status": "status"}
TICKETS_PATH = "tickets"
TICKET_MAP = {"ticket_id": "ticket_id", "subject": "subject", "status": "status"}


def _get(obj, path):
    for part in str(path).split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def _normalise(raw: dict) -> dict:
    """The CRM's JSON -> our standard customer shape."""
    c = {k: _get(raw, v) for k, v in CUSTOMER_MAP.items()}
    c["loans"] = [{k: _get(l, v) for k, v in LOAN_MAP.items()} for l in (_get(raw, LOANS_PATH) or [])]
    for l in c["loans"]:
        l["recent_payments"] = [{k: _get(p, v) for k, v in PAYMENT_MAP.items()} for p in (l.get("recent_payments") or [])]
    c["tickets"] = [{k: _get(t, v) for k, v in TICKET_MAP.items()} for t in (_get(raw, TICKETS_PATH) or [])]
    return c


# ------------------------------------ backends ------------------------------------
def _excel_lookup(phone: str):
    from openpyxl import load_workbook

    if not os.path.exists(CRM_XLSX):
        raise FileNotFoundError(f"CRM demo file not found: {CRM_XLSX} (create it with: python crm.py --make-demo)")
    wb = load_workbook(CRM_XLSX, data_only=True)

    def rows(name):
        ws = wb[name]
        it = ws.iter_rows(values_only=True)
        header = [str(h) for h in next(it)]
        return [dict(zip(header, r)) for r in it if any(c is not None for c in r)]

    custs = [r for r in rows("customers") if db.spoken_digits(r.get("phone"))[-10:] == phone]    # normally exactly one
    payments = rows("payments") if "payments" in wb.sheetnames else []
    all_loans, all_tickets = rows("loans"), rows("tickets")
    out = []
    for cust in custs:
        cid = cust["customer_id"]
        out.append({"customer_id": cid, "name": cust["name"], "dob": _iso(cust.get("dob")),
                    "loans": [{**l, "next_due_date": _iso(l.get("next_due_date")), "last_payment_date": _iso(l.get("last_payment_date")),
                               "recent_payments": sorted(({"date": _iso(p.get("date")), "amount": p.get("amount"), "status": p.get("status")}
                                                          for p in payments if p.get("loan_account") == l.get("loan_account")),
                                                         key=lambda p: p["date"], reverse=True)[:5]}
                              for l in all_loans if l["customer_id"] == cid],
                    "tickets": [t for t in all_tickets if t["customer_id"] == cid]})
    return out


def _api_lookup(phone: str):
    if not API_URL:
        raise RuntimeError("CRM_API_URL is not set")
    r = requests.get(API_URL + LOOKUP_PATH.format(phone=phone), headers={"Authorization": f"Bearer {API_KEY}"}, timeout=8)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else ([data] if data else [])


def find_all_by_phone(phone) -> list:
    """Every customer record that has this 10-digit mobile number. The phone number is the customer's unique ID, so
    this should be one record; if the CRM holds more than one, only the identity check can tell them apart."""
    digits = db.spoken_digits(phone)[-10:]
    if len(digits) != 10:
        return []
    raws = _api_lookup(digits) if BACKEND == "api" else _excel_lookup(digits)
    return [_normalise(r) for r in raws or []]


def find_by_phone(phone) -> dict:
    """The customer record for a mobile number, or None (the first one if the CRM wrongly holds several)."""
    found = find_all_by_phone(phone)
    return found[0] if found else None


def duplicate_phones() -> dict:
    """Mobile numbers that more than one customer record shares (a data problem to fix in the CRM)."""
    from collections import defaultdict

    from openpyxl import load_workbook

    ws = load_workbook(CRM_XLSX, data_only=True)["customers"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    by_phone = defaultdict(list)
    for r in rows[1:]:
        d = dict(zip(header, r))
        by_phone[db.spoken_digits(d.get("phone"))[-10:]].append(d.get("customer_id"))
    return {p: ids for p, ids in by_phone.items() if len(ids) > 1}


# ---------------------------------- identity check ----------------------------------
def _iso(v) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return "" if v is None else str(v)


def parse_dob(text):
    """A date from '1985-03-12', '12/03/1985', '12-03-1985', '12 March 1985' or a date object; None if unreadable."""
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    t = str(text or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def check_identity(customer: dict, dob, last_four) -> bool:
    """True only if the date of birth AND the last 4 digits of one of the customer's loan accounts both match."""
    given = parse_dob(dob)
    actual = parse_dob(customer.get("dob"))
    last4 = re.sub(r"\D", "", db.spoken_digits(last_four))[-4:]
    if given is None or actual is None or given != actual or len(last4) != 4:
        return False
    return any(re.sub(r"\D", "", str(l.get("loan_account") or ""))[-4:] == last4 for l in customer.get("loans", []))


def match_identity(candidates: list, dob, last_four):
    """The one customer, among those sharing the phone number, whose date of birth and loan-account digits both match.
    None if nobody matches, or if more than one does (then nobody can be told apart safely)."""
    matches = [c for c in candidates if check_identity(c, dob, last_four)]
    return matches[0] if len(matches) == 1 else None


def _mask(account) -> str:
    s = str(account or "")
    return "XXXX" + s[-4:] if len(s) >= 4 else "XXXX"


def public_view(customer: dict) -> dict:
    """What the agent may speak about, after verification. No DOB, no full account numbers, nothing else from the CRM."""
    return {
        "name": customer.get("name"),
        "loans": [{"loan_account_masked": _mask(l.get("loan_account")), "loan_type": l.get("loan_type"),
                   "outstanding_amount": l.get("outstanding_amount"), "emi_amount": l.get("emi_amount"),
                   "next_due_date": l.get("next_due_date"), "last_payment_date": l.get("last_payment_date"),
                   "last_payment_amount": l.get("last_payment_amount"), "last_payment_status": l.get("last_payment_status"),
                   "loan_status": l.get("loan_status"), "tenure_left_months": l.get("tenure_left_months"),
                   "recent_payments": (l.get("recent_payments") or [])[:5]}
                  for l in customer.get("loans", [])],
        "tickets": [{"ticket_id": t.get("ticket_id"), "subject": t.get("subject"), "status": t.get("status")}
                    for t in customer.get("tickets", [])],
    }


# ------------------------------- on-screen data cards -------------------------------
def inr(n) -> str:
    """12345678 -> '₹1,23,45,678' (Indian digit grouping)."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return "-" if n in (None, "") else str(n)
    s = str(abs(n))
    head, tail = s[:-3], s[-3:]
    if head:
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def pretty_date(v) -> str:
    d = parse_dob(v)
    return f"{d.day} {d.strftime('%b %Y')}" if d else ("-" if v in (None, "") else str(v))


ALL_FIELDS = ["outstanding_amount", "emi_amount", "next_due_date", "last_payment", "loan_status", "tenure_left_months",
              "recent_payments", "tickets"]


def cards(view: dict, show=None) -> list:
    """Turn the sanitized account view into cards the web page shows instantly: key-value cards (one per loan),
    a payments table inside each, and a requests table. `show` limits which fields are displayed (default: all)."""
    show = set(show or ALL_FIELDS) & set(ALL_FIELDS) or set(ALL_FIELDS)
    out = []
    for loan in view.get("loans", []):
        rows = []
        if "outstanding_amount" in show:
            rows.append(["Outstanding balance", inr(loan.get("outstanding_amount"))])
        if "emi_amount" in show:
            rows.append(["EMI amount", inr(loan.get("emi_amount"))])
        if "next_due_date" in show:
            rows.append(["Next due date", pretty_date(loan.get("next_due_date"))])
        if "last_payment" in show:
            rows.append(["Last payment", f"{inr(loan.get('last_payment_amount'))} on {pretty_date(loan.get('last_payment_date'))} ({loan.get('last_payment_status') or '-'})"])
        if "loan_status" in show:
            rows.append(["Loan status", str(loan.get("loan_status") or "-").title()])
        if "tenure_left_months" in show:
            rows.append(["Tenure left", f"{loan.get('tenure_left_months')} months" if loan.get("tenure_left_months") is not None else "-"])
        card = {"kind": "loan", "title": f"{str(loan.get('loan_type') or '').title()} loan · {loan.get('loan_account_masked')}", "rows": rows}
        if "recent_payments" in show and loan.get("recent_payments"):
            card["table"] = {"title": "Recent payments", "columns": ["Date", "Amount", "Status"],
                             "rows": [[pretty_date(p.get("date")), inr(p.get("amount")), str(p.get("status") or "-").title()] for p in loan["recent_payments"]]}
        if rows or "table" in card:
            out.append(card)
    if "tickets" in show and view.get("tickets"):
        out.append({"kind": "table", "title": "Your requests",
                    "table": {"title": "", "columns": ["Ticket", "Subject", "Status"],
                              "rows": [[t.get("ticket_id"), t.get("subject"), str(t.get("status") or "-").title()] for t in view["tickets"]]}})
    return out


# ------------------------------------ demo data ------------------------------------
def make_demo(path: str = CRM_XLSX) -> None:
    """Create crm_demo.xlsx with FAKE customers for testing."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "customers"
    ws.append(["customer_id", "name", "phone", "dob"])
    for r in [("C1001", "Rahul Sharma", "9990001111", "1985-03-12"), ("C1002", "Priya Verma", "9990002222", "1990-07-21"),
              ("C1003", "Amit Singh", "9876543210", "1988-11-02")]:
        ws.append(list(r))
    ws = wb.create_sheet("loans")
    ws.append(["customer_id", "loan_account", "loan_type", "outstanding_amount", "emi_amount", "next_due_date",
               "last_payment_date", "last_payment_amount", "last_payment_status", "loan_status", "tenure_left_months"])
    for r in [("C1001", "LIF10025678", "personal", 182500, 8500, "2026-11-05", "2026-10-05", 8500, "received", "active", 22),
              ("C1002", "LIF20049012", "home", 2450000, 25400, "2026-11-10", "2026-10-10", 25400, "bounced", "active", 118),
              ("C1003", "LIF30077341", "vehicle", 410000, 14200, "2026-11-02", "2026-10-02", 14200, "received", "active", 31),
              ("C1003", "LIF30081205", "gold", 65000, 0, "2027-02-15", "2026-08-15", 65000, "received", "active", 4)]:
        ws.append(list(r))
    ws = wb.create_sheet("payments")
    ws.append(["loan_account", "date", "amount", "status"])
    for r in [("LIF10025678", "2026-10-05", 8500, "received"), ("LIF10025678", "2026-09-05", 8500, "received"), ("LIF10025678", "2026-08-05", 8500, "received"),
              ("LIF20049012", "2026-10-10", 25400, "bounced"), ("LIF20049012", "2026-09-10", 25400, "received"), ("LIF20049012", "2026-08-10", 25400, "received"),
              ("LIF30077341", "2026-10-02", 14200, "received"), ("LIF30077341", "2026-09-02", 14200, "received"), ("LIF30077341", "2026-08-02", 14200, "received"), ("LIF30077341", "2026-07-02", 14200, "received"),
              ("LIF30081205", "2026-08-15", 65000, "received")]:
        ws.append(list(r))
    ws = wb.create_sheet("tickets")
    ws.append(["customer_id", "ticket_id", "subject", "status"])
    ws.append(["C1002", "T-5521", "EMI bounce charges query", "open"])
    wb.save(path)
    print("demo CRM data written to", path)


if __name__ == "__main__":
    if "--make-demo" in sys.argv:
        make_demo()
    elif "--check" in sys.argv:
        dups = duplicate_phones()
        print("Every mobile number belongs to exactly one customer." if not dups else f"Mobile numbers shared by several customers: {dups}")
    else:
        print(__doc__)
