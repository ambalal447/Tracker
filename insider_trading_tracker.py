"""
NSE Insider Trading Disclosure Tracker
========================================
Fetches publicly disclosed Prohibition of Insider Trading (PIT) filings that
NSE-listed companies and their insiders/promoters are legally required to
report under SEBI's PIT Regulations. This is regulatory disclosure data —
not non-public/material information.

Usage:
    python insider_trading_tracker.py

Optional environment variables:
    NSE_SYMBOL   - track a single ticker, e.g. "RELIANCE" (default: all companies)
    FROM_DATE    - DD-MM-YYYY (default: 7 days ago)
    TO_DATE      - DD-MM-YYYY (default: today)

NOTE: NSE's site has bot-protection (Akamai) that sometimes blocks requests
from datacenter IPs, including GitHub Actions runners. If you get repeated
403s or empty responses there, run this locally instead, or switch to BSE's
insider trading disclosures as a fallback source.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timedelta

import requests

NSE_HOME = "https://www.nseindia.com"
NSE_PIT_API = "https://www.nseindia.com/api/corporates-pit"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
}

RAW_DIR = "data/raw"
SUMMARY_CSV = "data/insider_trades_summary.csv"

# NSE's exact JSON keys aren't guaranteed stable. If the summary CSV comes
# out mostly blank after your first real run, open the matching file in
# data/raw/ and update these candidate key names to match what NSE actually
# returned for each field.
FIELD_MAP = {
    "symbol": ["symbol"],
    "company": ["company", "companyName"],
    "person_name": ["acqName", "personName", "name"],
    "category": ["personCategory", "category"],
    "transaction_type": ["secAcqType", "transactionType", "acqMode"],
    "quantity": ["secAcq", "secAcqNo", "quantity"],
    "value": ["secVal", "value"],
    "date_filed": ["date", "dateFiled", "intimDt"],
}


def get_session():
    """NSE requires cookies from a homepage visit before its API will respond."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(NSE_HOME, timeout=15)
    return session


def fetch_insider_trades(symbol=None, from_date=None, to_date=None):
    session = get_session()
    to_date = to_date or datetime.now().strftime("%d-%m-%Y")
    from_date = from_date or (datetime.now() - timedelta(days=7)).strftime("%d-%m-%Y")

    params = {"index": "equities", "from_date": from_date, "to_date": to_date}
    if symbol:
        params["symbol"] = symbol

    resp = session.get(NSE_PIT_API, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def save_raw(data):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def pick(record, candidates):
    for key in candidates:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return ""


def unique_id(record):
    """Hash the whole record so dedup works even if we don't know every field name."""
    blob = json.dumps(record, sort_keys=True)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def update_summary(records):
    os.makedirs(os.path.dirname(SUMMARY_CSV), exist_ok=True)
    file_exists = os.path.isfile(SUMMARY_CSV)

    existing_ids = set()
    if file_exists:
        with open(SUMMARY_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_ids.add(row.get("unique_id", ""))

    fieldnames = ["unique_id"] + list(FIELD_MAP.keys())
    new_rows = 0
    with open(SUMMARY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in records:
            uid = unique_id(r)
            if uid in existing_ids:
                continue
            row = {"unique_id": uid}
            for col, candidates in FIELD_MAP.items():
                row[col] = pick(r, candidates)
            writer.writerow(row)
            new_rows += 1
    return new_rows


def main():
    symbol = os.environ.get("NSE_SYMBOL")
    from_date = os.environ.get("FROM_DATE")
    to_date = os.environ.get("TO_DATE")

    try:
        data = fetch_insider_trades(symbol, from_date, to_date)
    except Exception as e:
        print(f"Fetch failed: {e}")
        return

    records = data.get("data", []) if isinstance(data, dict) else []
    print(f"Fetched {len(records)} disclosure(s).")

    if records:
        raw_path = save_raw(data)
        print(f"Raw response saved to {raw_path}")
        new_rows = update_summary(records)
        print(f"Added {new_rows} new row(s) to {SUMMARY_CSV}")
    else:
        print("No records returned — nothing to save.")


if __name__ == "__main__":
    main()
  
