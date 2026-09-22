# MPLADS AI Auditor 🇮🇳

**SIH-2026 PS26102: Development of an AI-powered system to detect anomalies, fraud, and inefficiencies in MPLAD Scheme implementation.**

The MPLADS AI Auditor is a comprehensive, production-grade platform designed to bring absolute transparency and predictive risk analysis to the Member of Parliament Local Area Development Scheme (MPLADS). By merging an advanced machine learning pipeline with a secure, role-based administrative dashboard, the system identifies financial anomalies, semantic duplications, and compliance risks in real-time.

---

## AI Models & Philosophy

Our artificial intelligence architecture is based on a 3 stage AI Engine. Instead, we utilized a highly modular, purpose-built ensemble approach. The models were trained on historical data from the 17th Lok Sabha and deployed to analyze the current 18th Lok Sabha term.

* **XGBoost (Cost & Delay Prediction):** Used for non-linear regression to accurately compute projected cost overruns and timeline delays for sanctioned works.
* **Isolation Forest (Compliance Index):** An unsupervised anomaly detection model used to isolate irregular financial patterns and flag projects that deviate from standard compliance protocols.
* **MiniLM Vector Embeddings (Duplication Detection):** To catch sophisticated evasion tactics (e.g., vendors or authorities double-dipping funds by slightly rephrasing project descriptions), we convert work descriptions into semantic vector embeddings using MiniLM. We then calculate the cosine similarity between projects under an MP to flag duplicate funding requests.
* **SHAP (Explainable AI):** All model outputs generate SHAP values to provide human-readable flagging reasons, ensuring auditors have actionable context for every risk score.

## Database Architecture

The system uses a robust PostgreSQL relational database modeled around a Star Schema optimized for high-speed analytical queries and persistent audit tracking.

* **Dimension Tables:** `dim_mp` (MP details, constituency, allocated limits), `dim_vendor` (contractor data), `dim_ida` (Implementing District Authority data).
* **Fact Tables:** `fact_projects` (core work orders, amounts, and statuses), `fact_expenditures` (transaction ledger).
* **Analytics & Security Schema:**
* `analytics.ai_risk_scores`: Stores the ML outputs (overall fraud probability, duplication index, delay cost index, compliance index).
* `analytics.audit_logs`: A persistent, IP-logged security ledger that tracks the exact status of auditor interventions (e.g., "Under Action", "Action Taken").



## Tech Stack

* **Frontend:** React, Node.js, Recharts, Lucide Icons (Role-Based Access Control, Server-Side Pagination, Glassmorphism UI).
* **Backend:** Node.js, Express.js.
* **Database:** PostgreSQL.
* **AI/ML Pipeline:** Python, scikit-learn, XGBoost, HuggingFace (MiniLM), SHAP.

---

## Setup & Installation

### 1. Database Setup (Crucial)

To regain database access quickly and ensure the dashboard functions correctly out of the box, you must restore the pre-configured database snapshots provided in the repository.

1. Locate the **Database Backups** folder in the project directory.
2. Ensure your local PostgreSQL server is running.
3. Create two new databases and name them exactly as follows:
* `Training`
* `mplads`


4. Restore the provided Google Drive backup files into their respective databases.
5. **https://drive.google.com/drive/folders/19mWbewlMrYRmrTjilLGhS1jTceVle_G0?usp=sharing**
6. **Database Credentials required for the backend:**
* **User:** `postgres`
* **Password:** `1234`



### 2. Backend Setup

1. Navigate to the backend directory.
2. Install dependencies:
```bash
npm install

```


3. Create a `.env` file in the root of the backend folder and configure your database connection:
```env
DB_USER=postgres
DB_HOST=localhost
DB_NAME=mplads
DB_PASSWORD=1234
DB_PORT=5432
PORT=5000

```


4. Start the backend server:
```bash
npm start

```



### 3. Frontend Setup

1. Navigate to the frontend directory.
2. Install dependencies:
```bash
npm install

```


3. Start the React development server:
```bash
npm run dev

```


*(Note: If you encounter a PowerShell script execution error on Windows, run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` as Administrator, or use standard Command Prompt).*

### 4. Application Access & Roles

The application features Role-Based Access Control (RBAC).

* **Civilian View:** By default, the application loads in read-only mode, masking sensitive audit tracking actions.
* **Auditor View:** To access the Risk Alerts inbox, initiate email workflows, and manage the Audit Trail, click the **Login** button in the top right of the header.
* **Username:** `Admin0`
* **Password:** `1234`

## Scripts

### AI Training and ETL Scripts

All scripts can be found in the venv\Scripts folder for inspection.
