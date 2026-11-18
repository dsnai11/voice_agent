"""
Company data layer. The LLM never touches data directly; it can only call the three
functions below (verify_customer, get_orders, request_callback).

Pick a backend with the DATA_BACKEND env var:
  excel  (default)  - reads company_data.xlsx (sheets: customers, orders, callbacks)
  api               - calls your company application over HTTP (set COMPANY_API_URL / COMPANY_API_KEY)

Excel column names differ per company, so edit the COLUMNS map below to match your sheets.
"""
import csv
import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from datetime import datetime

import requests

BACKEND = os.environ.get("DATA_BACKEND", "excel").lower()
EXCEL_PATH = os.environ.get("COMPANY_XLSX", r"C:\Voice-agent\company_data.xlsx")

# >>> EDIT to match your sheet names / column headers (case-insensitive)
SHEETS = {"customers": "customers", "orders": "orders", "callbacks": "callbacks"}
COLUMNS = {
    "customer_id": "customer_id",
    "name": "name",
    "phone": "phone",
    "pin": "pin",            # plain text, or "sha256:<hex>" for a hashed PIN
    "order_id": "order_id",
    "item": "item",
    "status": "status",
    "eta": "eta",
    "amount": "amount",
}
# Only these order columns are ever returned to the LLM.
ORDER_FIELDS = ["order_id", "item", "status", "eta", "amount"]

# >>> EDIT for the api backend: your application's endpoints
API_URL = os.environ.get("COMPANY_API_URL", "").rstrip("/")
API_KEY = os.environ.get("COMPANY_API_KEY", "")
API_PATHS = {"verify": "/customers/verify", "orders": "/customers/{customer_id}/orders", "callback": "/callbacks",
             "enquiry": "/enquiries", "leads": "/leads", "queries": "/queries",
             "previous": "/requests"}


_NUMBER_WORDS = {
    # Hindi (Devanagari) - common spellings Whisper produces
    "शून्य": "0", "ज़ीरो": "0", "जीरो": "0", "सुन्ना": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
    "पाँच": "5", "पांच": "5", "पाच": "5", "छह": "6", "छः": "6", "छे": "6", "छ": "6", "छै": "6",
    "सात": "7", "आठ": "8", "नौ": "9", "नो": "9",
    # Hindi in Roman letters
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4", "paanch": "5", "panch": "5",
    "chhe": "6", "che": "6", "chah": "6", "saat": "7", "aath": "8", "nau": "9",
    # English
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def spoken_digits(text) -> str:
    """Turn a spoken or typed number into digits: 'नौ नौ शून्य', 'nine nine zero', '९९०' and '990' all give '990'."""
    out = []
    for tok in re.split(r"[\s,.;:।\-]+", str(text or "")):
        if not tok:
            continue
        word = _NUMBER_WORDS.get(tok.lower())
        if word is not None:
            out.append(word)
        else:   # digits in any script (ASCII or Devanagari)
            out.extend(str(unicodedata.digit(ch)) for ch in tok if ch.isdigit())
    return "".join(out)


def _digits(s) -> str:
    return spoken_digits(s)[-10:]


def _pin_ok(stored, given) -> bool:
    stored, given = str(stored or "").strip(), str(given or "").strip()
    if not stored or not given:
        return False
    if stored.startswith("sha256:"):
        return hmac.compare_digest(stored[7:], hashlib.sha256(given.encode()).hexdigest())
    return hmac.compare_digest(stored, given)


# ------------------------------ Excel backend ------------------------------
def _rows(sheet_key):
    """Read a sheet as a list of dicts keyed by our logical column names.
    Works on a temp copy so it still reads while the file is open in Excel."""
    from openpyxl import load_workbook

    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "data.xlsx")
        shutil.copy2(EXCEL_PATH, copy)
        wb = load_workbook(copy, read_only=True, data_only=True)
        ws = next((wb[n] for n in wb.sheetnames if n.lower() == SHEETS[sheet_key].lower()), None)
        if ws is None:
            return []
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip().lower() for h in next(it, [])]
        inv = {v.lower(): k for k, v in COLUMNS.items()}
        keys = [inv.get(h, h) for h in header]
        out = [dict(zip(keys, r)) for r in it if any(c is not None for c in r)]
        wb.close()
        return out


