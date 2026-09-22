"""
propagate_allocated_limit.py

Completes task #2: takes the rows now sitting in
staging.raw_mospi_ls_allocations (loaded by load_csv_to_staging.py) and
writes the cleaned, numeric value into dim_mp.allocated_limit.

Matching strategy: by (mp_name, constituency), same uniqueness key as
dim_mp's own UNIQUE constraint. MPs not already in dim_mp are left alone —
this only updates existing rows, it does not create new MPs from the
allocations file. Run this AFTER schema_v5_full_layered.sql and
load_csv_to_staging.py, and after your main merge has populated dim_mp.

Prints anything it couldn't match, so you can sanity-check name/spelling
mismatches between the eSAKSHI-sourced dim_mp.mp_name and the MoSPI
allocations file's naming before deciding it's a real data gap.
"""

import re
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}


def parse_amount(raw):
    """'₹  2,50,00,000' / 'Rs. 25000000' / '2.5 Cr' style strings -> Decimal-safe float.
    Adjust here if your actual file's amount format differs — inspect a few
    real values first (print raw values below) before trusting this blindly."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r"[₹Rs.,\s]", "", s, flags=re.IGNORECASE)
    try:
        return float(s)
    except ValueError:
        return None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT "Hon'ble Members of Parliaments", "Constituency",
                   "Allocated AMOUNT ( ₹ )"
            FROM staging.raw_mospi_ls_allocations
        ''')
        rows = cur.fetchall()
        print(f"Found {len(rows)} rows in staging.raw_mospi_ls_allocations")

        matched, unmatched = 0, []

        for mp_name, constituency, amount_raw in rows:
            amount = parse_amount(amount_raw)
            if not mp_name or amount is None:
                unmatched.append((mp_name, constituency, amount_raw, "missing name or unparseable amount"))
                continue

            cur.execute('''
                UPDATE dim_mp
                SET allocated_limit = %s
                WHERE LOWER(TRIM(mp_name)) = LOWER(TRIM(%s))
                  AND (
                        constituency IS NULL
                        OR LOWER(TRIM(constituency)) = LOWER(TRIM(%s))
                      )
                RETURNING mp_id
            ''', (amount, mp_name, constituency or ""))

            if cur.fetchone():
                matched += 1
            else:
                unmatched.append((mp_name, constituency, amount_raw, "no dim_mp match found"))

        conn.commit()
        print(f"\nDone. {matched} dim_mp rows updated with allocated_limit.")

        if unmatched:
            print(f"\n{len(unmatched)} rows could NOT be matched/parsed — "
                  f"check these for name mismatches or format issues:")
            for mp_name, constituency, amount_raw, reason in unmatched[:20]:
                print(f"  - {mp_name!r} / {constituency!r} / {amount_raw!r} -> {reason}")
            if len(unmatched) > 20:
                print(f"  ...and {len(unmatched) - 20} more")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
