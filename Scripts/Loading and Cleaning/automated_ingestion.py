"""
automated_ingestion.py

What this script does, in plain terms:
  Instead of clicking through the eSAKSHI dashboard by hand for every MP,
  this talks directly to the same backend the dashboard's browser uses.

  For your chosen state, it:
    1. Looks up the state's internal ID.
    2. Gets the list of every constituency in that state.
    3. For each constituency, finds which MP represents it.
    4. For each MP, pulls all 4 work-stage tables (Recommended, Sanctioned,
       Completed, Expenditure) directly as JSON.
    5. Inserts every record straight into raw_landing - same table,
       same format, as load_raw_csvs.py already uses.

This means you do NOT need load_raw_csvs.py for MPs collected this way -
this script goes straight from the live website into your database.

IMPORTANT: this was built by reverse-engineering real browser requests,
not from official documentation. If eSAKSHI changes its site, this may
need small adjustments. If you get errors, share them and we'll debug
the same way we figured this out in the first place.

Please keep the delay between requests (REQUEST_DELAY_SECONDS below) -
it exists so we don't hammer a government server with rapid-fire calls.
"""

import hashlib
import json
import time

import psycopg2
import requests
from psycopg2.extras import execute_values


# ============================================================
# CONFIG - edit these values for your run
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

TARGET_STATE = "West Bengal"
HOUSE_ID = "2" 

REPORT_KEYS = [
    "Works Recommended",
    "Works Sanctioned",
    "Works Completed",
    "Expenditure on Completed and On-going Works as on Date",
]

# Maps each report key to a short label for the 'source' column in raw_landing,
# matching the naming style your existing scripts already use.
SOURCE_LABELS = {
    "Works Recommended": "esakshi_recommended",
    "Works Sanctioned": "esakshi_sanctioned",
    "Works Completed": "esakshi_completed",
    "Expenditure on Completed and On-going Works as on Date": "esakshi_expenditure",
}

BASE_URL = "https://mplads.mospi.gov.in/rest/PreLoginDashboardData"

REQUEST_DELAY_SECONDS = 0.6   # politeness delay between every request - do not remove


# ============================================================
# HTTP HELPERS
# ============================================================

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://mplads.mospi.gov.in",
    "Referer": "https://mplads.mospi.gov.in/digigov/dashboard.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

session = requests.Session()
session.headers.update(HEADERS)


def call_api(method_name: str, payload: dict):
    """POSTs to one of the eSAKSHI endpoints and returns the parsed JSON response."""
    url = f"{BASE_URL}/{method_name}"
    response = session.post(url, json=payload, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return response.json()


def get_state_id(state_name: str) -> str:
    """Looks up a state's internal ID by name (case-insensitive)."""
    data = call_api("getStateData", {})
    for row in data:
        if row.get("STATE_NAME", "").strip().lower() == state_name.strip().lower():
            return str(row["STATE_ID"])
    raise ValueError(f"State '{state_name}' not found in getStateData response.")


def get_constituencies(state_id: str):
    """Returns [{'ID': constituency_id, 'CAPTION': name}, ...] for a state."""
    return call_api("getConstituencyData", {"id": state_id})


def get_mp_for_constituency(constituency_id, house_id: str):
    """Returns (mp_id, mp_name) for the MP representing a constituency, or (None, None)."""
    combo = f"{constituency_id},{house_id},7"
    data = call_api("getMpAndConstCombo", {"const_combo": combo})
    if data:
        return str(data[0]["ID"]), data[0]["CAPTION"]
    return None, None


def get_report_records(state_id, constituency_id, mp_id, house_id: str, report_key: str):
    """
    Pulls one report table (e.g. 'Works Recommended') for one MP.
    Returns a list of record dicts, or an empty list if nothing came back.
    """
    combo = f"{state_id},{constituency_id},{mp_id},{house_id},7"
    data = call_api("getTilesReportData", {"combo": combo, "key": report_key})

    if not data:
        return []

    # The response wraps the real data under a single key whose exact name
    # varies (e.g. "Total Works Recommended" instead of "Works Recommended").
    # We don't rely on it matching - just take whatever the one value is.
    wrapped_value = next(iter(data.values()))
    if not wrapped_value:
        return []

    # The value itself is a JSON-encoded STRING (double-encoded), so it
    # needs a second parse to become an actual list of dicts.
    if isinstance(wrapped_value, str):
        try:
            return json.loads(wrapped_value)
        except json.JSONDecodeError:
            return []
    return wrapped_value


# ============================================================
# DATABASE HELPERS - same pattern as load_raw_csvs.py
# ============================================================

def clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN check without importing math
        return None
    return value


def record_to_json(record: dict) -> str:
    cleaned = {k: clean_value(v) for k, v in record.items()}
    return json.dumps(cleaned, ensure_ascii=False, default=str)


def compute_hash(json_text: str) -> str:
    return hashlib.sha256(json_text.encode("utf-8")).hexdigest()


def guess_work_id(record: dict):
    """Tries a few likely field names for a work identifier."""
    for key in ("WORK_ID", "ACTIVITY_ID", "UNIQUE_WORK_NUMBER", "ACTIVITY_NAME", "WORK"):
        if key in record and record[key]:
            return str(record[key]).strip()
    return None


def insert_records(cursor, source_label: str, records: list) -> int:
    if not records:
        return 0

    rows_to_insert = []
    for record in records:
        payload_json = record_to_json(record)
        rows_to_insert.append(
            (source_label, guess_work_id(record), compute_hash(payload_json), payload_json)
        )

    query = """
        INSERT INTO raw_landing (source, source_record_id, raw_hash, payload)
        VALUES %s
        ON CONFLICT (raw_hash) DO NOTHING;
    """
    execute_values(cursor, query, rows_to_insert, template="(%s, %s, %s, %s::jsonb)")
    return len(rows_to_insert)


# ============================================================
# MAIN LOGIC
# ============================================================

def main():
    print(f"Starting automated ingestion for: {TARGET_STATE}\n")

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    total_rows_inserted = 0
    total_mps_processed = 0

    try:
        print(f"Looking up state ID for '{TARGET_STATE}'...")
        state_id = get_state_id(TARGET_STATE)
        print(f"  -> state_id = {state_id}\n")

        print("Fetching constituency list...")
        constituencies = get_constituencies(state_id)
        print(f"  -> {len(constituencies)} constituencies found\n")

        for i, const in enumerate(constituencies, start=1):
            const_id = const["ID"]
            const_name = const["CAPTION"]

            mp_id, mp_name = get_mp_for_constituency(const_id, HOUSE_ID)
            if not mp_id:
                print(f"[{i}/{len(constituencies)}] {const_name}: no MP found, skipping.")
                continue

            print(f"[{i}/{len(constituencies)}] {const_name} -> {mp_name}")

            for report_key in REPORT_KEYS:
                records = get_report_records(state_id, const_id, mp_id, HOUSE_ID, report_key)
                source_label = SOURCE_LABELS[report_key]
                inserted = insert_records(cursor, source_label, records)
                total_rows_inserted += inserted
                print(f"    {report_key}: {len(records)} records ({inserted} sent to raw_landing)")

            conn.commit()  # commit after each MP, so partial progress is never lost
            total_mps_processed += 1

        print(f"\nDone. Processed {total_mps_processed} MPs, {total_rows_inserted} rows sent to raw_landing.")
        print("Run merge_into_projects.py next to build these into your projects table.")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong. Progress up to the last completed MP was already saved.")
        print("Error details:")
        print(e)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
