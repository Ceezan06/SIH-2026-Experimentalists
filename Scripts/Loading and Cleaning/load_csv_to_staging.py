"""
load_csv_to_staging.py

Loads the 4 staging tables that have NO data yet, because you haven't
sourced/downloaded these files before now:
  - staging.raw_sitting_members       <- Sitting Members.xlsx
  - staging.raw_mospi_ls_allocations  <- Allocated_Limit_for_Honble_MPs.csv (LS)
  - staging.raw_mospi_rs_allocations  <- Allocated Limit ... RS.csv (if/when you get it)
  - staging.raw_ei_mp_summary         <- mplads_mp_summary...EI.csv (if/when you get it)

Everything is loaded as TEXT/VARCHAR, untouched — matching the staging
layer's "raw, uncleaned" design. No parsing or amount-cleaning happens here;
that's the Core Master layer's job (see propagate_allocated_limit.py for the
one piece that's needed right now: dim_mp.allocated_limit).

Only fill in file paths for the CSVs you actually have right now — leave the
others as None and they'll be skipped. Right now that's very likely just the
Allocated Limit (LS) file per your immediate task.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ============================================================
# CONFIG - edit these
# ============================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}

# Set the path for any file you have ready; leave as None to skip.
FILE_PATHS = {
    "raw_mospi_ls_allocations": r"Allocated_Limit_for_Honble_MPs.csv",  # <-- your immediate task
    "raw_sitting_members": r"Sitting_Members.xlsx",     # r"Sitting Members.xlsx"
    "raw_mospi_rs_allocations": None,     # r"Allocated Limit ... RS.csv"
    "raw_ei_mp_summary": None,            # r"mplads_mp_summary...EI.csv"
}

# Table -> expected column names, in the exact quoted form used in
# schema_v5_full_layered.sql. Loader will match your file's headers to
# these case-insensitively and warn about anything it can't match.
TABLE_COLUMNS = {
    "raw_sitting_members": [
        "Name of Member", "Party Name", "Constituency", "State",
        "MemberShip Status", "Lok Sabha Terms",
    ],
    "raw_mospi_ls_allocations": [
        "Sr. No.", "State", "Hon'ble Members of Parliaments",
        "Constituency", "Allocated AMOUNT ( ₹ )",
    ],
    "raw_mospi_rs_allocations": [
        "Sr. No.", "State", "Hon'ble Members of Parliament",
        "Elected/Nominated", "Allocated AMOUNT ( ₹ )",
    ],
    "raw_ei_mp_summary": [
        "MP Name", "Constituency", "State", "House",
        "Allocated Amount (₹)", "Amount Recommended (₹)",
        "Total Expenditure (₹)", "Utilization %", "Completed Works",
        "Recommended Works", "Completion Rate %",
        "Balance Not Yet Paid to Vendors (₹)", "Transaction Count",
        "Successful Payments", "Pending Payments", "Average Rating",
    ],
}


def read_any(path):
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str)


def load_table(cur, table_short_name, path):
    expected_cols = TABLE_COLUMNS[table_short_name]
    df = read_any(path)

    # case-insensitive header matching, same spirit as get_field() elsewhere
    file_cols_lower = {c.strip().lower(): c for c in df.columns}
    resolved = {}
    missing = []
    for col in expected_cols:
        match = file_cols_lower.get(col.strip().lower())
        if match:
            resolved[col] = match
        else:
            missing.append(col)

    if missing:
        print(f"  WARNING: {table_short_name} — file is missing expected "
              f"column(s), will insert NULL for: {missing}")

    quoted_cols = ", ".join(f'"{c}"' for c in expected_cols)
    insert_sql = f'INSERT INTO staging.{table_short_name} ({quoted_cols}) VALUES %s'

    values = []
    for _, row in df.iterrows():
        values.append(tuple(
            (row[resolved[col]] if col in resolved and pd.notna(row[resolved[col]]) else None)
            for col in expected_cols
        ))

    execute_values(cur, insert_sql, values, page_size=1000)
    print(f"  -> inserted {len(values)} rows into staging.{table_short_name}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        any_loaded = False
        for table_short_name, path in FILE_PATHS.items():
            if not path:
                print(f"{table_short_name}: no file path set, skipping")
                continue
            print(f"{table_short_name}: loading from {path}")
            load_table(cur, table_short_name, path)
            any_loaded = True

        conn.commit()
        if any_loaded:
            print("\nDone. Committed all loaded tables.")
        else:
            print("\nNothing loaded — set at least one file path in FILE_PATHS.")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
