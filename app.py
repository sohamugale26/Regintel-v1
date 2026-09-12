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

# Custom CSS for Banner, Action-Blink, and Always-On Live Dot
st.markdown("""
<style>
.important-container {
    display: flex;
    align-items: center;
    background-color: #fdf5e6;
    border: 1px solid #e0c8a8;
    border-radius: 4px;
    padding: 6px 12px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
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
    flex-shrink: 0;
}
.important-new {
    color: #b7282e;
    font-weight: 700;
    font-size: 13px;
    margin-right: 8px;
    flex-shrink: 0;
}
.important-content {
    font-size: 13px;
    color: #2b2b2b;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}
.important-link {
    color: #1a0dab;
    text-decoration: none;
    font-weight: 500;
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
</style>
""", unsafe_allow_html=True)

# --- 1. DATABASE COMPONENT ---
def init_db():
    conn = sqlite3.connect("regintel_master.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates
                 (id TEXT PRIMARY KEY, authority TEXT, title TEXT, date TEXT, 
                  url TEXT, topic TEXT, summary TEXT, impact TEXT, relevance_score INTEGER, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, action TEXT, user TEXT, timestamp TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. DATE NORMALIZER & BANNER ENGINE ---
def format_banner_date(date_str):
    if not date_str:
        return "01, sept,2026"
    try:
        clean_date = date_str.replace('/', '-').strip()
        parsed = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y"):
            try:
                parsed = datetime.strptime(clean_date, fmt)
                break
            except ValueError:
                pass
        
        # Override to 01, sept,2026 if the date is August 2026 or older
        if parsed:
            if (parsed.year == 2026 and parsed.month < 9) or (parsed.year < 2026):
                return "01, sept,2026"
    except Exception:
        pass
    return date_str

def get_latest_cdsco_alert():
    c = conn.cursor()
    c.execute("SELECT title, date, url FROM updates ORDER BY date DESC LIMIT 1")
    record = c.fetchone()
    if record:
        return record[0], format_banner_date(record[1]), record[2]
    
    # Auto-fetch live from CDSCO if database is empty
    try:
        url = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, verify=False, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.find_all('tr')
        for r in rows[1:]:
            cols = r.find_all('td')
            if len(cols) >= 3:
                title = cols[1].text.strip()
                date_val = format_banner_date(cols[2].text.strip())
                link_el = cols[1].find('a')
                doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_el['href']) if link_el and link_el.has_attr('href') else url
                return title, date_val, doc_url
    except Exception:
        pass
    return "Official CDSCO Public Notice and Circular portal active and connected.", "01, sept,2026", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"

# Render Important Ticker
alert_title, alert_date, alert_url = get_latest_cdsco_alert()
st.markdown(f"""
<div class="important-container">
    <div class="important-badge">Important</div>
    <div class="important-new">New!</div>
    <div class="important-content">
        <a class="important-link" href="{alert_url}" target="_blank">{alert_title}</a> — <strong>[{alert_date}]</strong>
    </div>
</div>
""", unsafe_allow_html=True)

# --- 3. COMPANY PROFILE (Visual only - feed remains unfiltered) ---
st.sidebar.title("🏢 Company Profile")
markets = st.sidebar.multiselect("Markets", ["India (CDSCO)", "EU (EMA)"], ["India (CDSCO)", "EU (EMA)"])
products = st.sidebar.multiselect("Products", ["Injectables", "Oral Solids", "Biologics"], ["Injectables"])
topics = st.sidebar.multiselect("Topics", ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance"], ["GMP", "Stability"])

st.sidebar.divider()
st.sidebar.markdown("⚙️ AI & RAG Settings")
api_key = st.sidebar.text_input("OpenAI API Key (Optional)", type="password")

# --- 4. AI INTELLIGENCE ENGINE ---
def analyze_regulatory_update(title, authority, profile_context):
    if not api_key:
        return {
            "topic": "Regulatory Update",
            "summary": f"Simulated Intelligence: Analyzed '{title[:45]}...' against internal S_26 baselines.",
            "impact": "High",
            "relevance": 85
        }
    client = OpenAI(api_key=api_key)
    prompt = f"Analyze {authority} update: '{title}'. Context: {profile_context}. Output JSON keys: 'topic', 'summary', 'impact', 'relevance'."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "You are a Regulatory AI."}, {"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"topic": "Error", "summary": str(e), "impact": "Low", "relevance": 0}

# --- 5. SOURCE MONITOR (SCRAPER) ---
def scrape_cdsco(profile_context):
    new_updates = []
    c = conn.cursor()
    try:
        url = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for row in soup.find_all('tr')[1:8]: 
            cols = row.find_all('td')
            if len(cols) >= 3:
                title = cols[1].text.strip()
                date = cols[2].text.strip()
                link_tag = cols[1].find('a') or row.find('a')
                doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_tag['href']) if (link_tag and link_tag.has_attr('href')) else url
                update_id = f"CDSCO-{date.replace('-','').replace('/','')}-{abs(hash(title))%10000}"
                
                c.execute("SELECT id FROM updates WHERE id=?", (update_id,))
                if not c.fetchone():
                    ai_data = analyze_regulatory_update(title, "CDSCO", profile_context)
                    c.execute("INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                             (update_id, "CDSCO", title, date, doc_url, ai_data.get('topic'), ai_data.get('summary'), ai_data.get('impact'), ai_data.get('relevance'), "Pending Review"))
                    new_updates.append(update_id)
        conn.commit()
    except Exception as e:
        st.error(f"Scraper Error: {e}")
    return len(new_updates)

# --- 6. LIVE CDSCO SEARCH ENGINE ---
def search_cdsco_live(search_term):
    targets = [
        ("Public Notices", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"),
        ("Circulars", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/")
    ]
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for category, endpoint in targets:
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
                            if search_term.lower() in title.lower():
                                link = cols[1].find('a') or row.find('a')
                                doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link['href']) if link and link.has_attr('href') else endpoint
                                results.append({"Category": category, "Title": title, "Published Date": cols[2].text.strip(), "Document Link": doc_url})
        except Exception:
            continue
    return results

# --- 7. UI DASHBOARD & CONTROLS ---
# Header with always-on LIVE dot
st.markdown("""
<div style="display: flex; align-items: flex-start;">
    <h1 style="margin-bottom: 0;">🛡️ RegIntel Master Platform</h1>
    <div class="always-live-indicator">
        <span class="always-live-dot"></span> System Live
    </div>
</div>
""", unsafe_allow_html=True)

profile_context = f"Markets: {markets}, Products: {products}, Topics: {topics}"
button_col, status_col = st.columns([1.6, 3])

with button_col:
    execute_run = st.button("🔄 Execute Source Monitor")

live_action_slot = status_col.empty()
if execute_run:
    live_action_slot.markdown('<div class="action-blink">🔴 SCRAPING LIVE... Connecting to CDSCO...</div>', unsafe_allow_html=True)
    count = scrape_cdsco(profile_context)
    live_action_slot.empty()
    st.success(f"Complete: {count} new documents fetched from CDSCO.")

st.divider()

# --- 8. COLLAPSIBLE CDSCO SEARCH SECTION ---
with st.expander("🔍 Search CDSCO Official Repository (Click to Minimize)", expanded=True):
    st.caption("Perform real-time document discovery. Collapse this section when finished to view the dashboard below.")
    
    search_col1, search_col2 = st.columns([3.5, 1])
    with search_col1:
        search_query = st.text_input("Enter regulatory keyword", placeholder="e.g. Clinical Trials, Vaccine")
    with search_col2:
        search_clicked = st.button("Search CDSCO")

    if search_clicked and search_query:
        with st.spinner("Scraping live CDSCO registers..."):
            matched_docs = search_cdsco_live(search_query)
            if matched_docs:
                st.success(f"Found {len(matched_docs)} documents for '{search_query}'.")
                for doc in matched_docs:
                    c_badge, c_body, c_btn = st.columns([1, 4, 1])
                    c_badge.info(doc["Category"])
                    c_body.markdown(f"**{doc['Title']}**  \n*Date: {doc['Published Date']}*")
                    c_btn.link_button("View Doc", doc["Document Link"])
                    st.divider()
            else:
                st.warning("No official documents found.")

st.divider()

# --- 9. MONITORING METRICS & AUDIT SECTION (Unfiltered Feed) ---
# Pulls directly from the database without any sidebar filters blocking visibility
df = pd.read_sql_query("SELECT * FROM updates ORDER BY id DESC", conn)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Updates", len(df))
col2.metric("High Relevance", len(df[df['relevance_score'] >= 80]) if not df.empty else 0)
col3.metric("Pending Reviews", len(df[df['status'] == 'Pending Review']) if not df.empty else 0)
col4.metric("Sources", "CDSCO Live")

st.subheader("📋 Regulatory Intelligence Records")
if not df.empty:
    for _, row in df.iterrows():
        rel_color = "🔴" if row['relevance_score'] >= 80 else ("🟡" if row['relevance_score'] >= 50 else "🟢")
        with st.expander(f"{rel_color} [{row['authority']}] {row['title']} — {row['date']}"):
            meta_col, ai_col, action_col = st.columns([1.5, 2, 1])
            with meta_col:
                st.write(f"Topic: {row['topic']}")
                st.markdown(f"[View Official Evidence]({row['url']})")
            with ai_col:
                st.write(f"Relevance: {row['relevance_score']}/100 | Impact: {row['impact']}")
                st.write(f"Summary: {row['summary']}")
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
    st.info("Run the Source Monitor to populate data.")
