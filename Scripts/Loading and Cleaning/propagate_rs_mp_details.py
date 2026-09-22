"""
propagate_rs_mp_details.py

Fills in dim_mp.party_name, membership_status, and terms_served for
Rajya Sabha MPs (house = '1') from staging.raw_rs_sitting_members.

WHY THIS MATCHES BY NAME, UNLIKE THE LOK SABHA VERSION:
The RS file has no constituency column at all (Rajya Sabha has none),
so there's no safer join key available - name is the only option.
Same reversal problem as the LS file applies: this file stores
"Surname, Title Firstname" (e.g. "Agrawal, Dr. Radha Mohan Das"),
while dim_mp.mp_name comes from eSAKSHI in "Title Firstname Surname"
order. This script reorders the CSV's name into that shape before
comparing, then normalizes both sides (uppercase, strip punctuation,
collapse whitespace) for an exact - not fuzzy - match.

Also handles known state-naming differences spotted in this file:
"Keralam" (Kerala), "National Capital Territory of Delhi" (Delhi),
and "Jammu & Kashmir" (ampersand vs "and"). "Nominated" appears as a
pseudo-state for nominated members with no state affiliation - these
are matched on name only, without a state constraint.

Run this AFTER load_rs_sitting_members.py.
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

STATE_ALIASES = {
    "KERALAM": "KERALA",
    "NATIONAL CAPITAL TERRITORY OF DELHI": "DELHI",
    "NCT OF DELHI": "DELHI",
    "DELHI": "DELHI",
}


def normalize_state(value):
    if not value:
        return None
    s = str(value).upper().strip()
    s = s.replace("&", "AND")
    s = re.sub(r"\s+", " ", s).strip()
    return STATE_ALIASES.get(s, s)


def reorder_name(raw):
    """'Agrawal, Dr. Radha Mohan Das' -> 'Dr. Radha Mohan Das Agrawal'"""
    if not raw or "," not in raw:
        return raw
    surname, rest = raw.split(",", 1)
    return f"{rest.strip()} {surname.strip()}"


def normalize_name(value):
    if not value:
        return None
    s = str(value).upper()
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def clean_party_name(value):
    """Strip a trailing '(ABBR)' so RS party names match the LS file's
    plain-name style, e.g. 'Indian Union Muslim League (IUML)' ->
    'Indian Union Muslim League'."""
    if not value:
        return value
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(value)).strip()


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT name_of_member, party_name, state, rajya_sabha_terms
            FROM staging.raw_rs_sitting_members
        ''')
        rows = cur.fetchall()
        print(f"Found {len(rows)} rows in staging.raw_rs_sitting_members")

        matched, ambiguous, unmatched = 0, [], []
        debug_shown = 0

        for name_raw, party_raw, state_raw, terms in rows:
            reordered = reorder_name(name_raw)
            norm_name = normalize_name(reordered)
            norm_state = normalize_state(state_raw) if state_raw and state_raw != "Nominated" else None
            party = clean_party_name(party_raw)

            if debug_shown < 5:
                print(f"DEBUG: name_raw={name_raw!r} reordered={reordered!r} "
                      f"norm_name={norm_name!r} state_raw={state_raw!r} norm_state={norm_state!r}")
                debug_shown += 1

            if not norm_name:
                unmatched.append((name_raw, state_raw, "could not parse name"))
                continue

            if norm_state:
                cur.execute('''
                    UPDATE dim_mp
                    SET party_name = %s, membership_status = 'Sitting', terms_served = %s
                    WHERE house = '1'
                      AND UPPER(TRIM(state)) = %s
                      AND REGEXP_REPLACE(REGEXP_REPLACE(UPPER(mp_name), '[.,]', '', 'g'), '\\s+', ' ', 'g') = %s
                    RETURNING mp_id
                ''', (party, terms, norm_state, norm_name))
            else:
                # Nominated members have no state to constrain by - match on name alone.
                cur.execute('''
                    UPDATE dim_mp
                    SET party_name = %s, membership_status = 'Sitting', terms_served = %s
                    WHERE house = '1'
                      AND REGEXP_REPLACE(REGEXP_REPLACE(UPPER(mp_name), '[.,]', '', 'g'), '\\s+', ' ', 'g') = %s
                    RETURNING mp_id
                ''', (party, terms, norm_name))

            updated_ids = cur.fetchall()
            if len(updated_ids) == 1:
                matched += 1
            elif len(updated_ids) > 1:
                ambiguous.append((name_raw, state_raw, len(updated_ids)))
            else:
                unmatched.append((name_raw, state_raw, "no dim_mp match found"))

        conn.commit()
        print(f"\nDone. {matched} dim_mp rows updated with party/status/terms (Rajya Sabha).")

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