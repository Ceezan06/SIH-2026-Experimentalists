const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// Initialize PostgreSQL Connection Pool
const pool = new Pool({
  user: process.env.DB_USER,
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT,
});

// Test DB Connection on Startup
pool.connect()
  .then(() => console.log('Successfully connected to PostgreSQL'))
  .catch(err => console.error('Database connection error:', err.stack));

// ---AUDIT ACTIONS ENDPOINT ---
app.post('/api/audit-action', async (req, res) => {
  const { work_ids, action_taken } = req.body;

  // Extract client IP address (handles standard connections and proxies like Nginx/Vercel)
  const ipAddress = req.headers['x-forwarded-for'] || req.socket.remoteAddress || '127.0.0.1';

  if (!work_ids || !Array.isArray(work_ids)) return res.status(400).json({ error: "Invalid payload" });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const dummyUserId = '00000000-0000-0000-0000-000000000000';

    for (const wid of work_ids) {
      const check = await client.query('SELECT action_taken FROM analytics.audit_logs WHERE work_id = $1', [wid]);

      if (check.rows.length > 0) {
        if (check.rows[0].action_taken !== 'Action Taken' || action_taken === 'Action Taken') {
          // Update timestamp and IP address on subsequent actions
          await client.query('UPDATE analytics.audit_logs SET action_taken = $1, timestamp = NOW(), ip_address = $3 WHERE work_id = $2', [action_taken, wid, ipAddress]);
        }
      } else {
        // Insert with the NOT NULL ip_address field satisfied
        await client.query(`
          INSERT INTO analytics.audit_logs (log_id, user_id, work_id, action_taken, timestamp, ip_address)
          VALUES (gen_random_uuid(), $1, $2, $3, NOW(), $4)
        `, [dummyUserId, wid, action_taken, ipAddress]);
      }
    }
    await client.query('COMMIT');
    res.json({ success: true });
  } catch (err) {
    await client.query('ROLLBACK');
    console.error('Audit Log Error:', err);
    res.status(500).json({ error: "Database Error" });
  } finally {
    client.release();
  }
});

