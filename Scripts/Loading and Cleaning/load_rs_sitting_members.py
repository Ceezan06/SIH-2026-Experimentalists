"""
load_rs_sitting_members.py

Loads Rajya_Sabha_Sitting_Members (a CSV with no file extension - if
your copy has one, e.g. .csv, update CSV_PATH below) into
staging.raw_rs_sitting_members. Untouched, exactly as sourced -
column names, casing, everything - matching the "raw layer as-is"
principle used for every other staging table.

Run staging_rs_sitting_members_table.sql FIRST, then this.
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

CSV_PATH = "Rajya_Sabha_Sitting_Members.csv"   # adjust if your file has an extension

COLUMNS = ["name_of_member", "party_name", "state", "rajya_sabha_terms"]


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
        quoted_cols = ", ".join(COLUMNS)
        insert_sql = f"INSERT INTO staging.raw_rs_sitting_members ({quoted_cols}) VALUES %s"

        values = []
        for _, row in df.iterrows():
            values.append(tuple(
                (row[c] if c in df.columns and pd.notna(row[c]) else None)
                for c in COLUMNS
            ))

        execute_values(cur, insert_sql, values, page_size=500)
        conn.commit()
        print(f"-> inserted {len(values)} rows into staging.raw_rs_sitting_members")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