def _xl_verify(phone, pin):
    for c in _rows("customers"):
        if _digits(c.get("phone")) == _digits(phone) and _pin_ok(c.get("pin"), pin):
            return {"ok": True, "customer_id": str(c.get("customer_id")), "name": c.get("name")}
    return {"ok": False}


def _xl_orders(customer_id):
    return [
        {f: ("" if o.get(f) is None else str(o.get(f))) for f in ORDER_FIELDS}
        for o in _rows("orders")
        if str(o.get("customer_id")) == str(customer_id)
    ]


def _xl_callback(phone, note):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        from openpyxl import load_workbook

        wb = load_workbook(EXCEL_PATH)
        ws = next((wb[n] for n in wb.sheetnames if n.lower() == SHEETS["callbacks"].lower()), None) \
            or wb.create_sheet(SHEETS["callbacks"])
        if ws.max_row == 1 and ws.cell(1, 1).value is None:
            ws.append(["phone", "note", "created_at"])
        ws.append([phone, note, now])
        wb.save(EXCEL_PATH)
        return {"ok": True}
    except PermissionError:   # file open in Excel -> don't lose the request
        with open(os.path.join(os.path.dirname(EXCEL_PATH), "callbacks_pending.csv"), "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([phone, note, now])
        return {"ok": True, "note": "saved to callbacks_pending.csv (Excel file was open)"}


# ------------------------------- API backend -------------------------------
def _api(method, key, **kw):
    path = API_PATHS[key].format(**kw.pop("path", {}))
    r = requests.request(method, API_URL + path, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10, **kw)
    r.raise_for_status()
    return r.json()


# ---------------------------- public tool functions ----------------------------
def verify_customer(phone: str, pin: str) -> dict:
    phone, pin = spoken_digits(phone) or phone, spoken_digits(pin) or pin   # accept spoken Hindi/English numbers
    if BACKEND == "api":
        # >>> ADAPT the request/response shape to your application
        d = _api("POST", "verify", json={"phone": phone, "pin": pin})
        return {"ok": True, "customer_id": str(d["customer_id"]), "name": d.get("name")} if d.get("ok", True) else {"ok": False}
    return _xl_verify(phone, pin)


def get_orders(customer_id: str) -> list:
    if BACKEND == "api":
        # >>> ADAPT: must return a list of {order_id,item,status,eta,amount}
        return _api("GET", "orders", path={"customer_id": customer_id})
    return _xl_orders(customer_id)


def request_callback(phone: str, note: str) -> dict:
    if BACKEND == "api":
        return _api("POST", "callback", json={"phone": phone, "note": note})
    return _xl_callback(phone, note)


_xl_lock = threading.Lock()     # two calls ending at the same moment must not write the workbook together


def _cell(v):
    """Excel-safe value: stop text typed by a caller from being read as a formula."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def save_call_json(record: dict) -> str:
    """Full copy of every call as calls/<call_id>.json: nothing is lost even if Excel is open or locked."""
    folder = os.path.join(os.path.dirname(EXCEL_PATH), "calls")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{record['call_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path


def _xl_upsert(sheet: str, columns: list, record: dict, key_col: str = "call_id", id_col: str = "", id_prefix: str = "", merge=None) -> dict:
    """Write one row to an Excel sheet, updating the existing row with the same key_col value.
    A new row gets the next id (e.g. LD-0001) in id_col; an existing row keeps its id. Returns the record as written."""
    from openpyxl import load_workbook

    with _xl_lock:
        wb = load_workbook(EXCEL_PATH)
        ws = next((wb[n] for n in wb.sheetnames if n.lower() == sheet.lower()), None) or wb.create_sheet(sheet)
        header = [c.value for c in ws[1] if c.value is not None]
        if not header:                                  # brand-new sheet: header goes on row 1
            header = list(columns)
            for i, c in enumerate(header, 1):
                ws.cell(1, i, c)
        for c in columns:                               # new columns are added to the right, never reordered
            if c not in header:
                header.append(c)
                ws.cell(1, len(header), c)
        key_idx = header.index(key_col) + 1
        target = next((r for r in range(2, ws.max_row + 1) if str(ws.cell(r, key_idx).value) == str(record.get(key_col))), None)
        if target is not None and merge is not None:           # combine with what the row already holds
            record = merge({h: ws.cell(target, i).value for i, h in enumerate(header, 1)}, record)
        if id_col:
            id_idx = header.index(id_col) + 1
            if target is not None and ws.cell(target, id_idx).value:
                record = {**record, id_col: ws.cell(target, id_idx).value}          # keep the id this call already has
            else:
                nums = [int(m.group(1)) for r in range(2, ws.max_row + 1)
                        if (m := re.search(r"(\d+)$", str(ws.cell(r, id_idx).value or "")))]
                record = {**record, id_col: f"{id_prefix}{(max(nums) + 1 if nums else 1):04d}"}
        if target is None:
            target = max(ws.max_row + 1, 2)
        for i, h in enumerate(header, 1):
            ws.cell(target, i, _cell(record.get(h, "")))
        wb.save(EXCEL_PATH)
        return record


def save_enquiry(record: dict, columns: list) -> dict:
    """Store (or update, matched by call_id) one call's full record: sheet 'enquiries', or POST /enquiries on the company API."""
    record = {**record, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    cols = list(columns) + ["updated_at"]
    if BACKEND == "api":
        # >>> ADAPT to your application's endpoint
        return _api("POST", "enquiry", json=record)
    try:
        _xl_upsert("enquiries", cols, record)
        return {"ok": True}
    except PermissionError:   # file open in Excel -> the JSON copy still exists; also queue a CSV row
        path = os.path.join(os.path.dirname(EXCEL_PATH), "enquiries_pending.csv")
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([_cell(record.get(c, "")) for c in cols])
        return {"ok": True, "note": "Excel file was open; saved to enquiries_pending.csv and calls/ instead"}


CALLER_COLUMNS = ["customer_ref", "phone", "names_seen", "first_call_at", "last_call_at", "calls", "last_call_id",
                  "crm_customer_id", "identity_verified_ever"]


def save_caller(phone, name: str, call_id: str, when: str, crm_customer_id: str = "", verified: bool = False) -> dict:
    """One row per mobile number: the phone number is the customer's unique ID. Returns {'customer_ref': 'CU-0001', ...}.
    A number seen again updates the same row (new names are added, the call count goes up once per call)."""
    digits = spoken_digits(phone)[-10:]
    if len(digits) != 10 or BACKEND == "api":          # >>> ADAPT for api: customers are matched by phone in the company's CRM
        return {}

    def merge(existing: dict, new: dict) -> dict:
        names = [n for n in str(existing.get("names_seen") or "").split("; ") if n]
        if new["names_seen"] and new["names_seen"].lower() not in [n.lower() for n in names]:
            names.append(new["names_seen"])
        same_call = existing.get("last_call_id") == new["last_call_id"]
        return {**new, "names_seen": "; ".join(names), "first_call_at": existing.get("first_call_at") or new["first_call_at"],
                "calls": int(existing.get("calls") or 0) + (0 if same_call else 1),
                "crm_customer_id": new["crm_customer_id"] or existing.get("crm_customer_id") or "",
                "identity_verified_ever": "yes" if (new["identity_verified_ever"] == "yes" or existing.get("identity_verified_ever") == "yes") else ""}

    record = {"phone": digits, "names_seen": (name or "").strip(), "first_call_at": when, "last_call_at": when, "calls": 1,
              "last_call_id": call_id, "crm_customer_id": crm_customer_id, "identity_verified_ever": "yes" if verified else ""}
    try:
        saved = _xl_upsert("callers", CALLER_COLUMNS, record, "phone", "customer_ref", "CU-", merge=merge)
        return {"customer_ref": saved["customer_ref"], "calls": saved["calls"]}
    except PermissionError:                             # Excel open: the registry can be rebuilt from the calls, so do not fail the call
        return {}


def save_ticket(sheet: str, record: dict, columns: list, id_col: str, prefix: str) -> dict:
    """Create or update the LEAD ('leads') or QUERY ('queries') for a call. Returns {'ok': True, 'id': 'LD-0001'}."""
    record = {**record, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    cols = list(columns) + ["updated_at"]
    if BACKEND == "api":
        # >>> ADAPT: POST /leads or /queries on your CRM / support system; return its id
        out = _api("POST", sheet, json=record)
        return {"ok": True, "id": out.get("id") or out.get(id_col)}
    try:
        saved = _xl_upsert(sheet, cols, record, "call_id", id_col, prefix)
        return {"ok": True, "id": saved[id_col]}
    except PermissionError:   # Excel open: queue it and give the call a temporary reference
        temp_id = f"{prefix}{record['call_id'][:6].upper()}"
        path = os.path.join(os.path.dirname(EXCEL_PATH), f"{sheet}_pending.csv")
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([_cell({**record, id_col: temp_id}.get(c, "")) for c in cols])
        return {"ok": True, "id": temp_id, "note": f"Excel file was open; queued in {sheet}_pending.csv"}


def delete_ticket(sheet: str, call_id: str) -> None:
    """Remove a call's record from a sheet (used when a call's type changes, e.g. query -> lead)."""
    if BACKEND == "api" or not os.path.exists(EXCEL_PATH):
        return
    from openpyxl import load_workbook

    with _xl_lock:
        try:
            wb = load_workbook(EXCEL_PATH)
            ws = next((wb[n] for n in wb.sheetnames if n.lower() == sheet.lower()), None)
            if ws is None:
                return
            header = [c.value for c in ws[1]]
            if "call_id" not in header:
                return
            col = header.index("call_id") + 1
            for r in range(ws.max_row, 1, -1):
                if ws.cell(r, col).value == call_id:
                    ws.delete_rows(r)
                    wb.save(EXCEL_PATH)
                    return
        except PermissionError:
            pass


def previous_requests(phone, limit: int = 5) -> list:
    """Earlier leads and queries saved for this mobile number, newest first (from the 'leads' and 'queries' sheets, or the
    company API). Each: {reference, kind, status, created_at, summary, topic, saved_name, complete}."""
    digits = spoken_digits(phone)[-10:]
    if len(digits) != 10:
        return []
    if BACKEND == "api":
        # >>> ADAPT: GET /requests?phone=... on the company's CRM / ticketing system, returning the same fields
        return _api("GET", "previous", params={"phone": digits}) or []
    if not os.path.exists(EXCEL_PATH):
        return []
    from openpyxl import load_workbook

    out = []
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "data.xlsx")
        shutil.copy2(EXCEL_PATH, copy)                      # readable even while the file is open in Excel
        wb = load_workbook(copy, read_only=True, data_only=True)
        for sheet, kind, id_col, status_col in (("queries", "query", "query_id", "query_status"), ("leads", "lead", "lead_id", "lead_status")):
            name = next((n for n in wb.sheetnames if n.lower() == sheet), None)
            if not name:
                continue
            rows = wb[name].iter_rows(values_only=True)
            header = [str(h or "") for h in next(rows, [])]
            for r in rows:
                d = dict(zip(header, r))
                if spoken_digits(d.get("phone"))[-10:] != digits:
                    continue
                out.append({"reference": d.get(id_col), "kind": kind, "status": d.get(status_col), "created_at": str(d.get("created_at") or ""),
                            "summary": str(d.get("summary") or ""), "topic": str(d.get("query_type") or d.get("loan_type") or "new loan enquiry"),
                            "saved_name": str(d.get("full_name") or ""), "complete": str(d.get("record_status") or "").startswith("submitted")})
        wb.close()
    return sorted(out, key=lambda x: x["created_at"], reverse=True)[:limit]
