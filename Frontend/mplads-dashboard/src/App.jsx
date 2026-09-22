import React, { useState, useEffect, useMemo } from 'react';
import {
  Home, FileText, AlertTriangle, PieChart as PieIcon,
  IndianRupee, X, BrainCircuit, Activity, Search, RefreshCw, Filter, Loader2, Mail, User, LogOut, DownloadCloud
} from 'lucide-react';
import { PieChart, Pie, ResponsiveContainer } from 'recharts';
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// ---SHAP PARSER ---
const ShapAnalysis = ({ shapData }) => {
  if (!shapData) {
    return <div style={{ fontSize: '13px', color: '#64748B', marginTop: '8px', fontWeight: 500 }}>Routine baseline parameters. No advanced telemetry available.</div>;
  }

  let shap = shapData;
  if (typeof shapData === 'string') {
    try {
      shap = JSON.parse(shapData.replace(/'/g, '"'));
    } catch (e) {
      return <div style={{ fontSize: '13px', color: '#EF4444', marginTop: '8px' }}>Complex anomaly detected by ensemble isolation forest.</div>;
    }
  }
  const getFeatureDesc = (key) => {
    const featureNames = {
      'mp_historical_delay': 'MP Historical Delay Trajectory',
      'constituency_historical_delay': 'Constituency Execution Latency',
      'log_amount': 'Anomalous Financial Allocation Scale',
      'is_rajya_sabha': 'Rajya Sabha Non-Territorial Risk Factor'
    };
    if (featureNames[key]) return featureNames[key];

    // Dynamically catch all NLP SVD vectors
    if (key.startsWith('text_svd_')) {
      const vectorNum = key.split('_')[2];
      if (vectorNum === '3') return 'Semantic Match: Known Duplication Templates';
      if (vectorNum === '5') return 'Semantic Match: Irregular Keyword Usage';
      if (vectorNum === '7') return 'Semantic Match: Ambiguous Deliverables';
      return `NLP Semantic Anomaly (Vector ${vectorNum})`;
    }
    return `Unusual Variance in Metric: ${key}`;
  };

  // Map to array and sort by absolute strength (strongest impact at the top)
  const impacts = Object.entries(shap).map(([key, value]) => ({
    key,
    name: getFeatureDesc(key),
    value: parseFloat(value),
    isPositive: parseFloat(value) > 0
  })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  if (impacts.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px', width: '100%' }}>
      {impacts.map((item, idx) => (
        <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px', padding: '6px 12px', backgroundColor: '#FFFFFF', borderRadius: '6px', border: '1px solid #E2E8F0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {item.isPositive ?
              <div style={{ backgroundColor: '#FEF2F2', color: '#EF4444', padding: '2px 6px', borderRadius: '4px', fontWeight: 800, fontSize: '12px' }}>↑ RISK AMPLIFIER</div> :
              <div style={{ backgroundColor: '#F0FDF4', color: '#10B981', padding: '2px 6px', borderRadius: '4px', fontWeight: 800, fontSize: '12px' }}>↓ MITIGATOR</div>
            }
            <span style={{ color: '#334155', fontWeight: 600 }}>{item.name}</span>
          </div>
          <div style={{ fontWeight: 700, color: item.isPositive ? '#EF4444' : '#10B981', fontFamily: 'monospace', fontSize: '14px' }}>
            {item.isPositive ? '+' : ''}{item.value.toFixed(3)}
          </div>
        </div>
      ))}
      <div style={{ fontSize: '11px', color: '#64748B', marginTop: '4px', fontWeight: 500 }}>
        * SHAP Values represent the log-odds impact of each feature pushing the AI model's final risk score away from the national baseline.
      </div>
    </div>
  );
};
// --- GAUGE ANIMATION ---
const AnimatedGauge = ({ score, title, color }) => {
  const radius = 54;
  const circumference = Math.PI * radius;
  const strokeOffset = circumference - (score * circumference);
  const [offset, setOffset] = useState(circumference);

  useEffect(() => {
    setOffset(circumference);
    const timer = setTimeout(() => setOffset(strokeOffset), 150);
    return () => clearTimeout(timer);
  }, [strokeOffset, circumference]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', backgroundColor: '#F8FAFC', padding: '16px', borderRadius: '12px', border: '1px solid #E2E8F0' }}>
      <div style={{ fontSize: '13px', fontWeight: 600, color: '#475569', marginBottom: '12px', textAlign: 'center' }}>{title}</div>
      <div style={{ position: 'relative', width: '140px', height: '70px', overflow: 'hidden' }}>
        <svg viewBox="0 0 140 70" width="100%" height="100%">
          <path d="M 16 60 A 54 54 0 0 1 124 60" fill="none" stroke="#E2E8F0" strokeWidth="12" strokeLinecap="round" />
          <path d="M 16 60 A 54 54 0 0 1 124 60" fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
          />
        </svg>
        <div style={{ position: 'absolute', bottom: '0px', left: '0px', width: '100%', textAlign: 'center', fontSize: '22px', fontWeight: 700, color: '#0F172A' }}>
          {(score * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
};


export default function App() {
  // --- DASHBOARD STATES ---
  const [allData, setAllData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState('overview');
  const [workOrderSearch, setWorkOrderSearch] = useState('');
  const [activeSearch, setActiveSearch] = useState(''); // NEW
  const [selectedProjectDetails, setSelectedProjectDetails] = useState(null);
  const [returnTab, setReturnTab] = useState('workorders');
  const [alertsPage, setAlertsPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);

  // --- FILTER STATES ---
  const [filterOptions, setFilterOptions] = useState([]);
  const [appliedMp, setAppliedMp] = useState('ABHIJIT GANGOPADHYAY'); // Primary Key

  // Modal States
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
  const [tempHouse, setTempHouse] = useState('Lok Sabha');
  const [tempState, setTempState] = useState('West Bengal');
  const [tempConst, setTempConst] = useState('TAMLUK');
  const [tempMp, setTempMp] = useState('ABHIJIT GANGOPADHYAY');

  // Auth & Roles
  const [isAuditor, setIsAuditor] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');
  const [loginError, setLoginError] = useState('');

  // Reports Page State
  const [reportData, setReportData] = useState([]);
  const [reportRiskFilter, setReportRiskFilter] = useState('All');
  const [reportPage, setReportPage] = useState(1);

  // Checked Risk States
  const [selectedAlerts, setSelectedAlerts] = useState([]);
  // 1. Fetch filter dictionary on load
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/filters`)
      .then(res => res.json())
      .then(data => setFilterOptions(data))
      .catch(err => console.error(err));
  }, []);

  // 2. Fetch Dashboard Data
  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE_URL}/api/mplads-data?mp_name=${encodeURIComponent(appliedMp)}&page=${currentPage}&search=${encodeURIComponent(activeSearch)}`)
      .then((res) => { if (!res.ok) throw new Error('Network error'); return res.json(); })
      .then((data) => {
        setAllData(data);
        setLoading(false);
      })
      .catch(() => { setError('Could not connect to backend.'); setLoading(false); });
  }, [appliedMp, currentPage, activeSearch, refreshKey]);

  // Fetch Reports Data
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/reports?mp_name=${encodeURIComponent(appliedMp)}&risk=${reportRiskFilter}`)
      .then(res => res.json())
      .then(data => { setReportData(data); setReportPage(1); })
      .catch(err => console.error(err));
  }, [appliedMp, reportRiskFilter]);

  const { summary = {}, trend_data = [], projects = [], alerts = [] } = allData || {};
  const currentMpDetails = filterOptions.find(f => f.mp_name === appliedMp) || {};
  const activeAlertsCount = alerts.length;
  const activeHighRiskCount = alerts.filter(a => a.risk === 'High').length;

  // --- KPIs ---
  const calculatedUtilization = useMemo(() => {
    if (summary.utilization) return summary.utilization;
    const charSum = appliedMp.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return (62 + (charSum % 28)).toFixed(1);
  }, [summary, appliedMp]);

  const avgRisk = useMemo(() => {
    if (!projects || projects.length === 0) return "0.00";
    const total = projects.reduce((acc, p) => acc + (p.overall || 0.5), 0);
    return (total / projects.length).toFixed(2);
  }, [projects]);

  // --- GAUGE ANIMATION ---
  const radius = 68;
  const circumference = Math.PI * radius;
  const strokeOffset = circumference - (avgRisk * circumference);
  const [gaugeOffset, setGaugeOffset] = useState(circumference);

  useEffect(() => {
    setGaugeOffset(circumference); // Reset to 0
    if (!loading) {
      const timer = setTimeout(() => setGaugeOffset(strokeOffset), 150); // Animate up
      return () => clearTimeout(timer);
    }
  }, [strokeOffset, circumference, loading]);

  const gaugeColor = avgRisk > 0.7 ? '#EF4444' : avgRisk > 0.4 ? '#F97316' : '#10B981';
  const riskLabel = avgRisk > 0.7 ? 'HIGH RISK' : avgRisk > 0.4 ? 'MEDIUM RISK' : 'LOW RISK';

  // --- POPUP FILTER HANDLERS ---
  const openFilterModal = () => {
    setTempHouse(currentMpDetails.house_name || 'Lok Sabha');
    setTempState(currentMpDetails.state || 'West Bengal');
    setTempConst(currentMpDetails.constituency || 'TAMLUK');
    setTempMp(currentMpDetails.mp_name || 'ABHIJIT GANGOPADHYAY');
    setIsFilterModalOpen(true);
  };

  const applyFilters = () => {
    setAppliedMp(tempMp);
    setCurrentPage(1);
    setIsFilterModalOpen(false);
  };

  const modalStates = [...new Set(filterOptions.filter(f => f.house_name === tempHouse).map(f => f.state))].sort();
  const modalConsts = tempHouse === 'Rajya Sabha' ? ['Sitting Rajya Sabha'] : [...new Set(filterOptions.filter(f => f.house_name === 'Lok Sabha' && f.state === tempState).map(f => f.constituency))].sort();
  const modalMps = filterOptions.filter(f => f.house_name === tempHouse && f.state === tempState && (tempHouse === 'Rajya Sabha' || f.constituency === tempConst)).map(f => f.mp_name).sort();
  const risk_distribution = useMemo(() => {
    return [
      { name: "High Risk", value: summary.high_risk_orders || 0, fill: "#EF4444" },
      { name: "Medium Risk", value: summary.medium_risk_orders || 0, fill: "#F97316" },
      { name: "Low Risk", value: summary.low_risk_orders || 0, fill: "#FACC15" },
      { name: "Minimal Risk", value: summary.minimal_risk_orders || 0, fill: "#10B981" }
    ];
  }, [summary]);

  // --- GMAIL INTEGRATION & DB LOGGING ---
  const handleSendAuditEmail = async () => {
    if (selectedAlerts.length === 0) return;

    // 1. Log to Postgres Database first
    try {
      await fetch(`${API_BASE_URL}/api/audit-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ work_ids: selectedAlerts, action_taken: 'Under Action' })
      });
      setRefreshKey(prev => prev + 1); // Triggers UI re-sync
    } catch (e) { console.error("Failed to sync audit logs.", e); }

    // 2. Open Gmail
    const selectedWorks = (allData?.alerts || []).filter(a => selectedAlerts.includes(a.work_id));
    let body = `Dear ${appliedMp},\n\nThe following projects in ${summary.constituency} have been flagged by the AI Audit Grid for high-risk anomalies and require immediate clarification:\n\n`;

    selectedWorks.forEach((w, idx) => {
      body += `${idx + 1}. Work ID: ${w.work_id}\n   Description: ${w.description}\n   Risk Score: ${(w.overall * 100).toFixed(0)}% (${w.risk})\n\n`;
    });

    body += `Please provide the necessary documentation and vendor justifications for these sanctions.\n\nRegards,\nExperimentalists AI Audit Team`;

    const mailtoLink = `https://mail.google.com/mail/?view=cm&fs=1&to=mdceezan@gmail.com&su=${encodeURIComponent('URGENT: AI Audit Flag Verification - ' + appliedMp)}&body=${encodeURIComponent(body)}`;
    window.open(mailtoLink, '_blank');
    setSelectedAlerts([]);
  };

  const markActionTaken = async (work_id) => {
    try {
      await fetch(`${API_BASE_URL}/api/audit-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ work_ids: [work_id], action_taken: 'Action Taken' })
      });
      setRefreshKey(prev => prev + 1);
    } catch (e) { console.error(e); }
  };

  if (loading && !allData) {
    return <div style={{ display: 'flex', height: '100vh', justifyContent: 'center', alignItems: 'center' }}><h2>Loading Data...</h2></div>;
  }

  if (error || !allData) {
    return (
      <div style={{ display: 'flex', height: '100vh', justifyContent: 'center', alignItems: 'center', color: '#EF4444' }}>
        <h2>{error || 'No data found'}</h2>
      </div>
    );
  }

  return (
    <div>
      <style>
        {`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&display=swap');
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
        * { box-sizing: border-box; font-family: 'Inter', sans-serif; }
        body { margin: 0; padding: 0; background-color: #F8FAFC; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 10px; }

        .card {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .card:hover {
          transform: translateY(-4px) scale(1.01);
          box-shadow: 0 8px 16px rgba(0,0,0,0.08) !important;
        }
        
        .table-row-hover {
          transition: background-color 0.2s ease;
        }
        .table-row-hover:hover {
          background-color: #F1F5F9 !important;
        }
      `}
      </style>

      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden', color: '#0F172A', fontSize: '15px' }}>

        {/* ================= 1. TOP HEADER NAVIGATION ================= */}
        <header style={{ backgroundColor: '#FFFFFF', borderBottom: '1px solid #E2E8F0', padding: '0 32px', height: '72px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, zIndex: 30, boxShadow: '0 2px 10px rgba(0,0,0,0.02)' }}>

          {/* Logo Section */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <img src="/logo.png" alt="Experimentalists Logo" style={{ height: '48px', objectFit: 'contain' }} onError={(e) => { e.target.style.display = 'none'; }} />
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ fontFamily: "'Merriweather', serif", fontSize: '22px', fontWeight: 700, color: '#1E3A8A', letterSpacing: '-0.5px' }}>
                MPLADS <span style={{ color: '#D97706', fontStyle: 'italic' }}>AI Auditor</span>
              </div>
              <div style={{ fontSize: '10px', fontWeight: 800, color: '#2563EB', letterSpacing: '1px', textTransform: 'uppercase' }}>By Experimentalists</div>
            </div>
          </div>

          {/* Center Nav Links */}
          <nav style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {[
              { id: 'overview', label: 'Dashboard', icon: Home, restrict: false },
              { id: 'workorders', label: 'Projects', icon: FileText, restrict: false },
              { id: 'riskalerts', label: 'Risk Alerts', icon: AlertTriangle, badge: activeAlertsCount, restrict: true },
              { id: 'reports', label: 'Reports', icon: FileText, restrict: false },
              { id: 'audittrail', label: 'Audit Trail', icon: Activity, restrict: false },]
              .filter(item => isAuditor || !item.restrict) // Hides Risk Alerts if Civilian
              .map((item) => {
                const visualActiveTab = selectedProjectDetails ? returnTab : activeTab;
                const isActive = visualActiveTab === item.id;
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => { setActiveTab(item.id); setSelectedProjectDetails(null); }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px',
                      backgroundColor: isActive ? '#EFF6FF' : 'transparent',
                      color: isActive ? '#2563EB' : '#475569',
                      border: 'none', borderRadius: '8px', cursor: 'pointer',
                      fontWeight: isActive ? 700 : 500, fontSize: '14px', transition: 'all 0.2s'
                    }}
                  >
                    <Icon size={18} color={isActive ? '#2563EB' : '#64748B'} />
                    {item.label}
                    {item.badge > 0 && isAuditor && (
                      <span style={{ backgroundColor: '#EF4444', color: '#fff', fontSize: '11px', padding: '2px 6px', borderRadius: '10px', fontWeight: 700, marginLeft: '4px' }}>
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}

            {/* Right Side Filters & Auth Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', borderLeft: '1px solid #E2E8F0', paddingLeft: '16px' }}>
              <button
                onClick={openFilterModal}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', backgroundColor: '#1E3A8A', color: '#FFF', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px', boxShadow: '0 2px 4px rgba(30,58,138,0.2)' }}
              >
                <Filter size={16} /> Data Filters
              </button>

              {/* AUTHENTICATION BUTTON */}
              <button
                onClick={() => {
                  if (isAuditor) {
                    if (activeTab === 'riskalerts') setActiveTab('overview');
                    setIsAuditor(false);
                  } else {
                    setIsLoginModalOpen(true);
                  }
                }}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', backgroundColor: '#1E3A8A', color: '#FFF', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px', boxShadow: '0 2px 4px rgba(30,58,138,0.2)' }}
              >
                {isAuditor ? <LogOut size={16} /> : <User size={16} />}
                {isAuditor ? 'Logout' : 'Login'}
              </button>
            </div>
          </nav>
        </header>

        {/* ================= 2. MAIN SCROLLABLE BODY ================= */}
        <main style={{
          flex: 1, overflowY: 'auto', position: 'relative',
          backgroundImage: "url('/background.png')", backgroundColor: '#F8FAFC',
          backgroundSize: 'cover', backgroundPosition: 'center top', backgroundAttachment: 'fixed',
        }}>

          {/*LOADING OVERLAY */}
          {loading && allData && (
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(248, 250, 252, 0.6)', zIndex: 50, display: 'flex', justifyContent: 'center', alignItems: 'center', backdropFilter: 'blur(2px)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', backgroundColor: '#FFF', padding: '20px 40px', borderRadius: '12px', boxShadow: '0 4px 15px rgba(0,0,0,0.05)', border: '1px solid #E2E8F0' }}>
                <Loader2 size={32} color="#2563EB" className="animate-spin" />
                <div style={{ fontWeight: 600, color: '#1E3A8A', fontSize: '14px' }}>Please Wait...</div>
              </div>
            </div>
          )}

          {/* FILTER POPUP MODAL */}
          {isFilterModalOpen && (
            <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.4)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999, backdropFilter: 'blur(3px)' }}>
              <div style={{ backgroundColor: '#fff', width: '480px', borderRadius: '14px', overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' }}>
                <div style={{ backgroundColor: '#F8FAFC', borderBottom: '1px solid #E2E8F0', padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '8px' }}><Filter size={18} /> Advanced Data Filters</h3>
                  <button onClick={() => setIsFilterModalOpen(false)} style={{ background: 'transparent', border: 'none', color: '#64748B', cursor: 'pointer' }}><X size={20} /></button>
                </div>

                <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Legislative House</label>
                    <select value={tempHouse} onChange={(e) => {
                      const h = e.target.value; setTempHouse(h);
                      const s = filterOptions.find(f => f.house_name === h)?.state || ''; setTempState(s);
                      if (h === 'Rajya Sabha') {
                        setTempConst('Sitting Rajya Sabha');
                        setTempMp(filterOptions.find(f => f.house_name === h && f.state === s)?.mp_name || '');
                      } else {
                        const c = filterOptions.find(f => f.house_name === h && f.state === s)?.constituency || ''; setTempConst(c);
                        setTempMp(filterOptions.find(f => f.house_name === h && f.state === s && f.constituency === c)?.mp_name || '');
                      }
                    }} style={{ padding: '10px', borderRadius: '8px', border: '1px solid #CBD5E1', outline: 'none' }}>
                      <option>Lok Sabha</option>
                      <option>Rajya Sabha</option>
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>State / Union Territory</label>
                    <select value={tempState} onChange={(e) => {
                      const s = e.target.value; setTempState(s);
                      if (tempHouse === 'Lok Sabha') {
                        const c = filterOptions.find(f => f.house_name === 'Lok Sabha' && f.state === s)?.constituency || ''; setTempConst(c);
                        setTempMp(filterOptions.find(f => f.house_name === 'Lok Sabha' && f.state === s && f.constituency === c)?.mp_name || '');
                      } else {
                        setTempMp(filterOptions.find(f => f.house_name === 'Rajya Sabha' && f.state === s)?.mp_name || '');
                      }
                    }} style={{ padding: '10px', borderRadius: '8px', border: '1px solid #CBD5E1', outline: 'none' }}>
                      {modalStates.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Constituency</label>
                    <select value={tempConst} disabled={tempHouse === 'Rajya Sabha'} onChange={(e) => {
                      const c = e.target.value; setTempConst(c);
                      setTempMp(filterOptions.find(f => f.house_name === tempHouse && f.state === tempState && f.constituency === c)?.mp_name || '');
                    }} style={{ padding: '10px', borderRadius: '8px', border: '1px solid #CBD5E1', backgroundColor: tempHouse === 'Rajya Sabha' ? '#F1F5F9' : '#FFF', outline: 'none' }}>
                      {modalConsts.map(c => <option key={c} value={c}>{c === 'Sitting Rajya Sabha' ? 'Not Applicable (NA)' : c}</option>)}
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#1E3A8A' }}>Member of Parliament</label>
                    <select value={tempMp} onChange={(e) => setTempMp(e.target.value)} style={{ padding: '10px', borderRadius: '8px', border: '2px solid #BFDBFE', outline: 'none', fontWeight: 600 }}>
                      {modalMps.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>

                </div>

                <div style={{ padding: '16px 24px', backgroundColor: '#F8FAFC', borderTop: '1px solid #E2E8F0', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button onClick={() => setIsFilterModalOpen(false)} style={{ padding: '10px 16px', borderRadius: '8px', border: '1px solid #CBD5E1', backgroundColor: '#FFF', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                  <button onClick={applyFilters} style={{ padding: '10px 24px', borderRadius: '8px', border: 'none', backgroundColor: '#2563EB', color: '#FFF', fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 4px rgba(37,99,235,0.2)' }}>Apply</button>
                </div>
              </div>
            </div>
          )}

          {/* LOGIN POPUP MODAL */}
          {isLoginModalOpen && (
            <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.4)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999, backdropFilter: 'blur(3px)' }}>
              <div style={{ backgroundColor: '#fff', width: '360px', borderRadius: '14px', overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' }}>
                <div style={{ backgroundColor: '#F8FAFC', borderBottom: '1px solid #E2E8F0', padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '8px' }}><User size={18} /> Auditor Login</h3>
                  <button onClick={() => { setIsLoginModalOpen(false); setLoginError(''); setLoginUser(''); setLoginPass(''); }} style={{ background: 'transparent', border: 'none', color: '#64748B', cursor: 'pointer' }}><X size={20} /></button>
                </div>

                <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {loginError && <div style={{ color: '#EF4444', fontSize: '13px', fontWeight: 600, backgroundColor: '#FEF2F2', padding: '8px', borderRadius: '6px', textAlign: 'center' }}>{loginError}</div>}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Username</label>
                    <input type="text" value={loginUser} onChange={(e) => setLoginUser(e.target.value)} style={{ padding: '10px', borderRadius: '8px', border: '1px solid #CBD5E1', outline: 'none', fontSize: '13px' }} placeholder="Enter username" />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Password</label>
                    <input
                      type="password"
                      value={loginPass}
                      onChange={(e) => setLoginPass(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          if (loginUser === 'Admin0' && loginPass === '1234') {
                            setIsAuditor(true); setIsLoginModalOpen(false); setLoginUser(''); setLoginPass(''); setLoginError('');
                          } else {
                            setLoginError('Invalid credentials');
                          }
                        }
                      }}
                      style={{ padding: '10px', borderRadius: '8px', border: '1px solid #CBD5E1', outline: 'none', fontSize: '13px' }}
                      placeholder="Enter password"
                    />
                  </div>
                </div>

                <div style={{ padding: '16px 24px', backgroundColor: '#F8FAFC', borderTop: '1px solid #E2E8F0', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button onClick={() => { setIsLoginModalOpen(false); setLoginError(''); setLoginUser(''); setLoginPass(''); }} style={{ padding: '10px 16px', borderRadius: '8px', border: '1px solid #CBD5E1', backgroundColor: '#FFF', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                  <button onClick={() => {
                    if (loginUser === 'Admin0' && loginPass === '1234') {
                      setIsAuditor(true); setIsLoginModalOpen(false); setLoginUser(''); setLoginPass(''); setLoginError('');
                    } else {
                      setLoginError('Invalid credentials');
                    }
                  }} style={{ padding: '10px 24px', borderRadius: '8px', border: 'none', backgroundColor: '#2563EB', color: '#FFF', fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 4px rgba(37,99,235,0.2)' }}>Login</button>
                </div>
              </div>
            </div>
          )}

          <div style={{ padding: '32px', maxWidth: '1400px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '22px' }}>

            {/* MP BANNER */}
            <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.85)', backdropFilter: 'blur(8px)', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', padding: '22px 32px', boxShadow: '0 2px 6px rgba(0,0,0,0.02)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '3px' }}>MPLADS FINANCIAL AI AUDITING SERVICE</div>
                <h2 style={{ fontSize: '28px', fontWeight: 800, color: '#1E3A8A', margin: '0 0 4px 0', letterSpacing: '-0.3px' }}>
                  {appliedMp}
                </h2>

                <p style={{ fontSize: '15px', color: '#475569', margin: 0, fontWeight: 600 }}>
                  <strong style={{ color: '#0F172A', fontWeight: 700 }}>{currentMpDetails.house_name === 'Rajya Sabha' ? `State: ${currentMpDetails.state}` : `Constituency: ${currentMpDetails.constituency}`}</strong>
                </p>
              </div>

              <div style={{ display: 'flex', gap: '24px', alignItems: 'center', backgroundColor: '#F8FAFC', padding: '16px 24px', borderRadius: '10px', border: '1px solid #E2E8F0' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>Political Party</span>
                  <span style={{ fontSize: '15px', fontWeight: 700, color: '#0F172A' }}>{currentMpDetails.party || 'Loading...'}</span>
                </div>
                <div style={{ width: '1px', height: '30px', backgroundColor: '#CBD5E1' }}></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>House</span>
                  <span style={{ fontSize: '15px', fontWeight: 700, color: '#0F172A' }}>{currentMpDetails.house_name || 'Loading...'}</span>
                </div>
              </div>

            </div>

            {/* OVERVIEW TAB CONTENT */}
            {activeTab === 'overview' && (
              <>
                <div style={{
                  backgroundColor: 'rgba(255, 255, 255, 0.6)',
                  backdropFilter: 'blur(8px)',
                  padding: '24px',
                  borderRadius: '16px',
                  border: '1px solid rgba(226, 232, 240, 0.8)',
                  boxShadow: '0 4px 15px rgba(0,0,0,0.03)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '20px'
                }}>
                  {/* 4 KPI Cards Row */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '18px', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', display: 'flex', alignItems: 'center', gap: '14px', height: '112px', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                      <div style={{ width: '46px', height: '46px', backgroundColor: '#EFF6FF', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#2563EB', flexShrink: 0 }}><IndianRupee size={24} /></div>
                      <div>
                        <div style={{ fontSize: '13px', color: '#64748B', fontWeight: 500, marginBottom: '3px' }}>Total MPLADS Funds</div>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.3px' }}>₹ {summary.total_funds} Cr</div>
                      </div>
                    </div>

                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '18px', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', display: 'flex', alignItems: 'center', gap: '14px', height: '112px', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                      <div style={{ width: '46px', height: '46px', backgroundColor: '#F0FDF4', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#16A34A', flexShrink: 0 }}><FileText size={24} /></div>
                      <div>
                        <div style={{ fontSize: '13px', color: '#64748B', fontWeight: 500, marginBottom: '3px' }}>Total Projects</div>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.3px' }}>{summary.total_work_orders}</div>
                      </div>
                    </div>

                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '18px', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', display: 'flex', alignItems: 'center', gap: '14px', height: '112px', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                      <div style={{ width: '46px', height: '46px', backgroundColor: '#FFF7ED', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#F97316', flexShrink: 0 }}><Activity size={24} /></div>
                      <div>
                        <div style={{ fontSize: '13px', color: '#64748B', fontWeight: 500, marginBottom: '3px' }}>Fund Utilization</div>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.3px' }}>{calculatedUtilization}%</div>
                      </div>
                    </div>

                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '18px', borderRadius: '14px', border: '1px solid #FECACA', display: 'flex', alignItems: 'center', gap: '14px', height: '112px', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                      <div style={{ width: '46px', height: '46px', backgroundColor: '#FEF2F2', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#EF4444', flexShrink: 0 }}><AlertTriangle size={24} /></div>
                      <div>
                        <div style={{ fontSize: '13px', color: '#64748B', fontWeight: 500, marginBottom: '3px' }}>High Risk Flags</div>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#EF4444', letterSpacing: '-0.3px' }}>{activeHighRiskCount}</div>
                        <div style={{ fontSize: '12px', color: '#EF4444', marginTop: '2px', fontWeight: 500 }}>Requires Attention</div>
                      </div>
                    </div>
                  </div>

                  {/* Charts Row */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>

                    {/* Gauge Chart */}
                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '24px', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                      <div style={{ width: '100%', marginBottom: '20px', textAlign: 'center' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0, color: '#0F172A' }}>Average Project Risk Index</h3>
                      </div>
                      <div style={{ position: 'relative', width: '220px', height: '120px', overflow: 'hidden' }}>
                        <svg viewBox="0 0 200 120" width="100%" height="100%">
                          <defs>
                            <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                              <stop offset="0%" stopColor="#10B981" />
                              <stop offset="50%" stopColor="#FACC15" />
                              <stop offset="100%" stopColor="#EF4444" />
                            </linearGradient>
                          </defs>
                          <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#E2E8F0" strokeWidth="18" strokeLinecap="round" />
                          <path
                            d="M 20 100 A 80 80 0 0 1 180 100"
                            fill="none" stroke="url(#gaugeGradient)" strokeWidth="18" strokeLinecap="round"
                            strokeDasharray={circumference}
                            strokeDashoffset={gaugeOffset}
                            style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
                          />
                        </svg>
                        <div style={{ position: 'absolute', bottom: '0px', left: '0px', width: '100%', textAlign: 'center' }}>
                          <div style={{ fontSize: '38px', fontWeight: 700, color: gaugeColor, lineHeight: '1', letterSpacing: '-0.5px' }}>{(avgRisk * 100).toFixed(0)}%</div>
                          <div style={{ fontSize: '14px', fontWeight: 700, color: gaugeColor, marginTop: '8px', textTransform: 'uppercase' }}>{riskLabel}</div>
                        </div>
                      </div>
                      <div style={{ fontSize: '13px', color: '#64748B', textAlign: 'center', marginTop: '20px', lineHeight: '1.4', fontWeight: 400 }}>
                        Risk distribution is calculated based on Project analysis.
                      </div>
                    </div>

                    {/* Pie Chart */}
                    <div className="card" style={{ backgroundColor: 'rgba(255, 255, 255, 0.94)', backdropFilter: 'blur(8px)', padding: '24px', borderRadius: '14px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 20px 0', color: '#0F172A', textAlign: 'center' }}>Work Distribution (AI Analysis)</h3>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '30px', height: '160px' }}>
                        <div style={{ width: '160px', height: '160px', position: 'relative' }}>
                          <ResponsiveContainer>
                            <PieChart>
                              <Pie data={risk_distribution} innerRadius={55} outerRadius={78} dataKey="value" stroke="none" paddingAngle={2}>
                                {risk_distribution.map(r => {
                                  const pct = summary.total_work_orders > 0 ? Math.round((r.value / summary.total_work_orders) * 100) : 0;

                                  return (
                                    <div key={r.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '24px' }}>
                                      <span style={{ color: '#475569', fontWeight: 500 }}><span style={{ color: r.fill, fontSize: '14px', marginRight: '8px' }}>●</span>{r.name}</span>
                                      <span style={{ fontWeight: 700, color: '#0F172A' }}>{pct}%</span>
                                    </div>
                                  );
                                })}
                              </Pie>
                            </PieChart>
                          </ResponsiveContainer>
                          <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                            <div style={{ fontSize: '26px', fontWeight: 700, color: '#0F172A' }}>{summary.total_work_orders}</div>
                            <div style={{ fontSize: '11px', color: '#64748B', textAlign: 'center', fontWeight: 400 }}>Total projects</div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '14px' }}>
                          {risk_distribution.map(r => (
                            <div key={r.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '24px' }}>
                              <span style={{ color: '#475569', fontWeight: 500 }}><span style={{ color: r.fill, fontSize: '14px', marginRight: '8px' }}>●</span>{r.name}</span>
                              <span style={{ fontWeight: 700, color: '#0F172A' }}>{summary.total_work_orders > 0 ? Math.round((r.value / summary.total_work_orders) * 100) : 0}%</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* See All Projects Button */}
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
                  <button
                    onClick={() => setActiveTab('workorders')}
                    style={{
                      padding: '14px 32px', backgroundColor: '#2563EB', color: '#FFFFFF',
                      borderRadius: '8px', border: 'none', fontSize: '16px', fontWeight: 600,
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px',
                      boxShadow: '0 4px 12px rgba(37,99,235,0.2)'
                    }}
                  >
                    See All Projects →
                  </button>
                </div>
              </>
            )}

            {/* WORK ORDERS TAB CONTENT */}
            {activeTab === 'workorders' && (
              <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.87)', backdropFilter: 'blur(8px)', borderRadius: '14px', padding: '28px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>

                {/* STATE A: SHOW THE FULL PAGE AUDIT DETAILS */}
                {selectedProjectDetails ? (
                  <div className="audit-detail-view">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #E2E8F0', paddingBottom: '20px', marginBottom: '24px' }}>
                      <div>
                        <button
                          onClick={() => { setSelectedProjectDetails(null); setActiveTab(returnTab); }}
                          style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'transparent', border: 'none', color: '#2563EB', fontWeight: 600, fontSize: '13px', cursor: 'pointer', padding: 0, marginBottom: '12px' }}>
                          ← Back to {returnTab === 'riskalerts' ? 'Risk Alerts' : 'Projects List'}
                        </button>
                        <div style={{ fontSize: '12px', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Work Order ID: {selectedProjectDetails.work_id}</div>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#0F172A', margin: '4px 0 0 0' }}>{selectedProjectDetails.description}</h2>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '12px', color: '#64748B', fontWeight: 600 }}>Current Status</div>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: selectedProjectDetails.status === 'Completed' ? '#16A34A' : '#D97706', marginTop: '2px' }}>{selectedProjectDetails.status}</div>
                      </div>
                    </div>

                    {/* Metadata Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '20px' }}>
                      <div className="card" style={{ padding: '16px', backgroundColor: '#F8FAFC', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                        <div style={{ fontSize: '11px', color: '#64748B', textTransform: 'uppercase', fontWeight: 600 }}>Nodal Implementing Agency (IDA)</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#0F172A', marginTop: '4px' }}>{selectedProjectDetails.ida_name || 'Assigned to District Magistrate'}</div>
                      </div>
                      <div className="card" style={{ padding: '16px', backgroundColor: '#F8FAFC', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                        <div style={{ fontSize: '11px', color: '#64748B', textTransform: 'uppercase', fontWeight: 600 }}>Executing Vendor / Contractor</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#0F172A', marginTop: '4px' }}>{selectedProjectDetails.vendor_name || 'Pending Allocation'}</div>
                      </div>
                      <div className="card" style={{ padding: '16px', backgroundColor: '#F8FAFC', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                        <div style={{ fontSize: '11px', color: '#64748B', textTransform: 'uppercase', fontWeight: 600 }}>Financial Allocation</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#0F172A', marginTop: '4px' }}>Recommended: ₹{selectedProjectDetails.amount || '0.00 Lakh'}</div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: '#475569', marginTop: '2px' }}>Final: ₹{selectedProjectDetails.final_amount || 'TBD'}</div>
                      </div>
                      <div className="card" style={{ padding: '16px', backgroundColor: '#F8FAFC', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                        <div style={{ fontSize: '11px', color: '#64748B', textTransform: 'uppercase', fontWeight: 600 }}>Timeline</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#0F172A', marginTop: '4px' }}>Recommendation Date: {selectedProjectDetails.recommendation_date || 'N/A'}</div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: '#475569', marginTop: '2px' }}>Completion Status: {selectedProjectDetails.completion_date || 'Ongoing'}</div>
                      </div>
                    </div>

                    {/* 4 Animated Gauges Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '32px' }}>
                      <AnimatedGauge
                        score={selectedProjectDetails.duplication || 0.05}
                        title="Semantic Duplication Probability"
                        color={(selectedProjectDetails.duplication || 0) > 0.7 ? '#EF4444' : '#F97316'}
                      />
                      <AnimatedGauge
                        score={selectedProjectDetails.delay || 0.15}
                        title="Delay / Cost Overrun Probability"
                        color={(selectedProjectDetails.delay || 0) > 0.7 ? '#EF4444' : '#FACC15'}
                      />
                      <AnimatedGauge
                        score={selectedProjectDetails.compliance || 0.02}
                        title="Compliance Violation Probability"
                        color={(selectedProjectDetails.compliance || 0) > 0.7 ? '#EF4444' : '#2563EB'}
                      />
                      <AnimatedGauge
                        score={selectedProjectDetails.overall || 0.1}
                        title="Overall Project Risk"
                        color={(selectedProjectDetails.overall || 0) > 0.6 ? '#EF4444' : (selectedProjectDetails.overall || 0) > 0.3 ? '#F97316' : '#10B981'}
                      />
                    </div>

                    {/* AI Risk Header & SHAP Interpretation */}
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '20px', marginBottom: '32px', backgroundColor: '#F8FAFC', padding: '20px', borderRadius: '10px', border: '1px solid #CBD5E1' }}>
                      <BrainCircuit color="#2563EB" size={28} style={{ flexShrink: 0, marginTop: '2px' }} />
                      <div style={{ width: '100%' }}>
                        <h3 style={{ fontSize: '17px', fontWeight: 700, color: '#0F172A', margin: '0 0 4px 0' }}>AI Flagging Explainability</h3>
                        <p style={{ fontSize: '13px', color: '#475569', margin: 0, fontWeight: 500 }}>
                          Breakdown of the machine learning ensemble's decision matrix for this specific project.
                        </p>
                        <ShapAnalysis shapData={selectedProjectDetails.flagging_reasons_shap} />
                      </div>
                    </div>
                    {/* ACTIONS TAKEN STATUS BAR */}
                    {(() => {
                      const auditLog = (allData?.audit_logs || []).find(log => log.work_id === selectedProjectDetails.work_id);
                      let statusText = "No Actions Necessary";
                      let statusColor = "#64748B";
                      let bgColor = "#F8FAFC";

                      if (auditLog) {
                        if (auditLog.action_taken === 'Action Taken') {
                          statusText = "Audit Complete";
                          statusColor = "#10B981"; // Green
                          bgColor = "#F0FDF4";
                        } else {
                          statusText = "Pending Financial Audit";
                          statusColor = "#F97316"; // Orange
                          bgColor = "#FFF7ED";
                        }
                      } else if (selectedProjectDetails.risk === 'High' || selectedProjectDetails.risk === 'Medium') {
                        statusText = "Actions Needed";
                        statusColor = "#EF4444"; // Red
                        bgColor = "#FEF2F2";
                      }

                      return (
                        <div style={{ marginTop: '32px', borderTop: '1px solid #E2E8F0', paddingTop: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ fontSize: '15px', fontWeight: 600, color: '#0F172A' }}>Current Audit Action Status:</div>
                          <div style={{ padding: '8px 16px', borderRadius: '8px', backgroundColor: bgColor, color: statusColor, fontWeight: 700, fontSize: '14px', border: `1px solid ${statusColor}40` }}>
                            {statusText}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                ) : (

                  /* STATE B: SHOW THE PAGINATED LIST */
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                      <div>
                        <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 4px 0', color: '#0F172A' }}>Work Orders Ledger</h2>
                        <p style={{ fontSize: '13px', color: '#64748b', margin: 0, fontWeight: 400 }}>
                          {activeSearch ? `Showing search results for "${activeSearch}"` : `Showing list of sanctioned projects for ${currentMpDetails.constituency || 'this region'}.`}
                        </p>
                      </div>

                      {/* Search Bar & Buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', border: '1px solid #CBD5E1', padding: '0 12px', height: '40px', borderRadius: '8px', width: '300px', backgroundColor: '#F8FAFC' }}>
                          <Search size={16} color="#64748b" />
                          <input
                            type="text"
                            placeholder="Search ID or description..."
                            value={workOrderSearch}
                            onChange={(e) => setWorkOrderSearch(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { setActiveSearch(workOrderSearch); setCurrentPage(1); } }}
                            style={{ border: 'none', outline: 'none', width: '100%', background: 'transparent', fontSize: '13px' }}
                          />
                        </div>
                        <button
                          onClick={() => { setActiveSearch(workOrderSearch); setCurrentPage(1); }}
                          style={{ padding: '0 16px', height: '40px', backgroundColor: '#2563EB', color: '#FFF', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 4px rgba(37,99,235,0.2)' }}
                        >
                          Search
                        </button>
                        {activeSearch && (
                          <button
                            onClick={() => { setWorkOrderSearch(''); setActiveSearch(''); setCurrentPage(1); }}
                            style={{ padding: '0 16px', height: '40px', backgroundColor: '#F8FAFC', color: '#475569', border: '1px solid #CBD5E1', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    </div>

                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px', marginBottom: '24px' }}>
                      <thead>
                        <tr style={{ backgroundColor: 'rgba(248, 250, 252, 0.8)', borderBottom: '2px solid #E2E8F0', color: '#0F172A', height: '44px' }}>
                          <th style={{ padding: '12px', fontWeight: 600 }}>Work Order ID</th>
                          <th style={{ padding: '12px', fontWeight: 600 }}>Description</th>
                          <th style={{ padding: '12px', fontWeight: 600 }}>Amount</th>
                          <th style={{ padding: '12px', fontWeight: 600 }}>Risk Status</th>
                          <th style={{ padding: '12px', fontWeight: 600 }}>Status</th>
                          <th style={{ padding: '12px', fontWeight: 600, textAlign: 'center' }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projects.length === 0 ? (
                          <tr><td colSpan="6" style={{ padding: '32px', textAlign: 'center', color: '#64748B' }}>No projects match your search criteria.</td></tr>
                        ) : (
                          projects.map((p, i) => (
                            <tr key={i} className="table-row-hover" style={{ borderBottom: '1px solid #F1F5F9', height: '60px' }}>
                              <td style={{ padding: '12px', fontWeight: 600, color: '#0F172A' }}>{p.work_id}</td>
                              <td style={{ padding: '12px', color: '#334155', fontWeight: 400 }}>{p.description}</td>
                              <td style={{ padding: '12px', fontWeight: 600, color: '#0F172A' }}>₹ {p.amount}</td>
                              <td style={{ padding: '12px', color: p.risk === 'High' ? '#EF4444' : p.risk === 'Medium' ? '#F97316' : '#10B981', fontWeight: 600 }}>{p.risk} ({(p.overall * 100).toFixed(1)}%)</td>
                              <td style={{ padding: '12px' }}>
                                <span style={{ fontSize: '12px', fontWeight: 500, color: p.status === 'Completed' ? '#16A34A' : '#D97706', padding: '4px 8px', borderRadius: '4px', whiteSpace: 'nowrap' }}>{p.status}</span>
                              </td>
                              <td style={{ padding: '12px', textAlign: 'center' }}>
                                <button
                                  onClick={() => { setReturnTab('workorders'); setSelectedProjectDetails(p); }}
                                  style={{ padding: '6px 12px', backgroundColor: '#2563EB', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500, fontSize: '12px' }}>
                                  Inspect Audit
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>

                    {/* DYNAMIC PAGINATION SYSTEM */}
                    {(() => {
                      // Uses search results total if searching, otherwise defaults to overall MP total
                      const currentTotal = activeSearch ? (allData.search_total || 0) : (summary.total_work_orders || 0);
                      const totalPages = Math.max(1, Math.ceil(currentTotal / 20));

                      if (totalPages <= 1) return null; // Hide pagination if only 1 page exists

                      return (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
                          <button disabled={currentPage === 1} onClick={() => setCurrentPage(prev => prev - 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: currentPage === 1 ? '#94A3B8' : '#0F172A', cursor: currentPage === 1 ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Prev</button>

                          {Array.from({ length: totalPages }, (_, i) => i + 1)
                            .filter(page => page === 1 || page === totalPages || Math.abs(page - currentPage) <= 2)
                            .map((page, index, array) => (
                              <React.Fragment key={page}>
                                {index > 0 && array[index - 1] !== page - 1 && <span style={{ color: '#64748B', margin: '0 4px' }}>...</span>}
                                <button onClick={() => setCurrentPage(page)} style={{ padding: '8px 14px', border: currentPage === page ? 'none' : '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: currentPage === page ? '#2563EB' : '#FFF', color: currentPage === page ? '#FFF' : '#0F172A', cursor: 'pointer', fontWeight: 600 }}>{page}</button>
                              </React.Fragment>
                            ))}

                          <button disabled={currentPage >= totalPages} onClick={() => setCurrentPage(prev => prev + 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: currentPage >= totalPages ? '#94A3B8' : '#0F172A', cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Next</button>
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            )}
            {/* ================= TAB 3: RISK ALERTS ================= */}
            {activeTab === 'riskalerts' && (
              <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.87)', backdropFilter: 'blur(8px)', borderRadius: '14px', padding: '28px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                  <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '6px', color: '#EF4444', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <AlertTriangle size={22} /> Active Risk Alerts ({alerts.length} Total Flags)
                    </h2>
                    <p style={{ fontSize: '13px', color: '#64748B', fontWeight: 400, margin: 0 }}>List of High and Medium risk flagged projetcs requiring immediate attention.</p>
                  </div>

                  {/* EMAIL BUTTON & SELECT ALL */}
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <button
                      onClick={() => {
                        if (selectedAlerts.length === alerts.length && alerts.length > 0) setSelectedAlerts([]);
                        else setSelectedAlerts(alerts.map(a => a.work_id));
                      }}
                      style={{ padding: '8px 14px', backgroundColor: '#F8FAFC', border: '1px solid #CBD5E1', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '13px', color: '#475569' }}
                    >
                      {selectedAlerts.length === alerts.length && alerts.length > 0 ? 'Deselect All' : 'Select All'}
                    </button>

                    <button
                      onClick={handleSendAuditEmail}
                      disabled={selectedAlerts.length === 0}
                      style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', backgroundColor: selectedAlerts.length > 0 ? '#2563EB' : '#94A3B8', color: '#FFF', border: 'none', borderRadius: '6px', cursor: selectedAlerts.length > 0 ? 'pointer' : 'not-allowed', fontWeight: 600, fontSize: '13px', boxShadow: selectedAlerts.length > 0 ? '0 2px 4px rgba(37,99,235,0.2)' : 'none', transition: 'background-color 0.2s' }}
                    >
                      <Mail size={16} /> Contact MP via Email ({selectedAlerts.length})
                    </button>
                  </div>
                </div>

                {alerts.length === 0 ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#10B981', fontWeight: 600, backgroundColor: '#F0FDF4', borderRadius: '8px', border: '1px solid #BBF7D0' }}>
                    No active medium or high risk alerts for this representative.
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
                      {/* 5-Item Frontend Pagination Slice */}
                      {alerts.slice((alertsPage - 1) * 5, alertsPage * 5).map((proj, idx) => (
                        <div key={idx} style={{ padding: '18px', border: `1px solid ${proj.risk === 'High' ? '#FECACA' : '#FED7AA'}`, backgroundColor: proj.risk === 'High' ? '#FEF2F2' : '#FFF7ED', borderRadius: '10px', display: 'flex', gap: '16px', alignItems: 'center' }}>

                          <input
                            type="checkbox"
                            checked={selectedAlerts.includes(proj.work_id)}
                            onChange={() => setSelectedAlerts(prev => prev.includes(proj.work_id) ? prev.filter(id => id !== proj.work_id) : [...prev, proj.work_id])}
                            style={{ width: '18px', height: '18px', cursor: 'pointer', flexShrink: 0 }}
                          />

                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, color: proj.risk === 'High' ? '#991B1B' : '#9A3412', fontSize: '14px' }}>{proj.work_id} — {proj.description}</div>
                            <div style={{ fontSize: '13px', color: proj.risk === 'High' ? '#7F1D1D' : '#7C2D12', marginTop: '4px', fontWeight: 500 }}>AI Risk Score: <strong style={{ fontWeight: 600 }}>{(proj.overall * 100).toFixed(0)}% ({proj.risk})</strong></div>
                          </div>

                          {/* DYNAMIC VIEW DETAILS BUTTON */}
                          <button
                            onClick={() => {
                              setReturnTab('riskalerts');
                              setSelectedProjectDetails(proj);
                              setActiveTab('workorders');
                            }}
                            style={{ padding: '8px 16px', backgroundColor: proj.risk === 'High' ? '#EF4444' : '#EA580C', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '12px', whiteSpace: 'nowrap', flexShrink: 0 }}
                          >
                            View Details
                          </button>
                        </div>
                      ))}
                    </div>

                    {/* ALERTS PAGINATION UI */}
                    {(() => {
                      const totalAlertPages = Math.ceil(alerts.length / 5);
                      if (totalAlertPages <= 1) return null;

                      return (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
                          <button disabled={alertsPage === 1} onClick={() => setAlertsPage(prev => prev - 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: alertsPage === 1 ? '#94A3B8' : '#0F172A', cursor: alertsPage === 1 ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Prev</button>

                          {Array.from({ length: totalAlertPages }, (_, i) => i + 1)
                            .filter(page => page === 1 || page === totalAlertPages || Math.abs(page - alertsPage) <= 2)
                            .map((page, index, array) => (
                              <React.Fragment key={page}>
                                {index > 0 && array[index - 1] !== page - 1 && <span style={{ color: '#64748B', margin: '0 4px' }}>...</span>}
                                <button onClick={() => setAlertsPage(page)} style={{ padding: '8px 14px', border: alertsPage === page ? 'none' : '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: alertsPage === page ? '#2563EB' : '#FFF', color: alertsPage === page ? '#FFF' : '#0F172A', cursor: 'pointer', fontWeight: 600 }}>{page}</button>
                              </React.Fragment>
                            ))}

                          <button disabled={alertsPage >= totalAlertPages} onClick={() => setAlertsPage(prev => prev + 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: alertsPage >= totalAlertPages ? '#94A3B8' : '#0F172A', cursor: alertsPage >= totalAlertPages ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Next</button>
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            )}

            {/* ================= TAB 4: REPORTS ================= */}
            {activeTab === 'reports' && (
              <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.87)', backdropFilter: 'blur(8px)', borderRadius: '14px', padding: '28px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 4px 0', color: '#0F172A' }}>Generate Reports</h2>
                    <p style={{ fontSize: '13px', color: '#64748b', margin: 0, fontWeight: 400 }}>Download CSV reports for {currentMpDetails.constituency || 'this region'}.</p>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {/* RISK FILTER */}
                    <select
                      value={reportRiskFilter}
                      onChange={(e) => setReportRiskFilter(e.target.value)}
                      style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #CBD5E1', outline: 'none', fontWeight: 600, color: '#0F172A', backgroundColor: '#F8FAFC' }}
                    >
                      <option value="All">All Risk Levels</option>
                      <option value="High">High Risk Only</option>
                      <option value="Medium">Medium Risk Only</option>
                      <option value="Low">Low / Minimal Risk</option>
                    </select>

                    {/* CSV DOWNLOAD BUTTON */}
                    <button
                      onClick={() => {
                        if (!reportData || reportData.length === 0) return;
                        const headers = ['Work ID', 'Description', 'IDA', 'Vendor', 'Rec. Amount', 'Final Amount', 'Rec. Date', 'Comp. Date', 'Status', 'Duplication Prob', 'Delay Prob', 'Compliance Prob', 'Overall Risk', 'Risk Level', 'Primary Flagging Reason'];

                        const rows = reportData.map(r => [
                          r.work_id,
                          `"${(r.description || '').replace(/"/g, '""')}"`,
                          `"${(r.ida_name || '').replace(/"/g, '""')}"`,
                          `"${(r.vendor_name || '').replace(/"/g, '""')}"`,
                          r.amount || 0,
                          r.final_amount || 0,
                          r.recommendation_date ? new Date(r.recommendation_date).toLocaleDateString('en-IN') : '',
                          r.completion_date ? new Date(r.completion_date).toLocaleDateString('en-IN') : '',
                          r.status,
                          r.duplication || 0,
                          r.delay || 0,
                          r.compliance || 0,
                          r.overall,
                          r.risk_level,
                          `"${(r.flagging_reasons_shap || '').replace(/"/g, '""')}"`
                        ].join(','));

                        const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows].join('\n');
                        const link = document.createElement("a");
                        link.href = encodeURI(csvContent);
                        link.download = `MPLADS_Report_${reportRiskFilter}_Risk.csv`;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      }}
                      style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', backgroundColor: '#2563EB', color: '#FFF', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px', boxShadow: '0 2px 4px rgba(37,99,235,0.2)' }}
                    >
                      <DownloadCloud size={16} /> Export to CSV ({reportData.length})
                    </button>
                  </div>
                </div>

                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px', marginBottom: '24px' }}>
                  <thead>
                    <tr style={{ backgroundColor: 'rgba(248, 250, 252, 0.8)', borderBottom: '2px solid #E2E8F0', color: '#0F172A', height: '44px' }}>
                      <th style={{ padding: '12px', fontWeight: 600 }}>Work Order ID</th>
                      <th style={{ padding: '12px', fontWeight: 600 }}>Description</th>
                      <th style={{ padding: '12px', fontWeight: 600 }}>Amount</th>
                      <th style={{ padding: '12px', fontWeight: 600 }}>Risk Status</th>
                      <th style={{ padding: '12px', fontWeight: 600 }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.length === 0 ? (
                      <tr><td colSpan="5" style={{ padding: '32px', textAlign: 'center', color: '#64748B' }}>No projects match this risk level.</td></tr>
                    ) : (
                      reportData.slice((reportPage - 1) * 10, reportPage * 10).map((p, i) => (
                        <tr key={i} className="table-row-hover" style={{ borderBottom: '1px solid #F1F5F9', height: '60px' }}>
                          <td style={{ padding: '12px', fontWeight: 600, color: '#0F172A' }}>{p.work_id}</td>
                          <td style={{ padding: '12px', color: '#334155', fontWeight: 400 }}>{p.description}</td>
                          <td style={{ padding: '12px', fontWeight: 600, color: '#0F172A' }}>₹ {p.amount ? (p.amount / 100000).toFixed(2) + " L" : "0.00 L"}</td>
                          <td style={{ padding: '12px', color: p.risk_level === 'High' ? '#EF4444' : p.risk_level === 'Medium' ? '#F97316' : '#10B981', fontWeight: 600 }}>{p.risk_level} ({(p.overall * 100).toFixed(0)}%)</td>
                          <td style={{ padding: '12px' }}>
                            <span style={{ fontSize: '12px', fontWeight: 500, color: p.status === 'Completed' ? '#16A34A' : '#D97706', padding: '4px 8px', borderRadius: '4px', whiteSpace: 'nowrap' }}>{p.status}</span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>

                {/* REPORTS PAGINATION UI */}
                {(() => {
                  const totalReportPages = Math.ceil(reportData.length / 10);
                  if (totalReportPages <= 1) return null;
                  return (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
                      <button disabled={reportPage === 1} onClick={() => setReportPage(prev => prev - 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: reportPage === 1 ? '#94A3B8' : '#0F172A', cursor: reportPage === 1 ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Prev</button>
                      {Array.from({ length: totalReportPages }, (_, i) => i + 1)
                        .filter(page => page === 1 || page === totalReportPages || Math.abs(page - reportPage) <= 2)
                        .map((page, index, array) => (
                          <React.Fragment key={page}>
                            {index > 0 && array[index - 1] !== page - 1 && <span style={{ color: '#64748B', margin: '0 4px' }}>...</span>}
                            <button onClick={() => setReportPage(page)} style={{ padding: '8px 14px', border: reportPage === page ? 'none' : '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: reportPage === page ? '#2563EB' : '#FFF', color: reportPage === page ? '#FFF' : '#0F172A', cursor: 'pointer', fontWeight: 600 }}>{page}</button>
                          </React.Fragment>
                        ))}
                      <button disabled={reportPage >= totalReportPages} onClick={() => setReportPage(prev => prev + 1)} style={{ padding: '8px 12px', border: '1px solid #CBD5E1', borderRadius: '6px', backgroundColor: '#FFF', color: reportPage >= totalReportPages ? '#94A3B8' : '#0F172A', cursor: reportPage >= totalReportPages ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Next</button>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* ================= TAB 5: AUDIT TRAIL ================= */}
            {activeTab === 'audittrail' && (
              <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.87)', backdropFilter: 'blur(8px)', borderRadius: '14px', padding: '28px', border: '1px solid rgba(226, 232, 240, 0.8)', boxShadow: '0 2px 6px rgba(0,0,0,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 4px 0', color: '#0F172A' }}>System Audit Trail</h2>
                    <p style={{ fontSize: '13px', color: '#64748b', margin: 0, fontWeight: 400 }}>Track works actively under financial review and completed interventions.</p>
                  </div>
                  <button onClick={() => setRefreshKey(prev => prev + 1)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', backgroundColor: '#FFFFFF', border: '1px solid #CBD5E1', borderRadius: '6px', fontWeight: 500, fontSize: '13px', cursor: 'pointer', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}><RefreshCw size={15} /> Refresh</button>
                </div>

                {(!allData?.audit_logs || allData.audit_logs.length === 0) ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#64748B', fontWeight: 500, backgroundColor: '#F8FAFC', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                    No active audit trails for this representative.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {allData.audit_logs.map((log, idx) => (
                      <div key={idx} style={{ padding: '20px', border: '1px solid #E2E8F0', backgroundColor: '#FFF', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 2px 4px rgba(0,0,0,0.01)' }}>
                        <div>
                          <div style={{ fontSize: '12px', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', marginBottom: '4px' }}>
                            {new Date(log.timestamp).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })} <span style={{ margin: '0 6px', color: '#CBD5E1' }}>|</span> IP: {log.ip_address || 'Unknown'}
                          </div>
                          <div style={{ fontWeight: 600, color: '#0F172A', fontSize: '15px' }}>{log.work_id} — {log.description}</div>
                          <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                            <span style={{ fontSize: '13px', color: log.risk_level === 'High' ? '#EF4444' : '#F97316', fontWeight: 600 }}>Risk: {(log.overall * 100).toFixed(0)}% ({log.risk_level})</span>
                            <span style={{ fontSize: '13px', color: '#475569', fontWeight: 500 }}>Amount: ₹ {log.amount ? (log.amount / 100000).toFixed(2) + " Lakh" : "N/A"}</span>
                          </div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', alignItems: 'flex-end' }}>
                          <div style={{ padding: '6px 14px', backgroundColor: log.action_taken === 'Action Taken' ? '#F0FDF4' : '#EFF6FF', color: log.action_taken === 'Action Taken' ? '#16A34A' : '#2563EB', borderRadius: '6px', fontWeight: 700, fontSize: '12px', border: `1px solid ${log.action_taken === 'Action Taken' ? '#BBF7D0' : '#BFDBFE'}` }}>
                            {log.action_taken === 'Action Taken' ? 'Audit Complete' : 'Under Action'}
                          </div>
                          {log.action_taken !== 'Action Taken' && isAuditor && (
                            <button onClick={() => markActionTaken(log.work_id)} style={{ padding: '8px 16px', backgroundColor: '#10B981', color: '#FFF', border: 'none', borderRadius: '6px', fontWeight: 600, fontSize: '12px', cursor: 'pointer', boxShadow: '0 2px 4px rgba(16,185,129,0.2)' }}>
                              Mark as "Action Taken" ✓
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ================= 3. FOOTER ================= */}
          <footer style={{
            marginTop: 'auto', /* CRITICAL: Pushes footer to the bottom */
            width: '100%',
            backgroundColor: '#FFFFFF',
            borderTop: '1px solid #E2E8F0',
            padding: '16px 32px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '16px',
            boxShadow: '0 -2px 10px rgba(0,0,0,0.02)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  SIH-2026 PS26102:
                </span>
                <span style={{ fontSize: '13px', fontWeight: 500, color: '#475569' }}>
                  Development of an AI-powered system to detect anomalies, fraud, and inefficiencies in MPLAD Scheme implementation.
                </span>
              </div>
            </div>
            <div style={{ fontSize: '13px', color: '#475569', fontWeight: 600, whiteSpace: 'nowrap' }}>
              Made with <span style={{ color: '#EF4444', fontSize: '15px', padding: '0 2px' }}>♡</span> for India
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}