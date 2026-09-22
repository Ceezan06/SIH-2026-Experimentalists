"""
load_raw_csvs.py

What this script does, in plain terms:
  1. Reads each of your four eSAKSHI CSV files.
  2. For every row, it packages the whole row up as JSON (untouched)
     and computes a fingerprint (hash) of that JSON.
  3. It inserts that into the raw_landing table in Postgres.
  4. If you run this script twice on the same file, it will NOT create
     duplicate rows - the hash + a "do nothing on conflict" rule handles that.

You should NOT need to edit any logic below - only the CONFIG section
at the top needs your own details filled in.
"""

import hashlib
import json
import math
import re

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# ============================================================
# CONFIG - edit these values for your setup
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",       # change if you created a different database name
    "user": "postgres",         # your Postgres username (default is usually "postgres")
    "password": "1234",   # <-- put the password you set during install
}

# Map each CSV file to a "source" label (matches the raw_landing.source column)
# Edit the file paths on the right to match where your CSVs actually are on your computer.
CSV_SOURCES = {
    "esakshi_recommended": r"Works_Recommended_Sample.csv",
    "esakshi_sanctioned": r"Works_Sanctioned_Sample.csv",
    "esakshi_completed": r"Works_Completed_Sample.csv",
    "esakshi_expenditure": r"expenditure.csv",
}


# ============================================================
# HELPER FUNCTIONS - you shouldn't need to touch these
# ============================================================

def clean_value(value):
    """Convert pandas/NaN values into something JSON can store (None)."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def row_to_json(row: pd.Series) -> str:
    """Turn one CSV row into a JSON string, e.g. {"State": "West Bengal", ...}"""
    row_dict = {col: clean_value(val) for col, val in row.items()}
    return json.dumps(row_dict, ensure_ascii=False, default=str)


def compute_hash(json_text: str) -> str:
    """Fingerprint the row so we can detect exact duplicates later."""
    return hashlib.sha256(json_text.encode("utf-8")).hexdigest()


def extract_work_id(row: pd.Series) -> str | None:
    """
    Try to find a 'Work ID' style value in this row so we can use it as
    source_record_id. Looks for a column literally called 'Work ID', or
    pulls the ID out of a 'Work'/'WORK' column like:
      'WS/MP18251/2024-2025/155461-Street lights' -> 'WS/MP18251/2024-2025/155461'
    """
    for col in ("Work ID", "work_id"):
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()

    for col in ("Work", "WORK"):
        if col in row and pd.notna(row[col]):
            match = re.match(r"^([A-Z]{2}/[A-Za-z0-9]+/\d{4}-\d{4}/\d+)", str(row[col]))
            if match:
                return match.group(1)

    return None


# ============================================================
# MAIN LOGIC
# ============================================================

def load_csv_into_raw_landing(cursor, source_label: str, file_path: str) -> int:
    """Reads one CSV and inserts every row into raw_landing. Returns rows inserted."""

    df = pd.read_csv(file_path, encoding="utf-8-sig")

    rows_to_insert = []
    for _, row in df.iterrows():
        payload_json = row_to_json(row)
        rows_to_insert.append(
            (
                source_label,
                extract_work_id(row),
                compute_hash(payload_json),
                payload_json,
            )
        )

    # ON CONFLICT (raw_hash) DO NOTHING -> re-running this script is always safe
    query = """
        INSERT INTO raw_landing (source, source_record_id, raw_hash, payload)
        VALUES %s
        ON CONFLICT (raw_hash) DO NOTHING;
    """
    execute_values(cursor, query, rows_to_insert, template="(%s, %s, %s, %s::jsonb)")

    return len(rows_to_insert)


def main():
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    total_attempted = 0
    try:
        for source_label, file_path in CSV_SOURCES.items():
            print(f"\nLoading '{source_label}' from {file_path} ...")
            count = load_csv_into_raw_landing(cursor, source_label, file_path)
            total_attempted += count
            print(f"  -> {count} rows read and sent to raw_landing")

        conn.commit()
        print(f"\nDone. {total_attempted} rows attempted across all files.")
        print("(Rows that were exact duplicates of something already loaded were silently skipped.)")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()