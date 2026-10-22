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

st.set_page_config(page_title="RegIntel | CDSCO Live Monitor", layout="wide", page_icon="🛡️")

# Session state initialization
if 'executed' not in st.session_state:
    st.session_state.executed = False

# Robust HTTP headers mimicking modern Chrome on Windows
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Referer': 'https://cdsco.gov.in/'
}

# --- 1. DATABASE COMPONENT ---
def init_db():
    conn = sqlite3.connect("regintel_master_v3.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates
                 (id TEXT PRIMARY KEY, doc_type TEXT, title TEXT, date TEXT, 
                  url TEXT, topic TEXT, summary TEXT, impact TEXT, relevance_score INTEGER, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, action TEXT, user TEXT, timestamp TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. DATE NORMALIZER ---
def parse_db_date(date_str):
    if not date_str:
        return datetime(2000, 1, 1)
    clean_date = date_str.replace('/', '-').strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            pass
    return datetime(2000, 1, 1)

# --- 3. SIDEBAR CONFIGURATION ---
st.sidebar.title("🏢 Company Profile & Filters")
target_docs = st.sidebar.multiselect(
    "Document Categories", 
    ["Public Notices", "Circulars", "Safety Alerts", "Press Releases & Articles"],
    default=["Public Notices", "Circulars", "Safety Alerts"]
)
topics = st.sidebar.multiselect(
    "Topic Subscriptions", 
    ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance", "Medical Devices", "Cosmetics"],
    default=["GMP", "Clinical Trials", "Pharmacovigilance"]
)

st.sidebar.divider()
st.sidebar.markdown("⚙️ AI & LLM Engine")
api_key = st.sidebar.text_input("OpenAI API Key (Optional)", type="password")

# --- 4. REGULATORY ANALYSIS ENGINE ---
def analyze_regulatory_update(title, doc_type, selected_topics):
    if not api_key:
        lower = title.lower()
        detected_topic = "General Regulatory"
        
        if any(k in lower for k in ["trial", "ethics", "clinical", "subject", "investigator"]):
            detected_topic = "Clinical Trials"
        elif any(k in lower for k in ["manufacturing", "gmp", "quality", "standard", "schedule m"]):
            detected_topic = "GMP"
        elif any(k in lower for k in ["stability", "shelf", "storage"]):
            detected_topic = "Stability"
        elif any(k in lower for k in ["pharmacovigilance", "adverse", "safety", "spurious", "alert", "nsq"]):
            detected_topic = "Pharmacovigilance"
        elif any(k in lower for k in ["device", "ivd", "diagnostic"]):
            detected_topic = "Medical Devices"
        elif any(k in lower for k in ["cosmetic"]):
            detected_topic = "Cosmetics"

        is_match = detected_topic in selected_topics if selected_topics else True
        return {
            "topic": detected_topic,
            "summary": f"Categorized under '{detected_topic}' based on regulatory title heuristics.",
            "impact": "High" if (is_match or doc_type == "Safety Alert") else "Low",
            "relevance": 95 if is_match else 30
        }

    client = OpenAI(api_key=api_key)
    prompt = f"Analyze CDSCO {doc_type}: '{title}'. Topics of interest: {selected_topics}. Output JSON: 'topic', 'summary', 'impact', 'relevance'."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "You are a Pharma Regulatory Affairs AI."}, {"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"topic": "General Regulatory", "summary": str(e), "impact": "Low", "relevance": 20}

# --- 5. ROBUST CDSCO SCRAPER AGENT ---
CDSCO_REGISTERS = {
    "Public Notices": "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
    "Circulars": "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
    "Safety Alerts": "https://cdsco.gov.in/opencms/opencms/en/Alerts/",
    "Press Releases & Articles": "https://cdsco.gov.in/opencms/opencms/en/Latest-Public-Notices/"
}

def fetch_category_records(category_name, url):
    """Fetches and parses HTML tables across CDSCO sub-pages with robust exception handling."""
    records = []
    session = requests.Session()
    try:
        response = session.get(url, headers=BROWSER_HEADERS, verify=False, timeout=12)
        if response.status_code != 200:
            return records
            
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return records

        for row in tables[0].find_all('tr')[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 3:
                # Text cleanup
                title = cols[1].get_text(separator=" ", strip=True)
                date_val = cols[2].get_text(strip=True)
                
                # Link resolver (checks col 1, col 3, or whole row)
                link_tag = cols[1].find('a') or cols[-1].find('a') or row.find('a')
                if link_tag and link_tag.has_attr('href'):
                    doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_tag['href'])
                else:
                    doc_url = url
                
                if title:
                    records.append({
                        "category": category_name,
                        "title": title,
                        "date": date_val,
                        "url": doc_url
                    })
    except Exception:
        pass
    return records

def scrape_cdsco_agent(active_categories, selected_topics):
    new_count = 0
    c = conn.cursor()
    
    for category in active_categories:
        target_url = CDSCO_REGISTERS.get(category)
        if not target_url:
            continue
            
        entries = fetch_category_records(category, target_url)
        for item in entries[:15]:  # Process latest 15 records per category
            title = item["title"]
            date_str = item["date"]
            doc_url = item["url"]
            
            clean_date = date_str.replace('-', '').replace('/', '')
            update_id = f"CDSCO-{category[:3].upper()}-{clean_date}-{abs(hash(title)) % 100000}"
            
            c.execute("SELECT id FROM updates WHERE id=?", (update_id,))
            if not c.fetchone():
                ai = analyze_regulatory_update(title, category, selected_topics)
                c.execute(
                    "INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (update_id, category, title, date_str, doc_url, ai.get('topic'), ai.get('summary'), ai.get('impact'), ai.get('relevance'), "Pending Review")
                )
                new_count += 1
        conn.commit()
    return new_count

# --- 6. HISTORICAL REPOSITORY SEARCH ---
def search_cdsco_historical(query, selected_cats, year_filter):
    search_results = []
    for cat in selected_cats:
        url = CDSCO_REGISTERS.get(cat)
        if not url:
            continue
        entries = fetch_category_records(cat, url)
        for e in entries:
            if year_filter != "All" and year_filter not in e["date"]:
                continue
            if query.lower() in e["title"].lower():
                search_results.append(e)
    return search_results

# --- 7. UI PRESENTATION ---
st.title("🛡️ CDSCO Regulatory Intelligence Platform")

run_col, stat_col = st.columns([1.5, 3])
with run_col:
    start_sync = st.button("🔄 Execute CDSCO Scraper Agent")

status_placeholder = stat_col.empty()
if start_sync:
    st.session_state.executed = True
    status_placeholder.info("Scraping live CDSCO registers: Public Notices, Circulars, Alerts & Articles...")
    fetched = scrape_cdsco_agent(target_docs, topics)
    status_placeholder.success(f"Execution complete: {fetched} new regulatory notices indexed.")

# --- 8. SEARCH SECTION ---
with st.expander("🔍 Search Official CDSCO Archives (Circulars, Notices, Alerts)", expanded=False):
    s_col1, s_col2, s_col3 = st.columns([3, 1, 1])
    with s_col1:
        q = st.text_input("Enter regulatory keyword", placeholder="e.g. Schedule M, Bioavailability, Ethics")
    with s_col2:
        yr = st.selectbox("Year", ["All", "2026", "2025", "2024", "2023"])
    with s_col3:
        st.write("")
        st.write("")
        s_btn = st.button("Search Archive")
        
    if s_btn and q:
        matches = search_cdsco_historical(q, target_docs, yr)
        if matches:
            st.success(f"Found {len(matches)} matching documents:")
            for m in matches:
                c1, c2, c3 = st.columns([1, 4, 1])
                c1.info(m["category"])
                c2.markdown(f"**{m['title']}**  \n*Date:* {m['date']}")
                c3.link_button("View Document", m["url"])
                st.divider()
        else:
            st.warning("No official records matched your criteria.")

# --- 9. INTELLIGENCE RADAR FEED ---
st.divider()
st.subheader("📋 Regulatory Radar Feed")

df = pd.read_sql_query("SELECT * FROM updates ORDER BY date DESC", conn)

if not df.empty:
    if target_docs:
        df = df[df['doc_type'].isin(target_docs)]
    if topics:
        df = df[df['topic'].isin(topics) | (df['relevance_score'] >= 80)]
        
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Indexed Records", len(df))
    m2.metric("High Relevance (≥80)", len(df[df['relevance_score'] >= 80]))
    m3.metric("Pending Review", len(df[df['status'] == 'Pending Review']))
    m4.metric("Active Sources", f"{len(target_docs)} CDSCO Endpoints")

    for _, row in df.iterrows():
        tag_color = "🔴" if row['relevance_score'] >= 80 else ("🟡" if row['relevance_score'] >= 50 else "🟢")
        with st.expander(f"{tag_color} [{row['doc_type']}] {row['title']} ({row['date']})"):
            c_left, c_mid, c_right = st.columns([1.5, 2, 1])
            with c_left:
                st.write(f"**Category:** {row['doc_type']}")
                st.write(f"**Domain:** {row['topic']}")
                st.markdown(f"[Official Document Link]({row['url']})")
            with c_mid:
                st.write(f"**Relevance:** {row['relevance_score']}/100 | **Impact:** {row['impact']}")
                st.write(f"**Summary:** {row['summary']}")
            with c_right:
                opts = ["Pending Review", "Action Required", "Informational", "Not Relevant"]
                idx = opts.index(row['status']) if row['status'] in opts else 0
                new_st = st.selectbox("Action Status", opts, index=idx, key=row['id'])
                if new_st != row['status']:
                    c = conn.cursor()
                    c.execute("UPDATE updates SET status=? WHERE id=?", (new_st, row['id']))
                    c.execute("INSERT INTO audit_logs (update_id, action, user, timestamp) VALUES (?, ?, ?, ?)",
                              (row['id'], new_st, "Regulatory Analyst", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.rerun()
else:
    st.info("No updates stored yet. Click 'Execute CDSCO Scraper Agent' above to pull the latest notices.")
