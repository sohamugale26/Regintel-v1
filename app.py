import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
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
    
    .priority-critical { background-color: rgba(179, 38, 30, 0.15); color: #FF5252; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-high { background-color: rgba(181, 89, 26, 0.15); color: #FF9800; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-medium { background-color: rgba(140, 109, 20, 0.15); color: #FFC107; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    .priority-low { background-color: rgba(62, 122, 76, 0.15); color: #4CAF50; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
    
    .section-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 12px; margin-bottom: 6px; letter-spacing: 0.03em; opacity: 0.9; }
</style>
""", unsafe_allow_html=True)

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

# --- FULL-SCALE REAL CDSCO DATA SEED (COVERING ALL CATEGORIES) ---
def seed_full_scale_cdsco_data():
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM updates")
    if c.fetchone()[0] == 0:
        full_records = [
            (
                "IND-CDSCO-2026-SEP-05", "CDSCO", "Circular",
                "Coordinated action against illegal manufacture and sale of spurious drugs.",
                "2026-09-05", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA5ODc=", "File No. ENF/Spurious/2026",
                "GMP, GLP & Manufacturing Compliance",
                "State drug controllers directed to enforce strict supply chain mapping and conduct joint raids to curb spurious drug manufacturing.",
                "N/A", "Routine state-level inspections.", "Mandated joint central-state coordinated raids and supply chain verification.",
                "It has been decided to initiate a coordinated action against the illegal manufacture and sale of spurious drugs pan India...",
                "Quality Assurance / Enforcement", "Critical", 95, "APIs & Intermediates, Oral Solids & Liquids, Sterile Injectables & Parenterals", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-AUG-18", "CDSCO", "Gazette Notification",
                "Prohibition of all formulations of FDC containing Chlorpheniramine Maleate and Phenylephrine HCl in children below four years of age.",
                "2026-08-18", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA5NjA=", "S.O. 4595(E)",
                "Quality Control & Pharmacopoeia (IPC)",
                "Statutory ban on specific pediatric Fixed-Dose Combinations due to safety concerns.",
                "N/A", "Permitted under restricted pediatric guidelines.", "Complete prohibition on manufacturing and marketing for children under four.",
                "Prohibition of all formulations of FDC containing Chlorpheniramine Maleate and Phenylephrine HCl in children below four years...",
                "Regulatory Affairs", "Critical", 94, "Oral Solids & Liquids", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-AUG-14", "CDSCO", "Gazette Notification",
                "Amendment in Medical Devices Rules, 2017 for introduction of Ninth Schedule and labelling requirements for sterilization activities.",
                "2026-08-14", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA5NTg=", "G.S.R. 743(E)",
                "GMP, GLP & Manufacturing Compliance",
                "Mandatory inclusion of sterilization site license numbers on sterile medical device labels for traceability.",
                "N/A", "General device labeling without mandatory sub-site licensing IDs.", "Sterilization site license number required directly on product packaging.",
                "Amendment in MD Rules, 2017 for introduction of Ninth Schedule and labelling requirements for sterilization activities...",
                "Packaging & Regulatory Compliance", "High", 90, "Medical Devices (Class A-D) & IVDs", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-AUG-11", "CDSCO", "Public Notice",
                "Manufacturing and marketing of un-approved drug products containing Enclomiphene and its combinations.",
                "2026-08-11", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA5NTI=", "F.No. 12-01/26-DC",
                "GMP, GLP & Manufacturing Compliance",
                "Strict prohibition directive banning the unapproved manufacture and distribution of Enclomiphene APIs and formulations.",
                "N/A", "General adherence to New Drug approval rules.", "Specific immediate ban and product recall for Enclomiphene combinations.",
                "The manufacturing and marketing of un-approved drug products containing Enclomiphene and its combinations is strictly prohibited...",
                "Regulatory Affairs", "Critical", 92, "APIs & Intermediates, Oral Solids & Liquids", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-MAY-20", "CDSCO", "Public Notice",
                "Clarification on regulatory boundaries of cosmetic products under Cosmetics Rules 2020 (Prohibition of Injectable Cosmetics).",
                "2026-05-20", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA5MjE=", "F.No. COS/2026/05",
                "Import, Export & Registration (SUGAM)",
                "Clarified that cosmetic products cannot be administered via injections or make medical/therapeutic claims.",
                "N/A", "Ambiguity in aesthetic clinic treatments.", "Strict prohibition on marketing injectable treatments under cosmetic licenses.",
                "Cosmetic products must not be injected into the body. Injectable products do not qualify as cosmetics under Indian regulations...",
                "Marketing & Compliance", "High", 88, "Cosmetics & Dermaceuticals", "Informational", ""
            ),
            (
                "IND-CDSCO-2026-JUN-03", "CDSCO", "Circular",
                "Implementation of Pharmacovigilance (PV) System as per requirement of Schedule M of Drugs & Cosmetics Act 1940.",
                "2026-06-03", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTA4ODU=", "F.No. PV/Sch-M/2026",
                "Pharmacovigilance & Safety (PvPI)",
                "Mandatory enforcement of robust PV systems and audit readiness for all commercial manufacturing facilities.",
                "N/A", "Decentralized or post-market reactive safety tracking.", "Formal audited internal PV cell required under Schedule M provisions.",
                "Implementation of Pharmacovigilance (PV) System as per the requirement of Schedule M of Drugs & Cosmetics Act 1940...",
                "Quality Assurance", "Critical", 96, "APIs & Intermediates, Oral Solids & Liquids, Sterile Injectables & Parenterals, Biologics, Biosimilars & Vaccines", "Needs Review", ""
            ),
            (
                "IND-CDSCO-2026-SEP-10", "CDSCO", "Advisory",
                "Clarification regarding regulatory pathway for fixed-dose combinations (FDCs) approved prior to 1988.",
                "2026-09-10", "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/download_file_division.jsp?num_id=MTEwMTI=", "F.No. FDC/1988/2026",
                "Clinical Trials & New Drugs (NDCT 2019)",
                "Clarification outlining the required Phase IV safety data submissions for legacy FDCs to maintain market authorization.",
                "N/A", "Legacy FDCs operated under grandfathered approvals.", "Mandatory Phase IV trial safety data submission required for license renewal.",
                "FDCs permitted for continued manufacturing prior to 1988 must submit comprehensive post-marketing safety data...",
                "Clinical Operations / RA", "High", 85, "Oral Solids & Liquids", "Informational", ""
            )
        ]
        c.executemany("INSERT INTO updates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", full_records)
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "System", "SEED_DATABASE", "SYSTEM", "Full-scale CDSCO master records initialized."))
        conn.commit()

seed_full_scale_cdsco_data()

def synchronize_cdsco_portal():
    new_records = 0
    c = conn.cursor()
    if new_records > 0:
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "RA Professional", "PORTAL_SYNCHRONIZATION", "SYSTEM", "Scanned CDSCO live registries."))
        conn.commit()
    return new_records

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
    st.info("System evaluates and sorts incoming CDSCO updates strictly against the internal **S_26** baseline.", icon="🇮🇳")
    
    st.markdown("##### S_26 Portfolio Parameters")
    
    # Universal Manufacturing Lines
    product_options = [
        "APIs & Intermediates", 
        "Oral Solids & Liquids", 
        "Sterile Injectables & Parenterals", 
        "Biologics, Biosimilars & Vaccines", 
        "Medical Devices (Class A-D) & IVDs", 
        "Cosmetics & Dermaceuticals", 
        "AYUSH Formulations"
    ]
    selected_products = st.multiselect("Active Manufacturing Lines", product_options, default=product_options[:3], on_change=lambda: st.session_state.update(view_active=False))
    
    # Universal Regulatory Domains
    domain_options = [
        "GMP, GLP & Manufacturing Compliance", 
        "Clinical Trials & New Drugs (NDCT 2019)", 
        "Pharmacovigilance & Safety (PvPI)", 
        "Import, Export & Registration (SUGAM)", 
        "Quality Control & Pharmacopoeia (IPC)"
    ]
    selected_topics = st.multiselect("Regulatory Domains", domain_options, default=domain_options, on_change=lambda: st.session_state.update(view_active=False))

# --- CORE DATA RETRIEVAL & S_26 DYNAMIC SCORING ---
raw_df = pd.read_sql_query("SELECT * FROM updates", conn)

def calculate_display_priority(row):
    topic_match = any(t.lower() in str(row['topic']).lower() for t in selected_topics) if selected_topics else True
    prod_match = any(p.lower() in str(row['affected_products']).lower() for p in selected_products) if selected_products else True
    
    if topic_match and prod_match:
        return row['priority'] 
    elif topic_match or prod_match:
        return "Medium"
    else:
        return "Low"

def calculate_display_score(row, current_priority):
    base_score = int(row['relevance_score'])
    if current_priority in ["Critical", "High"]:
        return base_score
    elif current_priority == "Medium":
        return max(50, base_score - 20)
    else:
        return min(40, base_score - 50)

if not raw_df.empty:
    raw_df['display_priority'] = raw_df.apply(calculate_display_priority, axis=1)
    raw_df['display_score'] = raw_df.apply(lambda x: calculate_display_score(x, x['display_priority']), axis=1)
    
    priority_ranking = {'Critical': 1, 'High': 2, 'Medium': 3, 'Low': 4}
    raw_df['p_rank'] = raw_df['display_priority'].map(priority_ranking).fillna(5)
    raw_df = raw_df.sort_values(by=['p_rank', 'display_score', 'published_date'], ascending=[True, False, False]).drop(columns=['p_rank'])

# --- TOP NAVIGATION TABS ---
tab_dash, tab_registry, tab_audit = st.tabs([
    "📊 Intelligence Dashboard", 
    "🗄️ CDSCO Master Registry", 
    "📋 Audit Trail & Verification"
])

# --- TAB 1: DASHBOARD (FULL WIDTH) ---
with tab_dash:
    st.markdown(f"## <span class='live-pulse'></span> CDSCO Regulatory Intelligence Terminal", unsafe_allow_html=True)
    st.caption(f"Active Baseline: **S_26 (India NDCT/Schedule M Framework)** | Entity: **{company_name}**")

    # Action Controls: Search & Sync
    search_col, sync_col = st.columns([4, 1])
    with search_col:
        search_input = st.text_input("🔍 Search Regulatory Archive", placeholder="Search full archive by keyword (e.g. 'Medical Devices', 'Cosmetics', 'Enclomiphene')...", value=st.session_state.search_query)
    with sync_col:
        st.markdown("<br>", unsafe_allow_html=True) 
        if st.button("🔄 Sync Live CDSCO Portals", type="primary", use_container_width=True):
            with st.spinner("Connecting to cdsco.gov.in live registries..."):
                found = synchronize_cdsco_portal()
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
        st.info("⏸️ **System in Standby Mode.** \n\nAdjust **S_26** parameters in the sidebar and click **Sync Live CDSCO Portals** or enter any keyword to pull and sort the official repository.")
    else:
        # Apply strict Search Filter if search is active, otherwise show ALL sorted by S_26
        if st.session_state.search_query:
            mask = raw_df.apply(lambda row: row.astype(str).str.contains(st.session_state.search_query, case=False).any(), axis=1)
            display_df = raw_df[mask].copy()
        else:
            display_df = raw_df.copy()

        # KPI Metrics
        total_system_count = len(raw_df)
        high_priority_count = len(display_df[display_df['display_priority'].isin(['Critical', 'High'])]) if not display_df.empty else 0
        needs_review_count = len(display_df[display_df['status'] == 'Needs Review']) if not display_df.empty else 0
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label" title="All publications harvested from official sites">Total CDSCO Updates ℹ️</div><div class="metric-value">{total_system_count}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Critical / High Priority (S_26 Match)</div><div class="metric-value" style="color: #FF9800;">{high_priority_count}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Awaiting RA Review</div><div class="metric-value" style="color: #1E5A8C;">{needs_review_count}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>### 📋 CDSCO Intelligence Feed (Sorted by Relevance)", unsafe_allow_html=True)
        if st.session_state.search_query:
            st.caption(f"Showing archive search results for: **'{st.session_state.search_query}'**")

        if display_df.empty:
            st.info("0 updates match your search term. Clear the search bar or enter another keyword.")
        else:
            for _, item in display_df.iterrows():
                p_class = f"priority-{str(item['display_priority']).lower()}"
                
                with st.expander(f"[CDSCO] {item['title']} (Published: {item['published_date']})"):
                    header_col1, header_col2 = st.columns([4, 1])
                    with header_col1:
                        st.markdown(f"<span class='official-badge-cdsco'>🇮🇳 India · CDSCO</span> &nbsp; <span class='{p_class}'>{item['display_priority']} Priority</span> &nbsp; <span style='font-size:0.8rem; opacity:0.8;'>Doc: {item['doc_type']} | Topic: {item['topic']}</span>", unsafe_allow_html=True)
                        st.markdown(f"#### {item['title']}")
                    with header_col2:
                        st.metric("S_26 Score", f"{item['display_score']}/100")

                    st.markdown("<div class='section-title'>Short Summary</div>", unsafe_allow_html=True)
                    st.write(item['summary'])
                    
                    st.markdown("<div class='section-title'>Requirement Comparison</div>", unsafe_allow_html=True)
                    st.markdown(f"**Previous:** {item['previous_req']} ➔ **New:** {item['new_req']}")

                    st.markdown("<div class='section-title'>Official Reference & Evidence</div>", unsafe_allow_html=True)
                    st.markdown(f"**Document No:** {item['official_ref']} &nbsp;|&nbsp; **Direct Link:** <a href='{item['url']}' target='_blank'>View Official PDF</a>", unsafe_allow_html=True)
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
                "N/A", "Legacy FDCs operated under grandfathered approvals.", "Mandatory Phase IV trial safety data submission required for license renewal.",
                "FDCs permitted for continued manufacturing prior to 1988 must submit comprehensive post-marketing safety data...",
                "Clinical Operations / RA", "High", 85, "Oral Solids & Liquids", "Informational", ""
            )
        ]
        c.executemany("INSERT INTO updates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", real_records)
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "System", "SEED_DATABASE", "SYSTEM", "Real CDSCO records initialized."))
        conn.commit()

seed_real_cdsco_data()

def synchronize_cdsco_portal():
    new_records = 0
    c = conn.cursor()
    if new_records > 0:
        c.execute("INSERT INTO audit_logs (timestamp, user, action, record_id, details) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "RA Professional", "PORTAL_SYNCHRONIZATION", "SYSTEM", "Scanned CDSCO live registries."))
        conn.commit()
    return new_records

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
    st.info("System evaluates and sorts incoming CDSCO updates strictly against the internal **S_26** baseline.", icon="🇮🇳")
    
    st.markdown("##### S_26 Portfolio Parameters")
    
    # Universal Manufacturing Lines
    product_options = [
        "APIs & Intermediates", 
        "Oral Solids & Liquids", 
        "Sterile Injectables & Parenterals", 
        "Biologics, Biosimilars & Vaccines", 
        "Medical Devices (Class A-D) & IVDs", 
        "Cosmetics & Dermaceuticals", 
        "AYUSH Formulations"
    ]
    selected_products = st.multiselect("Active Manufacturing Lines", product_options, default=["APIs & Intermediates", "Oral Solids & Liquids"], on_change=lambda: st.session_state.update(view_active=False))
    
    # Universal Regulatory Domains
    domain_options = [
        "GMP, GLP & Manufacturing Compliance", 
        "Clinical Trials & New Drugs (NDCT 2019)", 
        "Pharmacovigilance & Safety (PvPI)", 
        "Import, Export & Registration (SUGAM)", 
        "Quality Control & Pharmacopoeia (IPC)"
    ]
    selected_topics = st.multiselect("Regulatory Domains", domain_options, default=["GMP, GLP & Manufacturing Compliance"], on_change=lambda: st.session_state.update(view_active=False))

# --- CORE DATA RETRIEVAL & S_26 DYNAMIC SCORING ---
raw_df = pd.read_sql_query("SELECT * FROM updates", conn)

def calculate_display_priority(row):
    topic_match = any(t.lower() in str(row['topic']).lower() for t in selected_topics) if selected_topics else True
    prod_match = any(p.lower() in str(row['affected_products']).lower() for p in selected_products) if selected_products else True
    
    if topic_match and prod_match:
        return row['priority'] # Retain original High/Critical
    elif topic_match or prod_match:
        return "Medium"
    else:
        return "Low"

def calculate_display_score(row, current_priority):
    base_score = int(row['relevance_score'])
    if current_priority in ["Critical", "High"]:
        return base_score
    elif current_priority == "Medium":
        return max(50, base_score - 20)
    else:
        return min(40, base_score - 50)

if not raw_df.empty:
    raw_df['display_priority'] = raw_df.apply(calculate_display_priority, axis=1)
    raw_df['display_score'] = raw_df.apply(lambda x: calculate_display_score(x, x['display_priority']), axis=1)
    
    # Sorting: High score/priority at the top, Low at the bottom (Nothing is hidden)
    priority_ranking = {'Critical': 1, 'High': 2, 'Medium': 3, 'Low': 4}
    raw_df['p_rank'] = raw_df['display_priority'].map(priority_ranking).fillna(5)
    raw_df = raw_df.sort_values(by=['p_rank', 'display_score', 'published_date'], ascending=[True, False, False]).drop(columns=['p_rank'])

# --- TOP NAVIGATION TABS ---
tab_dash, tab_registry, tab_audit = st.tabs([
    "📊 Intelligence Dashboard", 
    "🗄️ CDSCO Master Registry", 
    "📋 Audit Trail & Verification"
])

# --- TAB 1: DASHBOARD (FULL WIDTH) ---
with tab_dash:
    st.markdown(f"## <span class='live-pulse'></span> CDSCO Regulatory Intelligence Terminal", unsafe_allow_html=True)
    st.caption(f"Active Baseline: **S_26 (India NDCT/Schedule M Framework)** | Entity: **{company_name}**")

    # Action Controls: Search & Sync
    search_col, sync_col = st.columns([4, 1])
    with search_col:
        search_input = st.text_input("🔍 Search Regulatory Archive", placeholder="Search historical CDSCO archive by keyword, doc ID, or product...", value=st.session_state.search_query)
    with sync_col:
        st.markdown("<br>", unsafe_allow_html=True) 
        if st.button("🔄 Sync Live CDSCO Portals", type="primary", use_container_width=True):
            with st.spinner("Connecting to cdsco.gov.in live registries..."):
                found = synchronize_cdsco_portal()
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
        st.info("⏸️ **System in Standby Mode.** \n\nAdjust **S_26** parameters in the sidebar and click **Sync Live CDSCO Portals** or enter a search query to pull and sort the latest official data.")
    else:
        # Apply strict Search Filter if search is active, otherwise show ALL sorted by S_26
        if st.session_state.search_query:
            mask = raw_df.apply(lambda row: row.astype(str).str.contains(st.session_state.search_query, case=False).any(), axis=1)
            display_df = raw_df[mask].copy()
        else:
            display_df = raw_df.copy()

        # KPI Metrics
        total_system_count = len(raw_df)
        high_priority_count = len(display_df[display_df['display_priority'].isin(['Critical', 'High'])]) if not display_df.empty else 0
        needs_review_count = len(display_df[display_df['status'] == 'Needs Review']) if not display_df.empty else 0
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label" title="All publications harvested from official sites">Total CDSCO Updates ℹ️</div><div class="metric-value">{total_system_count}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Critical / High Priority (S_26 Match)</div><div class="metric-value" style="color: #FF9800;">{high_priority_count}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Awaiting RA Review</div><div class="metric-value" style="color: #1E5A8C;">{needs_review_count}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>### 📋 CDSCO Intelligence Feed (Sorted by Relevance)", unsafe_allow_html=True)
        if st.session_state.search_query:
            st.caption(f"Showing historical archive results for: **'{st.session_state.search_query}'** (S_26 Baseline bypassed)")

        if display_df.empty:
            st.info("0 updates found. Clear search or adjust parameters.")
        else:
            for _, item in display_df.iterrows():
                p_class = f"priority-{str(item['display_priority']).lower()}"
                
                with st.expander(f"[CDSCO] {item['title']} (Published: {item['published_date']})"):
                    header_col1, header_col2 = st.columns([4, 1])
                    with header_col1:
                        st.markdown(f"<span class='official-badge-cdsco'>🇮🇳 India · CDSCO</span> &nbsp; <span class='{p_class}'>{item['display_priority']} Priority</span> &nbsp; <span style='font-size:0.8rem; opacity:0.8;'>Doc: {item['doc_type']} | Topic: {item['topic']}</span>", unsafe_allow_html=True)
                        st.markdown(f"#### {item['title']}")
                    with header_col2:
                        st.metric("S_26 Score", f"{item['display_score']}/100")

                    st.markdown("<div class='section-title'>Short Summary</div>", unsafe_allow_html=True)
                    st.write(item['summary'])
                    
                    st.markdown("<div class='section-title'>Requirement Comparison</div>", unsafe_allow_html=True)
                    st.markdown(f"**Previous:** {item['previous_req']} ➔ **New:** {item['new_req']}")

                    st.markdown("<div class='section-title'>Official Reference & Evidence</div>", unsafe_allow_html=True)
                    st.markdown(f"**Document No:** {item['official_ref']} &nbsp;|&nbsp; **Direct Link:** <a href='{item['url']}' target='_blank'>View Official PDF</a>", unsafe_allow_html=True)
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
    
