"""After every call, turn what the caller needed into a LEAD (new business) or a QUERY (support ticket).

  new_loan_enquiry                                      -> lead   (sheet "leads",   ids LD-0001, LD-0002 ...)
  existing_loan_support / payment_or_emi / complaint / other
  (or the need was never made clear)                    -> query  (sheet "queries", ids QR-0001, QR-0002 ...)

The record is created when the call ends, even if the caller hangs up early (record_status "partial"), and is
updated in place when the form is submitted. Edit the rules and columns below to match the company's CRM.
"""

LEAD_PRIORITY = "normal"
QUERY_PRIORITY = {"complaint": "high", "payment_or_emi": "medium"}      # everything else: normal

LEAD_COLUMNS = ["lead_id", "call_id", "customer_ref", "created_at", "lead_status", "record_status", "priority", "full_name", "phone",
                "consent_to_contact", "preferred_callback_time", "loan_type", "loan_amount", "city", "monthly_income",
                "employment_type", "summary", "other_details", "needs_check", "crm_customer_id", "identity_verified", "source"]
QUERY_COLUMNS = ["query_id", "call_id", "customer_ref", "created_at", "query_status", "record_status", "priority", "query_type",
                 "full_name", "phone", "consent_to_contact", "preferred_callback_time", "loan_account_number",
                 "summary", "details", "needs_check", "crm_customer_id", "identity_verified", "source"]
_LEAD_DETAIL_COLUMNS = ["loan_type", "loan_amount", "city", "monthly_income", "employment_type"]
_CRM_DETAIL_COLUMNS = ["crm_customer_id", "identity_verified"]


def kind_for(category) -> str:
    return "lead" if category == "new_loan_enquiry" else "query"


def build(record: dict, details: dict, submitted: bool) -> dict:
    """record = the call record built by server.py; details = the flexible extra details.
    Returns {kind, sheet, id_col, prefix, columns, row}."""
    category = record.get("category") or ""
    kind = kind_for(category)
    summary = record.get("reason") or "No request was captured before the call ended"
    common = {
        "call_id": record["call_id"], "customer_ref": record.get("customer_ref", ""), "created_at": record["started_at"],
        "record_status": "submitted" if submitted else "partial (call ended before the form was submitted)",
        "full_name": record.get("full_name", ""), "phone": record.get("phone", ""),
        "consent_to_contact": record.get("consent_to_contact", ""),
        "preferred_callback_time": record.get("preferred_callback_time", ""),
        "summary": summary, "needs_check": record.get("needs_check", ""), "source": "AI voice call",
    }
    if kind == "lead":
        extra = {k: v for k, v in details.items() if k not in _LEAD_DETAIL_COLUMNS + _CRM_DETAIL_COLUMNS}
        row = {**common, "lead_status": "new", "priority": LEAD_PRIORITY,
               **{c: details.get(c, "") for c in _LEAD_DETAIL_COLUMNS + _CRM_DETAIL_COLUMNS},
               "other_details": "; ".join(f"{k}: {v}" for k, v in extra.items())}
        return {"kind": "lead", "sheet": "leads", "id_col": "lead_id", "prefix": "LD-", "columns": LEAD_COLUMNS, "row": row}
    row = {**common, "query_status": "open", "priority": QUERY_PRIORITY.get(category, "normal"),
           "query_type": category or "unclassified",
           "loan_account_number": details.get("loan_account_number", ""),
           **{c: details.get(c, "") for c in _CRM_DETAIL_COLUMNS},
           "details": "; ".join(f"{k}: {v}" for k, v in details.items())}
    return {"kind": "query", "sheet": "queries", "id_col": "query_id", "prefix": "QR-", "columns": QUERY_COLUMNS, "row": row}


def other_sheet(kind: str) -> str:
    """If a call's type changes (e.g. first an 'other' query, later a loan lead), the old record is removed from here."""
    return "queries" if kind == "lead" else "leads"
