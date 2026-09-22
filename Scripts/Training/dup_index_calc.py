import pandas as pd
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text
import warnings
from tqdm import tqdm

warnings.filterwarnings('ignore')

# Connect to the DB Team's Database
DB_URI = "postgresql://postgres:1234@localhost:5432/mplads"
engine = create_engine(DB_URI)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Initializing High-Speed Duplicate Engine on: {device.upper()}")

print("Fetching project descriptions from database...")
query = """
    SELECT work_id, work_description
    FROM public.fact_projects
    WHERE work_description IS NOT NULL AND work_description != 'description unavailable';
"""
df = pd.read_sql(query, engine)
print(f"Loaded {len(df):,} projects for similarity scanning.")

# 1. Generate Embeddings in FP16 (Half Precision for Tensor Core Acceleration)
print("Generating Semantic Vectors (FP16 Accelerated)...")
nlp_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

# Encode directly to FP16 PyTorch Tensors on GPU
embeddings = nlp_model.encode(
    df['work_description'].tolist(), 
    convert_to_tensor=True, 
    device=device, 
    show_progress_bar=True
).to(torch.float16)

# 2. Normalize embeddings for Cosine Similarity via Dot Product
embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

# 3. Maximum Speed Matrix Multiplication (Batch Size bumped to 16,000)
OPTIMAL_BATCH_SIZE = 16000 
print(f"Computing Pair-wise Similarities (Batch Size: {OPTIMAL_BATCH_SIZE:,})...")

duplicate_scores = []

with torch.no_grad(): # Disable gradient tracking to save VRAM
    for i in tqdm(range(0, len(embeddings), OPTIMAL_BATCH_SIZE), desc="Scanning Matrix"):
        batch = embeddings[i:i+OPTIMAL_BATCH_SIZE]
        
        # Matrix multiplication in FP16 (Tensor Core optimized)
        sim_matrix = torch.mm(batch, embeddings.T)
        
        # Mask out self-similarity
        for j in range(len(batch)):
            global_idx = i + j
            sim_matrix[j, global_idx] = -1.0 # Ignore self-match
            
        # Extract maximum duplicate score per project
        max_sim_values = sim_matrix.max(dim=1).values
        duplicate_scores.extend(max_sim_values.cpu().numpy())

df['duplicate_index'] = duplicate_scores

# Only flag severe semantic collisions (> 0.85 similarity)
df['duplicate_index'] = np.where(df['duplicate_index'] > 0.85, df['duplicate_index'], 0.0)

# 4. Fast In-Memory Update Filtering
updates = [
    {
        'work_id': row['work_id'], 
        'dup_idx': round(float(row['duplicate_index']), 3)
    }
    for _, row in df.iterrows() if row['duplicate_index'] > 0
]

if not updates:
    print("No severe duplicates found. Database remains clean.")
else:
    print(f"Found {len(updates):,} suspiciously similar projects. Writing to PostgreSQL...")
    
    # Standalone dynamic update query
    update_sql = text("""
        UPDATE analytics.ai_risk_scores
        SET duplicate_index = :dup_idx,
            overall_fraud_probability = LEAST(overall_fraud_probability + (:dup_idx * 0.4), 1.000)
        WHERE work_id = :work_id;
    """)
    
    with engine.begin() as conn:
        batch_write_size = 10000
        for i in range(0, len(updates), batch_write_size):
            conn.execute(update_sql, updates[i:i+batch_write_size])

print("\n" + "="*50)
print("DUPLICATE AUDIT COMPLETE!")
print("="*50)