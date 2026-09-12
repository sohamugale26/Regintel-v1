import json
import sqlite3
import urllib.parse
from datetime import datetime
import hashlib
import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from openai import OpenAI

# Suppress SSL warnings only when we explicitly fallback
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="RegIntel | Master Architecture", layout="wide", page_icon="🛡️")

Initialize Session State

if 'executed' not in st.session_state:
st.session_state.executed = False
if 'source_status' not in st.session_state:
st.session_state.source_status = {
"Public Notices": "⚪ Standby",
"Circulars": "⚪ Standby",
"Safety Alerts": "⚪ Standby"
}

--- 1. CSS INJECTION (Dark/Light Mode Compatible) ---

st.markdown("""

<style>  
.important-container {  
    display: flex; align-items: center; background-color: var(--secondary-background-color);  
    border: 1px solid var(--border-color, #e0c8a8); border-radius: 4px; padding: 8px 12px;  
    margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; position: relative; white-space: nowrap;  
}  
.important-badge {  
    background-color: #b7282e; color: #ffffff; font-weight: 700; font-size: 13px;  
    padding: 3px 10px; border-radius: 3px; margin-right: 12px; z-index: 2; position: relative;  
    box-shadow: 2px 0 5px var(--secondary-background-color);  
}  
.marquee-wrapper {  
    display: inline-block; white-space: nowrap; animation: marquee 25s linear infinite; padding-left: 20px;  
}  
.marquee-wrapper:hover { animation-play-state: paused; }  
@keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }  
.important-new { color: #b7282e; font-weight: 700; font-size: 13px; margin-right: 6px; }  
.important-link { color: var(--text-color); text-decoration: none; font-weight: 600; margin-right: 20px; }  
.important-link:hover { text-decoration: underline; color: var(--primary-color); }  
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }  
.always-live-indicator { display: inline-flex; align-items: center; color: #d93025; font-weight: 700; font-size: 14px; margin-left: 15px; margin-top: 15px; }  
.always-live-dot { width: 10px; height: 10px; background-color: #d93025; border-radius: 50%; margin-right: 6px; animation: pulse 1.5s infinite; }  
.ai-disclaimer { font-size: 12px; color: #888; font-style: italic; }  
</style>  """, unsafe_allow_html=True)

--- 2. DATABASE COMPONENT (V3 Architecture) ---

