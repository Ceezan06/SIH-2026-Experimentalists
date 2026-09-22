import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import json
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
import warnings

warnings.filterwarnings('ignore')

# 1. Connect to Training DB
DB_URI = "postgresql://postgres:1234@localhost:5432/Training"
engine = create_engine(DB_URI)

print("Fetching unified historical data from PostgreSQL...")
query = """
    SELECT 
        work_id,
        state,
        mp_name,
        constituency,
        work_description,
        recommended_amount,
        approval_delay_days
    FROM training.fact_projects_historical
    WHERE recommended_amount IS NOT NULL 
      AND work_description != 'description unavailable';
"""
df = pd.read_sql(query, engine)
print(f"Loaded {len(df):,} total projects for V5 training.")

# ----------------------------------------------------
# 2. FEATURE ENGINEERING (V5 UPGRADES)
# ----------------------------------------------------
print("Engineering features (including Rajya Sabha markers)...")

# Log transform budget
df['log_amount'] = np.log1p(df['recommended_amount'])

# NEW FEATURE: House Type Marker
df['is_rajya_sabha'] = (df['constituency'] == 'RAJYA SABHA').astype(int)

# Target Encoding: MP & Constituency Historical Speed
# (We only use projects that actually got sanctioned for delay averages)
df_sanc = df.dropna(subset=['approval_delay_days'])

mp_delay_map = df_sanc.groupby('mp_name')['approval_delay_days'].mean().to_dict()
constituency_delay_map = df_sanc.groupby('constituency')['approval_delay_days'].mean().to_dict()

global_mp_avg = df_sanc['approval_delay_days'].mean()
global_const_avg = df_sanc['approval_delay_days'].mean()

df['mp_historical_delay'] = df['mp_name'].map(mp_delay_map).fillna(global_mp_avg)
df['constituency_historical_delay'] = df['constituency'].map(constituency_delay_map).fillna(global_const_avg)

# State One-Hot Encoding
state_dummies = pd.get_dummies(df['state'], prefix='state')
df = pd.concat([df, state_dummies], axis=1)

# NLP Compression (Train SVD on the FULL corpus)
print("Generating NLP Embeddings (This will take a few minutes)...")
nlp_model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = nlp_model.encode(df['work_description'].tolist(), show_progress_bar=True)

print("Training SVD to compress text vectors into 10 dimensions...")
svd = TruncatedSVD(n_components=10, random_state=42)
svd_features = svd.fit_transform(embeddings)

for i in range(10):
    df[f'text_svd_{i}'] = svd_features[:, i]

# ----------------------------------------------------
# 3. TRAIN ISOLATION FOREST (Fraud & Anomaly)
# ----------------------------------------------------
print("Training Isolation Forest Anomaly Detector...")
# Train on Budget Scale + Text Complexity
X_iso = np.column_stack((df['log_amount'].values, svd_features))
iso_forest = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
iso_forest.fit(X_iso)

# ----------------------------------------------------
# 4. TRAIN XGBOOST V5 (Delay Predictor)
# ----------------------------------------------------
print("Training XGBoost V5 Delay Predictor...")
# Filter down to only sanctioned projects for the delay target
train_df = df.dropna(subset=['approval_delay_days'])

xgb_features = [
    'log_amount', 
    'mp_historical_delay', 
    'constituency_historical_delay',
    'is_rajya_sabha'  # The new V5 feature
] + list(state_dummies.columns) + [f'text_svd_{i}' for i in range(10)]

X_train = train_df[xgb_features]
y_train = train_df['approval_delay_days']

xgb_model = xgb.XGBRegressor(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42
)
xgb_model.fit(X_train, y_train)

# ----------------------------------------------------
# 5. EXPORT V5 ARTIFACTS
# ----------------------------------------------------
print("Saving V5 Models and Metadata...")
xgb_model.save_model("models/xgboost_v5.json")
joblib.dump(iso_forest, "models/isolation_forest_v5.joblib")
joblib.dump(svd, "models/text_svd_model_v5.joblib")

metadata = {
    'global_mp_avg': global_mp_avg,
    'global_const_avg': global_const_avg,
    'mp_map': mp_delay_map,
    'constituency_map': constituency_delay_map,
    'xgboost_columns': xgb_features
}

with open("models/v5_metadata.json", "w") as f:
    json.dump(metadata, f)

print("\n" + "="*50)
print("V5 AI PIPELINE TRAINING COMPLETE!")
print(f"XGBoost R² Score: {xgb_model.score(X_train, y_train):.4f}")
print("Artifacts saved to 'models/' directory.")
print("="*50)