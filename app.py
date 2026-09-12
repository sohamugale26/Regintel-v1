import json
import sqlite3
import urllib.parse
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from openai import OpenAI

# Suppress SSL warnings for government websites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="RegIntel | Master Architecture", layout="wide", page_icon="🛡️")

# Initialize Session State for Execution Lock
if 'executed' not in st.session_state:
    st.session_state.executed = False

# Custom CSS for UI enhancements, Marquee Animation, and Live Indicators
st.markdown("""
<style>
.important-container {
    display: flex;
    align-items: center;
    background-color: #fdf5e6;
    border: 1px solid #e0c8a8;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    overflow: hidden;
    position: relative;
    white-space: nowrap;
}
.important-badge {
    background-color: #b7282e;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    padding: 3px 10px;
    border-radius: 3px;
    letter-spacing: 0.5px;
    margin-right: 12px;
    z-index: 2;
    position: relative;
    box-shadow: 2px 0 5px #fdf5e6;
}
.marquee-wrapper {
    display: inline-block;
    white-space: nowrap;
    animation: marquee 25s linear infinite;
    padding-left: 20px;
}
.marquee-wrapper:hover {
    animation-play-state: paused;
}
@keyframes marquee {
    0%   { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}
.important-new {
    color: #b7282e;
    font-weight: 700;
    font-size: 13px;
    margin-right: 6px;
}
.important-link {
    color: #1a0dab;
    text-decoration: none;
    font-weight: 600;
    margin-right: 20px;
}
.important-link:hover {
    text-decoration: underline;
}
@keyframes pulse {
    0% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(1.1); }
    100% { opacity: 1; transform: scale(1); }
}
.always-live-indicator {
    display: inline-flex;
    align-items: center;
    color: #d93025;
    font-weight: 700;
    font-size: 14px;
    margin-left: 15px;
    margin-top: 15px;
}
.always-live-dot {
    width: 10px;
    height: 10px;
    background-color: #d93025;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 1.5s infinite;
}
.action-blink {
    animation: pulse 0.5s infinite;
    color: #d93025;
    font-weight: bold;
}
.doc-badge {
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    color: #fff;
}
.badge-alert { background-color: #d93025; }
.badge-circular { background-color: #f29900; }
.badge-notice { background-color: #188038; }
</style>
""", unsafe_allow_html=True)

