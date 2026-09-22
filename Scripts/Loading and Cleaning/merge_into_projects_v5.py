"""
merge_into_projects_v5.py

Same idea as v3, but writes into the team's renamed schema:
  mps -> dim_mp, districts -> dim_ida, vendors -> dim_vendor,
  projects -> fact_projects, and a NEW fact_expenditures table.

WHAT'S ACTUALLY NEW HERE (not just renaming):
  - fact_expenditures is a separate table now, one row per payment,
    instead of a few columns bolted onto the project row.
  - It needs the actual payment amount (FUND_DISBURSED_AMT), which
    earlier versions never extracted - only status/date/vendor were
    pulled before. This version adds that field.
  - dim_ida now stores BOTH the full raw IDA string (ida_name) and
    the parsed short name (district), since the team's schema wants
    both.
"""

import math
import re

import pandas as pd
import psycopg2


# ============================================================
# CONFIG
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mplads",
    "user": "postgres",
    "password": "1234",
}


# ============================================================
# HELPER FUNCTIONS (unchanged from v3)
# ============================================================

def normalize_key(k: str) -> str:
    k = k.replace("'", "")
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r"[^a-zA-Z ]", " ", k)
    k = re.sub(r"\s+", " ", k).strip().lower()
    return k


def get_field(payload: dict, concepts):
    if isinstance(concepts, str):
        concepts = [concepts]
    for concept in concepts:
        target = normalize_key(concept)
        for k, v in payload.items():
            if normalize_key(k) == target:
                if v is None:
                    continue
                if isinstance(v, float) and math.isnan(v):
                    continue
                if str(v).strip() == "" or str(v).strip().upper() == "NA":
                    continue
                return v
    return None


def parse_district(ida_value):
    if not ida_value:
        return None
    name = str(ida_value).split("(")[0].strip()
    return name or None