// Endpoint to fetch cascading filter options
app.get('/api/filters', async (req, res) => {
  try {
    const query = `
      SELECT DISTINCT 
        CASE WHEN house = '1' THEN 'Rajya Sabha' ELSE 'Lok Sabha' END as house_name,
        state, constituency, mp_name, party_name AS party
      FROM public.dim_mp 
      WHERE membership_status = 'Sitting' AND state IS NOT NULL
      ORDER BY house_name, state, constituency, mp_name;
    `;
    const result = await pool.query(query);
    res.json(result.rows);
  } catch (err) { res.status(500).json({ error: "Internal Server Error" }); }
});
app.get('/api/mplads-data', async (req, res) => {
  try {
    // 1. Get query parameters with defaults
    const page = parseInt(req.query.page) || 1;
    const limit = 20;
    const offset = (page - 1) * limit;

    const targetMp = req.query.mp_name || 'ABHIJIT GANGOPADHYAY';
    const searchTerm = req.query.search || ''; // NEW: Capture search term

    // 1. Fetch Aggregated Summary (UNCHANGED - KPI Dashboard remains stable)
    const constQuery = `
      SELECT 
          m.mp_name, m.party_name AS party, m.constituency || ' (' || m.state || ')' AS constituency_name, m.allocated_limit AS total_funds,
          COUNT(p.work_id) AS total_work_orders, 
          COUNT(p.work_id) FILTER (WHERE p.status = 'Completed') AS completed_projects,
          CASE WHEN COUNT(p.work_id) = 0 THEN 0 ELSE ROUND((COUNT(p.work_id) FILTER (WHERE p.status = 'Completed') * 100.0) / COUNT(p.work_id), 2) END AS completed_pct,
          COUNT(p.work_id) FILTER (WHERE COALESCE(a.overall_fraud_probability, 0.5) > 0.7) AS high_risk_orders,
          COUNT(p.work_id) FILTER (WHERE COALESCE(a.overall_fraud_probability, 0.5) > 0.4 AND COALESCE(a.overall_fraud_probability, 0.5) <= 0.7) AS medium_risk_orders,
          COUNT(p.work_id) FILTER (WHERE COALESCE(a.overall_fraud_probability, 0.5) > 0.2 AND COALESCE(a.overall_fraud_probability, 0.5) <= 0.4) AS low_risk_orders,
          COUNT(p.work_id) FILTER (WHERE COALESCE(a.overall_fraud_probability, 0.5) <= 0.2) AS minimal_risk_orders
      FROM public.dim_mp m
      LEFT JOIN public.fact_projects p ON m.mp_id = p.mp_id
      LEFT JOIN analytics.ai_risk_scores a ON p.work_id = a.work_id
      WHERE m.mp_name = $1
      GROUP BY m.mp_id, m.mp_name, m.party_name, m.constituency, m.state, m.allocated_limit;
    `;
    const summaryResult = await pool.query(constQuery, [targetMp]);

    // 2. Fetch Projects (With conditional Search clause)
    let searchCondition = "";
    let projectsParams = [targetMp, limit, offset];
    if (searchTerm) {
      searchCondition = "AND (p.work_id ILIKE $4 OR p.work_description ILIKE $4)";
      projectsParams.push(`%${searchTerm}%`);
    }

    const projectsQuery = `
      SELECT 
          p.work_id, p.work_description AS description, p.recommended_amount AS amount, p.final_amount, MAX(v.vendor_name) AS vendor_name,
          p.recommendation_date, p.completed_date AS completion_date, p.status, MAX(i.district) AS location, MAX(i.ida_name) AS ida_name,
          COALESCE(MAX(a.overall_fraud_probability), 0.5) AS overall,
          CASE WHEN MAX(a.overall_fraud_probability) > 0.7 THEN 'High' WHEN MAX(a.overall_fraud_probability) > 0.4 THEN 'Medium' ELSE 'Low' END AS risk_level,
          MAX(a.duplicate_index) AS duplication, MAX(a.delay_cost_index) AS delay, MAX(a.compliance_index) AS compliance, MAX(a.flagging_reasons_shap::TEXT) AS flagging_reasons_shap
      FROM public.fact_projects p
      JOIN public.dim_mp m ON p.mp_id = m.mp_id
      LEFT JOIN analytics.ai_risk_scores a ON p.work_id = a.work_id
      LEFT JOIN public.dim_ida i ON p.ida_id = i.ida_id
      LEFT JOIN public.fact_expenditures e ON p.work_id = e.work_id
      LEFT JOIN public.dim_vendor v ON e.vendor_id = v.vendor_id
      WHERE m.mp_name = $1 ${searchCondition}
      GROUP BY p.work_id, p.work_description, p.recommended_amount, p.final_amount, p.recommendation_date, p.completed_date, p.status
      ORDER BY p.work_id
      LIMIT $2 OFFSET $3;
    `;
    const projectsResult = await pool.query(projectsQuery, projectsParams);

    // 3. Count exact filtered total for React Pagination
    let countCondition = "";
    let countParams = [targetMp];
    if (searchTerm) {
      countCondition = "AND (p.work_id ILIKE $2 OR p.work_description ILIKE $2)";
      countParams.push(`%${searchTerm}%`);
    }
    const countQuery = `
      SELECT COUNT(p.work_id) as total
      FROM public.fact_projects p
      JOIN public.dim_mp m ON p.mp_id = m.mp_id
      WHERE m.mp_name = $1 ${countCondition};
    `;

    // 4. Fetch Global Alerts (Filters out works already present in the audit_logs)
    const alertsQuery = `
      SELECT 
          p.work_id, p.work_description AS description, p.recommended_amount AS amount, p.final_amount, MAX(v.vendor_name) AS vendor_name,
          p.recommendation_date, p.completed_date AS completion_date, p.status, MAX(i.district) AS location, MAX(i.ida_name) AS ida_name,
          COALESCE(MAX(a.overall_fraud_probability), 0.5) AS overall,
          CASE WHEN MAX(a.overall_fraud_probability) > 0.7 THEN 'High' ELSE 'Medium' END AS risk_level,
          MAX(a.duplicate_index) AS duplication, MAX(a.delay_cost_index) AS delay, MAX(a.compliance_index) AS compliance, MAX(a.flagging_reasons_shap::TEXT) AS flagging_reasons_shap
      FROM public.fact_projects p
      JOIN public.dim_mp m ON p.mp_id = m.mp_id
      JOIN analytics.ai_risk_scores a ON p.work_id = a.work_id
      LEFT JOIN public.dim_ida i ON p.ida_id = i.ida_id
      LEFT JOIN public.fact_expenditures e ON p.work_id = e.work_id
      LEFT JOIN public.dim_vendor v ON e.vendor_id = v.vendor_id
      WHERE m.mp_name = $1 
        AND a.overall_fraud_probability > 0.4
        AND p.work_id NOT IN (SELECT work_id FROM analytics.audit_logs WHERE action_taken = 'Action Taken')
      GROUP BY p.work_id, p.work_description, p.recommended_amount, p.final_amount, p.recommendation_date, p.completed_date, p.status
      ORDER BY overall DESC;
    `;
    const alertsResult = await pool.query(alertsQuery, [targetMp]);

    const countResult = await pool.query(countQuery, countParams);
    const searchTotal = parseInt(countResult.rows[0].total);

    // 5. Fetch Audit Logs for this MP
    const auditLogsQuery = `
      SELECT 
          al.work_id, al.action_taken, al.timestamp, al.ip_address,
          p.work_description AS description, p.recommended_amount AS amount,
          CASE WHEN COALESCE(a.overall_fraud_probability, 0.5) > 0.7 THEN 'High'
               WHEN COALESCE(a.overall_fraud_probability, 0.5) > 0.4 THEN 'Medium'
               ELSE 'Low' END AS risk_level,
          COALESCE(a.overall_fraud_probability, 0.5) AS overall
      FROM analytics.audit_logs al
      JOIN public.fact_projects p ON al.work_id = p.work_id
      JOIN public.dim_mp m ON p.mp_id = m.mp_id
      LEFT JOIN analytics.ai_risk_scores a ON al.work_id = a.work_id
      WHERE m.mp_name = $1
      ORDER BY al.timestamp DESC;
    `;
    const auditLogsResult = await pool.query(auditLogsQuery, [targetMp]);

    // ---REPORTS & CSV ENDPOINT---
    app.get('/api/reports', async (req, res) => {
      try {
        const targetMp = req.query.mp_name || 'ABHIJIT GANGOPADHYAY';
        const riskFilter = req.query.risk || 'All';

        let riskCondition = "";
        if (riskFilter === 'High') riskCondition = "AND COALESCE(a.overall_fraud_probability, 0.5) > 0.7";
        else if (riskFilter === 'Medium') riskCondition = "AND COALESCE(a.overall_fraud_probability, 0.5) > 0.4 AND COALESCE(a.overall_fraud_probability, 0.5) <= 0.7";
        else if (riskFilter === 'Low') riskCondition = "AND COALESCE(a.overall_fraud_probability, 0.5) <= 0.4";

        const query = `
      SELECT 
          p.work_id, p.work_description AS description, p.recommended_amount AS amount, p.final_amount, MAX(v.vendor_name) AS vendor_name,
          p.recommendation_date, p.completed_date AS completion_date, p.status, MAX(i.district) AS location, MAX(i.ida_name) AS ida_name,
          COALESCE(MAX(a.overall_fraud_probability), 0.5) AS overall,
          CASE WHEN MAX(a.overall_fraud_probability) > 0.7 THEN 'High' WHEN MAX(a.overall_fraud_probability) > 0.4 THEN 'Medium' ELSE 'Low' END AS risk_level,
          MAX(a.duplicate_index) AS duplication, MAX(a.delay_cost_index) AS delay, MAX(a.compliance_index) AS compliance, MAX(a.flagging_reasons_shap::TEXT) AS flagging_reasons_shap
      FROM public.fact_projects p
      JOIN public.dim_mp m ON p.mp_id = m.mp_id
      LEFT JOIN analytics.ai_risk_scores a ON p.work_id = a.work_id
      LEFT JOIN public.dim_ida i ON p.ida_id = i.ida_id
      LEFT JOIN public.fact_expenditures e ON p.work_id = e.work_id
      LEFT JOIN public.dim_vendor v ON e.vendor_id = v.vendor_id
      WHERE m.mp_name = $1 ${riskCondition}
      GROUP BY p.work_id, p.work_description, p.recommended_amount, p.final_amount, p.recommendation_date, p.completed_date, p.status
      ORDER BY overall DESC;`;
        const result = await pool.query(query, [targetMp]);
        res.json(result.rows);
      } catch (err) {
        console.error(err);
        res.status(500).json({ error: "Internal Server Error" });
      }
    });

    // 4. Return payload
    if (summaryResult.rows.length === 0) return res.status(404).json({ error: "MP not found" });
    const summaryRow = summaryResult.rows[0];

    res.json({
      summary: {
        mp_name: summaryRow.mp_name,
        constituency: summaryRow.constituency_name,
        total_funds: summaryRow.total_funds ? (summaryRow.total_funds / 10000000).toFixed(2) : "0.00",
        total_work_orders: parseInt(summaryRow.total_work_orders),
        completed_projects: parseInt(summaryRow.completed_projects),
        completed_pct: parseFloat(summaryRow.completed_pct),
        high_risk_orders: parseInt(summaryRow.high_risk_orders || 0),
        medium_risk_orders: parseInt(summaryRow.medium_risk_orders || 0),
        low_risk_orders: parseInt(summaryRow.low_risk_orders || 0),
        minimal_risk_orders: parseInt(summaryRow.minimal_risk_orders || 0)
      },
      search_total: searchTotal, // Passes the pagination cap to React
      projects: projectsResult.rows.map(p => ({
        work_id: p.work_id, 
        description: p.description, 
        location: p.location || "Block Area", 
        ida_name: p.ida_name, 
        vendor_name: p.vendor_name,
        amount: p.amount ? (p.amount / 100000).toFixed(2) + " Lakh" : "0.00 Lakh", 
        final_amount: p.final_amount ? (p.final_amount / 100000).toFixed(2) + " Lakh" : null,
        recommendation_date: p.recommendation_date ? new Date(p.recommendation_date).toLocaleDateString('en-IN') : null,
        completion_date: p.completion_date ? new Date(p.completion_date).toLocaleDateString('en-IN') : null,
        overall: parseFloat(p.overall), 
        risk: p.risk_level, status: p.status, 
        duplication: parseFloat(p.duplication || 0), delay: parseFloat(p.delay || 0), 
        compliance: parseFloat(p.compliance || 0), 
        flagging_reasons_shap: p.flagging_reasons_shap
      })),
      alerts: alertsResult.rows.map(p => ({
        work_id: p.work_id, 
        description: p.description, 
        location: p.location || "Block Area", 
        ida_name: p.ida_name, 
        vendor_name: p.vendor_name,
        amount: p.amount ? (p.amount / 100000).toFixed(2) + " Lakh" : "0.00 Lakh", 
        final_amount: p.final_amount ? (p.final_amount / 100000).toFixed(2) + " Lakh" : null,
        recommendation_date: p.recommendation_date ? new Date(p.recommendation_date).toLocaleDateString('en-IN') : null,
        completion_date: p.completion_date ? new Date(p.completion_date).toLocaleDateString('en-IN') : null,
        overall: parseFloat(p.overall), 
        risk: p.risk_level, 
        status: p.status, 
        duplication: parseFloat(p.duplication || 0), delay: parseFloat(p.delay || 0), 
        compliance: parseFloat(p.compliance || 0), 
        flagging_reasons_shap: p.flagging_reasons_shap
      })),
      audit_logs: auditLogsResult.rows.map(log => ({ ...log, ip_address: log.ip_address }))
    });
  } catch (err) {
    console.error('Database error:', err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Backend server running on http://localhost:${PORT}`);
});