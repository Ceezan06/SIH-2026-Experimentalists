import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import json
import shap
import uuid
import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text
from compliance_checker import MPLADSComplianceAuditor
import warnings
from tqdm import tqdm

warnings.filterwarnings('ignore')

# Connect to the DB Team's Evaluation Database
DB_URI = "postgresql://postgres:1234@localhost:5432/mplads"
engine = create_engine(DB_URI)

# 1. HARDWARE ALLOCATION
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Initializing models on: {device.upper()}")

print("Loading V5 AI Models & Artifacts...")
# Force SentenceTransformer to GPU
nlp_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
svd_model = joblib.load("models/text_svd_model_v5.joblib")
iso_forest = joblib.load("models/isolation_forest_v5.joblib")

xgb_model = xgb.XGBRegressor()
xgb_model.load_model("models/xgboost_v5.json")
explainer = shap.TreeExplainer(xgb_model)

# NOTE: Ensure your MPLADSComplianceAuditor class internally sets device='cuda' 
# or device=0 for its pipeline to prevent CPU bottlenecking!
auditor = MPLADSComplianceAuditor()

with open("models/v5_metadata.json", "r") as f:
    metadata = json.load(f)

# Fetch ALL valid projects (LIMIT removed)
print("Fetching all 131k projects from PostgreSQL...")
query = """
    SELECT 
        p.work_id,
        m.mp_name,
        m.state,
        m.constituency,
        m.house,
        p.work_description,
        p.recommended_amount
    FROM public.fact_projects p
    JOIN public.dim_mp m ON p.mp_id = m.mp_id
    WHERE p.recommended_amount IS NOT NULL;
"""
df = pd.read_sql(query, engine)
print(f"Loaded {len(df):,} projects for Enterprise Evaluation.")

# ----------------------------------------------------
# PRE-COMPUTE CPU FEATURES
# ----------------------------------------------------
print("Preparing CPU feature matrices...")
df['log_amount'] = np.log1p(df['recommended_amount'])
df['is_rajya_sabha'] = (df['house'] == '1').astype(int)
df['constituency'] = df['constituency'].fillna('RAJYA SABHA')
df['mp_historical_delay'] = df['mp_name'].map(metadata['mp_map']).fillna(metadata['global_mp_avg'])
df['constituency_historical_delay'] = df['constituency'].map(metadata['constituency_map']).fillna(metadata['global_const_avg'])

state_dummies = pd.get_dummies(df['state'], prefix='state')
df = pd.concat([df, state_dummies], axis=1)

# Clear the DB table once before starting the batches
with engine.begin() as conn:
    conn.execute(text("TRUNCATE TABLE analytics.ai_risk_scores;"))

# ----------------------------------------------------
# BATCH PROCESSING (VRAM PROTECTION)
# ----------------------------------------------------
BATCH_SIZE = 5000
total_batches = (len(df) // BATCH_SIZE) + 1

print(f"Starting GPU Batch Inference ({total_batches} batches of {BATCH_SIZE} rows)...")

for batch_num in range(total_batches):
    start_idx = batch_num * BATCH_SIZE
    end_idx = min((batch_num + 1) * BATCH_SIZE, len(df))
    
    batch_df = df.iloc[start_idx:end_idx].copy()
    if batch_df.empty:
        break
        
    print(f"\nProcessing Batch {batch_num + 1}/{total_batches} [{start_idx} to {end_idx}]...")

    # 1. NLP & SVD (GPU Accelerated)
    embeddings = nlp_model.encode(batch_df['work_description'].tolist(), batch_size=64, show_progress_bar=False)
    svd_features = svd_model.transform(embeddings)
    
    # 2. Build XGBoost Matrix
    X_xgb = pd.DataFrame({
        'log_amount': batch_df['log_amount'],
        'mp_historical_delay': batch_df['mp_historical_delay'],
        'constituency_historical_delay': batch_df['constituency_historical_delay'],
        'is_rajya_sabha': batch_df['is_rajya_sabha']
    }).reset_index(drop=True)
    
    for i in range(10):
        X_xgb[f'text_svd_{i}'] = svd_features[:, i]
        
    # Align states
    for col in metadata['xgboost_columns']:
        if col not in X_xgb.columns and col.startswith('state_'):
            # Grab from batch_df if it exists, otherwise 0
            if col in batch_df.columns:
                X_xgb[col] = batch_df[col].values
            else:
                X_xgb[col] = 0.0
                
    X_xgb = X_xgb[metadata['xgboost_columns']]

    # 3. Inference
    predicted_delays = xgb_model.predict(X_xgb)
    X_iso = np.column_stack((batch_df['log_amount'].values, svd_features))
    anomaly_scores = iso_forest.decision_function(X_iso)
    shap_values = explainer(X_xgb)

    # 4. Heavy Compliance Audit & Score Assembly
    risk_records = []
    
    # Using tqdm for inner loop so you know it hasn't frozen on the Zero-Shot model
    for idx, row in tqdm(batch_df.reset_index(drop=True).iterrows(), total=len(batch_df), desc="Auditing"):
        
        # Zero-Shot NLP Audit
        audit_res = auditor.audit_project(
            description=row['work_description'],
            amount=row['recommended_amount']
        )
        compliance_idx = 0.0 if audit_res['is_compliant'] else 0.85
        
        # SHAP
        row_shap = shap_values.values[idx]
        top_indices = np.argsort(np.abs(row_shap))[-3:][::-1]
        top_shap = {metadata['xgboost_columns'][i]: float(row_shap[i]) for i in top_indices}
        
        # Indexing
        delay_idx = min(max(predicted_delays[idx] / 180.0, 0.0), 1.0)
        raw_anomaly = anomaly_scores[idx]
        anomaly_idx = min(max((0.0 - raw_anomaly) * 2.0, 0.0), 1.0) 
        overall_fraud = min((anomaly_idx * 0.6) + (compliance_idx * 0.4), 1.0)
        
        risk_records.append({
            'score_id': str(uuid.uuid4()),
            'work_id': row['work_id'],
            'duplicate_index': 0.000, 
            'delay_cost_index': round(float(delay_idx), 3),
            'compliance_index': round(float(compliance_idx), 3),
            'overall_fraud_probability': round(float(overall_fraud), 3),
            'flagging_reasons_shap': json.dumps(top_shap)
        })

    # 5. Database Upsert per chunk
    upsert_sql = text("""
        INSERT INTO analytics.ai_risk_scores (
            score_id, work_id, duplicate_index, delay_cost_index, 
            compliance_index, overall_fraud_probability, flagging_reasons_shap, computed_at
        ) VALUES (
            :score_id, :work_id, :duplicate_index, :delay_cost_index, 
            :compliance_index, :overall_fraud_probability, CAST(:flagging_reasons_shap AS JSONB), NOW()
        )
        ON CONFLICT (score_id) DO NOTHING;
    """)
    
    with engine.begin() as conn:
        conn.execute(upsert_sql, risk_records)

print("\n" + "="*50)
print("ENTERPRISE AI EVALUATION COMPLETE!")
print("="*50)