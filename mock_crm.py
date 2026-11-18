"""A stand-in CRM for development: serves the demo customers over REST so the 'api' connector can be tested.

Run:   python mock_crm.py                     (listens on http://127.0.0.1:9100)
Use:   CRM_BACKEND=api CRM_API_URL=http://127.0.0.1:9100 CRM_API_KEY=demo-token python server.py

It documents the contract the connector expects from a real CRM:
  GET /customers?phone=<10 digits>   with header  Authorization: Bearer <key>
  200 + JSON  {"customer_id", "name", "dob", "loans": [{...}], "tickets": [{...}]}      404 if there is no such customer
If the real CRM uses different field names or paths, change the maps at the top of crm.py - not this file.
"""
import os

import uvicorn
from fastapi import FastAPI, Header, HTTPException

import crm

TOKEN = os.environ.get("MOCK_CRM_TOKEN", "demo-token")
app = FastAPI()


@app.get("/customers")
def customers(phone: str, authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="bad or missing API key")
    raws = crm._excel_lookup(phone[-10:])
    if not raws:
        raise HTTPException(status_code=404, detail="no such customer")
    return raws[0] if len(raws) == 1 else raws          # a real CRM may return a list when a number is shared


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("MOCK_CRM_PORT", "9100")), log_level="warning")