def init_db():
conn = sqlite3.connect("regintel_master_v3.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS updates
(id TEXT PRIMARY KEY, authority TEXT, doc_type TEXT, title TEXT,
published_date_original TEXT, published_date_normalized TEXT,
url TEXT, topic TEXT, summary TEXT, change_type TEXT, impact TEXT,
why_relevant TEXT, required_action TEXT, relevance_score INTEGER, status TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS audit_logs  
             (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, previous_status TEXT,  
              new_status TEXT, user TEXT, timestamp TEXT, comment TEXT)''')  
conn.commit()  
return conn

conn = init_db()

--- 3. UTILITIES (Deterministic IDs & Strict Dates) ---

def generate_document_id(authority, doc_type, date_str, title, url):
raw = f"{authority}|{doc_type}|{date_str}|{title}|{url}"
return hashlib.sha256(raw.encode()).hexdigest()

def normalize_date(date_str):
if not date_str:
return None
clean_date = date_str.replace('/', '-').strip()
for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y"):
try:
return datetime.strptime(clean_date, fmt).strftime("%Y-%m-%d")
except ValueError:
continue
return None

def fetch_with_ssl_fallback(url):
"""Tries strict SSL first, falls back to unverified if Indian govt server fails, logs errors."""
headers = {'User-Agent': 'Mozilla/5.0'}
try:
return requests.get(url, headers=headers, verify=True, timeout=12)
except requests.exceptions.SSLError:
# Fallback for known CDSCO certificate issues
return requests.get(url, headers=headers, verify=False, timeout=12)
except Exception as e:
raise e

--- 4. AI INTELLIGENCE ENGINE (100-Point Model) ---

def fallback_baseline_analysis(title, selected_topics):
topic = "General Regulatory"
if any(k in title.lower() for k in ["gmp", "manufacturing", "quality"]): topic = "GMP"
if any(k in title.lower() for k in ["trial", "ethics"]): topic = "Clinical Trials"

return {  
    "regulatory_topic": topic, "change_type": "Administrative",   
    "summary": "Baseline tagging applied due to missing API key.",   
    "impact": "Low", "why_relevant": "Broad matching applied.",   
    "required_action": "Review document manually to assess impact.", "relevance_score": 30  
}

def analyze_regulatory_update(title, authority, doc_type, profile_context, selected_topics, api_key):
if not api_key:
return fallback_baseline_analysis(title, selected_topics)

client = OpenAI(api_key=api_key)  
system_prompt = """You are an expert Regulatory Affairs (RA) AI assistant.  
Assess the regulatory document based strictly on the title. If a field cannot be deduced, return null. Do NOT fabricate obligations.  
Calculate relevance (0-100) using this matrix: Market Match (25), Product Match (25), Topic Match (25), Activity Relevance (15), Criticality (10).  
Output strictly in this JSON format:  
{ "regulatory_topic": "string", "change_type": "New Requirement|Amendment|Revision|Guidance|Safety Update|Administrative",  
  "summary": "What changed? (max 2 sentences)", "impact": "High|Moderate|Low",   
  "why_relevant": "Why does this matter to the company? (1 sentence)",   
  "required_action": "Specific RA/QA action required", "relevance_score": integer }"""  

user_prompt = f"Authority: {authority}\nType: {doc_type}\nTitle: '{title}'\nCompany Context: {profile_context}"  
try:  
    response = client.chat.completions.create(  
        model="gpt-4o-mini", response_format={"type": "json_object"},  
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]  
    )  
    return json.loads(response.choices[0].message.content)  
except Exception as e:  
    return fallback_baseline_analysis(title, selected_topics)

--- 5. SOURCE MONITOR (Error-Resilient & Full Pagination Prep) ---

def scrape_cdsco_all(profile_context, selected_topics, api_key):
endpoints = {
"Public Notices": ("Public Notice", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"),
"Circulars": ("Circular", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/"),
"Safety Alerts": ("Safety Alert", "https://cdsco.gov.in/opencms/opencms/en/Alerts/")
}

new_updates = 0  
c = conn.cursor()  
  
for status_key, (doc_type, url) in endpoints.items():  
    try:  
        res = fetch_with_ssl_fallback(url)  
        if res.status_code == 200:  
            soup = BeautifulSoup(res.text, 'html.parser')  
            # Fetch all rows, not just top 7  
            for row in soup.find_all('tr')[1:]:   
                cols = row.find_all('td')  
                if len(cols) >= 3:  
                    title = cols[1].text.strip()  
                    date_str = cols[2].text.strip()  
                    link_tag = cols[1].find('a') or row.find('a')  
                    doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_tag['href']) if link_tag and link_tag.has_attr('href') else url  
                      
                    update_id = generate_document_id("CDSCO", doc_type, date_str, title, doc_url)  
                      
                    c.execute("SELECT id FROM updates WHERE id=?", (update_id,))  
                    if not c.fetchone():  
                        ai_data = analyze_regulatory_update(title, "CDSCO", doc_type, profile_context, selected_topics, api_key)  
                        norm_date = normalize_date(date_str)  
                          
                        c.execute('''INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',   
                                 (update_id, "CDSCO", doc_type, title, date_str, norm_date, doc_url,   
                                  ai_data.get('regulatory_topic'), ai_data.get('summary'), ai_data.get('change_type'),  
                                  ai_data.get('impact'), ai_data.get('why_relevant'), ai_data.get('required_action'),  
                                  ai_data.get('relevance_score'), "Pending Review"))  
                        new_updates += 1  
            conn.commit()  
            st.session_state.source_status[status_key] = "🟢 Available"  
        else:  
            st.session_state.source_status[status_key] = "🔴 Unavailable (Bad Status)"  
    except Exception as e:  
        st.session_state.source_status[status_key] = "🔴 Error (Connection)"  
          
return new_updates

--- 6. SIDEBAR & DASHBOARD SETUP ---

st.sidebar.title("🏢 Company Profile")
markets = st.sidebar.multiselect("Markets", ["India (CDSCO)"], ["India (CDSCO)"])
products = st.sidebar.multiselect("Products", ["Injectables", "Oral Solids", "Biologics"], ["Injectables"])
topics = st.sidebar.multiselect("Topics", ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance"], ["GMP", "Stability"])
st.sidebar.divider()
api_key = st.sidebar.text_input("OpenAI API Key (Required for deep analysis)", type="password")

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
st.markdown("""<div style="display: flex; align-items: flex-start;"><h1 style="margin-bottom: 0;">🛡️ RegIntel Master Platform</h1><div class="always-live-indicator"><span class="always-live-dot"></span> Source Monitor Ready</div></div>""", unsafe_allow_html=True)
with header_col2:
st.markdown(f"<div style='text-align: right; margin-top: 25px; color: #5f6368; font-weight: 500;'>{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>", unsafe_allow_html=True)

Important Marquee

c = conn.cursor()
c.execute("SELECT doc_type, title, published_date_original, url FROM updates ORDER BY id DESC LIMIT 15")
marquee_html = ""
for doc_type, title, date_str, url in c.fetchall():
emoji = "🔴" if doc_type == "Safety Alert" else ("🟡" if doc_type == "Circular" else "🟢")
marquee_html += f"""<span class="important-new">New!</span><a class="important-link" href="{url}" target="_blank">{emoji} {doc_type}: {title} [{date_str}]</a>"""
if not marquee_html: marquee_html = "<span>No intelligence gathered yet. Run the monitor.</span>"

st.markdown(f"""<div class="important-container"><div class="important-badge">Important</div><div class="marquee-wrapper">{marquee_html}</div></div>""", unsafe_allow_html=True)

Execution Controls

profile_context = f"Markets: {markets}, Products: {products}, Topics: {topics}"
b_col, stat_col1, stat_col2, stat_col3 = st.columns([2, 1, 1, 1])

with b_col:
if st.button("🔄 Execute Source Monitor"):
with st.spinner("MONITORING SOURCES..."):
count = scrape_cdsco_all(profile_context, topics, api_key)
st.session_state.executed = True
st.success(f"Radar Complete: {count} new regulatory documents fetched.")

with stat_col1: st.markdown(f"Notices: {st.session_state.source_status['Public Notices']}")
with stat_col2: st.markdown(f"Circulars: {st.session_state.source_status['Circulars']}")
with stat_col3: st.markdown(f"Alerts: {st.session_state.source_status['Safety Alerts']}")

st.divider()

--- 7. REGULATORY INTELLIGENCE FEED (Professional Card Layout) ---

st.subheader("📋 Regulatory Intelligence Radar")

if not st.session_state.executed:
st.info("🕒 Awaiting Execution. Press 'Execute Source Monitor' above to scan active updates.")
else:
df = pd.read_sql_query("SELECT * FROM updates ORDER BY published_date_normalized DESC NULLS LAST", conn)

if not df.empty:  
    # High Level Metrics  
    m1, m2, m3, m4 = st.columns(4)  
    m1.metric("Total Updates", len(df))  
    m2.metric("High Priority", len(df[df['relevance_score'] >= 80]))  
    m3.metric("Action Required", len(df[df['status'] == 'Action Required']))  
    m4.metric("Pending Review", len(df[df['status'] == 'Pending Review']))  
    st.write("")  

    for _, row in df.iterrows():  
        rel_color = "🔴 HIGH PRIORITY" if row['relevance_score'] >= 80 else ("🟡 MODERATE PRIORITY" if row['relevance_score'] >= 50 else "🟢 LOW PRIORITY")  
          
        with st.expander(f"{rel_color.split()[0]} [{row['authority']}] {row['title']} — {row['published_date_original']}"):  
              
            # Priority 10 Card Layout  
            st.markdown(f"### {rel_color}")  
            st.markdown(f"**{row['authority']} — {row['doc_type']}** | Published: {row['published_date_original']} | Topic: {row['topic']}")  
              
            col_ai, col_review = st.columns([2, 1.2])  
              
            with col_ai:  
                st.markdown("#### 🤖 AI Assessment")  
                st.markdown(f"<span class='ai-disclaimer'>AI-assisted assessment. Regulatory interpretation requires human RA review.</span>", unsafe_allow_html=True)  
                st.markdown(f"**Change Type:** {row['change_type']}")  
                st.markdown(f"**What Changed:** {row['summary']}")  
                st.markdown(f"**Why does it matter?** {row['why_relevant']}")  
                st.markdown(f"**Required Action:** {row['required_action']}")  
                st.progress(row['relevance_score'] / 100, text=f"**Relevance Score:** {row['relevance_score']} / 100")  
              
            with col_review:  
                st.markdown("#### 👤 RA Human Review")  
                st.markdown(f"[View Official Source Document]({row['url']})")  
                  
                with st.form(key=f"review_form_{row['id']}"):  
                    options = ["Pending Review", "Action Required", "Informational", "Not Relevant"]  
                    current_idx = options.index(row['status']) if row['status'] in options else 0  
                      
                    new_status = st.selectbox("Regulatory Decision", options, index=current_idx)  
                    comment = st.text_area("Reviewer Comment", placeholder="Enter your RA assessment here...")  
                    submit = st.form_submit_button("Save Review & Audit")  
                      
                    if submit:  
                        c = conn.cursor()  
                        c.execute("UPDATE updates SET status=? WHERE id=?", (new_status, row['id']))  
                        c.execute("INSERT INTO audit_logs (update_id, previous_status, new_status, user, timestamp, comment) VALUES (?, ?, ?, ?, ?, ?)",   
                                  (row['id'], row['status'], new_status, "RA Professional", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), comment))  
                        conn.commit()  
                        st.success("Review saved to Audit Log.")  
                        st.rerun()
                    
