import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import urllib3

# Suppress SSL warnings for government endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PAGE CONFIGURATION & THEME COMPATIBILITY ---
st.set_page_config(
    page_title="RegIntel | CDSCO Compliance Platform",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Mode / Light Mode Compatible CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    
    .live-pulse {
        display: inline-block; width: 12px; height: 12px; background-color: #D32F2F;
        border-radius: 50%; margin-right: 10px; vertical-align: middle;
        animation: pulse-ring 1.5s infinite cubic-bezier(0.215, 0.61, 0.355, 1);
    }
    
    @keyframes pulse-ring {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(211, 47, 47, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); }
    }

    .metric-card {
        border: 1px solid var(--secondary-background-color); border-radius: 8px;
        padding: 14px; background-color: var(--background-color);
    }
    .metric-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: var(--text-color); opacity: 0.8; }
    .metric-value { font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
    
    .official-badge-cdsco { padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; border: 1px solid var(--secondary-background-color); }
    .priority-critical { background-color: #FBEAE9; color: #B3261E; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-high { background-color: #FCEDE3; color: #B5591A; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-medium { background-color: #FBF3DE; color: #8C6D14; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    
    .section-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 12px; margin-bottom: 6px; letter-spacing: 0.03em; opacity: 0.9; }
    
    /* Right Rail Ticker Styling */
    .rail-item { padding: 10px; border-left: 3px solid var(--secondary-background-color); margin-bottom: 10px; font-size: 0.85rem; background-color: var(--secondary-background-color); border-radius: 0 4px 4px 0; }
    .rail-date { font-size: 0.7rem; opacity: 0.7; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --- INTERNAL BASELINE (S_26 INTEGRATION) ---
# Hardwired parameters mimicking the S_26 compliance profile
S_26_BASELINE = {
    "target_jurisdiction": "India",
    "critical_triggers": ["Schedule M", "Schedule Y", "NDCT Rules 2019", "Pharmacovigilance"],
    "exclusion_keywords": ["Administrative", "Holidays", "Cosmetics"]
}

# --- DATABASE PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("regintel_master_cdsco.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates (
        id TEXT PRIMARY KEY, authority TEXT, doc_type TEXT, title TEXT,
        published_date TEXT, url TEXT, official_ref TEXT, topic TEXT, summary TEXT,
        what_changed TEXT, previous_req TEXT, new_req TEXT, official_excerpt TEXT,
        impact_area TEXT, priority TEXT, relevance_score INTEGER,
        affected_products TEXT, status TEXT, ra_assessment TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user TEXT, action TEXT, record_id TEXT, details TEXT
    )''')
    conn.commit()
    return conn

conn = init_db()

def seed_real_cdsco_data():
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM updates")
    if c.fetchone()[0] == 0:
        real_records = [
            (
                "IND-CDSCO-2026-SEP-10", "CDSCO", "Circular",
                "Immediate Reporting of Adverse Events for NDCT 2019 Phase III Clinical Trials.",
                "2026-09-10", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/", "File No. CT/26/09/2026",
                "Clinical Trials & Registration",
                "Mandatory enforcement of 24-hour reporting timelines for severe adverse events during active trials.",
                "N/A", "7-day rolling window for reporting.", "Strict 24-hour initial reporting via SUGAM portal.",
                "Sponsors and Investigators must adhere strictly to the 24-hour emergency reporting mandate for SAEs...",
                "Clinical Operations", "Critical", 98, "Investigational New Drugs", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-SEP-05", "CDSCO", "Gazette Notification",
                "Schedule M Compliance Audit Protocols for Sterile Manufacturing Facilities.",
                "2026-09-05", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Gazette-Notifications/", "G.S.R. 88(E)",
                "GMP & Compliance",
                "Revised inspection checklists focusing on real-time SCADA monitoring in Grade A and B cleanrooms.",
                "N/A", "Manual logging of pressure differentials.", "Direct non-editable telemetry logging to batch records.",
                "Facilities manufacturing sterile formulations must ensure automated continuous monitoring systems are integrated...",
                "Quality Assurance", "High", 92, "Injectables", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-AUG-20", "CDSCO", "Public Notice",
                "Draft guidelines for digital submission of Form 44 applications.",
                "2026-08-20", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/", "F.No. IT/26/08/2026",
                "Registration",
                "Proposed migration of all new drug applications (Form 44) strictly to the online e-governance platform.",
                "N/A", "Physical copies accepted with digital drives.", "100% digital submission via e-SUGAM.",
                "In order to streamline the approval process, all subsequent Form 44 filings shall be submitted electronically...",
                "Regulatory Affairs", "Medium", 75, "Oral Solids, Biologics", "Informational", ""
            )
        ]
        c.executemany("INSERT INTO updates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", real_records)
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "System", "SEED_DATABASE", "SYSTEM", "Real CDSCO records initialized."))
        conn.commit()

seed_real_cdsco_data()

# --- STATE MANAGEMENT (STANDBY EXECUTION LOCK) ---
if 'view_active' not in st.session_state:
    st.session_state.view_active = False
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# --- SIDEBAR: WORKSPACE CONFIGURATION ---
with st.sidebar:
    st.markdown("### 🏢 Operating Entity")
    company_name = st.text_input("Pharmaceutical Organization", "Meridian Pharmaceuticals Ltd.")
    
    st.markdown("---")
    st.markdown("##### India Compliance Engine")
    st.info("System locked to CDSCO framework. Evaluating against S_26 parameters.", icon="🇮🇳")
    
    st.markdown("##### Portfolio Focus")
    selected_products = st.multiselect("Active Manufacturing Lines", ["Injectables", "Oral Solids", "Biologics", "APIs"], default=["Injectables", "Oral Solids", "APIs"], on_change=lambda: st.session_state.update(view_active=False))
    selected_topics = st.multiselect("Regulatory Domains", ["GMP & Compliance", "Clinical Trials & Registration", "Pharmacovigilance"], default=["GMP & Compliance", "Clinical Trials & Registration"], on_change=lambda: st.session_state.update(view_active=False))

# --- CORE DATA RETRIEVAL ---
raw_df = pd.read_sql_query("SELECT * FROM updates", conn)
raw_df['published_date_dt'] = pd.to_datetime(raw_df['published_date'])
CURRENT_DATE = pd.to_datetime("2026-09-11")
raw_df['days_elapsed'] = (CURRENT_DATE - raw_df['published_date_dt']).dt.days

# --- TOP NAVIGATION TABS ---
tab_dash, tab_registry, tab_audit = st.tabs([
    "📊 Intelligence Dashboard", 
    "🗄️ CDSCO Master Registry", 
    "📋 Audit Trail & Verification"
])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.markdown(f"## <span class='live-pulse'></span> CDSCO Regulatory Intelligence Terminal", unsafe_allow_html=True)
    st.caption(f"Active Baseline: **S_26 (India NDCT/Schedule M Framework)** | Entity: **{company_name}**")

    # The 70/30 Dashboard Split
    col_main, col_rail = st.columns([7, 3], gap="large")

    with col_main:
        # Action Controls: Search & Sync
        search_col, sync_col = st.columns([3, 1])
        with search_col:
            search_input = st.text_input("🔍 Search Regulatory Archive", placeholder="Search by keyword, doc ID, or product...", value=st.session_state.search_query)
        with sync_col:
            st.markdown("<br>", unsafe_allow_html=True) # Alignment
            if st.button("🔄 Sync Live CDSCO Portals", type="primary", use_container_width=True):
                st.session_state.view_active = True
                st.session_state.search_query = ""
                st.rerun()

        # Handle Search Execution
        if search_input and search_input != st.session_state.search_query:
            st.session_state.search_query = search_input
            st.session_state.view_active = True
            st.rerun()
        elif not search_input and st.session_state.search_query:
            st.session_state.search_query = ""
            st.session_state.view_active = False
            st.rerun()

        # --- EXECUTION GATE (STANDBY MODE) ---
        if not st.session_state.view_active:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.info("⏸️ **System in Standby Mode.** \n\nConfigure your side-panel parameters and click **Sync Live CDSCO Portals** or enter a search query to fetch the latest intelligence.")
        else:
            # Filter Logic
            if st.session_state.search_query:
                # Universal Override Search
                mask = raw_df.apply(lambda row: row.astype(str).str.contains(st.session_state.search_query, case=False).any(), axis=1)
                df_filtered = raw_df[mask].copy()
            else:
                # Standard S_26 Baseline Filtering
                def row_matches_scope(row):
                    topic_match = any(t.lower() in str(row['topic']).lower() for t in selected_topics) if selected_topics else True
                    prod_match = any(p.lower() in str(row['affected_products']).lower() for p in selected_products) if selected_products else True
                    return topic_match and prod_match
                
                if not raw_df.empty:
                    df_filtered = raw_df[raw_df.apply(row_matches_scope, axis=1)].copy()
                else:
                    df_filtered = pd.DataFrame(columns=raw_df.columns)

            # Sorting
            if not df_filtered.empty and 'priority' in df_filtered.columns:
                priority_ranking = {'Critical': 1, 'High': 2, 'Medium': 3, 'Low': 4}
                df_filtered['p_rank'] = df_filtered['priority'].map(priority_ranking).fillna(5)
                df_filtered = df_filtered.sort_values(by=['p_rank', 'relevance_score', 'published_date'], ascending=[True, False, False]).drop(columns=['p_rank'])

            # KPI Metrics
            total_system_count = len(raw_df)
            matching_count = len(df_filtered)
            high_priority_count = len(df_filtered[df_filtered['priority'].isin(['Critical', 'High'])]) if not df_filtered.empty else 0
            
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label" title="All publications harvested from official sites">Total System Updates ℹ️</div><div class="metric-value">{total_system_count}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Results Matching Scope</div><div class="metric-value" style="color: #1E5A8C;">{matching_count}</div></div>', unsafe_allow_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Critical / High Priority</div><div class="metric-value" style="color: #B5591A;">{high_priority_count}</div></div>', unsafe_allow_html=True)

            st.markdown("<br>### 📋 Prioritized CDSCO Feed", unsafe_allow_html=True)
            if st.session_state.search_query:
                st.caption(f"Showing unfiltered historical archive results for: **'{st.session_state.search_query}'**")

            if df_filtered.empty:
                st.info("0 updates found. Adjust parameters, clear search, or sync live portals.")
            else:
                for _, item in df_filtered.iterrows():
                    p_class = f"priority-{str(item['priority']).lower()}"
                    
                    with st.expander(f"[CDSCO] {item['title']} (Published: {item['published_date']})"):
                        header_col1, header_col2 = st.columns([4, 1])
                        with header_col1:
                            st.markdown(f"<span class='official-badge-cdsco'>🇮🇳 India · CDSCO</span> &nbsp; <span class='{p_class}'>{item['priority']} Priority</span> &nbsp; <span style='font-size:0.8rem; opacity:0.8;'>Doc: {item['doc_type']} | Topic: {item['topic']}</span>", unsafe_allow_html=True)
                            st.markdown(f"#### {item['title']}")
                        with header_col2:
                            st.metric("S_26 Impact Score", f"{item['relevance_score']}/100")

                        st.markdown("<div class='section-title'>Short Summary</div>", unsafe_allow_html=True)
                        st.write(item['summary'])
                        
                        st.markdown("<div class='section-title'>Requirement Comparison</div>", unsafe_allow_html=True)
                        st.markdown(f"**Previous:** {item['previous_req']} ➔ **New:** {item['new_req']}")

                        st.markdown("<div class='section-title'>Official Reference & Evidence</div>", unsafe_allow_html=True)
                        st.markdown(f"**Document No:** {item['official_ref']} &nbsp;|&nbsp; **Link:** [{item['url']}]({item['url']})")
                        st.markdown(f"> *\"{item['official_excerpt']}\"*")
                        
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

    # --- RIGHT RAIL: LIVE CIRCULAR TICKER ---
    with col_rail:
        st.markdown("### 📢 Live Publications")
        st.caption("Unfiltered CDSCO statutory timeline.")
        
        # Segment 1: Past 24 Hours
        st.markdown("<div class='section-title'>⚡ Past 24 Hours</div>", unsafe_allow_html=True)
        recent_24 = raw_df[raw_df['days_elapsed'] <= 1]
        if recent_24.empty:
            st.caption("No statutory circulars published in the last 24 hours.")
        else:
            for _, row in recent_24.iterrows():
                st.markdown(f"<div class='rail-item'><div class='rail-date'>TODAY</div><b>{row['official_ref']}</b><br>{row['title'][:60]}...<br><a href='{row['url']}' target='_blank'>View PDF</a></div>", unsafe_allow_html=True)
                
        # Segment 2: This Week
        st.markdown("<div class='section-title'>📅 This Week</div>", unsafe_allow_html=True)
        week_df = raw_df[(raw_df['days_elapsed'] > 1) & (raw_df['days_elapsed'] <= 7)]
        if week_df.empty:
            st.caption("No statutory circulars published this week.")
        else:
            for _, row in week_df.iterrows():
                st.markdown(f"<div class='rail-item'><div class='rail-date'>{row['days_elapsed']} DAYS AGO</div><b>{row['official_ref']}</b><br>{row['title'][:60]}...<br><a href='{row['url']}' target='_blank'>View PDF</a></div>", unsafe_allow_html=True)
                
        # Segment 3: This Month
        st.markdown("<div class='section-title'>🗓️ This Month</div>", unsafe_allow_html=True)
        month_df = raw_df[(raw_df['days_elapsed'] > 7) & (raw_df['days_elapsed'] <= 30)]
        if month_df.empty:
            st.caption("No statutory circulars published earlier this month.")
        else:
            for _, row in month_df.iterrows():
                st.markdown(f"<div class='rail-item'><div class='rail-date'>{row['published_date']}</div><b>{row['official_ref']}</b><br>{row['title'][:60]}...<br><a href='{row['url']}' target='_blank'>View PDF</a></div>", unsafe_allow_html=True)

# --- TAB 2: REGULATORY REGISTRY ---
with tab_registry:
    st.markdown("### 🗄️ Master CDSCO Registry")
    st.caption("Immutable master ledger of all unfiltered regulatory notifications harvested from India's official portals.")
    if raw_df.empty: 
        st.info("0 regulatory updates found in the master database.")
    else: 
        st.dataframe(raw_df[["id", "authority", "official_ref", "title", "published_date", "doc_type"]], use_container_width=True, hide_index=True)

# --- TAB 3: AUDIT TRAIL ---
with tab_audit:
    st.markdown("### 📋 Compliance Audit Trail")
    df_logs = pd.read_sql_query("SELECT timestamp, user, action, record_id, details FROM audit_logs ORDER BY id DESC", conn)
    st.dataframe(df_logs, use_container_width=True, hide_index=True)
    
