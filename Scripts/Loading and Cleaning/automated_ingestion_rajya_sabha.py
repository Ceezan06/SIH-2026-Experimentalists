"""
automated_ingestion_rajya_sabha.py

Rajya Sabha counterpart to automated_ingestion_all_states.py. Same HTTP
session, same retry/politeness/checkpoint pattern — the only real
differences are the lookup chain and the combo format, both confirmed
by hand via DevTools on the live RS dashboard:

  - House code is "1" for Rajya Sabha (vs "2" for Lok Sabha).
  - RS has NO constituency step. Lok Sabha goes
        state -> getConstituencyData -> getMpAndConstCombo -> MP
    Rajya Sabha goes
        state -> getMpNamesData -> MP
    directly. getMpNamesData also returns MULTIPLE entries per state,
    one per MP *term* (RS seats rotate on a staggered 6-year cycle,
    so a state can show several past + current MP IDs). We deliberately
    process every one returned, not just the newest, so we don't miss
    works tied to an MP ID from an earlier term.
  - The tile-report combo is "state_id,0,mp_id,1,1" — constituency slot
    is always 0, and (confirmed empirically, not guessed) the trailing
    tag is "1" for RS where Lok Sabha's equivalent call uses "7".

Writes into the SAME raw_landing table, under NEW source labels
(rajyasabha_recommended / _sanctioned / _completed / _expenditure) so
LS and RS rows are distinguishable and neither overwrites the other.
merge_into_projects_v4.py needs a small addition to also read these
4 new labels — see the comment block at the end of this file for the
exact change.
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

HOUSE_ID = "1"          # 1 = Rajya Sabha (confirmed via DevTools, unlike the
                         # LS script's old "not yet confirmed" comment)
COMBO_TAIL = "1"         # trailing combo tag for RS (LS uses "7" instead)

ALREADY_DONE_STATES = []   # fill in as you go, same pattern as the LS script

PROGRESS_FILE = "ingestion_progress_rajyasabha.json"   # separate from the LS one on purpose

REPORT_KEYS = [
    "Works Recommended",
    "Works Sanctioned",
    "Works Completed",
    "Expenditure on Completed and On-going Works as on Date",
]

SOURCE_LABELS = {
    "Works Recommended": "rajyasabha_recommended",
    "Works Sanctioned": "rajyasabha_sanctioned",
    "Works Completed": "rajyasabha_completed",
    "Expenditure on Completed and On-going Works as on Date": "rajyasabha_expenditure",
}

BASE_URL = "https://mplads.mospi.gov.in/rest/PreLoginDashboardData"
REQUEST_DELAY_SECONDS = 0.6


# ============================================================
# PROGRESS TRACKING (identical pattern to the LS script)
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
# HTTP HELPERS - identical to the LS script
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
    """Same call as the LS script — state list is shared across both houses."""
    return call_api("getStateData", {})


def get_rs_mps_for_state(state_id: str, house_id: str):
    """RS-specific: state -> MP names DIRECTLY, no constituency step.
    Returns [(mp_id, mp_caption), ...] — one entry PER TERM, so a state
    with 3 MPs across 2 terms each could return up to 6 entries. That's
    expected, not a bug — process all of them."""
    combo = f"{state_id},{house_id},"
    data = call_api("getMpNamesData", {"state_combo": combo})
    if not data:
        return []
    return [(str(entry["ID"]), entry["CAPTION"]) for entry in data]


def get_report_records(state_id, mp_id, house_id: str, combo_tail: str, report_key: str):
    combo = f"{state_id},0,{mp_id},{house_id},{combo_tail}"
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
# DATABASE HELPERS - identical to the LS script
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
    for key in ("WORK_RECOMMENDATION_DTL_ID", "WORK_ID", "ACTIVITY_ID",
                "UNIQUE_WORK_NUMBER", "ACTIVITY_NAME", "WORK"):
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
    """Returns (mp_terms_processed, rows_inserted) for this one state."""
    print(f"\n{'='*60}\nSTATE: {state_name} (id={state_id})\n{'='*60}")

    mp_entries = get_rs_mps_for_state(state_id, HOUSE_ID)
    print(f"  {len(mp_entries)} MP term(s) found (includes past terms)")

    mp_terms_processed = 0
    rows_inserted = 0

    for i, (mp_id, mp_caption) in enumerate(mp_entries, start=1):
        print(f"  [{i}/{len(mp_entries)}] {mp_caption} (id={mp_id})")

        for report_key in REPORT_KEYS:
            records = get_report_records(state_id, mp_id, HOUSE_ID, COMBO_TAIL, report_key)
            source_label = SOURCE_LABELS[report_key]
            inserted = insert_records(cursor, source_label, records)
            rows_inserted += inserted

        conn.commit()
        mp_terms_processed += 1

    return mp_terms_processed, rows_inserted


def main():
    completed_states = load_completed_states()
    print(f"States already marked complete (will be skipped): {sorted(completed_states)}\n")

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    grand_total_mp_terms = 0
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
                mp_terms, rows = process_state(cursor, conn, state_name, state_id)
                grand_total_mp_terms += mp_terms
                grand_total_rows += rows
                mark_state_complete(state_name)
                print(f"  DONE with {state_name}: {mp_terms} MP-terms, {rows} rows. Progress saved.")

            except Exception as e:
                conn.rollback()
                print(f"\n  ERROR while processing {state_name} - this state was NOT marked complete.")
                print(f"  You can re-run this script later and it will retry {state_name}.")
                print(f"  Error details: {e}\n")
                continue

        print(f"\n{'='*60}")
        print(f"ALL DONE. {grand_total_mp_terms} MP-terms processed, "
              f"{grand_total_rows} rows sent to raw_landing this run.")
        print("Run merge_into_projects_v4.py next (after adding the rajyasabha_* "
              "source labels — see the comment block at the bottom of this file).")
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


# ============================================================
# REQUIRED CHANGE TO merge_into_projects_v4.py TO INCLUDE RS DATA
# ============================================================
#
# In merge_into_projects_v4.py, main() currently has:
#
#     recommended = fetch_source_rows(cur, "esakshi_recommended")
#     sanctioned = fetch_source_rows(cur, "esakshi_sanctioned")
#     completed = fetch_source_rows(cur, "esakshi_completed")
#     expenditure = fetch_source_rows(cur, "esakshi_expenditure")
#
# Change it to also pull in the RS-labeled rows and merge the two
# dicts together (RS work IDs won't collide with LS ones, since they
# follow the same WS/MP.../... scheme with different MP numbers):
#
#     recommended = {**fetch_source_rows(cur, "esakshi_recommended"),
#                    **fetch_source_rows(cur, "rajyasabha_recommended")}
#     sanctioned = {**fetch_source_rows(cur, "esakshi_sanctioned"),
#                   **fetch_source_rows(cur, "rajyasabha_sanctioned")}
#     completed = {**fetch_source_rows(cur, "esakshi_completed"),
#                  **fetch_source_rows(cur, "rajyasabha_completed")}
#     expenditure = {**fetch_source_rows(cur, "esakshi_expenditure"),
#                    **fetch_source_rows(cur, "rajyasabha_expenditure")}
#
# No other change needed — dim_mp.house already stores "1" or "2" per
# MP from the house field in each payload, so Lok Sabha and Rajya
# Sabha MPs naturally end up as separate dim_mp rows in the same table.
# ============================================================
