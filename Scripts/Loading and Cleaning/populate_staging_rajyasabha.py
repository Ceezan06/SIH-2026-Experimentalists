"""
populate_staging_rajyasabha.py

Same idea as populate_staging_from_raw_landing.py, but for the 4
rajyasabha_* source labels that automated_ingestion_rajya_sabha.py
writes into raw_landing. Fills the 4 new staging.raw_rs_* tables from
staging_rajyasabha_tables.sql.

Run order: schema_v5_full_layered.sql -> staging_rajyasabha_tables.sql
-> automated_ingestion_rajya_sabha.py -> this script.

Does not touch raw_landing or any Lok Sabha table.
"""

import json
import psycopg2
from psycopg2.extras import execute_values

# ============================================================
# CONFIG - edit to match your setup
# ============================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

# Maps: raw_landing.source label -> (staging table, ordered column list)
SOURCE_MAP = {
    "rajyasabha_recommended": (
        "staging.raw_rs_recommended_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Recommended Amount (₹)", "Recommendation Date",
         "Has Images", "IDA"],
    ),
    "rajyasabha_sanctioned": (
        "staging.raw_rs_sanctioned_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Recommended Amount (₹)", "Recommendation Date",
         "Sanction Amount (₹)", "Sanction Date", "Work Status", "IDA"],
    ),
    "rajyasabha_completed": (
        "staging.raw_rs_completed_works",
        ["Work ID", "Work Description", "Category", "MP Name", "Constituency",
         "State", "House", "Final Amount (₹)", "Completed Date",
         "Has Images", "Average Rating", "IDA"],
    ),
    "rajyasabha_expenditure": (
        "staging.raw_rs_expenditures",
        ["MP Name", "Constituency", "State", "House", "Work Description",
         "Vendor", "IDA", "Expenditure Amount (₹)", "Expenditure Date",
         "Payment Status"],
    ),
}

# Same alias-handling idea as the LS version — the live API's field names
# are ALL_CAPS_WITH_UNDERSCORES (e.g. WORK_DESCRIPTION), so this maps the
# staging column's human-readable name to what get_value() actually
# normalizes and looks for. get_value() below is case/spacing tolerant,
# so this list just needs to cover real alternate spellings if any turn up.
FIELD_ALIASES = {
    "Recommended Amount (₹)": ["Recommended Amount (₹)", "Recommended Amount"],
    "Final Amount (₹)": ["Final Amount (₹)", "Final Amount"],
    "Sanction Amount (₹)": ["Sanction Amount (₹)", "Sanction Amount"],
    "Expenditure Amount (₹)": ["Expenditure Amount (₹)", "Fund Disbursed Amount",
                                "Fund Disbursed Amt", "FUND_DISBURSED_AMT"],
}


def load_payload(payload):
    if isinstance(payload, dict):
        return payload
    return json.loads(payload)


def get_value(payload, column_name):
    """Case/spacing/underscore-tolerant lookup, so 'Work Description' matches
    a real payload key of 'WORK_DESCRIPTION' without needing every alias
    spelled out by hand."""
    candidates = FIELD_ALIASES.get(column_name, [column_name])

    def normalize(s):
        return "".join(ch.lower() for ch in s if ch.isalnum())

    norm_map = {normalize(k): v for k, v in payload.items()}
    for candidate in candidates:
        v = norm_map.get(normalize(candidate))
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
                print(f"  (nothing yet — run automated_ingestion_rajya_sabha.py first if this is unexpected)")
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
        print("\nDone. All 4 Rajya Sabha staging tables backfilled from raw_landing.")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
