"""
populate_staging_from_raw_landing.py

What this does:
Your raw_landing table already has every eSAKSHI row you've collected,
stored as JSONB under source labels ('esakshi_recommended', 'esakshi_sanctioned',
'esakshi_completed', 'esakshi_expenditure'). This script reads those rows back
out and inserts them into the 4 matching TYPED staging tables from
schema_v5_full_layered.sql (staging.raw_ei_recommended_works, etc.) —
no re-downloading, no re-scraping.

It does NOT change or delete anything in raw_landing. It also does not touch
dim_mp / fact_projects / fact_expenditures — this only fills the staging layer.

Run schema_v5_full_layered.sql FIRST, then run this.
"""

import json
import psycopg2
from psycopg2.extras import execute_values

# ============================================================
# CONFIG - edit to match your setup (same as your other scripts)
# ============================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

# Maps: raw_landing.source label -> (staging table, ordered column list)
# Column names must match the staging table's quoted column names EXACTLY.
SOURCE_MAP = {
    "esakshi_recommended": (
        "staging.raw_ei_recommended_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Recommended Amount (₹)", "Recommendation Date",
         "Has Images", "IDA"],
    ),
    "esakshi_sanctioned": (
        "staging.raw_ei_sanctioned_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Recommended Amount (₹)", "Recommendation Date",
         "Sanction Amount (₹)", "Sanction Date", "Work Status", "IDA"],
    ),
    "esakshi_completed": (
        "staging.raw_ei_completed_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Final Amount (₹)", "Completed Date",
         "Has Images", "Average Rating", "IDA"],
    ),
    "esakshi_expenditure": (
        "staging.raw_ei_expenditures",
        ["MP Name", "Constituency", "State", "House", "Work Description",
         "Vendor", "IDA", "Expenditure Amount (₹)", "Expenditure Date",
         "Payment Status"],
    ),
}

# If your CSV headers differ slightly from the spec's exact column names
# (e.g. abbreviations, alternate spellings you already handle in
# merge_into_projects_v4.py's get_field()), add lookups here:
# {expected_column_name: [alias1, alias2, ...]}
FIELD_ALIASES = {
    "Recommended Amount (₹)": ["Recommended Amount (₹)", "Recommended Amount"],
    "Final Amount (₹)": ["Final Amount (₹)", "Final Amount"],
    "Sanction Amount (₹)": ["Sanction Amount (₹)", "Sanction Amount"],
    "Expenditure Amount (₹)": ["Expenditure Amount (₹)", "Fund Disbursed Amount",
                                "Fund Disbursed Amt", "FUND_DISBURSED_AMT"],
}


def load_payload(payload):
    """raw_landing.payload may come back as dict (jsonb) or str depending on driver."""
    if isinstance(payload, dict):
        return payload
    return json.loads(payload)


def get_value(payload, column_name):
    """Case-insensitive, alias-aware lookup — mirrors get_field() from
    merge_into_projects_v4.py so the same real-world field-name mismatches
    (aliases, case) don't silently drop data here too."""
    candidates = FIELD_ALIASES.get(column_name, [column_name])
    lower_map = {k.strip().lower(): v for k, v in payload.items()}
    for candidate in candidates:
        v = lower_map.get(candidate.strip().lower())
        if v is not None:
            return v
    return None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        for source_label, (table_name, columns) in SOURCE_MAP.items():
            cur.execute(
                "SELECT payload FROM raw_landing WHERE source = %s",
                (source_label,),
            )
            rows = cur.fetchall()
            print(f"{source_label}: {len(rows)} raw rows found")

            if not rows:
                continue

            quoted_cols = ", ".join(f'"{c}"' for c in columns)
            insert_sql = f'INSERT INTO {table_name} ({quoted_cols}) VALUES %s'

            values = []
            for (payload_raw,) in rows:
                payload = load_payload(payload_raw)
                values.append(tuple(get_value(payload, col) for col in columns))

            execute_values(cur, insert_sql, values, page_size=1000)
            print(f"  -> inserted {len(values)} rows into {table_name}")

        conn.commit()
        print("\nDone. All 4 eSAKSHI staging tables backfilled from raw_landing.")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
