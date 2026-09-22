"""
load_rs_allocated_limit.py

Dedicated loader for the Rajya Sabha Allocated Limit CSV into
staging.raw_mospi_rs_allocations. Standalone - doesn't touch
load_csv_to_staging.py or any other staging table, so there's no
FILE_PATHS juggling and no risk of accidentally reloading the Lok
Sabha allocations file alongside it.

Run staging table already exists (created by schema_v5_full_layered.sql).
This just loads into it.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

CSV_PATH = "Allocated_Limit_for_Honble_MPs__1_.csv"   # adjust if your filename differs

COLUMNS = ["Sr. No.", "State", "Hon'ble Members of Parliament",
           "Elected/Nominated", "Allocated AMOUNT ( ₹ )"]


def main():
    df = pd.read_csv(CSV_PATH, dtype=str)
    print(f"Read {len(df)} rows from {CSV_PATH}")

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        print(f"WARNING: file is missing expected column(s): {missing}")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        quoted_cols = ", ".join(f'"{c}"' for c in COLUMNS)
        insert_sql = f"INSERT INTO staging.raw_mospi_rs_allocations ({quoted_cols}) VALUES %s"

        values = []
        for _, row in df.iterrows():
            values.append(tuple(
                (row[c] if c in df.columns and pd.notna(row[c]) else None)
                for c in COLUMNS
            ))

        execute_values(cur, insert_sql, values, page_size=500)
        conn.commit()
        print(f"-> inserted {len(values)} rows into staging.raw_mospi_rs_allocations")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
