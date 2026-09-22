"""
propagate_mp_details_v2.py

Second pass at matching staging.raw_sitting_members to dim_mp, for the
rows propagate_mp_details.py couldn't match. Adds two safe improvements
over the first pass, plus honest diagnostics for what's left:

  1. STATE_ALIASES - a few known state/UT naming differences between
     this file and eSAKSHI (e.g. "NCT of Delhi" vs "Delhi").

  2. Punctuation-insensitive constituency matching - strips ALL
     non-alphanumeric characters (not just parentheses) before
     comparing, so "Anantnag-Rajouri" matches "Anantnag Rajouri"
     regardless of hyphen vs space vs no separator at all.

For whatever's STILL unmatched after those two fixes, this does NOT
guess via fuzzy/substring matching - that risks silently assigning
the wrong MP's party to someone. Instead it lists every dim_mp
constituency that exists in the same state, so you can eyeball
whether it's a genuine spelling variant (fixable by adding one line
to STATE_ALIASES or a future CONSTITUENCY_ALIASES) or a real data
gap (an MP with zero recorded works, so no dim_mp row exists at all
for them to match against).

Safe to run after propagate_mp_details.py - it only re-attempts rows
that are still NULL, so it won't re-update anything already fixed.
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

# Known state/UT naming differences between Sitting_Members.xlsx and eSAKSHI.
# Add more here if the diagnostic list below reveals others.
STATE_ALIASES = {
    "NCT OF DELHI": "DELHI",
    "DELHI": "DELHI",
}


def normalize_state(value):
    if not value:
        return None
    s = str(value).upper().strip()
    return STATE_ALIASES.get(s, s)


def normalize_constituency_strict(value):
    """Alphanumeric characters only - drops spaces, hyphens, parentheses,
    everything. 'Anantnag-Rajouri' and 'Anantnag Rajouri' both become
    'ANANTNAGRAJOURI'."""
    if not value:
        return None
    s = str(value).upper()
    s = re.sub(r"\(.*?\)", "", s)          # drop (SC)/(ST)/etc content first
    s = re.sub(r"[^A-Z0-9]", "", s)        # then strip everything non-alnum
    return s or None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT "Party Name", "Constituency", "State",
                   "MemberShip Status", "Lok Sabha Terms"
            FROM staging.raw_sitting_members
        ''')
        rows = cur.fetchall()

        still_unmatched = []
        matched_this_pass = 0
        ambiguous = []

        for party, constituency, state, membership_status, terms in rows:
            norm_state = normalize_state(state)
            norm_const = normalize_constituency_strict(constituency)
            if not norm_state or not norm_const:
                continue

            # Only touch dim_mp rows that are STILL missing party_name -
            # this is a second pass, don't re-process what pass 1 fixed.
            cur.execute('''
                UPDATE dim_mp
                SET party_name = %s,
                    membership_status = %s,
                    terms_served = %s
                WHERE house = '2'
                  AND party_name IS NULL
                  AND UPPER(TRIM(state)) = ANY(%s)
                  AND REGEXP_REPLACE(UPPER(constituency), '[^A-Z0-9]', '', 'g') = %s
                RETURNING mp_id
            ''', (
                party, membership_status, terms,
                # match against every raw state string that normalizes to norm_state
                [k for k, v in STATE_ALIASES.items() if v == norm_state] + [norm_state],
                norm_const,
            ))

            updated_ids = cur.fetchall()
            if len(updated_ids) == 1:
                matched_this_pass += 1
            elif len(updated_ids) > 1:
                ambiguous.append((constituency, state, len(updated_ids)))
            else:
                still_unmatched.append((constituency, state))

        conn.commit()
        print(f"Second pass matched {matched_this_pass} additional dim_mp rows.")

        if ambiguous:
            print(f"\n{len(ambiguous)} pairs matched multiple dim_mp rows (updated all - review these):")
            for c, s, n in ambiguous:
                print(f"  - {c!r} / {s!r} -> {n} rows")

        if still_unmatched:
            print(f"\n{len(still_unmatched)} rows still unmatched after pass 2. "
                  f"Diagnostic - dim_mp constituencies that DO exist in the same state, "
                  f"for you to eyeball for spelling variants:\n")
            for constituency, state in still_unmatched:
                cur.execute('''
                    SELECT DISTINCT constituency FROM dim_mp
                    WHERE house = '2' AND UPPER(TRIM(state)) = ANY(%s)
                    ORDER BY constituency
                ''', ([k for k, v in STATE_ALIASES.items()
                       if v == normalize_state(state)] + [normalize_state(state)],))
                candidates = [r[0] for r in cur.fetchall()]
                print(f"  Sitting Members says: {constituency!r} / {state!r}")
                if candidates:
                    print(f"    dim_mp has these constituencies in {state}: {candidates}")
                else:
                    print(f"    dim_mp has NO constituencies at all for state {state!r} "
                          f"(check the state name itself, or this state's MPs may have "
                          f"zero recorded works)")
                print()

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
