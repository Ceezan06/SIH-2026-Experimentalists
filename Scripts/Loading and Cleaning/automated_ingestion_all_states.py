"""
automated_ingestion_all_states.py

Same idea as automated_ingestion.py, but loops through every state
instead of just one. Built for a long, mostly-unattended run.

Resume safety: after each state finishes completely, its name gets
written to ingestion_progress.json. If this script crashes or you
need to stop it partway through (Ctrl+C), just run it again - it
will skip every state already marked complete and pick up where it
left off, instead of re-doing everything from scratch.

Expect this to take a while - roughly 30-45 minutes for all of India,
since it's deliberately paced to avoid hammering a government server.
It's fine to let it run in the background while you do something else.
"""

import hashlib
import json
import os
import time

import psycopg2
import requests
from psycopg2.extras import execute_values


# ============================================================
# CONFIG
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

HOUSE_ID = "2"   # 2 = Lok Sabha (Rajya Sabha code not yet confirmed)

# States already fully collected in a previous run - skipped even on
# a totally fresh start, so you never accidentally re-do West Bengal.
ALREADY_DONE_STATES = ["West Bengal"]

PROGRESS_FILE = "ingestion_progress.json"

REPORT_KEYS = [
    "Works Recommended",
    "Works Sanctioned",
    "Works Completed",
    "Expenditure on Completed and On-going Works as on Date",
]

SOURCE_LABELS = {
    "Works Recommended": "esakshi_recommended",
    "Works Sanctioned": "esakshi_sanctioned",
    "Works Completed": "esakshi_completed",
    "Expenditure on Completed and On-going Works as on Date": "esakshi_expenditure",
}

BASE_URL = "https://mplads.mospi.gov.in/rest/PreLoginDashboardData"
REQUEST_DELAY_SECONDS = 0.6


# ============================================================
# PROGRESS TRACKING
# ============================================================

def load_completed_states() -> set:
    completed = set(ALREADY_DONE_STATES)
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            data = json.load(f)
            completed.update(data.get("completed_states", []))
    return completed


def mark_state_complete(state_name: str):
    completed = load_completed_states()
    completed.add(state_name)
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"completed_states": sorted(completed)}, f, indent=2)


# ============================================================
# HTTP HELPERS - same as the single-state version
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
    url = f"{BASE_URL}/{method_name}"
    response = session.post(url, json=payload, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return response.json()


def get_all_states():
    """Returns [{'STATE_NAME': ..., 'STATE_ID': ...}, ...] for every state."""
    return call_api("getStateData", {})


def get_constituencies(state_id: str):
    return call_api("getConstituencyData", {"id": state_id})


def get_mp_for_constituency(constituency_id, house_id: str):
    combo = f"{constituency_id},{house_id},7"
    data = call_api("getMpAndConstCombo", {"const_combo": combo})
    if data:
        return str(data[0]["ID"]), data[0]["CAPTION"]
    return None, None


def get_report_records(state_id, constituency_id, mp_id, house_id: str, report_key: str):
    combo = f"{state_id},{constituency_id},{mp_id},{house_id},7"
    data = call_api("getTilesReportData", {"combo": combo, "key": report_key})
    if not data:
        return []
    wrapped_value = next(iter(data.values()))
    if not wrapped_value:
        return []
    if isinstance(wrapped_value, str):
        try:
            return json.loads(wrapped_value)
        except json.JSONDecodeError:
            return []
    return wrapped_value


# ============================================================
# DATABASE HELPERS
# ============================================================

def clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    return value


def record_to_json(record: dict) -> str:
    cleaned = {k: clean_value(v) for k, v in record.items()}
    return json.dumps(cleaned, ensure_ascii=False, default=str)


def compute_hash(json_text: str) -> str:
    return hashlib.sha256(json_text.encode("utf-8")).hexdigest()


def guess_work_id(record: dict):
    for key in ("WORK_RECOMMENDATION_DTL_ID", "WORK_ID", "ACTIVITY_ID", "UNIQUE_WORK_NUMBER", "ACTIVITY_NAME", "WORK"):
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

def process_state(cursor, conn, state_name: str, state_id: str) -> tuple:
    """Returns (mps_processed, rows_inserted) for this one state."""
    print(f"\n{'='*60}\nSTATE: {state_name} (id={state_id})\n{'='*60}")

    constituencies = get_constituencies(state_id)
    print(f"  {len(constituencies)} constituencies found")

    mps_processed = 0
    rows_inserted = 0

    for i, const in enumerate(constituencies, start=1):
        const_id = const["ID"]
        const_name = const["CAPTION"]

        mp_id, mp_name = get_mp_for_constituency(const_id, HOUSE_ID)
        if not mp_id:
            print(f"  [{i}/{len(constituencies)}] {const_name}: no MP found, skipping.")
            continue

        print(f"  [{i}/{len(constituencies)}] {const_name} -> {mp_name}")

        for report_key in REPORT_KEYS:
            records = get_report_records(state_id, const_id, mp_id, HOUSE_ID, report_key)
            source_label = SOURCE_LABELS[report_key]
            inserted = insert_records(cursor, source_label, records)
            rows_inserted += inserted

        conn.commit()
        mps_processed += 1

    return mps_processed, rows_inserted


def main():
    completed_states = load_completed_states()
    print(f"States already marked complete (will be skipped): {sorted(completed_states)}\n")

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    grand_total_mps = 0
    grand_total_rows = 0

    try:
        print("Fetching full list of states...")
        all_states = get_all_states()
        print(f"  -> {len(all_states)} states/UTs found\n")

        remaining = [s for s in all_states if s["STATE_NAME"] not in completed_states]
        print(f"{len(remaining)} states remaining to process.\n")

        for state in remaining:
            state_name = state["STATE_NAME"]
            state_id = str(state["STATE_ID"])

            try:
                mps, rows = process_state(cursor, conn, state_name, state_id)
                grand_total_mps += mps
                grand_total_rows += rows
                mark_state_complete(state_name)
                print(f"  DONE with {state_name}: {mps} MPs, {rows} rows. Progress saved.")

            except Exception as e:
                conn.rollback()
                print(f"\n  ERROR while processing {state_name} - this state was NOT marked complete.")
                print(f"  You can re-run this script later and it will retry {state_name}.")
                print(f"  Error details: {e}\n")
                continue

        print(f"\n{'='*60}")
        print(f"ALL DONE. {grand_total_mps} MPs processed, {grand_total_rows} rows sent to raw_landing this run.")
        print("Run merge_into_projects_v2.py next to build these into your projects table.")
        print(f"{'='*60}")

    except Exception as e:
        print("\nA top-level error stopped the run. Progress for completed states is saved.")
        print("Just run this script again to continue from where it left off.")
        print(f"Error details: {e}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
