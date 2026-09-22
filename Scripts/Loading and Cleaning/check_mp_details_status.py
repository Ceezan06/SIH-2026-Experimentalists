"""
check_mp_details_status.py

Read-only diagnostic - makes NO changes to the database. Fixes a flaw
in propagate_mp_details_v2.py's own printout, which could wrongly
report an already-successfully-matched row as "unmatched" just
because its party_name was already filled in (so the second pass's
UPDATE correctly skipped it, but the print statement didn't know
that and reported it as a miss).

For every row in staging.raw_sitting_members, this checks what's
ACTUALLY true in dim_mp right now and puts it in exactly one bucket:

  - ALREADY_FILLED   : a matching dim_mp row exists and already has
                        party_name set (success, nothing to do)
  - NEEDS_FILL        : a matching dim_mp row exists but party_name
                        is still NULL (genuine remaining work)
  - NO_MATCH          : no dim_mp row exists for this constituency+
                         state at all (likely an MP with zero
                         recorded works, or a real spelling/renaming
                         gap - see the candidate list printed for it)
  - AMBIGUOUS         : more than one dim_mp row matches

Run this any time you want an honest status check, after either
propagate_mp_details.py or propagate_mp_details_v2.py.
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
    "NCT OF DELHI": "DELHI",
    "DELHI": "DELHI",
}


def normalize_state(value):
    if not value:
        return None
    s = str(value).upper().strip()
    return STATE_ALIASES.get(s, s)


def normalize_constituency_strict(value):
    if not value:
        return None
    s = str(value).upper()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s or None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute('''
        SELECT "Party Name", "Constituency", "State"
        FROM staging.raw_sitting_members
    ''')
    rows = cur.fetchall()

    buckets = {"ALREADY_FILLED": [], "NEEDS_FILL": [], "NO_MATCH": [], "AMBIGUOUS": []}

    for party, constituency, state in rows:
        norm_state = normalize_state(state)
        norm_const = normalize_constituency_strict(constituency)
        if not norm_state or not norm_const:
            buckets["NO_MATCH"].append((constituency, state, "missing data in source row"))
            continue

        state_variants = [k for k, v in STATE_ALIASES.items() if v == norm_state] + [norm_state]

        cur.execute('''
            SELECT mp_id, party_name FROM dim_mp
            WHERE house = '2'
              AND UPPER(TRIM(state)) = ANY(%s)
              AND REGEXP_REPLACE(UPPER(constituency), '[^A-Z0-9]', '', 'g') = %s
        ''', (state_variants, norm_const))
        matches = cur.fetchall()

        if len(matches) == 0:
            buckets["NO_MATCH"].append((constituency, state, None))
        elif len(matches) > 1:
            buckets["AMBIGUOUS"].append((constituency, state, len(matches)))
        elif matches[0][1] is not None:
            buckets["ALREADY_FILLED"].append((constituency, state))
        else:
            buckets["NEEDS_FILL"].append((constituency, state))

    print(f"Total rows checked: {len(rows)}")
    print(f"  Already filled correctly: {len(buckets['ALREADY_FILLED'])}")
    print(f"  Match exists but still needs filling: {len(buckets['NEEDS_FILL'])}")
    print(f"  Ambiguous (multiple dim_mp matches): {len(buckets['AMBIGUOUS'])}")
    print(f"  Genuinely no dim_mp match found: {len(buckets['NO_MATCH'])}")

    if buckets["NEEDS_FILL"]:
        print(f"\n--- NEEDS_FILL (real remaining work - run propagate_mp_details_v2.py again, "
              f"or these are new since your last run) ---")
        for c, s in buckets["NEEDS_FILL"]:
            print(f"  - {c!r} / {s!r}")

    if buckets["AMBIGUOUS"]:
        print(f"\n--- AMBIGUOUS (review manually) ---")
        for c, s, n in buckets["AMBIGUOUS"]:
            print(f"  - {c!r} / {s!r} -> {n} dim_mp matches")

    if buckets["NO_MATCH"]:
        print(f"\n--- NO_MATCH (genuine gaps - either zero recorded works for this MP, "
              f"or a real spelling/renaming difference) ---")
        for c, s, reason in buckets["NO_MATCH"]:
            if reason:
                print(f"  - {c!r} / {s!r} -> {reason}")
            else:
                print(f"  - {c!r} / {s!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
