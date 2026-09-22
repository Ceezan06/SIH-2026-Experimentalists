"""
propagate_rs_allocated_limit.py

Fills in dim_mp.allocated_limit for Rajya Sabha MPs (house = '1') from
staging.raw_mospi_rs_allocations.

Unlike the RS Sitting Members file, names here are ALREADY in the
correct "Title Firstname Surname" order (matching dim_mp.mp_name) -
no reordering needed. But they carry the same tenure-year problem as
the raw eSAKSHI work records did before the v3 merge fix, e.g.:
    "Dr. Abhishek Manu Singhvi (2026-32) (2026-2032)"
with BOTH a 2-digit and 4-digit year range appended. This strips both
in one pass before comparing.

State names in this file are already clean (plain "Kerala", "Delhi",
etc. - no "Keralam" or "NCT of Delhi" quirks like the Sitting Members
file had), so no state aliasing is needed here.

Run this AFTER load_csv_to_staging.py has populated
staging.raw_mospi_rs_allocations.
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


def strip_tenure_suffix(name):
    """Strips one OR MORE trailing '(YYYY-YY)' / '(YYYY-YYYY)' groups.
    'Dr. Abhishek Manu Singhvi (2026-32) (2026-2032)' -> 'Dr. Abhishek Manu Singhvi'"""
    if not name:
        return name
    return re.sub(r"(\s*\(\d{4}-\d{2,4}\))+\s*$", "", str(name)).strip()


def normalize_name(value):
    if not value:
        return None
    s = str(value).upper()
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def normalize_state(value):
    if not value:
        return None
    s = str(value).upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s or None


def parse_amount(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # NOTE: '.' is deliberately NOT in this character class - stripping it
    # would merge the integer and fractional parts into one huge number
    # (e.g. "33,58,94,82,301.82" -> wrongly "3358948230182" instead of
    # correctly "33589482301.82"). Found via a real NUMERIC overflow error
    # on the Grand Total row.
    s = re.sub(r"[₹Rs,\s]", "", s, flags=re.IGNORECASE)
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
            SELECT "Hon'ble Members of Parliament", "State", "Allocated AMOUNT ( ₹ )"
            FROM staging.raw_mospi_rs_allocations
        ''')
        rows = cur.fetchall()
        print(f"Found {len(rows)} rows in staging.raw_mospi_rs_allocations")

        matched, ambiguous, unmatched = 0, [], []

        for name_raw, state_raw, amount_raw in rows:
            if name_raw and str(name_raw).strip().lower() == "grand total":
                continue  # summary row, not a real MP - skip explicitly

            cleaned_name = strip_tenure_suffix(name_raw)
            norm_name = normalize_name(cleaned_name)
            norm_state = normalize_state(state_raw)
            amount = parse_amount(amount_raw)

            if not norm_name or amount is None:
                unmatched.append((name_raw, state_raw, "missing name or unparseable amount"))
                continue

            cur.execute('''
                UPDATE dim_mp
                SET allocated_limit = %s
                WHERE house = '1'
                  AND UPPER(TRIM(state)) = %s
                  AND REGEXP_REPLACE(REGEXP_REPLACE(UPPER(mp_name), '[.,]', '', 'g'), '\\s+', ' ', 'g') = %s
                RETURNING mp_id
            ''', (amount, norm_state, norm_name))

            updated_ids = cur.fetchall()
            if len(updated_ids) == 1:
                matched += 1
            elif len(updated_ids) > 1:
                ambiguous.append((name_raw, state_raw, len(updated_ids)))
            else:
                unmatched.append((name_raw, state_raw, "no dim_mp match found"))

        conn.commit()
        print(f"\nDone. {matched} dim_mp rows updated with allocated_limit (Rajya Sabha).")

        if ambiguous:
            print(f"\n{len(ambiguous)} names matched multiple dim_mp rows (updated all - review these):")
            for n, s, c in ambiguous:
                print(f"  - {n!r} / {s!r} -> {c} rows")

        if unmatched:
            print(f"\n{len(unmatched)} rows could NOT be matched:")
            for n, s, reason in unmatched[:30]:
                print(f"  - {n!r} / {s!r} -> {reason}")
            if len(unmatched) > 30:
                print(f"  ...and {len(unmatched) - 30} more")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()