def parse_date(value):
    if not value:
        return None
    parsed = pd.to_datetime(str(value), dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def parse_amount(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def load_payloads_json(payload):
    if isinstance(payload, str):
        import json
        return json.loads(payload)
    return payload


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_or_create_mp(cursor, cache, name, constituency, state, house):
    if not name:
        return None
    key = (name.strip().upper(), (constituency or "").strip().upper())
    if key in cache:
        return cache[key]
    cursor.execute(
        """
        INSERT INTO dim_mp (mp_name, constituency, state, house)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mp_name, constituency) DO UPDATE SET state = EXCLUDED.state
        RETURNING mp_id
        """,
        (name.strip(), constituency.strip() if constituency else None, state, house),
    )
    mp_id = cursor.fetchone()[0]
    cache[key] = mp_id
    return mp_id


def get_or_create_ida(cursor, cache, ida_raw, state):
    """ida_raw is the full raw string, e.g. 'South 24 Parganas(DISTRICT MAGISTRATE ...)'."""
    if not ida_raw:
        return None
    key = ida_raw.strip().upper()
    if key in cache:
        return cache[key]
    district_name = parse_district(ida_raw)
    cursor.execute(
        """
        INSERT INTO dim_ida (ida_name, district, state)
        VALUES (%s, %s, %s)
        ON CONFLICT (ida_name) DO UPDATE SET state = EXCLUDED.state
        RETURNING ida_id
        """,
        (ida_raw.strip(), district_name, state),
    )
    ida_id = cursor.fetchone()[0]
    cache[key] = ida_id
    return ida_id


def get_or_create_vendor(cursor, cache, vendor_name):
    if not vendor_name:
        return None
    key = vendor_name.strip().upper()
    if key in cache:
        return cache[key]
    cursor.execute(
        """
        INSERT INTO dim_vendor (vendor_name)
        VALUES (%s)
        ON CONFLICT (vendor_name) DO NOTHING
        RETURNING vendor_id
        """,
        (vendor_name.strip(),),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute("SELECT vendor_id FROM dim_vendor WHERE vendor_name = %s", (vendor_name.strip(),))
        row = cursor.fetchone()
    vendor_id = row[0]
    cache[key] = vendor_id
    return vendor_id


def fetch_source_rows(cursor, source_label):
    cursor.execute(
        "SELECT source_record_id, payload FROM raw_landing WHERE source = %s",
        (source_label,),
    )
    result = {}
    for work_id, payload in cursor.fetchall():
        if not work_id:
            continue
        result[work_id] = load_payloads_json(payload)
    return result


# ============================================================
# MAIN LOGIC
# ============================================================

def main():
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    print("Reading raw_landing rows for each lifecycle stage...")
    recommended = fetch_source_rows(cur, "esakshi_recommended")
    sanctioned = fetch_source_rows(cur, "esakshi_sanctioned")
    completed = fetch_source_rows(cur, "esakshi_completed")
    expenditure = fetch_source_rows(cur, "esakshi_expenditure")

    def add_to_group(grouped_dict, stage_key, source_dict):
        for raw_id, payload in source_dict.items():
            dtl_id = payload.get("WORK_RECOMMENDATION_DTL_ID")
            resolved_id = f"DTL-{dtl_id}" if dtl_id else raw_id
            grouped_dict.setdefault(resolved_id, {"rec": {}, "sanc": {}, "comp": {}, "exp": {}})
            grouped_dict[resolved_id][stage_key] = payload

    grouped = {}
    add_to_group(grouped, "rec", recommended)
    add_to_group(grouped, "sanc", sanctioned)
    add_to_group(grouped, "comp", completed)
    add_to_group(grouped, "exp", expenditure)

    print(f"Found {len(grouped)} unique works to merge.\n")

    mp_cache, ida_cache, vendor_cache = {}, {}, {}
    projects_written = 0
    expenditures_written = 0

    try:
        for work_id, stages in sorted(grouped.items()):
            rec, sanc, comp, exp = stages["rec"], stages["sanc"], stages["comp"], stages["exp"]

            mp_name = get_field(sanc, ["honble members of parliament", "mp name"]) \
                or get_field(rec, ["honble members of parliament", "mp name"]) \
                or get_field(comp, ["honble members of parliament", "mp name"]) \
                or get_field(exp, ["honble members of parliament", "mp name"])

            constituency = get_field(sanc, "constituency") or get_field(rec, "constituency") \
                or get_field(comp, "constituency") or get_field(exp, "constituency")

            state = get_field(sanc, ["state", "state name"]) or get_field(rec, ["state", "state name"]) \
                or get_field(comp, ["state", "state name"]) or get_field(exp, ["state", "state name"])

            house = get_field(sanc, "house of parliament") or get_field(rec, "house of parliament") \
                or get_field(exp, "house of parliament")

            ida_raw = get_field(sanc, ["ida", "ida name"]) or get_field(rec, ["ida", "ida name"]) \
                or get_field(comp, ["ida", "ida name"]) or get_field(exp, ["ida", "ida name"])

            category = get_field(rec, "work category") or get_field(sanc, "work category") \
                or get_field(comp, "work category")

            description = get_field(sanc, "work description") or get_field(rec, "work description") \
                or get_field(comp, "work description") or get_field(exp, ["work description", "activity name"])

            recommended_amount = parse_amount(get_field(rec, "recommended amount"))
            recommended_date = parse_date(get_field(rec, ["recommended date", "recommendation date"]))

            sanctioned_amount = parse_amount(get_field(sanc, "sanction amount"))
            # Team-confirmed definition: final_amount IS the sanction amount,
            # full stop. NULL until the work is actually sanctioned - no
            # fallback to recommended_amount. (Previously fell back to
            # recommended_amount pre-sanction; team decided against that.)
            final_amount = sanctioned_amount

            work_status = get_field(sanc, ["work status", "work stage"]) \
                or get_field(rec, ["work status", "work stage"]) or "Recommended"

            actual_completion_date = parse_date(get_field(comp, ["completion date", "actual end date"]))

            if not mp_name or not description:
                continue  # can't create a valid fact_projects row without these NOT NULL fields

            mp_id = get_or_create_mp(cur, mp_cache, mp_name, constituency, state, house)
            ida_id = get_or_create_ida(cur, ida_cache, ida_raw, state)

            cur.execute(
                """
                INSERT INTO fact_projects (
                    work_id, mp_id, ida_id, work_description, category,
                    recommended_amount, final_amount,
                    recommendation_date, completed_date, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (work_id) DO UPDATE SET
                    mp_id = EXCLUDED.mp_id,
                    ida_id = EXCLUDED.ida_id,
                    work_description = EXCLUDED.work_description,
                    category = EXCLUDED.category,
                    recommended_amount = EXCLUDED.recommended_amount,
                    final_amount = EXCLUDED.final_amount,
                    recommendation_date = EXCLUDED.recommendation_date,
                    completed_date = COALESCE(EXCLUDED.completed_date, fact_projects.completed_date),
                    status = EXCLUDED.status
                """,
                (
                    work_id, mp_id, ida_id, description, category,
                    recommended_amount, final_amount,
                    recommended_date, actual_completion_date, work_status,
                ),
            )
            projects_written += 1

            # --- fact_expenditures: only created if this work actually reached that stage ---
            vendor_name = get_field(exp, "vendor name")
            payment_status = get_field(exp, ["payment status", "work status"])
            expenditure_date = parse_date(get_field(exp, "expenditure date"))
            expenditure_amount = parse_amount(get_field(exp, ["fund disbursed amount", "fund disbursed amt", "expenditure amount"]))

            if expenditure_amount is not None and expenditure_date:
                vendor_id = get_or_create_vendor(cur, vendor_cache, vendor_name)
                cur.execute(
                    """
                    INSERT INTO fact_expenditures (
                        work_id, mp_id, vendor_id, ida_id,
                        expenditure_amount, expenditure_date, payment_status
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (work_id, mp_id, vendor_id, ida_id, expenditure_amount, expenditure_date, payment_status or "Unknown"),
                )
                expenditures_written += 1

        conn.commit()
        print(f"Done. {projects_written} fact_projects rows inserted/updated.")
        print(f"       {expenditures_written} fact_expenditures rows inserted.")
        print(f"MPs touched: {len(mp_cache)} | IDAs touched: {len(ida_cache)} | Vendors touched: {len(vendor_cache)}")

    except Exception as e:
        conn.rollback()
        print("\nSomething went wrong - no changes were saved. Error details:")
        print(e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
