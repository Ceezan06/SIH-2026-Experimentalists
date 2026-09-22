import pandas as pd
import hashlib
import re
import warnings

warnings.filterwarnings('ignore')

def extract_ws_id(row, work_col='WORK', desc_col='Work description', mp_col="Hon'ble Members of Parliament"):
    """
    Cleans tabs/spaces and uses Regex to perfectly extract the WS ID.
    If NA, generates a deterministic SYN- hash to track the project across files.
    """
    work_str = str(row.get(work_col, ''))
    if pd.isna(work_str): work_str = ""
        
    # Fix the space/tab bug
    work_raw = work_str.replace('WS/\t ', 'WS/').replace('WS/ ', 'WS/').replace('\t', '').strip()
    
    # Regex for standard eSAKSHI ID: WS/MP[numbers]/[4 digits]-[4 digits]/[numbers]
    match = re.search(r'(WS/MP\d+/\d{4}-\d{4}/\d+)', work_raw, re.IGNORECASE)
    if match:
        return match.group(1).upper()
        
    # If no match (NA- projects), generate deterministic hash based on MP and Description
    desc_c = str(row.get(desc_col, '')).strip().lower()
    mp_c = str(row.get(mp_col, '')).strip().lower()
    hash_str = f"{mp_c}_{desc_c}".encode('utf-8')
    
    return "SYN-" + hashlib.md5(hash_str).hexdigest()[:12].upper()

def process_and_merge_term_data():
    print("📥 Loading 18th Term CSVs...")
    
    # 1. Load Recommended (Base Universe of Projects)
    df_rec_ls = pd.read_csv("Current Data\\MoSPI\\Lok Sabha\\Works Recommended LS.csv", low_memory=False)
    df_rec_rs = pd.read_csv("Current Data\\MoSPI\\Rajya Sabha\\Works Recommended.csv", low_memory=False)

    df_rec_ls['house_type'] = 'Lok Sabha'
    df_rec_rs['house_type'] = 'Rajya Sabha'
    df_rec = pd.concat([df_rec_ls, df_rec_rs], ignore_index=True)
    
    print(" Extracting exact WS/ IDs via Regex and generating hashes for NA projects...")
    df_rec['work_id'] = df_rec.apply(extract_ws_id, axis=1)
    
    # Format Base Columns
    df_clean = pd.DataFrame({
        'work_id': df_rec['work_id'],
        'house_type': df_rec['house_type'],
        'mp_name': df_rec["Hon'ble Members of Parliament"].str.title(),
        'state': df_rec['State'].str.upper(),
        'constituency': df_rec.get('Constituency', pd.Series(['UNKNOWN']*len(df_rec))).fillna('UNKNOWN').str.title(),
        'work_category': df_rec['Work category'],
        'work_description': df_rec['Work description'].str.strip(),
        'recommended_amount': pd.to_numeric(df_rec['RECOMMENDED AMOUNT   ( ₹ )'].astype(str).str.replace(',', ''), errors='coerce'),
        'recommended_date': pd.to_datetime(df_rec['Recommended date'], errors='coerce')
    })
    
    # 2. Merge Sanctioned Data
    print("Merging Sanctioned Lifecycle Data...")
    df_sanc_ls = pd.read_csv("C:\\Users\\ekbal\\Desktop\\SIH 2026\\Data Files\\Current Data 18 LS\\MoSPI\\Lok Sabha\\Works Sanctioned LS.csv", low_memory=False)
    df_sanc_rs = pd.read_csv("C:\\Users\\ekbal\\Desktop\\SIH 2026\\Data Files\\Current Data 18 LS\\MoSPI\\Rajya Sabha\\Works Sanctioned.csv", low_memory=False)
    df_sanc = pd.concat([df_sanc_ls, df_sanc_rs], ignore_index=True)
    
    df_sanc['work_id'] = df_sanc.apply(lambda r: extract_ws_id(r, work_col='Work'), axis=1)
    df_sanc = df_sanc.drop_duplicates(subset=['work_id'], keep='last')
    
    sanc_map = df_sanc.set_index('work_id')
    df_clean['sanction_date'] = df_clean['work_id'].map(pd.to_datetime(sanc_map['Sanction Date'], errors='coerce'))
    df_clean['sanction_amount'] = df_clean['work_id'].map(pd.to_numeric(sanc_map['Sanction Amount ( ₹ )'].astype(str).str.replace(',', ''), errors='coerce'))
    
    # 3. Merge Completed Data
    print("Merging Completed Lifecycle Data...")
    df_comp_ls = pd.read_csv("C:\\Users\\ekbal\\Desktop\\SIH 2026\\Data Files\\Current Data 18 LS\\MoSPI\\Lok Sabha\\Works Completed LS.csv", low_memory=False)
    df_comp_rs = pd.read_csv("C:\\Users\\ekbal\\Desktop\\SIH 2026\\Data Files\\Current Data 18 LS\\MoSPI\\Rajya Sabha\\Works Completed.csv", low_memory=False)
    df_comp = pd.concat([df_comp_ls, df_comp_rs], ignore_index=True)
    
    df_comp['work_id'] = df_comp.apply(lambda r: extract_ws_id(r, work_col='Work', desc_col='Work Description'), axis=1)
    df_comp = df_comp.drop_duplicates(subset=['work_id'], keep='last')
    
    comp_map = df_comp.set_index('work_id')
    df_clean['completed_date'] = df_clean['work_id'].map(pd.to_datetime(comp_map['Completion Date'], errors='coerce'))
    df_clean['completed_amount'] = df_clean['work_id'].map(pd.to_numeric(comp_map['Amount Disbursed ( ₹ )'].astype(str).str.replace(',', ''), errors='coerce'))

    # Calculate actual delay days
    df_clean['approval_delay_days'] = (df_clean['sanction_date'] - df_clean['recommended_date']).dt.days
    
    # Export
    output_path = "data\\clean_18th_term_projects.csv"
    df_clean.to_csv(output_path, index=False)
    
    print("\n" + "="*50)
    print(f"18th TERM DATA PREPARATION COMPLETE!")
    print(f"Total Projects (Universe): {len(df_clean):,}")
    print(f"Projects reaching Sanctioned Status: {df_clean['sanction_date'].notna().sum():,}")
    print(f"Saved to: {output_path}")
    print("="*50)

if __name__ == "__main__":
    process_and_merge_term_data()