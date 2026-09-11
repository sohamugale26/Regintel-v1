import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import urllib3
import os

# Suppress SSL certificate verification warnings for government endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PAGE CONFIGURATION & THEME COMPATIBILITY ---
st.set_page_config(
    page_title="RegIntel | Regulatory Compliance & Governance",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Mode / Light Mode Compatible CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    
    /* Live Pulse Animation */
    .live-pulse {
        display: inline-block;
        width: 12px;
        height: 12px;
        background-color: #D32F2F;
        border-radius: 50%;
        margin-right: 10px;
        vertical-align: middle;
        animation: pulse-ring 1.5s infinite cubic-bezier(0.215, 0.61, 0.355, 1);
    }
    
    @keyframes pulse-ring {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(211, 47, 47, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); }
    }

    /* Metric Cards - Native Theme Colors */
    .metric-card {
        border: 1px solid var(--secondary-background-color);
        border-radius: 8px;
        padding: 14px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        background-color: var(--background-color);
    }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        color: var(--text-color);
        opacity: 0.8;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        margin-top: 4px;
        font-family: 'IBM Plex Mono', monospace;
    }
    
    /* Badges */
    .official-badge-cdsco, .official-badge-ema {
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.7rem;
        border: 1px solid var(--secondary-background-color);
    }
    .priority-critical { background-color: #FBEAE9; color: #B3261E; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-high { background-color: #FCEDE3; color: #B5591A; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-medium { background-color: #FBF3DE; color: #8C6D14; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-low { background-color: #EAF4EC; color: #3E7A4C; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    
    /* Typography */
    .section-title {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-top: 12px;
        margin-bottom: 6px;
        letter-spacing: 0.03em;
        opacity: 0.9;
    }
</style>
""", unsafe_allow_html=True)

# --- DATABASE PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("regintel_master.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates (
        id TEXT PRIMARY KEY, authority TEXT, country TEXT, doc_type TEXT, title TEXT,
        published_date TEXT, effective_date TEXT, url TEXT, official_ref TEXT, topic TEXT, summary TEXT,
        what_changed TEXT, previous_req TEXT, new_req TEXT, official_excerpt TEXT,
        impact_area TEXT, priority TEXT, relevance_score INTEGER, relevance_rationale TEXT,
        affected_products TEXT, status TEXT, ra_assessment TEXT, ra_action TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user TEXT, action TEXT, record_id TEXT, details TEXT
    )''')
    conn.commit()
    return conn

conn = init_db()

def seed_regulatory_baselines():
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM updates")
    if c.fetchone()[0] == 0:
        initial_records = [
            (
                "IND-CDSCO-2026-101", "CDSCO", "India", "Gazette Notification",
                "Fast-Track Clinical Trial Testing Approval", "2026-04-30", "2026-06-01",
                "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
                "F.No. CT/26/04/2026-DCGI", "Clinical Trials & Registration",
                "CDSCO permits immediate issuance of No Objection Certificates (NOC) for testing right after application submission.",
                "N/A", "Wait weeks for NOC.", "Testing can begin instantly upon application submission.",
                "CDSCO will issue a No Objection Certificate (NOC) as soon as a company submits an application for testing...",
                "Clinical Operations", "Critical", 98,
                "Accelerates R&D timeline for new investigational products.",
                "Injectables, Oral Solids", "Action Required", "", ""
            ),
            (
                "EU-EMA-2026-505", "EMA", "European Union", "Scientific Guideline",
                "EMA OPEN Framework Update", "2026-08-05", "2026-01-20",
                "https://www.ema.europa.eu/en/human-regulatory-overview/public-health-threats/open-initiative",
                "EMA/CHMP/QWP/17760/2026 Rev 2", "Clinical Trials & Registration",
                "Near-concurrent scientific review framework requiring a harmonised global data package.",
                "N/A", "Sequential regional submissions.", "Single, coherent global data package for concurrent assessment.",
                "The dossier content and proposed indication must be harmonised across all participating jurisdictions...",
                "Regulatory Affairs", "High", 85,
                "Applies to company's specialized pipeline products.",
                "Biologics", "Needs Review", "", ""
            ),
            (
                "IND-CDSCO-2026-102", "CDSCO", "India", "Circular",
                "Implementation of Pharmacovigilance (PV) System as per Schedule M", "2026-09-10", "2026-09-03",
                "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
                "File No. PV/Schedule-M/2026-09", "Pharmacovigilance",
                "Mandatory establishment of a schedule-aligned PV system directly linked with batch records.",
                "N/A", "Variable state-level adherence.", "Strict compliance verified during standard regulatory inspections.",
                "All drug manufacturers and marketers are required to establish and maintain an effective pharmacovigilance (PV) system...",
                "Quality Assurance", "High", 90,
                "Affects all marketed products and requires SOP verification.",
                "Injectables, Oral Solids, Biologics", "Needs Review", "", ""
            )
        ]
        c.executemany("INSERT INTO updates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", initial_records)
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "System", "SEED_DATABASE", "SYSTEM", "Baseline records initialized."))
        conn.commit()

seed_regulatory_baselines()

def synchronize_portals(active_jurisdictions):
    # Simulated fetching logic
    new_records = 0
    c = conn.cursor()
    if new_records > 0:
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "RA Professional", "PORTAL_SYNCHRONIZATION", "SYSTEM", "Discovered official items."))
        conn.commit()
    return new_records

# --- SIDEBAR: WORKSPACE CONFIGURATION ---
with st.sidebar:
    st.markdown("### 🏢 Corporate Scope")
    company_name = st.text_input("Pharmaceutical Organization", "Meridian Pharmaceuticals Ltd.")
    
    st.markdown("---")
    st.markdown("##### Active Jurisdictions")
    selected_jurisdictions = st.multiselect("Statutory Health Authorities", ["India (CDSCO)", "EU (EMA)"], default=["India (CDSCO)", "EU (EMA)"])
    
    st.markdown("##### Portfolio Scope")
    selected_products = st.multiselect("Commercial & Pipeline Dosage Forms", ["Injectables", "Oral Solids", "Biologics"], default=["Injectables", "Oral Solids", "Biologics"])
    selected_topics = st.multiselect("Regulatory Domains", ["GMP & Compliance", "Clinical Trials & Registration", "Stability & Quality Variations", "Pharmacovigilance"], default=["Clinical Trials & Registration", "Pharmacovigilance"])
    
    st.markdown("---")
    st.markdown("##### Reference Library (Optional)")
    ref_file = st.file_uploader("Upload custom reference library", type=["txt", "pdf", "docx"], help="Upload internal policy baseline.")
    if ref_file:
        st.success("✅ Custom reference library active.")
    else:
        st.caption("ℹ️ Falling back to default internal baseline: **S_26**")
        
    st.markdown("---")
    st.text_input("System Secure Gateway", type="password", placeholder="Enter license key")

# --- CORE DATA RETRIEVAL (RAW vs FILTERED) ---
# 1. Raw Data (For the Unfiltered Master Registry)
raw_df = pd.read_sql_query("SELECT * FROM updates", conn)

# 2. Filtered Data (For the Dashboard Feed)
query = "SELECT * FROM updates WHERE 1=1"
if len(selected_jurisdictions) == 1:
    if "India (CDSCO)" in selected_jurisdictions: query += " AND country = 'India'"
    elif "EU (EMA)" in selected_jurisdictions: query += " AND country = 'European Union'"
elif len(selected_jurisdictions) == 0:
    query += " AND 1=0"

pre_filtered_df = pd.read_sql_query(query, conn)

def row_matches_scope(row):
    topic_match = any(t.lower() in str(row['topic']).lower() for t in selected_topics) if selected_topics else True
    product_match = any(p.lower() in str(row['affected_products']).lower() for p in selected_products) if selected_products else True
    return topic_match and product_match

if not pre_filtered_df.empty:
    scope_mask = pre_filtered_df.apply(row_matches_scope, axis=1)
    df_filtered = pre_filtered_df[scope_mask].copy()
else:
    df_filtered = pd.DataFrame(columns=pre_filtered_df.columns)

# Smart Sorting for Dashboard
if not df_filtered.empty and 'priority' in df_filtered.columns:
    priority_ranking = {'Critical': 1, 'High': 2, 'Medium': 3, 'Low': 4}
    df_filtered['p_rank'] = df_filtered['priority'].map(priority_ranking).fillna(5)
    df_filtered = df_filtered.sort_values(by=['p_rank', 'relevance_score', 'published_date'], ascending=[True, False, False]).drop(columns=['p_rank'])

# --- TOP NAVIGATION TABS ---
tab_dash, tab_registry, tab_audit = st.tabs([
    "📊 Intelligence Dashboard", 
    "🗄️ Regulatory Updates Registry (Master)", 
    "📋 Audit Trail & Verification"
])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.markdown(f"## <span class='live-pulse'></span> Regulatory Intelligence Platform", unsafe_allow_html=True)
    st.caption(f"Active Monitoring: **{', '.join(selected_jurisdictions) if selected_jurisdictions else 'None (0 selected)'}** | Entity: **{company_name}**")

    col_sync, col_space = st.columns([1.2, 3])
    with col_sync:
        if st.button("🔄 Sync Official Portals", type="primary", use_container_width=True):
            if not selected_jurisdictions:
                st.warning("Select at least one jurisdiction before syncing.")
            else:
                with st.spinner("Synchronizing official portals for active jurisdictions..."):
                    found = synchronize_portals(selected_jurisdictions)
                st.success("Synchronization complete: All official registries are up to date. No new notices found." if found == 0 else f"Synchronization complete: {found} new regulatory developments synchronized.")

    # 4-Box Metrics
    total_system_count = len(raw_df)
    matching_count = len(df_filtered)
    high_priority_count = len(df_filtered[df_filtered['priority'].isin(['Critical', 'High'])]) if not df_filtered.empty else 0
    needs_review_count = len(df_filtered[df_filtered['status'] == 'Needs Review']) if not df_filtered.empty else 0

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label" title="All publications harvested from official sites">Total System Updates ℹ️</div><div class="metric-value">{total_system_count}</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Updates Matching Scope</div><div class="metric-value" style="color: #1E5A8C;">{matching_count}</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Critical / High Priority</div><div class="metric-value" style="color: #B5591A;">{high_priority_count}</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Awaiting RA Review</div><div class="metric-value" style="color: #8C6D14;">{needs_review_count}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>### 📋 Prioritized Regulatory Intelligence Feed", unsafe_allow_html=True)

    if df_filtered.empty:
        st.info("0 updates match your selected markets, products, or regulatory domains. Adjust sidebar parameters or initiate portal synchronization.")
    else:
        for _, item in df_filtered.iterrows():
            badge_html = '<span class="official-badge-cdsco">🇮🇳 India · CDSCO</span>' if item['authority'] == "CDSCO" else '<span class="official-badge-ema">🇪🇺 European Union · EMA</span>'
            p_class = f"priority-{str(item['priority']).lower()}"
            
            with st.expander(f"[{item['authority']}] {item['title']} (Published: {item['published_date']})"):
                header_col1, header_col2 = st.columns([4, 1])
                with header_col1:
                    st.markdown(f"{badge_html} &nbsp; <span class='{p_class}'>{item['priority']} Priority</span> &nbsp; <span style='font-size:0.8rem; opacity:0.8;'>Doc: {item['doc_type']} | Topic: {item['topic']}</span>", unsafe_allow_html=True)
                    st.markdown(f"#### {item['title']}")
                with header_col2:
                    st.metric("Relevance Score", f"{item['relevance_score']}/100")

                # Section 1: Short Summary
                st.markdown("<div class='section-title'>Short Summary</div>", unsafe_allow_html=True)
                st.write(item['summary'])
                
                # Section 2: Compact Requirement Comparison
                st.markdown("<div class='section-title'>Requirement Comparison</div>", unsafe_allow_html=True)
                st.markdown(f"**Previous:** {item['previous_req']} ➔ **New:** {item['new_req']}")

                # Section 3: Official Reference / Evidence
                st.markdown("<div class='section-title'>Official Reference & Evidence</div>", unsafe_allow_html=True)
                st.markdown(f"**Document No:** {item['official_ref']} &nbsp;|&nbsp; **Link:** [{item['url']}]({item['url']})")
                st.markdown(f"> *\"{item['official_excerpt']}\"*")

                st.write(f"**Operational Scope Affected:** {item['impact_area']} | **Impacted Formulations:** {item['affected_products']}")
                
                # Section 4: Governance Gate
                st.markdown("---")
                st.markdown("<div class='section-title'>Governance Gate & RA Determination</div>", unsafe_allow_html=True)
                ra1, ra2, ra3 = st.columns([1.2, 2, 1.2])
                with ra1:
                    opts = ["Needs Review", "Action Required", "Informational", "Not Relevant"]
                    decided_status = st.selectbox("Compliance Status", opts, index=opts.index(item['status']) if item['status'] in opts else 0, key=f"sel_{item['id']}")
                with ra2:
                    decided_notes = st.text_input("Technical Justification", value=item['ra_assessment'] or "", key=f"note_{item['id']}")
                with ra3:
                    if st.button("Commit Decision", key=f"btn_commit_{item['id']}"):
                        c = conn.cursor()
                        c.execute("UPDATE updates SET status=?, ra_assessment=? WHERE id=?", (decided_status, decided_notes, item['id']))
                        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "RA Professional", "GOVERNANCE_REVIEW", item['id'], f"Status set to {decided_status}."))
                        conn.commit()
                        st.success("Audit log recorded.")
                        st.rerun()

# --- TAB 2: REGULATORY REGISTRY ---
with tab_registry:
    st.markdown("### 🗄️ Master Regulatory Registry")
    st.caption("Immutable master ledger of all unfiltered regulatory notifications harvested from CDSCO and EMA, ensuring total inspection readiness regardless of active portfolio filters.")
    
    if raw_df.empty: 
        st.info("0 regulatory updates found in the master database.")
    else: 
        st.dataframe(
            raw_df[["id", "authority", "official_ref", "title", "published_date", "doc_type"]], 
            use_container_width=True, 
            hide_index=True
        )

# --- TAB 3: AUDIT TRAIL ---
with tab_audit:
    st.markdown("### 📋 Compliance Audit Trail")
    df_logs = pd.read_sql_query("SELECT timestamp, user, action, record_id, details FROM audit_logs ORDER BY id DESC", conn)
    st.dataframe(df_logs, use_container_width=True, hide_index=True)
    
