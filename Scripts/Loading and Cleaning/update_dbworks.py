import pandas as pd
import hashlib
import glob
import re
from sqlalchemy import create_engine, text
import warnings

warnings.filterwarnings('ignore')

DB_URI = "postgresql://postgres:1234@localhost:5432/mplads"
engine = create_engine(DB_URI)

def clean_desc(text_str):
    if not text_str or pd.isna(text_str): return "description unavailable"
    return str(text_str).strip().lower()

def extract_ws_id(work_str):
    """Regex extraction that defeats spaces, tabs, and missing hyphens."""
    if pd.isna(work_str): return None
    work_raw = str(work_str).replace('WS/\t ', 'WS/').replace('WS/ ', 'WS/').replace('\t', '').strip()
    match = re.search(r'(WS/MP\d+/\d{4}-\d{4}/\d+)', work_raw, re.IGNORECASE)
    if match: return match.group(1).upper()
    return None

def build_csv_lookup():
    print("Stage 1: Building (MP + Amount + Description) -> WS/ ID Lookup from local CSVs...")
    lookup = {}
    csv_files = glob.glob("*.csv") + glob.glob("data/raw_csvs/*.csv")
    
    for file in csv_files:
        if "Recommended" in file or "Sanctioned" in file or "Completed" in file:
            try:
                df = pd.read_csv(file, low_memory=False)
                work_col = [c for c in df.columns if c.lower() in ['work', 'work id']][0] if any(c.lower() in ['work', 'work id'] for c in df.columns) else None
                desc_col = 'Work description' if 'Work description' in df.columns else ('Work Description' if 'Work Description' in df.columns else None)
                amt_col = [c for c in df.columns if 'AMOUNT' in c.upper()][0] if any('AMOUNT' in c.upper() for c in df.columns) else None
                mp_col = "Hon'ble Members of Parliament" if "Hon'ble Members of Parliament" in df.columns else None
                
                if work_col and desc_col and mp_col:
                    for _, row in df.iterrows():
                        ws_id = extract_ws_id(row[work_col])
                        if ws_id:
                            mp_clean = clean_desc(row[mp_col])
                            desc_c = clean_desc(row[desc_col])
                            amt_val = float(str(row[amt_col]).replace(',', '')) if amt_col and pd.notna(row[amt_col]) else 0.0
                            
                            key = (mp_clean, round(amt_val, 2), desc_c[:50]) 
                            lookup[key] = ws_id
            except Exception:
                continue
                
    print(f"Mapped {len(lookup):,} raw WS/ IDs from CSVs.")
    return lookup

def fetch_db_landing_lookup():
    print("Stage 2: Building secondary lookup from DB team's public.raw_landing JSONB table...")
    lookup = {}
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    source_record_id,
                    payload->>'Hon''ble Members of Parliament' AS mp_name,
                    payload->>'Work description' AS desc,
                    payload->>'RECOMMENDED AMOUNT   ( ₹ )' AS amt
                FROM public.raw_landing
                WHERE source_record_id IS NOT NULL;
            """)
            df_landing = pd.read_sql(query, conn)
            
            for _, row in df_landing.iterrows():
                ws_id = extract_ws_id(row['source_record_id'])
                if ws_id:
                    mp_clean = clean_desc(row['mp_name'])
                    desc_c = clean_desc(row['desc'])
                    try:
                        amt_val = float(str(row['amt']).replace(',', '')) if pd.notna(row['amt']) else 0.0
                    except:
                        amt_val = 0.0
                    
                    key = (mp_clean, round(amt_val, 2), desc_c[:50])
                    lookup[key] = ws_id
            print(f"Extracted an additional {len(lookup):,} WS/ IDs directly from database payload.")
    except Exception as e:
        print("Skipping DB JSONB extraction (table not found or formatted differently).")
    return lookup

def update_database_in_place():
    csv_lookup = build_csv_lookup()
    db_lookup = fetch_db_landing_lookup()
    
    # Merge lookups (CSV takes priority as it is fresher)
    master_lookup = {**db_lookup, **csv_lookup}
    
    print("\n" + "="*60)
    print("DIRECT POSTGRESQL IN-PLACE MIGRATION ('mplads')")
    print("="*60)
    
    with engine.begin() as conn:
        print("Setting Foreign Key constraint to ON UPDATE CASCADE on public.fact_expenditures...")
        conn.execute(text("""
            ALTER TABLE public.fact_expenditures 
            DROP CONSTRAINT IF EXISTS fact_expenditures_work_id_fkey;

            ALTER TABLE public.fact_expenditures 
            ADD CONSTRAINT fact_expenditures_work_id_fkey 
            FOREIGN KEY (work_id) REFERENCES public.fact_projects(work_id) 
            ON UPDATE CASCADE ON DELETE CASCADE;
        """))
        
        print("Fetching existing DTL- records from public.fact_projects...")
        query = text("""
            SELECT p.work_id AS old_work_id, p.work_description, p.recommended_amount, m.mp_name
            FROM public.fact_projects p
            LEFT JOIN public.dim_mp m ON p.mp_id = m.mp_id;
        """)
        df_db = pd.read_sql(query, conn)
        
        updates = []
        seen_new_ids = set()
        
        for idx, row in df_db.iterrows():
            old_id = row['old_work_id']
            desc_clean = clean_desc(row['work_description'])
            mp_clean = clean_desc(row['mp_name'])
            amt_val = float(row['recommended_amount']) if pd.notna(row['recommended_amount']) else 0.0
            
            # Lookup real WS/ ID
            lookup_key = (mp_clean, round(amt_val, 2), desc_clean[:50])
            new_id = master_lookup.get(lookup_key)
            
            if not new_id:
                hash_input = f"{mp_clean}_{desc_clean}".encode('utf-8')
                new_id = "SYN-" + hashlib.md5(hash_input).hexdigest()[:12].upper()
            
            # Prevent PK collision
            if new_id in seen_new_ids:
                new_id = f"{new_id}_DUP{idx}"
            seen_new_ids.add(new_id)
            
            updates.append({'old_id': old_id, 'new_id': new_id, 'desc_clean': desc_clean})

        print(f"Updating {len(updates):,} WS/ IDs and lowercasing descriptions in PostgreSQL...")
        
        update_sql = text("""
            UPDATE public.fact_projects 
            SET work_id = :new_id, work_description = :desc_clean
            WHERE work_id = :old_id;
        """)
        
        batch_size = 5000
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            conn.execute(update_sql, batch)
            print(f" -> Updated {min(i+batch_size, len(updates)):,}/{len(updates):,} rows...")

    print("\n" + "="*60)
    print("MIGRATION COMPLETE! 'fact_projects' updated, 'fact_expenditures' cascaded.")
    print("="*60)

if __name__ == "__main__":
    update_database_in_place()