# --- 1. DATABASE COMPONENT (Upgraded with doc_type) ---
# Using a new database file to avoid schema mismatch errors with previous runs
def init_db():
    conn = sqlite3.connect("regintel_master_v2.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates
                 (id TEXT PRIMARY KEY, doc_type TEXT, title TEXT, date TEXT, 
                  url TEXT, topic TEXT, summary TEXT, impact TEXT, relevance_score INTEGER, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, action TEXT, user TEXT, timestamp TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. DATE NORMALIZER & MARQUEE ENGINE ---
def parse_db_date(date_str):
    if not date_str:
        return datetime(2000, 1, 1)
    clean_date = date_str.replace('/', '-').strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            pass
    return datetime(2000, 1, 1)

def get_current_month_updates():
    """Fetches updates strictly from the current calendar month for the Marquee."""
    c = conn.cursor()
    c.execute("SELECT doc_type, title, date, url FROM updates ORDER BY date DESC LIMIT 20")
    records = c.fetchall()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    valid_updates = []
    for rec in records:
        parsed = parse_db_date(rec[2])
        if parsed.month == current_month and parsed.year == current_year:
            valid_updates.append(rec)
            
    return valid_updates

# Render Scrolling Important Ticker (Strict Current Month Filter)
current_month_alerts = get_current_month_updates()
marquee_html = ""

if current_month_alerts:
    for doc_type, title, date_str, url in current_month_alerts:
        emoji = "🔴" if doc_type == "Safety Alert" else ("🟡" if doc_type == "Circular" else "🟢")
        marquee_html += f"""
        <span class="important-new">New!</span>
        <a class="important-link" href="{url}" target="_blank">{emoji} {doc_type}: {title} [{date_str}]</a>
        """
else:
    marquee_html = f"<span class='important-content'>No new circulars, alerts, or notices published by CDSCO in {datetime.now().strftime('%B %Y')}.</span>"

st.markdown(f"""
<div class="important-container">
    <div class="important-badge">Important</div>
    <div class="marquee-wrapper">
        {marquee_html}
    </div>
</div>
""", unsafe_allow_html=True)

# --- 3. COMPANY PROFILE (Sidebar) ---
st.sidebar.title("🏢 Company Profile")
markets = st.sidebar.multiselect("Markets", ["India (CDSCO)", "EU (EMA)"], ["India (CDSCO)", "EU (EMA)"])
products = st.sidebar.multiselect("Products", ["Injectables", "Oral Solids", "Biologics"], ["Injectables"])
topics = st.sidebar.multiselect("Topics", ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance"], ["GMP", "Stability"])

st.sidebar.divider()
st.sidebar.markdown("⚙️ AI & RAG Settings")
api_key = st.sidebar.text_input("OpenAI API Key (Optional)", type="password")

# --- 4. AI INTELLIGENCE ENGINE (S_26 Baseline) ---
def analyze_regulatory_update(title, authority, profile_context, selected_topics):
    if not api_key:
        lower_title = title.lower()
        detected_topic = "General Regulatory"
        
        if any(k in lower_title for k in ["trial", "ethics", "clinical", "subject"]):
            detected_topic = "Clinical Trials"
        elif any(k in lower_title for k in ["manufacturing", "gmp", "quality", "standard"]):
            detected_topic = "GMP"
        elif any(k in lower_title for k in ["stability", "shelf"]):
            detected_topic = "Stability"
        elif any(k in lower_title for k in ["pharmacovigilance", "adverse", "safety", "spurious", "alert"]):
            detected_topic = "Pharmacovigilance"

        is_match = detected_topic in selected_topics if selected_topics else True
        score = 95 if is_match else 20
        impact = "High" if is_match else "Low"

        return {
            "topic": detected_topic,
            "summary": f"S_26 Baseline: Auto-tagged as '{detected_topic}' based on keyword analysis.",
            "impact": impact,
            "relevance": score
        }

    client = OpenAI(api_key=api_key)
    prompt = f"Analyze CDSCO update: '{title}'. Context: {profile_context}. Output JSON keys: 'topic', 'summary', 'impact', 'relevance'."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "You are a Regulatory AI."}, {"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"topic": "Error", "summary": str(e), "impact": "Low", "relevance": 0}

# --- 5. 3-WAY MULTI-ENDPOINT SOURCE MONITOR ---
def scrape_cdsco_all(profile_context, selected_topics):
    endpoints = [
        ("Public Notice", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"),
        ("Circular", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/"),
        ("Safety Alert", "https://cdsco.gov.in/opencms/opencms/en/Alerts/")
    ]
    
    new_updates = 0
    c = conn.cursor()
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for doc_type, url in endpoints:
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Scrape top 7 entries from each category to maintain balance
            for row in soup.find_all('tr')[1:8]: 
                cols = row.find_all('td')
                if len(cols) >= 3:
                    title = cols[1].text.strip()
                    date = cols[2].text.strip()
                    link_tag = cols[1].find('a') or row.find('a')
                    doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_tag['href']) if (link_tag and link_tag.has_attr('href')) else url
                    update_id = f"CDSCO-{doc_type[:3]}-{date.replace('-','').replace('/','')}-{abs(hash(title))%10000}"
                    
                    c.execute("SELECT id FROM updates WHERE id=?", (update_id,))
                    if not c.fetchone():
                        ai_data = analyze_regulatory_update(title, "CDSCO", profile_context, selected_topics)
                        c.execute("INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                                 (update_id, doc_type, title, date, doc_url, ai_data.get('topic'), ai_data.get('summary'), ai_data.get('impact'), ai_data.get('relevance'), "Pending Review"))
                        new_updates += 1
            conn.commit()
        except Exception as e:
            continue
    return new_updates

# --- 6. 3-WAY HISTORICAL SEARCH ENGINE ---
def search_cdsco_live_all(search_term, year_filter):
    endpoints = [
        ("Public Notice", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"),
        ("Circular", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/"),
        ("Safety Alert", "https://cdsco.gov.in/opencms/opencms/en/Alerts/")
    ]
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for doc_type, endpoint in endpoints:
        try:
            res = requests.get(endpoint, headers=headers, verify=False, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                table = soup.find('table')
                if table:
                    for row in table.find_all('tr')[1:]:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            title = cols[1].text.strip()
                            date_str = cols[2].text.strip()
                            
                            if year_filter != "All" and year_filter not in date_str:
                                continue
                                
                            if search_term.lower() in title.lower():
                                link = cols[1].find('a') or row.find('a')
                                doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link['href']) if link and link.has_attr('href') else endpoint
                                results.append({"Type": doc_type, "Title": title, "Date": date_str, "Link": doc_url})
        except Exception:
            continue
    return results

# --- 7. HEADER DASHBOARD & REAL-TIME CLOCK ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown("""
    <div style="display: flex; align-items: flex-start;">
        <h1 style="margin-bottom: 0;">🛡️ RegIntel Master Platform</h1>
        <div class="always-live-indicator">
            <span class="always-live-dot"></span> System Live
        </div>
    </div>
    """, unsafe_allow_html=True)
with header_col2:
    st.markdown(f"<div style='text-align: right; margin-top: 25px; color: #5f6368; font-weight: 500;'>Session Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)

profile_context = f"Markets: {markets}, Products: {products}, Topics: {topics}"
button_col, status_col = st.columns([1.6, 3])

with button_col:
    execute_run = st.button("🔄 Execute Source Monitor")

live_action_slot = status_col.empty()
if execute_run:
    st.session_state.executed = True
    live_action_slot.markdown('<div class="action-blink">🔴 SCRAPING LIVE... Checking Public Notices, Circulars & Alerts...</div>', unsafe_allow_html=True)
    count = scrape_cdsco_all(profile_context, topics)
    live_action_slot.empty()
    st.success(f"Radar Complete: {count} new regulatory documents fetched across 3 CDSCO registers.")

st.divider()

# --- 8. COLLAPSIBLE 3-WAY HISTORICAL SEARCH ---
with st.expander("🔍 Search CDSCO Official Repository (Click to Minimize)", expanded=True):
    st.caption("Deep-dive historical search across Public Notices, Circulars, and Alerts. Filter by year to exclude outdated noise.")
    
    search_col1, search_col2, search_col3 = st.columns([3, 1, 1])
    with search_col1:
        search_query = st.text_input("Enter regulatory keyword", placeholder="e.g. Clinical Trials, Vaccine, Ethics")
    with search_col2:
        search_year = st.selectbox("Select Year", ["All", "2026", "2025", "2024", "2023", "2022", "2021"])
    with search_col3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        search_clicked = st.button("Search CDSCO")

    if search_clicked and search_query:
        with st.spinner(f"Scraping live CDSCO registers for {search_year}..."):
            matched_docs = search_cdsco_live_all(search_query, search_year)
            if matched_docs:
                st.success(f"Found {len(matched_docs)} direct documents for '{search_query}' in {search_year}.")
                for doc in matched_docs:
                    c_badge, c_body, c_btn = st.columns([1, 4, 1])
                    c_badge.info(doc["Type"])
                    c_body.markdown(f"**{doc['Title']}**  \n*Published Date: {doc['Date']}*")
                    c_btn.link_button("View Doc", doc["Link"])
                    st.divider()
            else:
                st.warning(f"No official documents found for '{search_query}' matching year {search_year}.")

st.divider()

# --- 9. STRICT INTELLIGENCE FEED ---
if not st.session_state.executed:
    st.info("🕒 Awaiting Execution. Press 'Execute Source Monitor' above to scan for today's active updates.")
else:
    if not markets and not products and not topics:
        st.warning("Please select your target Markets, Products, or Topics from the sidebar to view relevant intelligence.")
    else:
        # Corner Timeframe Shield
        head_col1, head_col2 = st.columns([4, 1])
        with head_col1:
            st.subheader("📋 Regulatory Intelligence Radar")
        with head_col2:
            time_filter = st.selectbox("Timeline", ["Past 24 Hours", "Past 7 Days", "Past 30 Days"], index=1, label_visibility="collapsed")
        
        days_allowed = 1 if time_filter == "Past 24 Hours" else (7 if time_filter == "Past 7 Days" else 30)
        df = pd.read_sql_query("SELECT * FROM updates ORDER BY id DESC", conn)
        
        if not df.empty:
            if topics:
                df = df[df['topic'].isin(topics) | (df['relevance_score'] >= 80)]
                
            # Date Shield logic against old pinned records
            df['parsed_date'] = df['date'].apply(parse_db_date)
            df['days_old'] = (datetime.now() - df['parsed_date']).dt.days
            display_df = df[df['days_old'] <= days_allowed]
            
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric(f"Updates ({time_filter})", len(display_df))
            m_col2.metric("High Relevance", len(display_df[display_df['relevance_score'] >= 80]) if not display_df.empty else 0)
            m_col3.metric("Pending Reviews", len(display_df[display_df['status'] == 'Pending Review']) if not display_df.empty else 0)
            m_col4.metric("Sources", "CDSCO (3 Registers)")

            if display_df.empty:
                st.success(f"Shield Active: No active regulatory updates match your profile within the {time_filter}. Older pinned documents have been successfully blocked.")
            else:
                for _, row in display_df.iterrows():
                    rel_color = "🔴" if row['relevance_score'] >= 80 else ("🟡" if row['relevance_score'] >= 50 else "🟢")
                    
                    # Clean UI tags
                    badge_class = "badge-alert" if row['doc_type'] == "Safety Alert" else ("badge-circular" if row['doc_type'] == "Circular" else "badge-notice")
                    
                    with st.expander(f"{rel_color} [CDSCO] {row['title']} — {row['date']}"):
                        meta_col, ai_col, action_col = st.columns([1.5, 2, 1])
                        
                        with meta_col:
                            st.markdown(f"<span class='doc-badge {badge_class}'>Type: {row['doc_type']}</span>", unsafe_allow_html=True)
                            st.write("")
                            st.write(f"**Topic:** {row['topic']}")
                            st.markdown(f"[View Official Document]({row['url']})")
                            
                        with ai_col:
                            st.write(f"**Relevance:** {row['relevance_score']}/100 | **Impact:** {row['impact']}")
                            st.write(f"**AI Summary:** {row['summary']}")
                            
                        with action_col:
                            options = ["Pending Review", "Action Required", "Informational", "Not Relevant"]
                            current_idx = options.index(row['status']) if row['status'] in options else 0
                            new_status = st.selectbox("Decision", options, index=current_idx, key=row['id'])
                            if new_status != row['status']:
                                c = conn.cursor()
                                c.execute("UPDATE updates SET status=? WHERE id=?", (new_status, row['id']))
                                c.execute("INSERT INTO audit_logs (update_id, action, user, timestamp) VALUES (?, ?, ?, ?)", 
                                          (row['id'], new_status, "RA Professional", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                conn.commit()
                                st.rerun()
        else:
            st.info("The intelligence database is empty.")
